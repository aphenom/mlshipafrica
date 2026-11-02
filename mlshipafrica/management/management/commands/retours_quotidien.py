"""Calendrier des retours : rappels J5, J7, J8, J10 et garde dès J11. Chaque matin (voir CRONJOBS)."""
from django.core.management.base import BaseCommand

from management.retours import traiter_retours


class Command(BaseCommand):
    help = "Rappels et garde des colis revenus à Abidjan (rejouable sans double comptage)."

    def handle(self, *args, **options):
        bilan = traiter_retours()
        self.stdout.write('Retours : %(colis)d colis, %(sms)d SMS, %(garde_maj)d gardes mises à jour' % bilan)
        if bilan['a_abandonner']:
            self.stdout.write('À déclarer abandonnés par le manager : ' + ', '.join(bilan['a_abandonner']))
