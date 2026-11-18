"""
Messages automatiques réglés par le CEO (Paramètres › Messages automatiques).

Chaque évènement a un modèle (SmsModele) : SMS actif ou non, e-mail actif ou non (vendeur seulement), textes avec
des informations entre accolades choisies par le CEO : {client}, {vendeur}, {montant}, {produit}, {sku}…
Le nom du prestataire n'est jamais une information disponible : le livreur est toujours « ML COD Intérieur ».
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from sms.models import EmailAuto, SmsModele, SmsParametres
from sms.service import mettre_en_file
from sms.texte import montant_f, remplir

logger = logging.getLogger('sms')

# Informations proposées au CEO, par rubrique (clé → libellé du bouton)
INFOS_COLIS = [
    ('client', 'Nom du client'), ('vendeur', 'Nom du vendeur'), ('montant', 'Montant à encaisser'), ('prix', 'Prix unitaire'),
    ('produit', 'Produit'), ('sku', 'Référence produit (SKU)'), ('quantite', 'Quantité'), ('ville', 'Ville'),
    ('ref', 'N° de commande'), ('date', 'Livraison prévue'), ('tel', 'Téléphone du service'),
]
INFOS = {
    'compte': [('vendeur', 'Nom du vendeur'), ('contact', 'Nom du contact'), ('code_vendeur', 'Code vendeur'), ('tel', 'Téléphone du service')],
    'livraison': INFOS_COLIS,
    'retours': INFOS_COLIS + [('colis', 'Code colis'), ('garde', 'Garde par jour'), ('n', 'N° d’alerte')],
    'paiement': [('vendeur', 'Nom du vendeur'), ('facture', 'N° de facture'), ('montant', 'Montant'),
                 ('montant_envoye', 'Montant envoyé'), ('moyen', 'Moyen de paiement'), ('reference', 'Référence du transfert'),
                 ('mois', 'Mois'), ('pieces', 'Pièces'), ('tel', 'Téléphone du service')],
}
EXEMPLE = {
    'client': 'Kouassi Aya', 'vendeur': 'Aya Beaute', 'boutique': 'Aya Beaute', 'contact': 'Aya', 'code_vendeur': 'V26RSNE11',
    'montant': '15 000 F', 'prix': '7 500 F', 'produit': 'Creme visage', 'sku': 'CR-50', 'quantite': '2', 'ville': 'Bouake',
    'ref': 'A26BHUZ11', 'colis': 'A26BHUZ11', 'date': '21/11', 'tel': '0700000000', 'facture': 'RL-261118-V26RSNE11-001',
    'montant_envoye': '92 149 F', 'moyen': 'Wave', 'reference': 'WV-123456', 'mois': 'novembre 2026', 'pieces': '52',
    'garde': '200 F', 'n': '1re', 'nb': '30', 'refs': '2', 'id': 'BS-V26RSNE11-003', 'jour': '18/11', 'recus': '5',
    'expedies': '4', 'livres': '3', 'echecs': '1', 'annules': '0', 'debut': '28/11',
}


def variables_colis(article, date_prevue=''):
    """Toutes les informations d'un colis pour les messages (aucune donnée du prestataire)."""
    vendeur = article.vendeur
    nom_vendeur = (vendeur.nom_store if vendeur else '') or 'ML COD Interieur'
    montant = article.valeur_totale if article.is_option_encaissement and article.valeur_totale else 0
    produit = article.produit_stock.designation if article.produit_stock_id else (article.designation or '')
    return {
        'client': ('%s %s' % (article.nom_destinataire or '', article.prenom_destinataire or '')).strip(),
        'vendeur': nom_vendeur, 'boutique': nom_vendeur, 'montant': montant_f(montant), 'prix': montant_f(article.valeur or 0),
        'produit': produit[:40], 'sku': (article.produit_stock.reference if article.produit_stock_id else (article.reference_externe or ''))[:30],
        'quantite': article.quantite or 1, 'ville': article.localite_arrivee.nom if article.localite_arrivee_id else '',
        'ref': article.code, 'colis': article.code, 'date': date_prevue,
    }


def variables_vendeur(vendeur):
    return {'vendeur': vendeur.nom_store or vendeur.code, 'boutique': vendeur.nom_store or vendeur.code,
            'contact': ('%s' % (getattr(vendeur, 'prenom_contact', '') or getattr(vendeur, 'nom_contact', '') or vendeur.nom_store or '')).strip(),
            'code_vendeur': vendeur.code}


def email_vendeur(vendeur):
    return (vendeur.email or (vendeur.user.email if vendeur.user_id else '') or '').strip()


def envoyer_email(modele, vendeur, variables, cle_dedoublonnage):
    """E-mail au vendeur (une seule fois par évènement). Jamais bloquant."""
    adresse = email_vendeur(vendeur)
    if not (modele.email_actif and modele.email_texte and adresse):
        return None
    variables = dict(variables)
    variables.setdefault('tel', SmsParametres.charger().tel_service)
    objet = remplir(modele.email_objet or modele.libelle, variables)[:200]
    texte = remplir(modele.email_texte, variables)
    try:
        with transaction.atomic():
            trace = EmailAuto.objects.create(modele_cle=modele.cle, destinataire=adresse[:200], objet=objet, texte=texte,
                                             cle_dedoublonnage=cle_dedoublonnage[:150],
                                             vendeur=vendeur if getattr(vendeur, '_meta', None) else None)
    except IntegrityError:
        return None
    try:
        send_mail(objet, texte, settings.DEFAULT_FROM_EMAIL, [adresse])
        EmailAuto.objects.filter(pk=trace.pk).update(envoye=True)
    except Exception as e:  # un e-mail raté ne bloque jamais le travail
        logger.exception('E-mail %s non envoyé', modele.cle)
        EmailAuto.objects.filter(pk=trace.pk).update(erreur=str(e)[:255])
    return trace


def pour_vendeur(cle, vendeur, variables, cle_dedoublonnage, article=None, historique=None, maintenant=None):
    """SMS et/ou e-mail au vendeur, selon les réglages du CEO pour cet évènement."""
    if vendeur is None:
        return
    modele = SmsModele.objects.filter(cle=cle).first()
    if modele is None:
        return
    variables = dict(variables_vendeur(vendeur), **variables)
    if modele.actif:
        mettre_en_file(cle, vendeur.numero_sms or vendeur.numero_contact, variables, cle_dedoublonnage,
                       article=article, historique=historique, vendeur=vendeur, maintenant=maintenant)
    envoyer_email(modele, vendeur, variables, cle_dedoublonnage)


def apres_validation(fonction, *args, **kwargs):
    """Les messages partent seulement si l'enregistrement réussit."""
    def lancer():
        try:
            fonction(*args, **kwargs)
        except Exception:
            logger.exception('Message automatique non préparé')
    transaction.on_commit(lancer)
