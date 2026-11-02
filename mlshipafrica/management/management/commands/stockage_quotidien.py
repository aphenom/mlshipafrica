"""Coût de stockage du jour pour chaque vendeur en stockage (pièces × tarif). Chaque soir (voir CRONJOBS)."""
from django.core.management.base import BaseCommand

from management.stock import facturer_stockage


class Command(BaseCommand):
    help = "Facture le stockage du jour (une ligne par vendeur et par jour, rejouable)."

    def handle(self, *args, **options):
        self.stdout.write('Stockage facturé pour %d vendeur(s).' % facturer_stockage())
