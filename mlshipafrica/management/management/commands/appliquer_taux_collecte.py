"""
Applique le taux de collecte réglé par le CEO (Paramètres › Frais et réglages) aux colis existants.

    python manage.py appliquer_taux_collecte              # simulation : combien de colis, quel écart
    python manage.py appliquer_taux_collecte --appliquer  # colis pas encore facturés
    python manage.py appliquer_taux_collecte --appliquer --inclure-factures   # aussi les colis déjà facturés ou versés
Les écarts des colis livrés sont écrits en comptabilité et repris dans la prochaine facture de paiement du vendeur.
"""
from django.core.management.base import BaseCommand

from core.models import License
from management.finance import appliquer_taux_collecte, taux_collecte


class Command(BaseCommand):
    help = "Applique le taux de collecte global aux colis existants (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true')
        parser.add_argument('--inclure-factures', action='store_true')

    def handle(self, *args, **o):
        for license in License.objects.all():
            taux = taux_collecte(license)
            n, ecart = appliquer_taux_collecte(license, taux, inclure_factures=o['inclure_factures'], simuler=not o['appliquer'])
            self.stdout.write('%s : taux %s %% · %d colis %s · écart sur les livrés %s F' % (
                license, taux.normalize(), n, 'modifiés' if o['appliquer'] else 'à modifier (simulation)', ecart))
