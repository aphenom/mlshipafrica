"""Chaque matin : alertes des commerciaux sur leurs vendeurs (voir CRONJOBS)."""
from django.core.management.base import BaseCommand

from management.commercial import envoyer_alertes


class Command(BaseCommand):
    help = "Envoie aux commerciaux les alertes sur leurs vendeurs (sans commande, en chute, retours, stock épuisé)."

    def handle(self, *args, **options):
        self.stdout.write('Alertes commerciales : %d envoyée(s).' % envoyer_alertes())
