"""
Quels SMS partent quand un colis change de statut (plan validé par la direction le 29/10/2026).

Principe : un SMS seulement quand il change ce que fait le client (préparer l'argent, rappeler).

  Client  : reçu chez nous (ramassé ou déposé) · arrivé dans sa ville · 1er échec · annulé avant expédition
  Vendeur : annulé avant expédition (il doit agir) · résumé du soir (désactivé par défaut)
  Rien    : en transit, en cours de livraison, livré, en retour, retourné

Chaque SMS porte une clé de dédoublonnage : un même évènement n'envoie jamais deux SMS, et l'échec
n'est signalé qu'une fois par colis.
"""
from datetime import timedelta

from django.utils import timezone

from mlshipafrica.enums import StatutTraitement as S
from sms.service import mettre_en_file
from sms.texte import montant_f

SMS_CLIENT_PAR_STATUT = {
    S.RAMASSE: 'cl_recu',
    S.DEPOT: 'cl_recu',
    S.EN_TRANSIT: 'cl_transit',
    S.ARRIVE: 'cl_arrive',
    S.EN_COURS_LIVRAISON: 'cl_en_livraison',
    S.LIVRE: 'cl_livre',
    S.ECHEC_LIVRAISON: 'cl_echec',
    S.ANNULE: 'cl_annule',
}
# Messages au vendeur (SMS et/ou e-mail, selon les réglages du CEO) ; « revenu à Abidjan » : calendrier des retours
MESSAGE_VENDEUR_PAR_STATUT = {
    S.RAMASSE: 'v_recu', S.DEPOT: 'v_recu', S.EN_TRANSIT: 'v_transit', S.ARRIVE: 'v_arrive',
    S.EN_COURS_LIVRAISON: 'v_en_livraison', S.LIVRE: 'v_livre', S.ECHEC_LIVRAISON: 'v_echec',
    S.ANNULE: 'v_annule_av', S.RETOURNE: 'v_retourne',
}


def date_livraison_prevue(depart, jours_ouvres):
    """« JJ/MM » : borne haute du délai de la zone, en jours ouvrés (lundi à samedi)."""
    jour = depart
    reste = jours_ouvres
    while reste > 0:
        jour += timedelta(days=1)
        if jour.weekday() != 6:  # dimanche
            reste -= 1
    return jour.strftime('%d/%m')


def texte_deja_paye(texte):
    """Commande sans encaissement : on ne demande pas au client de préparer 0 F."""
    return (texte.replace('A payer a la livraison : 0 F.', 'Deja payee, rien a regler a la livraison.')
            .replace('Preparez 0 F, nous', 'Rien a payer, nous')
            .replace(' (0 F)', ''))


def montant_a_encaisser(article):
    return article.valeur_totale if article.is_option_encaissement and article.valeur_totale else 0


def sms_pour_historique(historique, maintenant=None):
    """Met en file les SMS liés à un nouveau mouvement. Renvoie la liste des SmsMessage créés."""
    maintenant = maintenant or timezone.now()
    article = historique.article
    vendeur = article.vendeur
    statut = historique.statut_traitement
    crees = []

    from sms.messages_auto import pour_vendeur, variables_colis
    localite = article.localite_arrivee
    zone = localite.zone if localite is not None else None
    montant = montant_a_encaisser(article)
    variables = variables_colis(article, date_livraison_prevue(
        timezone.localtime(maintenant).date(), (zone.delai_max_jours if zone and zone.delai_max_jours else 4)))
    generation = ':g%d' % article.generation if article.generation else ''

    cle_client = SMS_CLIENT_PAR_STATUT.get(statut)
    if cle_client:
        message = mettre_en_file(
            cle_client, article.numero_principal_destinataire, variables,
            # une fois par colis et par type de SMS (le 1er échec seulement, une seule confirmation…)
            # (après une substitution, le nouveau client repart avec son propre parcours SMS)
            cle_dedoublonnage='%s:%s%s' % (cle_client, article.code, generation),
            article=article, historique=historique, vendeur=vendeur,
            post_traitement=texte_deja_paye if not montant else None, maintenant=maintenant)
        if message:
            crees.append(message)

    cle_vendeur = MESSAGE_VENDEUR_PAR_STATUT.get(statut)
    if cle_vendeur and vendeur is not None:
        # une annulation peut revenir après une relance : un message par annulation ; les autres, une fois par colis
        dedoublonnage = ('%s:%s:%s' % (cle_vendeur, article.code, historique.pk) if statut == S.ANNULE
                         else '%s:%s%s' % (cle_vendeur, article.code, generation))
        from sms.models import SmsMessage
        avant = set(SmsMessage.objects.filter(cle_dedoublonnage=dedoublonnage).values_list('pk', flat=True))
        pour_vendeur(cle_vendeur, vendeur, variables, dedoublonnage, article=article, historique=historique, maintenant=maintenant)
        crees.extend(SmsMessage.objects.filter(cle_dedoublonnage=dedoublonnage).exclude(pk__in=avant))
    return crees


def sms_resume_soir(vendeur, jour, compteurs, maintenant=None):
    """Résumé du soir, seulement si le vendeur a eu de l'activité dans la journée."""
    c = {'recus': 0, 'expedies': 0, 'livres': 0, 'echecs': 0, 'annules': 0}
    c.update(compteurs)
    if not sum(c.values()):
        return None
    variables = dict(c, jour=jour.strftime('%d/%m'))
    return mettre_en_file('recap', vendeur.numero_sms or vendeur.numero_contact, variables,
                          cle_dedoublonnage='recap:%s:%s' % (vendeur.code, jour.isoformat()),
                          vendeur=vendeur, maintenant=maintenant)
