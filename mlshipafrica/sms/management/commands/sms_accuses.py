"""Relève les accusés de réception et le solde HSMS (secours si le webhook n'arrive pas). Toutes les 10 minutes."""
from django.core.management.base import BaseCommand

from sms.hsms import ErreurHsms
from sms.service import relever_accuses, relever_solde


class Command(BaseCommand):
    help = "Met à jour les statuts de livraison des SMS et le solde HSMS."

    def handle(self, *args, **options):
        n = relever_accuses()
        try:
            solde = relever_solde()
        except ErreurHsms as erreur:
            solde = 'indisponible (%s)' % erreur
        self.stdout.write('Accusés mis à jour : %d · solde SMS : %s' % (n, solde))
