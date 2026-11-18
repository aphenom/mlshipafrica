"""Espace vendeur de la maquette : tableau de bord et Shipping, sur les colis de la recette (un colis par parcours)."""
from django.utils import timezone

from management import tests_pages
from management.espace_vendeur import a_recevoir, tableau_de_bord
from management.finance import generer_releves
from management.models import Article, Releve
from mlshipafrica.enums import StatutTraitement as S


class EspaceVendeur(tests_pages.RecettePages):
    test_toutes_les_pages = None  # la recette complète tourne déjà dans tests_pages

    def setUp(self):
        super().setUp()
        self.client.force_login(self.vendeur.user)

    def test_taux_de_livraison_et_a_faire(self):
        Article.objects.filter(vendeur=self.vendeur, statut_traitement=S.EN_RETOUR).update(statut_traitement=S.REVENU_ABIDJAN)
        debut = timezone.now() - timezone.timedelta(days=1)
        tb = tableau_de_bord(self.vendeur, debut, timezone.now() + timezone.timedelta(minutes=1))
        # Parcours de la recette : 1 livré ; échecs et retours : echec, retour, retourne, stock, abime (reconduit repart)
        self.assertEqual((tb['livres'], tb['echecs']), (1, 5))
        self.assertEqual(tb['taux'], round(100 / 6))
        self.assertEqual(tb['taux_classe'], 't-bad')
        titres = ' '.join(t[1] or '' for t in tb['a_faire'])
        self.assertIn('en échec de livraison', titres)
        self.assertIn('revenu(s) à Abidjan', titres)
        self.assertIn('attente de ramassage', titres)

    def test_a_recevoir_egal_au_prochain_releve(self):
        attendu = a_recevoir(self.vendeur)
        generer_releves()
        releves = Releve.objects.filter(vendeur=self.vendeur)
        self.assertEqual(sum(r.net for r in releves), attendu)
        self.assertEqual(a_recevoir(self.vendeur), attendu)  # relevés pas encore versés : toujours à recevoir

    def test_tableau_de_bord(self):
        page = self.client.get('/').content.decode()
        self.assertIn('Bonjour Melina Shop', page)
        self.assertIn('Taux de livraison par ville', page)
        self.assertIn('Bouaké', page)
        self.assertNotIn('acompte', page.lower())

    def test_shipping_filtre_par_statut_et_recherche(self):
        page = self.client.get('/management/vendeur_liste_colis/').content.decode()
        for a in self.articles:
            self.assertIn(a.code, page)
        echec = Article.objects.filter(vendeur=self.vendeur, statut_traitement=S.ECHEC_LIVRAISON).first()
        page = self.client.get('/management/vendeur_liste_colis/?etape=%s' % S.ECHEC_LIVRAISON).content.decode()
        self.assertIn(echec.code, page)
        self.assertEqual(page.count('class="linkcode"'), Article.objects.filter(vendeur=self.vendeur, statut_traitement=S.ECHEC_LIVRAISON).count())
        page = self.client.get('/management/vendeur_liste_colis/?q=%s' % echec.code).content.decode()
        self.assertEqual(page.count('class="linkcode"'), 1)
        self.assertNotIn('acompte', page.lower())

    def test_shipping_ne_montre_que_mes_colis(self):
        from management.tests import vendeur_pour
        autre = vendeur_pour(self.vendeur.license, nom='Autre Shop')
        Article.objects.filter(pk=self.articles[0].pk).update(vendeur=autre)
        page = self.client.get('/management/vendeur_liste_colis/').content.decode()
        self.assertNotIn(self.articles[0].code, page)

    def test_nouvelle_commande_frais_annonces_egaux_aux_frais_factures(self):
        import json, re
        from core.models import FormatArticle, Localite
        page = self.client.get('/management/vendeur_edit_colis/').content.decode()
        self.assertIn('Deux filtres, un seul discours', page)
        self.assertNotIn('ML SHIP', page)
        grille = json.loads(re.search(r'<script id="grille" type="application/json">(.*?)</script>', page, re.S).group(1))
        bouake = Localite.objects.get(nom='Bouaké', license=self.vendeur.license)
        petit = FormatArticle.objects.filter(nom='Petit', license=self.vendeur.license).first()
        annonce = grille[str(bouake.pk)]['formats'][str(petit.pk)]['frais']
        self.assertEqual(annonce, 3481)
        reponse = self.client.post('/management/vendeur_edit_colis/', {
            'nom_destinataire': 'KONE', 'prenom_destinataire': 'Seydou', 'numero_principal_destinataire': '+2250707070707',
            'adresse_destinataire': 'Commerce, près de la pharmacie', 'localite_arrivee': bouake.pk, 'format_article': petit.pk,
            'designation': 'Montre', 'valeur': '15000', 'quantite': '2', 'produits': ['mode'],
            'is_option_recuperation': 'False', 'is_option_encaissement': 'True'})
        self.assertEqual(reponse.status_code, 302, reponse.content.decode()[:3000] if reponse.status_code != 302 else '')
        article = Article.objects.filter(vendeur=self.vendeur, designation='Montre').get()
        self.assertEqual(int(article.montant_frais), annonce)
        self.assertEqual(int(article.valeur_totale), 30000)

    def test_detail_colis_frise_et_prix_lisible_par_le_navigateur(self):
        # Le colis du parcours « retour » finit « Revenu à Abidjan » (avant le correctif du 18/11, il restait à tort « En retour »)
        a = Article.objects.filter(vendeur=self.vendeur, statut_traitement__in=(S.EN_RETOUR, S.REVENU_ABIDJAN)).first()
        Article.objects.filter(pk=a.pk).update(statut_traitement=S.REVENU_ABIDJAN, date_revenu_abidjan=timezone.now())
        page = self.client.get('/management/vendeur_detail_colis/%s/' % a.code).content.decode()
        self.assertIn('name="valeur" type="number" min="0" value="15000"', page)   # pas « 15 000 » : invalide dans un champ nombre
        self.assertIn('class="step fail"', page)
        page = self.client.get('/management/vendeur_detail_colis/%s/' % self.articles[-1].code).content.decode()  # en transit
        self.assertIn('à venir', page)

    def test_autres_ecrans_vendeur(self):
        for url in ('/management/vendeur_stock/', '/management/vendeur_profil/', '/management/vendeur_edit_profil/',
                    '/integrations/mes-integrations/', '/management/vendeur_liste_colis_reversement/', '/management/vendeur_releves/'):
            reponse = self.client.get(url)
            self.assertEqual(reponse.status_code, 200, url)
            page = reponse.content.decode()
            self.assertNotIn('acompte', page.lower(), url)
            self.assertNotIn('ML SHIP Africa', page, url)          # la marque vue par le vendeur est ML COD Intérieur
        page = self.client.get('/integrations/mes-integrations/').content.decode()
        from integrations.models import IntegrationVendeur
        cle = IntegrationVendeur.objects.get(vendeur=self.vendeur).cle_live
        self.assertIn(cle[:8] + '••••', page)                       # clé de production masquée à l'affichage
