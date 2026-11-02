"""Relevés vendeurs du lundi et du jeudi (voir CRONJOBS). Rejouable : une écriture n'entre que dans un relevé."""
from django.core.management.base import BaseCommand

from management.finance import generer_releves


class Command(BaseCommand):
    help = "Génère un relevé par vendeur avec ses écritures pas encore relevées."

    def handle(self, *args, **options):
        releves = generer_releves()
        self.stdout.write('%d relevé(s) généré(s).' % len(releves))
