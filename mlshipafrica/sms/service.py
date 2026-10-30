"""
File d'envoi des SMS.

    mettre_en_file(...)   écrit un SMS dans la file (appelé par les déclencheurs, jamais bloquant)
    envoyer_file(...)     envoie les SMS dus (tâche planifiée `sms_envoyer`, chaque minute)
    relever_accuses(...)  met à jour les statuts de livraison (tâche `sms_accuses`, toutes les 10 min)
    appliquer_accuse(...) applique un accusé reçu par le webhook HSMS

Garanties :
  - un même évènement ne produit jamais deux SMS (clé de dédoublonnage unique en base) ;
  - deux tâches lancées en même temps ne prennent jamais le même SMS (réservation par UPDATE atomique,
    compatible MySQL et MariaDB, sans SELECT … SKIP LOCKED) ;
  - heures calmes : rien ne part entre 21 h et 7 h (heure d'Abidjan), sauf priorité 1 ;
  - solde épuisé ou compte refusé : la file se met en pause 15 min au lieu de brûler les tentatives ;
  - panne réseau : nouvel essai après 1, 5, 15 puis 60 min, abandon après 5 essais.
"""
import json
import logging
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from sms.hsms import ClientHsms, ErreurHsms
from sms.models import SmsMessage, SmsModele, SmsParametres
from sms.telephone import normaliser_ci
from sms.texte import preparer, remplir

logger = logging.getLogger('sms')

ABIDJAN = ZoneInfo('Africa/Abidjan')
ATTENTES_APRES_ECHEC = (1, 5, 15, 60)  # minutes
TENTATIVES_MAX = 5
PAUSE_COMPTE = timedelta(minutes=15)
ENVOI_BLOQUE_APRES = timedelta(minutes=10)


# ----------------------------------------------------------------------------- heures calmes

def prochaine_heure_autorisee(moment, parametres):
    """Premier instant ≥ moment hors des heures calmes (heure d'Abidjan)."""
    debut, fin = parametres.heure_debut_silence, parametres.heure_fin_silence
    if debut == fin:
        return moment
    local = moment.astimezone(ABIDJAN)
    heure = local.hour
    dans_silence = (heure >= debut or heure < fin) if debut > fin else (debut <= heure < fin)
    if not dans_silence:
        return moment
    jour = local.date() if heure < fin else local.date() + timedelta(days=1)
    return datetime.combine(jour, time(fin, 0), tzinfo=ABIDJAN)


# ----------------------------------------------------------------------------- mise en file

def mettre_en_file(cle_modele, numero, variables, cle_dedoublonnage, article=None, historique=None, vendeur=None,
                   post_traitement=None, maintenant=None):
    """Écrit un SMS dans la file. Renvoie le SmsMessage, ou None si le modèle est désactivé ou déjà envoyé."""
    modele = SmsModele.objects.filter(cle=cle_modele).first()
    if modele is None or not modele.actif:
        return None
    if SmsMessage.objects.filter(cle_dedoublonnage=cle_dedoublonnage).exists():
        return None
    parametres = SmsParametres.charger()
    maintenant = maintenant or timezone.now()

    variables = dict(variables)
    variables.setdefault('tel', parametres.tel_service)
    texte = remplir(modele.texte, variables)
    if post_traitement:
        texte = post_traitement(texte)
    texte, unicode, nb_segments = preparer(texte)

    msisdn, raison = normaliser_ci(numero)
    message = SmsMessage(
        modele_cle=cle_modele, destinataire=msisdn or str(numero or '')[:20], texte=texte, unicode=unicode,
        segments=nb_segments, priorite=modele.priorite, cle_dedoublonnage=cle_dedoublonnage[:150],
        article=article, historique=historique, vendeur=vendeur,
        envoyer_apres=maintenant if modele.priorite <= 1 else prochaine_heure_autorisee(maintenant, parametres),
    )
    if raison:
        # Gardé pour la traçabilité (« pourquoi ce client n'a pas reçu de SMS ? »), jamais envoyé
        message.statut, message.erreur = SmsMessage.ECHEC, 'Numéro refusé : %s' % raison
    try:
        with transaction.atomic():
            message.save()
    except IntegrityError:
        return None  # même évènement déjà en file (deux enregistrements simultanés)
    return message


