"""
Factures de paiement à la main (secours). Ce n'est plus une tâche planifiée : la comptable génère les factures
depuis « Paiements vendeurs ». Seuls les colis passés en Unpaid, les retours et le stockage y entrent.
"""
from django.core.management.base import BaseCommand

from management.finance import generer_releves


class Command(BaseCommand):
    help = "Génère une facture de paiement par vendeur avec ses lignes payables (colis Unpaid, retours, stockage)."

    def handle(self, *args, **options):
        releves = generer_releves()
        self.stdout.write('%d facture(s) générée(s).' % len(releves))
