"""
Woura et API vendeur : commandes entrantes, événements sortants, file d'envoi.

WOURA (réglages dans le .env : WOURA_API_KEY = wk_test… ou wk_live…, WOURA_WEBHOOK_SECRET, WOURA_BASE_URL,
WOURA_EVENTS_PATH)
  Entrée : webhook « shipment.assigned » signé (en-tête Woura-Signature : t=<horodatage>,v1=<HMAC-SHA256>),
           réponse 2xx immédiate, un même identifiant d'événement n'est traité qu'une fois.
  Sortie : accepted, in_transit, delivered (+ delivery_fee), failed, rescheduled, returned, cancelled,
           avec Authorization: Bearer et Idempotency-Key. Le livreur déclaré est TOUJOURS « ML COD Intérieur »
           et notre numéro de service : jamais le transporteur partenaire.

À CONFIRMER AVEC WOURA avant la mise en ligne : la forme exacte du JSON reçu (lire_shipment) et du JSON envoyé
(evenement_woura), ainsi que l'URL des événements. Tout est regroupé ici pour s'ajuster en un seul endroit.

API VENDEUR (clés du vendeur, en-tête Authorization: Bearer mlc_live_… ou mlc_test_…)
  Les commandes créées avec une clé de test sont marquées et ne partent jamais en livraison.
  Webhook du vendeur : événement « colis.statut » signé (en-tête X-MLCOD-Signature : t=…,v1=… sur le même principe).
"""
import hashlib
import hmac
import json
import logging
import time
import unicodedata
import re
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from decouple import config
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from integrations.models import EvenementIntegration as E, IntegrationVendeur

logger = logging.getLogger('integrations')

NOM_LIVREUR = 'ML COD Intérieur'
ATTENTES = (1, 5, 15, 60, 240)  # minutes entre deux essais d'envoi
TOLERANCE_SIGNATURE = 300       # secondes

# Statut ML → événement Woura (passation, « à confirmer avec Woura »)
EVENEMENTS_WOURA = {
    'depot': 'accepted', 'ramasse': 'accepted',
    'en_transit': 'in_transit', 'en_cours_livraison': 'in_transit', 'arrive': 'in_transit',
    'livre': 'delivered', 'livre_paye': 'delivered',
    'echec_livraison': 'failed', 'reconduit': 'rescheduled',
    'en_retour': 'returned', 'annule': 'cancelled',
}


# ----------------------------------------------------------------------------------------- signatures

def signer(secret, corps_brut, horodatage=None):
    t = str(int(horodatage or time.time()))
    v1 = hmac.new(secret.encode(), (t + '.').encode() + corps_brut, hashlib.sha256).hexdigest()
    return 't=%s,v1=%s' % (t, v1)


def verifier_signature(secret, entete, corps_brut, maintenant=None):
    if not secret or not entete:
        return False
    morceaux = dict(p.split('=', 1) for p in entete.replace(' ', '').split(',') if '=' in p)
    t, v1 = morceaux.get('t'), morceaux.get('v1')
    if not t or not v1 or not t.isdigit():
        return False
    if abs((maintenant or time.time()) - int(t)) > TOLERANCE_SIGNATURE:
        return False
    attendu = hmac.new(secret.encode(), (t + '.').encode() + corps_brut, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, v1)


# ----------------------------------------------------------------------------------------- entrée Woura

def _normaliser(nom):
    texte = unicodedata.normalize('NFKD', str(nom or ''))
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in texte if not unicodedata.combining(c)).lower())


def _premier(d, *chemins):
    for chemin in chemins:
        valeur = d
        for cle in chemin.split('.'):
            valeur = valeur.get(cle) if isinstance(valeur, dict) else None
        if valeur not in (None, ''):
            return valeur
    return None