def annuler_pour_historique(historique):
    """Le mouvement a été annulé dans l'admin : les SMS pas encore partis ne partent pas."""
    return (SmsMessage.objects.filter(historique=historique, statut=SmsMessage.EN_FILE)
            .update(statut=SmsMessage.ANNULE, erreur="Mouvement annulé avant l'envoi", verrou=''))


# ----------------------------------------------------------------------------- envoi

def client_par_defaut(parametres):
    def memoriser(jeton):
        SmsParametres.objects.filter(pk=1).update(jeton_api=jeton)
    return ClientHsms(jeton=parametres.jeton_api or None, sur_nouveau_jeton=memoriser)


def envoyer_file(limite=200, client=None, maintenant=None):
    """Envoie les SMS dus. Renvoie un dictionnaire de compteurs (pour les journaux)."""
    maintenant = maintenant or timezone.now()
    parametres = SmsParametres.charger()
    bilan = {'envoyes': 0, 'reportes': 0, 'echecs': 0, 'pause': False}

    # SMS restés « en cours d'envoi » après un arrêt brutal : on les remet en file
    SmsMessage.objects.filter(statut=SmsMessage.ENVOI, date_verrou__lt=maintenant - ENVOI_BLOQUE_APRES).update(
        statut=SmsMessage.EN_FILE, verrou='')

    if not parametres.actif:
        return bilan
    if parametres.pause_jusqua and parametres.pause_jusqua > maintenant:
        bilan['pause'] = True
        return bilan

    client = client or client_par_defaut(parametres)
    if not client.configure:
        SmsParametres.objects.filter(pk=1).update(derniere_erreur='Variables HSMS_* absentes du fichier .env')
        return bilan

    ids = list(SmsMessage.objects.filter(statut=SmsMessage.EN_FILE, envoyer_apres__lte=maintenant)
               .order_by('priorite', 'envoyer_apres', 'id').values_list('id', flat=True)[:limite])
    if not ids:
        return bilan
    verrou = uuid.uuid4().hex
    SmsMessage.objects.filter(id__in=ids, statut=SmsMessage.EN_FILE).update(
        statut=SmsMessage.ENVOI, verrou=verrou, date_verrou=maintenant)
    lot = list(SmsMessage.objects.filter(verrou=verrou, statut=SmsMessage.ENVOI).order_by('priorite', 'envoyer_apres', 'id'))

    for position, message in enumerate(lot):
        try:
            tickets, reponse = client.envoyer(message.destinataire, message.texte, message.unicode)
        except ErreurHsms as erreur:
            message.reponse_fournisseur = _json(erreur.corps)
            message.erreur = str(erreur)[:255]
            if erreur.met_en_pause:
                # Problème de compte : on remet tout le lot en file et on suspend
                message.statut, message.verrou = SmsMessage.EN_FILE, ''
                message.save(update_fields=['statut', 'verrou', 'erreur', 'reponse_fournisseur'])
                SmsMessage.objects.filter(id__in=[m.id for m in lot[position + 1:]], verrou=verrou).update(
                    statut=SmsMessage.EN_FILE, verrou='')
                SmsParametres.objects.filter(pk=1).update(pause_jusqua=maintenant + PAUSE_COMPTE,
                                                          derniere_erreur=str(erreur)[:255])
                logger.error('SMS en pause : %s', erreur)
                bilan['pause'] = True
                break
            message.tentatives += 1
            if erreur.reessayable and message.tentatives < TENTATIVES_MAX:
                attente = ATTENTES_APRES_ECHEC[min(message.tentatives, len(ATTENTES_APRES_ECHEC)) - 1]
                message.statut = SmsMessage.EN_FILE
                message.envoyer_apres = maintenant + timedelta(minutes=attente)
                bilan['reportes'] += 1
            else:
                message.statut = SmsMessage.ECHEC
                bilan['echecs'] += 1
            message.verrou = ''
            message.save()
            continue
        message.statut = SmsMessage.ENVOYE
        message.ticket = (tickets[0] if tickets else '')[:64]
        message.reponse_fournisseur = _json(reponse)
        message.date_envoi = maintenant
        message.tentatives += 1
        message.erreur, message.verrou = '', ''
        message.save()
        bilan['envoyes'] += 1
    return bilan


