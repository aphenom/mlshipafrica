"""Écrans de l'équipe de la maquette (agent COD, manager), sur les colis de la recette."""
from django.utils import timezone

from management import tests_pages
from management.models import Article
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R

URL = '/management/admin_confirmations/'


class FileAppels(tests_pages.RecettePages):
    test_toutes_les_pages = None  # la recette complète tourne déjà dans tests_pages

    def setUp(self):
        super().setUp()
        self.agent = self.comptes[R.AGENT]
        self.client.force_login(self.agent)
        self.colis = Article.objects.get(vendeur=self.vendeur, statut_traitement=S.EN_ATTENTE_RAMASSAGE)

    def test_annulation_avec_le_motif_de_la_liste(self):
        page = self.client.get(URL).content.decode()
        self.assertIn(self.colis.code, page)
        self.assertIn('✓ Acompte reçu', page)
        self.client.post(URL, {'article': self.colis.code, 'resultat': 'annule', 'motif': 'Commande en double'})
        self.colis.refresh_from_db()
        self.assertEqual(self.colis.statut_traitement, S.ANNULE)
        self.assertEqual(self.colis.appels.last().commentaire, 'Commande en double')

    def test_confirmee_sans_acompte_passe_en_attente_de_reception(self):
        self.client.post(URL, {'article': self.colis.code, 'resultat': 'confirme'})
        self.colis.refresh_from_db()
        self.assertEqual(self.colis.etat_confirmation, 'confirme')
        self.assertNotIn('>%s</a>' % self.colis.code, self.client.get(URL).content.decode())
        page = self.client.get(URL + '?vue=attente').content.decode()
        self.assertIn(self.colis.code, page)
        self.assertIn('Confirmées aujourd’hui</span><span class="v t-ok">1</span>', page)

    def test_acompte_recu_avec_reference(self):
        self.client.post(URL, {'article': self.colis.code, 'resultat': 'confirme', 'acompte_reseau': 'wave',
                               'acompte_reference': 'WV-TEST-1', 'acompte_numero': '0707070707'})
        self.colis.refresh_from_db()
        self.assertEqual(self.colis.etat_confirmation, 'confirme')
        self.assertTrue(self.colis.acomptes.filter(reference_depot='WV-TEST-1').exists())


class TableauxDeBord(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def page(self, role, url='/'):
        self.client.force_login(self.comptes[role])
        return self.client.get(url, follow=True).content.decode()

    def test_manager_voit_les_volumes_sans_argent(self):
        for p in ('', '?p=jour', '?p=7j', '?p=moisprec', '?du=2026-01-01&au=2026-12-31'):
            page = self.page(R.MANAGER, '/' + p)
            self.assertIn('Pilotage de l’activité', page)
            self.assertNotIn('Bénéfice', page)
            self.assertNotIn('Trésorerie', page)
            self.assertNotIn(' F<', page)               # aucun montant en francs
        self.assertIn('Colis en circulation', page)

    def test_ceo_voit_le_benefice(self):
        page = self.page(R.SUPER)
        self.assertIn('Bénéfice ML COD Intérieur', page)
        self.assertIn('Trésorerie à venir', page)

    def test_comptable_voit_sa_journee(self):
        from management.models import Releve
        Releve.objects.create(code='RL-TEST-1', vendeur=self.vendeur, date_arrete=timezone.now(), net=12500)
        page = self.page(R.COMPTABLE)
        self.assertIn('voici votre journée', page)
        self.assertIn('relevé(s) à verser', page)
        self.assertIn('Calendrier financier', page)

    def test_agent_arrive_sur_sa_file(self):
        self.client.force_login(self.comptes[R.AGENT])
        self.assertRedirects(self.client.get('/'), '/management/admin_confirmations/', fetch_redirect_response=False)