def lire_shipment(corps):
    """Champs utiles d'un shipment Woura, quelle que soit la forme exacte du JSON (à confirmer avec Woura)."""
    s = _premier(corps, 'data.shipment', 'data.object', 'data', 'shipment') or {}
    return {
        'id': str(_premier(s, 'id', 'shipment_id', 'reference') or ''),
        'boutique': str(_premier(s, 'store_id', 'store.id', 'seller_id', 'seller.id', 'merchant_id', 'shop_id') or ''),
        'nom': _premier(s, 'recipient.name', 'customer.name', 'recipient_name', 'customer_name') or '',
        'telephone': _premier(s, 'recipient.phone', 'customer.phone', 'recipient_phone', 'customer_phone') or '',
        'telephone2': _premier(s, 'recipient.phone2', 'customer.alt_phone') or '',
        'ville': _premier(s, 'recipient.city', 'delivery_address.city', 'address.city', 'city') or '',
        'adresse': _premier(s, 'recipient.address', 'delivery_address.line1', 'address.line1', 'address') or '',
        'montant': _premier(s, 'cod_amount', 'amount_to_collect', 'cash_on_delivery', 'total') or 0,
        'designation': _premier(s, 'items.0.name', 'description', 'product_name') or '',
        'taille': str(_premier(s, 'package_size', 'size', 'parcel_size') or '').lower(),
    }


def _items(corps):
    s = _premier(corps, 'data.shipment', 'data.object', 'data', 'shipment') or {}
    items = s.get('items') if isinstance(s, dict) else None
    return items if isinstance(items, list) else []


@transaction.atomic
def creer_commande(vendeur, donnees, source, reference_externe, test=False):
    """Crée une commande (Woura ou API vendeur) qui suit ensuite le circuit normal (confirmation, dépôt…)."""
    from core.models import Configuration, FormatArticle, Localite
    from management.models import Article
    from mlshipafrica.enums import StatutTraitement as S
    if not reference_externe:
        raise ValidationError("Référence de la commande manquante.")
    existant = Article.objects.filter(source=source, reference_externe=reference_externe).first()
    if existant is not None:
        return existant, False
    cible = _normaliser(donnees.get('ville'))
    localite = next((l for l in Localite.objects.filter(license=vendeur.license, is_arrivee=True, etat_validation=True,
                                                         etat_suppression=False) if _normaliser(l.nom) == cible), None)
    if localite is None:
        raise ValidationError("Ville non desservie ou inconnue : %s" % donnees.get('ville'))
    if not donnees.get('telephone'):
        raise ValidationError("Téléphone du client manquant.")
    try:
        montant = Decimal(str(donnees.get('montant') or 0))
    except InvalidOperation:
        raise ValidationError("Montant invalide.")
    nom_format = 'Moyen' if donnees.get('taille') in ('moyen', 'medium', 'm') else 'Petit'
    fmt = FormatArticle.objects.filter(license=vendeur.license, nom__iexact=nom_format, etat_suppression=False).first()
    depart = Localite.objects.filter(license=vendeur.license, is_depart=True, etat_suppression=False).first()
    conf = Configuration.objects.filter(license=vendeur.license, etat_suppression=False).order_by('-pk').first()
    article = Article(vendeur=vendeur, license=vendeur.license, config=conf, localite_depart=depart, localite_arrivee=localite,
                      format_article=fmt, valeur=montant, quantite=1, valeur_totale=montant,
                      designation=(donnees.get('designation') or '')[:100], nom_destinataire=(donnees.get('nom') or '')[:100],
                      numero_principal_destinataire=donnees['telephone'], numero_secondaire_destinataire=donnees.get('telephone2') or None,
                      adresse_destinataire=(donnees.get('adresse') or '')[:255], is_option_encaissement=montant > 0,
                      source=source, reference_externe=reference_externe[:80], etat_validation=False)
    article.save()                      # brouillon : tarif calculé
    if not test:
        article.statut_traitement = S.EN_ATTENTE_DEPOT  # Woura et API : stock déposé chez nous, entre dans la file de confirmation
        article.save()
    return article, True


