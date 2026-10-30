"""Résumé du soir aux vendeurs (19 h, heure d'Abidjan). Ne fait rien tant qu'il est désactivé dans les paramètres SMS."""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from management.models import HistoriqueArticle, Vendeur
from mlshipafrica.enums import StatutTraitement as S
from sms.declencheurs import sms_resume_soir
from sms.models import SmsParametres


class Command(BaseCommand):
    help = "Prépare le SMS de résumé du jour pour chaque vendeur actif dans la journée."

    def handle(self, *args, **options):
        if not SmsParametres.charger().resume_soir_actif:
            self.stdout.write('Résumé du soir désactivé.')
            return
        jour = timezone.localdate()
        lignes = (HistoriqueArticle.objects.filter(date_creation__date=jour, etat_suppression=False, etat_validation=True,
                                                   article__vendeur__isnull=False)
                  .values('article__vendeur')
                  .annotate(recus=Count('id', filter=Q(statut_traitement__in=[S.RAMASSE, S.DEPOT])),
                            expedies=Count('id', filter=Q(statut_traitement=S.EN_TRANSIT)),
                            livres=Count('id', filter=Q(statut_traitement__in=[S.LIVRE, S.LIVRE_PAYE])),
                            echecs=Count('id', filter=Q(statut_traitement=S.ECHEC_LIVRAISON)),
                            annules=Count('id', filter=Q(statut_traitement=S.ANNULE))))
        vendeurs = Vendeur.objects.in_bulk([l['article__vendeur'] for l in lignes])
        n = 0
        for ligne in lignes:
            vendeur = vendeurs.get(ligne['article__vendeur'])
            compteurs = {k: ligne[k] for k in ('recus', 'expedies', 'livres', 'echecs', 'annules')}
            if vendeur and sms_resume_soir(vendeur, jour, compteurs):
                n += 1
        self.stdout.write('%d résumés mis en file.' % n)
