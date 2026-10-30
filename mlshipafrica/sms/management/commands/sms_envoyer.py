"""Envoie les SMS dus. Tâche planifiée chaque minute (voir CRONJOBS dans settings.py)."""
from django.core.management.base import BaseCommand

from sms.service import envoyer_file


class Command(BaseCommand):
    help = "Envoie les SMS en file (à lancer chaque minute)."

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=200, help="Nombre maximum de SMS par passage.")

    def handle(self, *args, **options):
        bilan = envoyer_file(limite=options['limite'])
        if bilan['envoyes'] or bilan['reportes'] or bilan['echecs'] or bilan['pause']:
            self.stdout.write('SMS : %(envoyes)d envoyés, %(reportes)d reportés, %(echecs)d en échec, pause=%(pause)s' % bilan)