def recevoir_woura(corps_brut, entete_signature, maintenant=None):
    """Webhook Woura. Renvoie (code HTTP, message). Toujours rapide : la commande est créée en une transaction."""
    secret = config('WOURA_WEBHOOK_SECRET', default='')
    if not verifier_signature(secret, entete_signature, corps_brut, maintenant):
        return 401, 'signature invalide'
    try:
        corps = json.loads(corps_brut.decode('utf-8'))
    except ValueError:
        return 400, 'JSON invalide'
    identifiant = str(corps.get('id') or corps.get('event_id') or '')
    type_ = str(corps.get('type') or corps.get('event') or '')
    if not identifiant:
        return 400, "identifiant d'événement manquant"
    try:
        with transaction.atomic():
            evenement = E.objects.create(sens=E.ENTRANT, canal=E.WOURA, type=type_, identifiant='woura:in:' + identifiant,
                                         contenu=corps, statut=E.EN_FILE)
    except IntegrityError:
        return 200, 'déjà reçu'           # dédoublonnage : un même événement ne crée qu'une commande
    traiter_entrant(evenement)
    return 200, 'reçu'


def traiter_entrant(evenement):
    if evenement.type != 'shipment.assigned':
        evenement.statut, evenement.reponse = E.TRAITE, 'ignoré'
        evenement.save()
        return
    donnees = lire_shipment(evenement.contenu)
    integration = IntegrationVendeur.objects.filter(woura_actif=True, woura_boutique_id=donnees['boutique']).select_related('vendeur').first()
    try:
        if integration is None:
            raise ValidationError("Boutique Woura %s non reliée à un vendeur ML COD Intérieur." % donnees['boutique'])
        article, cree = creer_commande(integration.vendeur, donnees, 'woura', donnees['id'])
        evenement.article, evenement.vendeur = article, integration.vendeur
        evenement.statut, evenement.reponse = E.TRAITE, 'commande %s %s' % (article.code, 'créée' if cree else 'déjà connue')
    except ValidationError as erreur:
        evenement.statut, evenement.reponse = E.ECHEC, ' '.join(erreur.messages)
        evenement.vendeur = getattr(integration, 'vendeur', None)
    evenement.save()


# ----------------------------------------------------------------------------------------- sorties

def evenement_woura(article, historique, type_):
    from sms.models import SmsParametres
    contenu = {
        'event': type_, 'shipment_id': article.reference_externe, 'reference': article.code,
        'status': historique.statut_traitement, 'occurred_at': (historique.date_creation or timezone.now()).isoformat(),
        'rider_name': NOM_LIVREUR, 'rider_phone': SmsParametres.charger().tel_service,
    }
    if type_ == 'delivered':
        contenu['delivery_fee'] = int(article.montant_total_frais or 0)
    if historique.commentaire:
        contenu['note'] = historique.commentaire[:300]
    return contenu


def mettre_en_file_sortant(article, historique):
    from mlshipafrica.enums import SourceCommande
    crees = []
    if article.source == SourceCommande.WOURA and article.reference_externe:
        type_ = EVENEMENTS_WOURA.get(historique.statut_traitement)
        if type_:
            crees.append(_creer_sortant(E.WOURA, type_, 'woura:out:%s' % historique.pk, article, evenement_woura(article, historique, type_)))
    integration = getattr(article.vendeur, 'integration', None) if article.vendeur_id else None
    if integration and integration.api_actif and integration.webhook_url and (
            not integration.webhook_evenements or historique.statut_traitement in integration.webhook_evenements):
        crees.append(_creer_sortant(E.API, 'colis.statut', 'api:out:%s' % historique.pk, article, {
            'event': 'colis.statut', 'code': article.code, 'reference_externe': article.reference_externe,
            'statut': historique.statut_traitement, 'libelle': historique.get_statut_traitement_display(),
            'date': (historique.date_creation or timezone.now()).isoformat()}))
    return [c for c in crees if c]


