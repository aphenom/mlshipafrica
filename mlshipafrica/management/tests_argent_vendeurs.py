"""Argent des vendeurs : un seul circuit (les relevés), numéros de versement validés, frais de versement à leur charge."""
import shutil
import tempfile
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from management import tests_pages
from management.finance import (enregistrer_coordonnees, frais_versement, journal, marquer_verse, refuser_coordonnees,
                                valider_coordonnees)
from management.models import Article, Ecriture, FraisVersement, Releve, Vendeur
from mlshipafrica.enums import StatutReleve, StatutTraitement as S, TypeEcriture as T, TypeProfilStaffChoice as R

MEDIA = tempfile.mkdtemp()


def procuration(nom='procuration.pdf'):
    return SimpleUploadedFile(nom, b'%PDF-1.4 procuration signee', content_type='application/pdf')


@override_settings(MEDIA_ROOT=MEDIA)
class ArgentVendeurs(tests_pages.RecettePages):
    test_toutes_les_pages = None  # la recette complète tourne déjà dans tests_pages

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        FraisVersement.objects.update_or_create(moyen='wave', defaults={'taux': Decimal('1'), 'plafond': None})
        self.vendeur.moyen_versement = self.vendeur.compte_versement = None
        self.vendeur.moyen_valide = self.vendeur.compte_valide = ''
        self.vendeur.versement_valide = False
        self.vendeur.save()
        self.releve = Releve.objects.create(code='RL-TEST-1', vendeur=self.vendeur, date_arrete=self.vendeur.date_creation,
                                            total_collecte=Decimal('483628'), net=Decimal('483628'))

    # ------------------------------------------------------------------ règles

    def test_frais_wave_un_pour_cent_arrondi_et_plafond(self):
        self.assertEqual(frais_versement('wave', Decimal('483628')), Decimal('4836'))
        self.assertEqual(frais_versement('wave', Decimal('150')), Decimal('2'))     # 1,5 → 2
        self.assertEqual(frais_versement('orange', Decimal('483628')), Decimal('0'))  # pas de règle : pas de frais
        self.assertEqual(frais_versement('wave', Decimal('-500')), Decimal('0'))
        FraisVersement.objects.filter(moyen='wave').update(plafond=Decimal('3000'))
        self.assertEqual(frais_versement('wave', Decimal('483628')), Decimal('3000'))

    def test_nouveau_numero_bloque_le_versement_jusqu_a_validation(self):
        with self.assertRaises(ValidationError):                       # procuration obligatoire
            enregistrer_coordonnees(self.vendeur, 'wave', '0707070707', 'Mi Shop')
        enregistrer_coordonnees(self.vendeur, 'wave', '0707070707', 'Mi Shop', procuration())
        self.assertFalse(self.vendeur.versement_valide)
        with self.assertRaises(ValidationError):
            marquer_verse(self.releve, self.comptes[R.COMPTABLE], 'WV-1')
        valider_coordonnees(self.vendeur, self.comptes[R.COMPTABLE])
        releve = marquer_verse(self.releve, self.comptes[R.COMPTABLE], 'WV-1')
        self.assertEqual(releve.statut, StatutReleve.VERSE)
        self.assertEqual((releve.moyen_versement, releve.compte_verse), ('wave', '0707070707'))
        self.assertEqual((releve.frais_versement, releve.montant_verse), (Decimal('4836'), Decimal('478792')))

    def test_changement_de_numero_puis_refus_revient_a_l_ancien(self):
        enregistrer_coordonnees(self.vendeur, 'wave', '0707070707', 'Mi Shop', procuration())
        valider_coordonnees(self.vendeur, self.comptes[R.COMPTABLE])
        enregistrer_coordonnees(self.vendeur, 'orange', '0101010101', 'Inconnu', procuration('autre.pdf'))
        self.assertFalse(self.vendeur.versement_valide)
        self.assertEqual(self.vendeur.compte_valide, '0707070707')        # le numéro validé n'a pas bougé
        with self.assertRaises(ValidationError):
            refuser_coordonnees(self.vendeur, self.comptes[R.COMPTABLE], '')
        refuser_coordonnees(self.vendeur, self.comptes[R.COMPTABLE], 'Procuration illisible')
        self.vendeur.refresh_from_db()
        self.assertTrue(self.vendeur.versement_valide)
        self.assertEqual((self.vendeur.moyen_versement, self.vendeur.compte_versement), ('wave', '0707070707'))
        self.assertEqual(self.vendeur.versement_refus_motif, 'Procuration illisible')
        self.assertEqual(marquer_verse(self.releve, self.comptes[R.COMPTABLE], 'WV-2').compte_verse, '0707070707')

    def test_releve_negatif_ou_nul_se_solde_sans_coordonnees(self):
        self.releve.net = Decimal('-1691')
        self.releve.save()
        releve = marquer_verse(self.releve, self.comptes[R.COMPTABLE], 'SOLDE')
        self.assertEqual((releve.frais_versement, releve.montant_verse), (Decimal('0'), Decimal('0')))

    # ------------------------------------------------------------------ écrans

    def test_vendeur_saisit_son_numero_avec_procuration(self):
        self.client.force_login(self.vendeur.user)
        self.client.post('/management/vendeur_releves/', {'moyen_versement': 'wave', 'compte_versement': '0707070707'})
        self.vendeur.refresh_from_db()
        self.assertIsNone(self.vendeur.compte_versement)                 # refusé sans procuration
        self.client.post('/management/vendeur_releves/', {'moyen_versement': 'wave', 'compte_versement': '0707070707',
                                                          'titulaire_versement': 'Mi Shop', 'procuration_versement': procuration()})
        self.vendeur.refresh_from_db()
        self.assertEqual(self.vendeur.compte_versement, '0707070707')
        self.assertFalse(self.vendeur.versement_valide)
        page = self.client.get('/management/vendeur_releves/').content.decode()
        self.assertIn('En attente de validation', page)
        self.assertIn('Wave 1 %', page)

    def test_comptable_valide_et_verse_le_montant_apres_frais(self):
        enregistrer_coordonnees(self.vendeur, 'wave', '0707070707', 'Mi Shop', procuration())
        self.client.force_login(self.comptes[R.COMPTABLE])
        releves = self.client.get('/management/admin_releves/').content.decode()
        self.assertIn('bloqué', releves)
        page = self.client.get('/management/admin_moyens_versement/').content.decode()
        self.assertIn('0707070707', page)
        self.assertNotIn('Enregistrer les frais', page)                 # les frais sont réglés par le CEO
        self.assertEqual(self.client.post('/management/admin_moyens_versement/', {'frais': '1', 'taux_wave': '0'}).status_code, 403)
        self.client.post('/management/admin_moyens_versement/', {'vendeur': self.vendeur.code, 'action': 'valider'})
        self.vendeur.refresh_from_db()
        self.assertTrue(self.vendeur.versement_valide)
        releves = self.client.get('/management/admin_releves/').content.decode()
        self.assertIn('478\u202f792', releves)                               # montant à envoyer, frais déduits
        self.client.post('/management/admin_releves/', {'releve': self.releve.pk, 'reference': 'WV-OK'})
        self.releve.refresh_from_db()
        self.assertEqual(self.releve.montant_verse, Decimal('478792'))

    def test_ceo_regle_les_frais_et_l_agent_n_a_pas_acces(self):
        self.client.force_login(self.comptes[R.SUPER])
        self.client.post('/management/admin_moyens_versement/', {'frais': '1', 'taux_wave': '1,5', 'plafond_wave': '5000', 'taux_orange': '1'})
        self.assertEqual(FraisVersement.objects.get(moyen='wave').taux, Decimal('1.5'))
        self.assertEqual(FraisVersement.objects.get(moyen='wave').plafond, Decimal('5000'))
        self.assertEqual(FraisVersement.objects.get(moyen='orange').taux, Decimal('1'))
        self.client.force_login(self.comptes[R.AGENT])
        self.assertEqual(self.client.get('/management/admin_moyens_versement/').status_code, 403)

    def test_un_seul_circuit_de_paiement_dans_les_menus(self):
        for role in (R.SUPER, R.COMPTABLE):
            self.client.force_login(self.comptes[role])
            page = self.client.get('/management/admin_releves/').content.decode()
            self.assertIn('Moyens de paiement', page)
            self.assertIn('Anciens reversements', page)
            self.assertNotIn('Reversements à faire', page)
            self.assertNotIn('Frais à régler', page)

    def test_liens_facture_et_fiche_vendeur(self):
        colis = Article.objects.filter(vendeur=self.vendeur).first()
        self.client.force_login(self.comptes[R.AGENT])
        page = self.client.get('/management/admin_detail_colis/%s/' % colis.code).content.decode()
        self.assertNotIn('/management/admin_vendeur_profil/%s/' % self.vendeur.code, page)
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_detail_colis/%s/' % colis.code).content.decode()
        self.assertIn('/management/admin_vendeur_profil/%s/' % self.vendeur.code, page)

    def test_benefice_realise_sans_le_cout_des_colis_en_route(self):
        en_route = Article.objects.filter(vendeur=self.vendeur, statut_traitement__in=(S.EN_TRANSIT, S.ARRIVE)).first()
        livre = Article.objects.filter(vendeur=self.vendeur, statut_traitement=S.LIVRE).first()
        debut = min(en_route.date_creation, livre.date_creation).replace(year=2000)
        fin = debut.replace(year=2100)
        avant = journal(self.vendeur.license, debut, fin)
        Ecriture.objects.create(vendeur=self.vendeur, article=en_route, type=T.COUT_PRESTATAIRE, montant=Decimal('2700'),
                                cle='test-cout-route', license=self.vendeur.license)
        Ecriture.objects.create(vendeur=self.vendeur, article=livre, type=T.COUT_PRESTATAIRE, montant=Decimal('2700'),
                                cle='test-cout-livre', license=self.vendeur.license)
        apres = journal(self.vendeur.license, debut, fin)
        self.assertEqual(apres['cout_engage'] - avant['cout_engage'], Decimal('2700'))
        self.assertEqual(apres['cout_realise'] - avant['cout_realise'], Decimal('2700'))
        self.assertEqual(apres['benefice_realise'], apres['revenus'] - apres['cout_realise'])

