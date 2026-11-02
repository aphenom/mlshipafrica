"""Envoie les événements en file (Woura, webhooks des vendeurs). Chaque minute (voir CRONJOBS)."""
from django.core.management.base import BaseCommand

from integrations.service import envoyer_file


class Command(BaseCommand):
    help = "Envoie les événements sortants en file."

    def handle(self, *args, **options):
        bilan = envoyer_file()
        if bilan['envoyes'] or bilan['erreurs']:
            self.stdout.write('Intégrations : %(envoyes)d envoyés, %(erreurs)d en erreur' % bilan)
