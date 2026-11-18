"""Le 1er du mois : rappel à la comptable de valider la charge de stockage du mois (voir CRONJOBS)."""
from django.core.management.base import BaseCommand

from management.stock import rappel_stockage


class Command(BaseCommand):
    help = "Le 1er du mois, rappelle à la comptable (et au CEO) de valider le stockage du mois. Rejouable."

    def handle(self, *args, **options):
        self.stdout.write('Stockage : rappel envoyé pour %d licence(s).' % rappel_stockage())