# ----------------------------------------------------------------------------- accusés de réception

# Codes HSMS : 0 en attente · 1 en cours · 2 remis à l'opérateur · 3 délivré · 4 rejeté · 5 non délivré
STATUT_PAR_CODE = {3: SmsMessage.DELIVRE, 4: SmsMessage.REJETE, 5: SmsMessage.NON_DELIVRE}


def appliquer_accuse(ticket, code, maintenant=None):
    """Applique un accusé. Un accusé ne fait jamais reculer un message (accusés en double ou en désordre)."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return False
    if code not in range(6):
        return False
    message = SmsMessage.objects.filter(ticket=str(ticket)).first()
    if message is None or message.statut in SmsMessage.STATUTS_FINAUX:
        return False
    if message.code_accuse is not None and code <= message.code_accuse:
        return False
    message.code_accuse = code
    message.date_accuse = maintenant or timezone.now()
    if code in STATUT_PAR_CODE:
        message.statut = STATUT_PAR_CODE[code]
    message.save(update_fields=['code_accuse', 'date_accuse', 'statut'])
    return True


def lire_accuses(corps):
    """Liste (ticket, code) dans une réponse HSMS, quelle que soit sa forme."""
    if isinstance(corps, dict):
        for cle in ('data', 'notifications'):
            if isinstance(corps.get(cle), (list, dict)):
                return lire_accuses(corps[cle])
        corps = [corps]
    sortie = []
    for element in corps if isinstance(corps, list) else []:
        if not isinstance(element, dict):
            continue
        ticket = element.get('ticket') or element.get('ticket_id') or element.get('id')
        code = element.get('status') if element.get('status') is not None else element.get('statut')
        if ticket is not None and code is not None:
            sortie.append((str(ticket), code))
    return sortie


def relever_accuses(client=None, maintenant=None):
    """Interroge HSMS pour les SMS envoyés sans accusé final (secours si le webhook n'arrive pas)."""
    maintenant = maintenant or timezone.now()
    parametres = SmsParametres.charger()
    client = client or client_par_defaut(parametres)
    if not client.configure:
        return 0
    tickets = list(SmsMessage.objects.filter(
        statut=SmsMessage.ENVOYE, date_envoi__lte=maintenant - timedelta(minutes=5),
        date_envoi__gte=maintenant - timedelta(days=3)).exclude(ticket='').values_list('ticket', flat=True)[:500])
    mis_a_jour = 0
    for i in range(0, len(tickets), 50):
        try:
            reponse = client.accuses(tickets[i:i + 50])
        except ErreurHsms as erreur:
            logger.warning('Accusés HSMS indisponibles : %s', erreur)
            break
        for ticket, code in lire_accuses(reponse):
            mis_a_jour += appliquer_accuse(ticket, code, maintenant)
    return mis_a_jour


def relever_solde(client=None):
    parametres = SmsParametres.charger()
    client = client or client_par_defaut(parametres)
    solde, _ = client.solde()
    SmsParametres.objects.filter(pk=1).update(solde_sms=solde, date_solde=timezone.now())
    return solde


def _json(valeur):
    if valeur is None:
        return ''
    try:
        return json.dumps(valeur, ensure_ascii=False)[:4000]
    except (TypeError, ValueError):
        return str(valeur)[:4000]
