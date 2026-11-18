"""Circuit de paiement : Livré → Unpaid (comptable) → facture de paiement Paid → Versé ; réglages des frais par le CEO."""
from decimal import Decimal

from management import tests_pages
from management.finance import a_payer_par_vendeur, ecritures_a_payer, generer_releves
from management.models import Article, Ecriture, Releve
from mlshipafrica.enums import StatutReleve, StatutTraitement as S, TypeEcriture as T, TypeProfilStaffChoice as R


class Paiements(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def setUp(self):
        super().setUp()
        # La recette génère des relevés au démarrage : on repart d'une situation sans facture
        from management.finance import comptabiliser
        for a in Article.objects.all():      # en test, les écritures « après validation » ne partent pas d'elles-mêmes
            comptabiliser(a)
        Ecriture.objects.update(releve=None)
        Releve.objects.all().delete()
        self.livre = Article.objects.get(vendeur=self.vendeur, statut_traitement=S.LIVRE)

    def test_livre_n_entre_dans_un_paiement_qu_apres_unpaid(self):
        self.assertFalse(ecritures_a_payer(vendeurs=[self.vendeur]).filter(article=self.livre).exists())
        self.client.force_login(self.comptes[R.COMPTABLE])
        page = self.client.get('/management/admin_releves/?etape=unpaid').content.decode()
        self.assertIn(self.livre.code, page)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post('/management/admin_colis_actions/', {'action': 'unpaid', 'codes': [self.livre.code],
                                                                     'retour': '/management/admin_releves/?etape=unpaid'})
        self.assertEqual(r['Location'], '/management/admin_releves/?etape=unpaid')
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.statut_traitement, S.LIVRE_PAYE)
        lignes = ecritures_a_payer(vendeurs=[self.vendeur]).filter(article=self.livre)
        self.assertEqual(set(lignes.values_list('type', flat=True)), {T.COLLECTE, T.FRAIS, T.FRAIS_COLLECTE})

    def test_frais_de_collecte_cinq_pour_cent_des_la_livraison(self):
        self.assertEqual(self.livre.cout_option_encaissement, Decimal('750'))
        frais = Ecriture.objects.filter(article=self.livre, type=T.FRAIS_COLLECTE).first()
        self.assertEqual(frais.montant, Decimal('750'))

    def test_generer_factures_des_vendeurs_coches_puis_verser(self):
        Article.objects.filter(pk=self.livre.pk).update(statut_traitement=S.LIVRE_PAYE)
        self.client.force_login(self.comptes[R.COMPTABLE])
        page = self.client.get('/management/admin_releves/?etape=a_payer').content.decode()
        self.assertIn(self.vendeur.code, page)
        self.assertIn('Frais de collecte', page)
        self.client.post('/management/admin_releves/', {'action': 'generer', 'vendeurs': [self.vendeur.code]})
        releve = Releve.objects.get(vendeur=self.vendeur)
        self.assertEqual(releve.genere_par, self.comptes[R.COMPTABLE])
        self.assertTrue(releve.ecritures.filter(article=self.livre, type=T.FRAIS_COLLECTE).exists())
        self.assertEqual(generer_releves(vendeurs=[self.vendeur]), [])          # rien n'est facturé deux fois
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.statut_traitement, S.PAYE)                  # Shipping : Unpaid → Paid
        self.assertEqual(self.livre.get_last_historique().statut_traitement, S.PAYE)
        # Le vendeur voit sa facture et l'imprime ligne par ligne
        self.client.force_login(self.vendeur.user)
        mon_argent = self.client.get('/management/vendeur_releves/').content.decode()
        self.assertIn(releve.code, mon_argent)
        self.assertIn('Paid · versement en cours', mon_argent)
        facture = self.client.get('/management/facture_paiement/%s/' % releve.code).content.decode()
        self.assertIn(self.livre.code, facture)
        self.assertIn('Frais de collecte', facture)
        self.assertIn('750', facture)
        # Un autre vendeur ne la voit pas
        from management.tests import vendeur_pour
        autre = vendeur_pour(self.vendeur.license, 'Autre boutique')
        self.client.force_login(autre.user)
        self.assertEqual(self.client.get('/management/facture_paiement/%s/' % releve.code).status_code, 404)

    def test_annuler_une_facture_remet_les_colis_a_payer(self):
        Article.objects.filter(pk=self.livre.pk).update(statut_traitement=S.LIVRE_PAYE)
        releve = generer_releves(vendeurs=[self.vendeur])[0]
        self.client.force_login(self.comptes[R.COMPTABLE])
        self.client.post('/management/admin_releves/', {'action': 'annuler', 'releve': releve.pk, 'motif': ''})
        releve.refresh_from_db()
        self.assertEqual(releve.statut, StatutReleve.A_VERSER)                  # motif obligatoire
        self.client.post('/management/admin_releves/', {'action': 'annuler', 'releve': releve.pk, 'motif': 'Généré par erreur'})
        releve.refresh_from_db()
        self.assertEqual(releve.statut, StatutReleve.ANNULE)
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.statut_traitement, S.LIVRE_PAYE)            # facture annulée : le colis revient en Unpaid
        self.assertFalse(releve.ecritures.exists())
        self.assertTrue(any(v['vendeur'] == self.vendeur for v in a_payer_par_vendeur(self.vendeur.license)))
        self.client.force_login(self.vendeur.user)
        self.assertNotIn(releve.code + '<div', self.client.get('/management/vendeur_releves/').content.decode())

    def test_shipping_suit_unpaid_paid_verse(self):
        from management.finance import marquer_verse
        Article.objects.filter(pk=self.livre.pk).update(statut_traitement=S.LIVRE_PAYE)
        releve = generer_releves(vendeurs=[self.vendeur])[0]
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_liste_colis/?statut=paye').content.decode()
        self.assertIn(self.livre.code, page)
        self.assertIn('Paid (facture émise, à verser)', page)
        self.vendeur.versement_valide, self.vendeur.moyen_valide, self.vendeur.compte_valide = True, 'wave', '0707070707'
        self.vendeur.save()
        marquer_verse(releve, self.comptes[R.COMPTABLE], 'WV-1')
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.statut_traitement, S.REVERSE)
        etapes = list(self.livre.article_historiquearticles.filter(etat_suppression=False).order_by('date_creation')
                      .values_list('statut_traitement', flat=True))
        self.assertEqual(etapes[-2:], [S.PAYE, S.REVERSE])

    def test_vendeur_bloque_sans_numero_valide(self):
        Article.objects.filter(pk=self.livre.pk).update(statut_traitement=S.LIVRE_PAYE)
        self.vendeur.versement_valide, self.vendeur.compte_valide, self.vendeur.compte_versement = False, '', '0707'
        self.vendeur.save()
        ligne = [v for v in a_payer_par_vendeur(self.vendeur.license) if v['vendeur'] == self.vendeur][0]
        self.assertEqual(ligne['bloque'], 'Numéro de paiement à valider')

    def test_ceo_regle_le_taux_de_collecte_pour_tous(self):
        self.client.force_login(self.comptes[R.COMPTABLE])
        self.assertEqual(self.client.get('/management/admin_reglages_frais/').status_code, 403)
        self.client.force_login(self.comptes[R.SUPER])
        page = self.client.get('/management/admin_reglages_frais/').content.decode()
        self.assertIn('Frais de collecte', page)
        self.client.post('/management/admin_reglages_frais/', {'taux_option_encaissement': '4', 'appliquer': '1'})
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.cout_option_encaissement, Decimal('600'))   # 4 % de 15 000
        total = sum(Ecriture.objects.filter(article=self.livre, type=T.FRAIS_COLLECTE).values_list('montant', flat=True))
        self.assertEqual(total, Decimal('600'))                                 # l'écart (−150) est écrit

    def test_colis_deja_facture_garde_son_taux_sauf_demande(self):
        Article.objects.filter(pk=self.livre.pk).update(statut_traitement=S.LIVRE_PAYE)
        generer_releves(vendeurs=[self.vendeur])
        self.client.force_login(self.comptes[R.SUPER])
        self.client.post('/management/admin_reglages_frais/', {'taux_option_encaissement': '4', 'appliquer': '1'})
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.cout_option_encaissement, Decimal('750'))
        self.client.post('/management/admin_reglages_frais/', {'taux_option_encaissement': '4', 'appliquer': '1', 'inclure_factures': '1'})
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.cout_option_encaissement, Decimal('600'))
        regul = Ecriture.objects.filter(article=self.livre, type=T.FRAIS_COLLECTE, releve__isnull=True).first()
        self.assertEqual(regul.montant, Decimal('-150'))                        # régularisé sur la prochaine facture

    def test_numero_de_paiement_dans_les_parametres(self):
        self.client.force_login(self.vendeur.user)
        mon_argent = self.client.get('/management/vendeur_releves/').content.decode()
        self.assertNotIn('name="compte_versement"', mon_argent)
        self.assertIn('/management/vendeur_paiement/', mon_argent)
        self.assertIn('name="compte_versement"', self.client.get('/management/vendeur_paiement/').content.decode())

    def test_comptable_charge_le_stockage_du_mois_en_un_bloc(self):
        from management.models import ProduitStock
        self.vendeur.option_stockage = True
        self.vendeur.save()
        ProduitStock.objects.create(vendeur=self.vendeur, reference='ST-1', designation='Savon', quantite_disponible=7)
        self.client.force_login(self.comptes[R.COMPTABLE])
        page = self.client.get('/management/admin_releves/?etape=stockage').content.decode()
        self.assertIn('Charger le stockage des vendeurs cochés', page)
        self.assertIn(self.vendeur.code, page)
        r = self.client.post('/management/admin_releves/', {'action': 'stockage', 'vendeurs': [self.vendeur.code]})
        self.assertEqual(r['Location'], '/management/admin_releves/?etape=a_payer')
        ligne = Ecriture.objects.get(vendeur=self.vendeur, type=T.STOCKAGE, cle__startswith='stockage:mois:')
        self.assertEqual(int(ligne.montant), 7 * 300)
        self.assertNotIn(self.vendeur.code, self.client.get('/management/admin_releves/?etape=stockage').content.decode())
        self.client.force_login(self.comptes[R.MANAGER])
        self.assertNotEqual(self.client.get('/management/admin_releves/?etape=stockage').status_code, 200)   # comptable et CEO seulement
