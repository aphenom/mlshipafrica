"""
À lancer UNE FOIS à la mise en service des relevés : passe en écritures les colis livrés que l'ancien outil
n'a pas encore reversés (les colis déjà reversés par l'ancien outil sont ignorés).

Sans risque à relancer : elle n'écrit que la différence entre ce qui est dû et ce qui est déjà compté. À relancer
après le correctif du 18/11/2026 (ordre colis / historique) pour rattraper les encaissements et frais non comptés
sur les colis livrés hors de l'écran de l'équipe ; ils apparaissent dans le prochain relevé du vendeur.

    python manage.py reprise_comptable --dry-run
    python manage.py reprise_comptable
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from management.finance import LIVRES, comptabiliser
from management.models import Article
from mlshipafrica.enums import StatutTraitement as S


class Command(BaseCommand):
    help = "Reprise : écritures des colis livrés non reversés et des retours en cours."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        colis = Article.objects.filter(etat_suppression=False, etat_reversement=False).filter(
            statut_traitement__in=LIVRES + (S.EN_RETOUR, S.REVENU_ABIDJAN))
        self.stdout.write('%d colis à reprendre.' % colis.count())
        if options['dry_run']:
            return
        n = 0
        with transaction.atomic():
            for article in colis.iterator():
                n += comptabiliser(article)
        self.stdout.write(self.style.SUCCESS('%d écritures créées.' % n))
