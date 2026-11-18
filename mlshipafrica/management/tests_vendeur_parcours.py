"""Espace vendeur : import de commandes, validation puis commande suivante, frais sur la facture, stock et photos."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from management import tests_pages
from management.models import Article, EntreeStock, ProduitStock
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R

MEDIA = tempfile.mkdtemp()
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00'
       b'\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')


@override_settings(MEDIA_ROOT=MEDIA)
class ParcoursVendeur(tests_pages.RecettePages):
    test_toutes_les_pages = None

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.vendeur.user)

    def test_import_de_commandes_au_format_de_la_plateforme(self):
        modele = self.client.get('/management/vendeur_import_colis/?modele=1').content.decode('utf-8-sig')
        self.assertIn('Nom du client *', modele)
        csv = ('Nom du client *;Téléphone *;Ville *;Produit *;Quantité;Prix unitaire (F) *;Ma référence\n'
               'Kouassi;0707070707;Bouaké;Crème;2;7500;CMD-1\n'
               'Yao;12;Paris;Savon;1;5000;CMD-2\n')
        avant = Article.objects.filter(vendeur=self.vendeur).count()
        self.client.post('/management/vendeur_import_colis/', {'fichier': SimpleUploadedFile('c.csv', csv.encode('utf-8'))})
        apercu = self.client.get('/management/vendeur_import_colis/').content.decode()
        self.assertIn('ville non desservie', apercu)
        self.assertIn('téléphone invalide', apercu)
        self.assertEqual(Article.objects.filter(vendeur=self.vendeur).count(), avant)        # rien avant confirmation
        self.client.post('/management/vendeur_import_colis/', {'confirmer': '1'})
        nouvelle = Article.objects.get(vendeur=self.vendeur, reference_externe='CMD-1')
        self.assertEqual(nouvelle.statut_traitement, S.EN_ATTENTE_DEPOT)
        self.assertEqual(int(nouvelle.valeur_totale), 15000)
        self.assertEqual(int(nouvelle.cout_option_encaissement), 750)                        # 5 % de collecte
        self.assertFalse(Article.objects.filter(reference_externe='CMD-2').exists())

    def test_meme_reference_chez_deux_vendeurs_et_reimport(self):
        from management.tests import vendeur_pour
        csv = ('Nom du client *;Téléphone *;Ville *;Produit *;Prix unitaire (F) *;Ma référence\n'
               'Kouassi;0707070707;Bouaké;Crème;7500;CMD-1\n')
        fichier = lambda: SimpleUploadedFile('c.csv', csv.encode('utf-8'))
        self.client.post('/management/vendeur_import_colis/', {'fichier': fichier()})
        self.client.post('/management/vendeur_import_colis/', {'confirmer': '1'})
        self.client.post('/management/vendeur_import_colis/', {'fichier': fichier()})          # même fichier une 2e fois
        self.assertIn('déjà utilisée', self.client.get('/management/vendeur_import_colis/').content.decode())
        self.client.post('/management/vendeur_import_colis/', {'annuler': '1'})
        autre = vendeur_pour(self.vendeur.license, 'Autre boutique')
        autre.etat_approbation = True
        autre.save()
        self.client.force_login(autre.user)
        self.client.post('/management/vendeur_import_colis/', {'fichier': fichier()})
        self.client.post('/management/vendeur_import_colis/', {'confirmer': '1'})
        self.assertEqual(Article.objects.filter(reference_externe='CMD-1').count(), 2)          # une par vendeur

    def test_valider_puis_creer_une_autre_commande(self):
        brouillon = Article.objects.filter(vendeur=self.vendeur).first()
        brouillon_code = Article.objects.create(
            vendeur=self.vendeur, license=self.vendeur.license, config=brouillon.config, localite_depart=brouillon.localite_depart,
            localite_arrivee=brouillon.localite_arrivee, format_article=brouillon.format_article, valeur=10000, quantite=1,
            is_option_encaissement=True, etat_validation=False).code
        page = self.client.get('/management/vendeur_facture_colis/%s/' % brouillon_code).content.decode()
        self.assertIn('Frais de collecte de fonds', page)
        self.assertIn('Valider et créer une autre commande', page)
        self.assertIn('Quitter', page)
        r = self.client.post('/management/vendeur_facture_colis/%s/' % brouillon_code, {'submit_validation': 'continuer'})
        self.assertEqual(r['Location'], '/management/vendeur_edit_colis/?apres=%s' % brouillon_code)
        page = self.client.get(r['Location']).content.decode()
        self.assertIn('créée', page)
        self.assertIn('voir la commande', page)

    def test_stock_photo_et_validation_du_manager(self):
        photo = SimpleUploadedFile('creme.png', PNG, content_type='image/png')
        self.client.post('/management/vendeur_stock/', {'reference': ['CR-1'], 'designation': ['Crème'], 'quantite': ['12'],
                                                        'photo_0': photo})
        entree = EntreeStock.objects.get(vendeur=self.vendeur)
        ligne = entree.lignes.get()
        self.assertTrue(ligne.photo)
        self.assertFalse(ProduitStock.objects.filter(vendeur=self.vendeur, reference='CR-1').exists())   # en attente
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_stock/').content.decode()
        self.assertIn(ligne.photo.url, page)
        self.client.post('/management/admin_stock/', {'valider_entree': entree.pk, 'recu_%d' % ligne.pk: '10'})
        produit = ProduitStock.objects.get(vendeur=self.vendeur, reference='CR-1')
        self.assertEqual(produit.quantite_disponible, 10)
        self.assertTrue(produit.photo)

    def test_sans_option_stockage_le_vendeur_peut_la_demander(self):
        self.vendeur.option_stockage = False
        self.vendeur.save()
        page = self.client.get('/').content.decode()
        self.assertNotIn('Mon stock', page)
        page = self.client.get('/management/vendeur_stock/').content.decode()
        self.assertIn('Demander le stockage', page)
        self.client.post('/management/vendeur_stock/', {'demander_stockage': '1'})
        self.vendeur.refresh_from_db()
        self.assertIsNotNone(self.vendeur.demande_stockage_le)

    def test_tableau_de_bord_les_montants_suivent_les_dates(self):
        page = self.client.get('/?periode=dates&du=2001-01-01&au=2001-01-31').content.decode()
        self.assertIn('Encaissé sur la période', page)

    def donnees_commande(self, **extra):
        a = self.articles[0]
        d = {'nom_destinataire': 'Kouassi', 'numero_principal_destinataire': '+2250707070707', 'localite_arrivee': a.localite_arrivee_id,
             'adresse_destinataire': 'Commerce', 'designation': 'Crème', 'valeur': '10000', 'quantite': '2',
             'format_article': a.format_article_id, 'produits': ['cosmetiques'], 'is_option_encaissement': 'True', 'action': 'valider'}
        d.update(extra)
        return d

    def test_valider_d_un_clic_depuis_mon_stock_puis_commande_suivante(self):
        produit = ProduitStock.objects.create(vendeur=self.vendeur, reference='CR-9', designation='Crème 50 ml', quantite_disponible=5)
        page = self.client.get('/management/vendeur_edit_colis/').content.decode()
        self.assertIn('Depuis mon stock ML COD Intérieur', page)
        self.assertIn('Valider la commande', page)
        r = self.client.post('/management/vendeur_edit_colis/', self.donnees_commande(type_colis='stock', produit_stock=produit.pk, designation=''))
        commande = Article.objects.filter(vendeur=self.vendeur, produit_stock=produit).get()
        self.assertEqual(r['Location'], '/management/vendeur_edit_colis/?apres=%s' % commande.code)
        self.assertEqual(commande.statut_traitement, S.EN_ATTENTE_DEPOT)
        self.assertEqual(commande.designation, 'Crème 50 ml')                       # repris du produit
        produit.refresh_from_db()
        self.assertEqual(produit.quantite_disponible, 3)                            # 2 pièces sorties du stock
        self.assertIn('enregistrée et envoyée', self.client.get(r['Location']).content.decode())

    def test_stock_choisi_sans_produit_refuse(self):
        avant = Article.objects.count()
        page = self.client.post('/management/vendeur_edit_colis/', self.donnees_commande(type_colis='stock')).content.decode()
        self.assertIn('Choisissez le produit de votre stock', page)
        self.assertEqual(Article.objects.count(), avant)

    def test_ramassage_d_un_clic(self):
        self.client.post('/management/vendeur_edit_colis/', self.donnees_commande(type_colis='ramassage', designation='Sac'))
        self.assertEqual(Article.objects.filter(vendeur=self.vendeur, designation='Sac').get().statut_traitement, S.EN_ATTENTE_RAMASSAGE)

    def test_shipping_vendeur_suivi_et_impressions(self):
        page = self.client.get('/management/vendeur_liste_colis/').content.decode()
        self.assertNotIn('Nouvelle commande</a>', page)
        self.assertIn('Bordereau de dépôt', page)
        codes = [a.code for a in self.articles[:3]]
        for doc in ('bordereau', 'factures', 'etiquettes'):
            r = self.client.post('/management/vendeur_imprimer/', {'doc': doc, 'codes': codes})
            self.assertEqual(r.status_code, 200)
            self.assertIn(codes[0], r.content.decode())
        export = self.client.post('/management/vendeur_imprimer/', {'doc': 'export', 'codes': codes}).content.decode('utf-8-sig')
        self.assertIn(codes[0], export)
        self.assertNotIn('Agent', export.splitlines()[0])
        from management.tests import vendeur_pour
        autre = vendeur_pour(self.vendeur.license, 'Autre')
        self.client.force_login(autre.user)
        r = self.client.post('/management/vendeur_imprimer/', {'doc': 'bordereau', 'codes': codes})
        self.assertEqual(r.status_code, 302)                                         # pas les colis d'un autre vendeur

    def test_bouton_retour(self):
        self.assertIn('← Retour', self.client.get('/management/vendeur_releves/').content.decode())
        self.assertNotIn('← Retour', self.client.get('/').content.decode())