def _creer_sortant(canal, type_, identifiant, article, contenu):
    try:
        with transaction.atomic():
            return E.objects.create(sens=E.SORTANT, canal=canal, type=type_, identifiant=identifiant, article=article,
                                    vendeur=article.vendeur, contenu=contenu)
    except IntegrityError:
        return None


def _post(url, corps, entetes, delai=15):
    requete = urllib.request.Request(url, data=corps, method='POST', headers=entetes)
    try:
        with urllib.request.urlopen(requete, timeout=delai) as r:
            return r.status, r.read(2000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode('utf-8', 'replace')
    except Exception as e:  # réseau, délai, DNS
        return 0, str(e)[:500]


def transport_par_defaut(evenement):
    corps = json.dumps(evenement.contenu, ensure_ascii=False).encode('utf-8')
    if evenement.canal == E.WOURA:
        cle = config('WOURA_API_KEY', default='')
        if not cle:
            return 0, 'WOURA_API_KEY absente du .env'
        base = config('WOURA_BASE_URL', default='').rstrip('/')
        chemin = config('WOURA_EVENTS_PATH', default='/shipments/{id}/events').replace('{id}', str(evenement.contenu.get('shipment_id')))
        return _post(base + chemin, corps, {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cle,
                                           'Idempotency-Key': evenement.identifiant})
    integration = evenement.vendeur.integration
    return _post(integration.webhook_url, corps, {'Content-Type': 'application/json',
                                                  'X-MLCOD-Signature': signer(integration.webhook_secret, corps),
                                                  'Idempotency-Key': evenement.identifiant})


def envoyer_file(transport=None, maintenant=None, limite=200):
    maintenant = maintenant or timezone.now()
    transport = transport or transport_par_defaut
    bilan = {'envoyes': 0, 'erreurs': 0}
    lot = list(E.objects.filter(sens=E.SORTANT, statut__in=(E.EN_FILE, E.ERREUR), envoyer_apres__lte=maintenant)
               .select_related('vendeur').order_by('date')[:limite])
    for ev in lot:
        # réservation : un seul processus traite cet événement
        if not E.objects.filter(pk=ev.pk, statut=ev.statut, tentatives=ev.tentatives).update(tentatives=ev.tentatives + 1):
            continue
        ev.tentatives += 1
        code, texte = transport(ev)
        ev.reponse = ('%s %s' % (code, texte))[:2000]
        if 200 <= code < 300:
            ev.statut = E.ENVOYE
            bilan['envoyes'] += 1
        elif ev.tentatives >= len(ATTENTES) or code in (400, 401, 403, 404, 422):
            ev.statut = E.ECHEC
            bilan['erreurs'] += 1
        else:
            ev.statut = E.ERREUR
            ev.envoyer_apres = maintenant + timedelta(minutes=ATTENTES[ev.tentatives - 1])
            bilan['erreurs'] += 1
        ev.save(update_fields=['statut', 'reponse', 'envoyer_apres', 'tentatives'])
    return bilan


def zones_pour_woura(license):
    """Corps du PUT /zones : 275 localités, pays CI, frais du format Petit (prix ML, jamais le coût interne)."""
    from core.models import Localite
    from management.models import Tarification
    tarifs = {t.zone_arrivee_id: int(t.montant_frais or 0) for t in Tarification.objects.filter(
        license=license, vendeur__isnull=True, etat_validation=True, etat_suppression=False, format_article__nom__iexact='Petit')}
    return {'zones': [{'country': 'CI', 'city': l.nom, 'fee': tarifs.get(l.zone_id), 'delay': l.zone.get_delai_display() if l.zone_id else ''}
                      for l in Localite.objects.filter(license=license, is_arrivee=True, etat_validation=True,
                                                       etat_suppression=False, zone__numero__isnull=False).select_related('zone')
                      if tarifs.get(l.zone_id)]}
