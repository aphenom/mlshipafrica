"""
Branche les SMS sur l'historique des colis.

Tous les changements de statut (vendeur, équipe, import) créent une ligne HistoriqueArticle :
c'est donc le seul point d'accroche. Les SMS sont mis en file APRÈS la validation de la transaction
(transaction.on_commit) : si l'enregistrement échoue, aucun SMS ne part.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from management.models import HistoriqueArticle
from sms.declencheurs import sms_pour_historique
from sms.service import annuler_pour_historique

logger = logging.getLogger('sms')


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='sms_historique_article')
def sms_apres_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return  # chargement de fixtures
    if instance.etat_suppression:
        # « Annuler le dernier mouvement » dans l'admin : les SMS pas encore partis sont annulés
        transaction.on_commit(lambda: annuler_pour_historique(instance))
        return
    if not created or not instance.etat_validation:
        return

    def mettre_en_file():
        try:
            sms_pour_historique(instance)
        except Exception:  # un problème de SMS ne doit jamais bloquer le travail de l'équipe
            logger.exception('SMS non préparé pour le mouvement %s', instance.pk)

    transaction.on_commit(mettre_en_file)
