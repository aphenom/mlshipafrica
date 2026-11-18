"""
Factures de paiement à la main (secours). Ce n'est plus une tâche planifiée : la comptable génère les factures
depuis « Paiements vendeurs ». Seuls les colis passés en Unpaid, les retours et le stockage y entrent.
"""
from django.core.management.base import BaseCommand

from management.finance import generer_releves


class Command(BaseCommand):
    help = "Génère une facture de paiement par vendeur avec ses lignes payables (colis Unpaid, retours, stockage)."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help="Générer vraiment (sinon : rien, la comptable pilote).")

    def handle(self, *args, **options):
        if not options['force']:
            # Ancienne tâche planifiée (lundi et jeudi 6 h) : si la crontab n'a pas été rechargée après la mise à jour,
            # elle ne doit surtout pas générer de factures à la place de la comptable.
            self.stdout.write("Rien généré : la comptable génère les factures dans Paiements vendeurs (--force pour forcer).")
            return
        releves = generer_releves()
        self.stdout.write('%d facture(s) générée(s).' % len(releves))
