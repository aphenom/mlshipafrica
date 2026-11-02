"""Chaque nouveau mouvement d'un colis Woura ou d'un vendeur avec webhook → un événement sortant en file (après commit)."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from management.models import HistoriqueArticle

logger = logging.getLogger('integrations')


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='integrations_mouvement')
def evenement_apres_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw') or not created or instance.etat_suppression or not instance.etat_validation:
        return

    def mettre_en_file():
        from integrations.service import mettre_en_file_sortant
        try:
            mettre_en_file_sortant(instance.article, instance)
        except Exception:
            logger.exception('Événement sortant non préparé pour le mouvement %s', instance.pk)
    transaction.on_commit(mettre_en_file)
