"""Comptabilité des colis dans les conditions réelles (hors transaction)."""
from decimal import Decimal

from django.test import TransactionTestCase

from management.models import Article
from mlshipafrica.enums import StatutTraitement as S, TypeEcriture as T


class ComptabiliteHorsTransaction(TransactionTestCase):
    """
    Conditions réelles : un changement de statut fait par le vendeur, une tâche planifiée, Woura ou l'API n'est pas
    dans une transaction ; la comptabilité se déclenche aussitôt sur l'historique. Le colis doit déjà porter son
    nouveau statut à ce moment-là, sinon l'encaissement et les frais d'un colis livré ne sont pas comptés.
    """

    def test_colis_livre_hors_transaction_est_comptabilise(self):
        from io import StringIO
        from django.core.management import call_command
        from core.models import Localite
        from management.tests import base_ancienne, vendeur_pour
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        vendeur = vendeur_pour(license)
        a = Article(vendeur=vendeur, license=license, config=config, localite_depart=abidjan,
                    localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=petit, valeur=9400, quantite=1,
                    is_option_encaissement=True)
        a.save()
        for statut in (S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE_PAYE):
            a.statut_traitement = statut
            a.save()
        types = dict(a.ecritures.values_list('type', 'montant'))
        self.assertEqual(types.get(T.COLLECTE), Decimal('9400'))
        self.assertEqual(types.get(T.FRAIS), a.montant_frais)
        self.assertEqual(a.article_historiquearticles.filter(statut_traitement=S.LIVRE_PAYE).count(), 1)
        a.save()                                                      # enregistrer sans changer de statut : pas de doublon
        self.assertEqual(a.article_historiquearticles.filter(statut_traitement=S.LIVRE_PAYE).count(), 1)
