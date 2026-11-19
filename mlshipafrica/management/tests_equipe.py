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
        self.assertIn('voici votre dashboard', page)
        self.assertIn('relevé(s) à verser', page)
        self.assertIn('Calendrier financier', page)

    def test_agent_arrive_sur_sa_file(self):
        self.client.force_login(self.comptes[R.AGENT])
        self.assertRedirects(self.client.get('/'), '/management/admin_confirmations/', fetch_redirect_response=False)


class FicheVendeur(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def test_suivi_par_l_equipe_garde_l_agent_et_le_stockage(self):
        from management.models import ProfilStaff
        self.client.force_login(self.comptes[R.SUPER])
        url = '/management/admin_vendeur_edit_profil/%s/' % self.vendeur.code
        page = self.client.get(url).content.decode()
        self.assertNotIn("attr('disabled'", page)                   # l'ancien script désactivait les champs du suivi
        self.assertIn('name="agent_cod"', page)
        agent = ProfilStaff.objects.get(role_profil=R.AGENT)
        self.client.post(url, {'submit_affectation': '1', 'agent_cod': agent.code, 'option_stockage': '1'})
        self.vendeur.refresh_from_db()
        self.assertEqual(self.vendeur.agent_cod, agent)
        self.assertTrue(self.vendeur.option_stockage)

    def test_fiche_sans_argent_pour_le_commercial(self):
        from management.models import Vendeur
        Vendeur.objects.filter(pk=self.vendeur.pk).update(commercial=self.comptes[R.COMMERCIAL].account_profil_staff)
        self.client.force_login(self.comptes[R.COMMERCIAL])
        page = self.client.get('/management/admin_vendeur_profil/%s/' % self.vendeur.code).content.decode()
        self.assertIn('30 derniers jours', page)
        self.assertNotIn(' F', page)
        liste = self.client.get('/management/admin_liste_vendeurs/?type_vendeur=actif').content.decode()
        self.assertIn(self.vendeur.nom_store, liste)


class CommercialEtStock(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def test_portefeuille_du_commercial(self):
        from management.models import Vendeur
        from management.tests import vendeur_pour
        autre = vendeur_pour(self.vendeur.license, 'Boutique Ailleurs')   # approuvé, suivi par personne : pas à lui
        Vendeur.objects.filter(pk=self.vendeur.pk).update(commercial=self.comptes[R.COMMERCIAL].account_profil_staff)
        self.client.force_login(self.comptes[R.COMMERCIAL])
        page = self.client.get('/').content.decode()
        self.assertIn('Mon portefeuille', page)
        self.assertIn(self.vendeur.nom_store, page)
        self.assertNotIn(autre.nom_store, page)
        self.assertNotIn(' F', page)

    def test_stock_du_manager(self):
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_stock/').content.decode()
        self.assertIn('Envois à réceptionner', page)
        self.assertIn('Derniers mouvements', page)


class ZonesEtTarifs(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def test_le_ceo_modifie_prix_et_cout_avec_trace(self):
        from core.models import JournalAudit
        self.client.force_login(self.comptes[R.SUPER])
        r = self.client.get('/core/zones_tarifs/')
        page = r.content.decode()
        # Un tarif réellement affiché (zone numérotée, avec des villes), quel que soit l'ordre des autres tests
        tarif = next(l['tarif'] for z in r.context['zones'] for l in z['lignes'] if l['tarif'])
        self.assertIn('name="prix_%d"' % tarif.pk, page)
        self.client.post('/core/zones_tarifs/', {'prix_%d' % tarif.pk: '3600', 'cout_%d' % tarif.pk: '2700'})
        tarif.refresh_from_db()
        self.assertEqual((int(tarif.montant_frais), int(tarif.cout_partenaire)), (3600, 2700))
        self.assertTrue(JournalAudit.objects.filter(modele='Tarification', objet_id=str(tarif.pk)).exists())

    def test_reserve_au_ceo(self):
        for role in (R.COMPTABLE, R.MANAGER, R.ADMINISTRATEUR):
            self.client.force_login(self.comptes[role])
            self.assertEqual(self.client.get('/core/zones_tarifs/').status_code, 403, role)

    def test_indicateurs_alertes_et_relances_du_commercial(self):
        from datetime import date, timedelta
        from django.utils import timezone
        from management import commercial as com
        from management.models import Notification, ProduitStock, RelanceVendeur, Vendeur
        from management.tests import vendeur_pour
        commerciale = self.comptes[R.COMMERCIAL]
        Vendeur.objects.filter(pk=self.vendeur.pk).update(commercial=commerciale.account_profil_staff, option_stockage=True)
        dormant = vendeur_pour(self.vendeur.license, 'Boutique Dormante')
        Vendeur.objects.filter(pk=dormant.pk).update(commercial=commerciale.account_profil_staff,
                                                     date_approbation=timezone.now() - timedelta(days=5))
        ProduitStock.objects.create(vendeur=self.vendeur, reference='EP-1', designation='Savon', quantite_disponible=0)
        mes = Vendeur.objects.filter(commercial=commerciale.account_profil_staff)
        v = [x for x in com.indicateurs(mes) if x.pk == self.vendeur.pk][0]
        self.assertGreater(v.commandes_30, 0)
        self.assertIn(v.profil, com.PROFILS)
        types = {(a[0].pk, a[1]) for a in com.alertes(mes)}
        self.assertIn((dormant.pk, 'sans_commande'), types)
        self.assertIn((self.vendeur.pk, 'stock'), types)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertGreaterEqual(com.envoyer_alertes(), 2)
        with self.captureOnCommitCallbacks(execute=True):
            com.envoyer_alertes()                                                     # pas deux fois la même semaine
        self.assertEqual(Notification.objects.filter(destinataire=commerciale, titre__contains='Boutique Dormante').count(), 1)
        self.client.force_login(commerciale)
        page = self.client.get('/').content.decode()
        self.assertIn('Alertes sur mes vendeurs', page)
        self.assertIn('Taux de livraison', page)
        self.assertNotIn(' F<', page)                                                # jamais d'argent de la société
        suivi = '/management/commercial/suivi/%s/' % dormant.code
        self.client.post(suivi, {'note': 'Appelé, commence lundi', 'rappeler_le': timezone.localdate().isoformat()})
        self.assertEqual(RelanceVendeur.objects.get(vendeur=dormant).note, 'Appelé, commence lundi')
        self.assertIn('Boutique Dormante', self.client.get('/').content.decode().split('À rappeler aujourd’hui')[1][:2000])
        autre = vendeur_pour(self.vendeur.license, 'Pas a elle')
        self.assertEqual(self.client.get('/management/commercial/suivi/%s/' % autre.code).status_code, 404)
        self.client.force_login(self.comptes[R.MANAGER])
        self.assertNotEqual(self.client.get(suivi).status_code, 200)

    def test_vendeur_a_proposer_au_stockage(self):
        from management import commercial as com
        from management.models import Vendeur
        Vendeur.objects.filter(pk=self.vendeur.pk).update(option_stockage=False)
        ancien = com.SEUIL_STOCKAGE
        com.SEUIL_STOCKAGE = 1
        try:
            self.assertIn(self.vendeur.pk, [v.pk for v in com.a_proposer_stockage(Vendeur.objects.filter(pk=self.vendeur.pk))])
        finally:
            com.SEUIL_STOCKAGE = ancien
