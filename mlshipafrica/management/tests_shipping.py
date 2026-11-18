"""Shipping : statuts dans l'ordre logique, actions groupées, corrections, impressions, modification réservée au CEO."""
from decimal import Decimal

from management import tests_pages
from management.models import Article, Depart, HistoriqueArticle
from management.statuts import appliquer_mouvement, statuts_correction, statuts_suivants
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R



def texte_xlsx(contenu):
    """Contenu d'un export .xlsx → texte, une ligne par rangée (cellules séparées par ;)."""
    from management.fichier_prestataire import lire_xlsx
    return '\n'.join(';'.join('' if c is None else str(c) for c in l) for l in lire_xlsx(contenu)[0]['lignes'])

class Shipping(tests_pages.RecettePages):
    test_toutes_les_pages = None  # la recette complète tourne déjà dans tests_pages

    def colis(self, statut):
        return Article.objects.filter(vendeur=self.vendeur, statut_traitement=statut).first()

    def nouveau_depose(self):
        a = Article.objects.create(vendeur=self.vendeur, license=self.vendeur.license, config=self.articles[0].config,
                                   localite_depart=self.articles[0].localite_depart,
                                   localite_arrivee=self.articles[0].localite_arrivee,
                                   format_article=self.articles[0].format_article, valeur=15000, quantite=1,
                                   is_option_encaissement=True)
        for statut in (S.EN_ATTENTE_DEPOT, S.DEPOT):
            a.statut_traitement = statut
            a.save()
        return Article.objects.get(pk=a.pk)

    def test_ordre_logique_et_sauts_vers_l_avant(self):
        transit = self.colis(S.EN_TRANSIT)
        agent = self.comptes[R.AGENT]
        suivants = [s for s, _ in statuts_suivants(transit, transit.get_last_historique(), agent)]
        self.assertEqual(suivants, [S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE, S.EN_RETOUR])
        self.assertNotIn(S.LIVRE_PAYE, suivants)

    def test_saut_depuis_depose_enregistre_le_depart(self):
        colis = self.nouveau_depose()
        with self.captureOnCommitCallbacks(execute=True):
            ok, raison = appliquer_mouvement(colis, S.ARRIVE, self.comptes[R.MANAGER], "parti hier")
        self.assertTrue(ok, raison)
        statuts = list(colis.article_historiquearticles.order_by('date_creation').values_list('statut_traitement', flat=True))
        self.assertEqual(statuts[-2:], [S.EN_TRANSIT, S.ARRIVE])         # l'étape « En transit » est gardée
        self.assertTrue(Depart.objects.filter(article=colis).exists())     # le coût du transport est figé

    def test_colis_sans_historique_peut_avancer(self):
        transit = self.colis(S.EN_TRANSIT)
        HistoriqueArticle.objects.filter(article=transit).update(etat_suppression=True)   # colis repris par import, sans historique
        transit = Article.objects.get(pk=transit.pk)
        ok, raison = appliquer_mouvement(transit, S.ARRIVE, self.comptes[R.AGENT])
        self.assertTrue(ok, raison)
        self.client.force_login(self.comptes[R.AGENT])
        self.assertEqual(self.client.get('/management/admin_detail_colis/%s/' % transit.code).status_code, 200)

    def test_actions_groupees_agent(self):
        transit = self.colis(S.EN_TRANSIT)
        livre = self.colis(S.LIVRE)
        self.client.force_login(self.comptes[R.AGENT])
        r = self.client.post('/management/admin_colis_actions/', {'action': 'avancer', 'statut': S.ARRIVE,
                                                                 'codes': [transit.code, livre.code]}, follow=True)
        transit.refresh_from_db()
        livre.refresh_from_db()
        self.assertEqual(transit.statut_traitement, S.ARRIVE)
        self.assertEqual(livre.statut_traitement, S.LIVRE)                 # le circuit refuse : laissé tel quel
        page = r.content.decode()
        self.assertIn('1 colis passé', page)
        self.assertIn('non modifié', page)
        # l'agent ne pose ni Unpaid ni correction
        self.assertEqual(self.client.post('/management/admin_colis_actions/', {'action': 'unpaid', 'codes': [livre.code]}).status_code, 403)
        self.assertEqual(self.client.post('/management/admin_colis_actions/', {'action': 'corriger', 'statut': S.ARRIVE,
                                                                               'commentaire': 'x', 'codes': [livre.code]}).status_code, 403)

    def test_unpaid_par_la_comptable_sur_toute_la_selection_filtree(self):
        livre = self.colis(S.LIVRE)
        self.client.force_login(self.comptes[R.COMPTABLE])
        page = self.client.get('/management/admin_liste_colis/?statut=livre').content.decode()
        self.assertIn('Passer en Unpaid', page)
        self.assertNotIn('Appliquer</button>', page)                       # pas de mouvement de transport
        self.client.post('/management/admin_colis_actions/', {'action': 'unpaid', 'tous': '1', 'filtres': 'statut=livre'})
        livre.refresh_from_db()
        self.assertEqual(livre.statut_traitement, S.LIVRE_PAYE)
        self.assertTrue(livre.etat_encaissement)

    def test_correction_manager_avec_raison(self):
        livre = self.colis(S.LIVRE)
        self.client.force_login(self.comptes[R.MANAGER])
        self.client.post('/management/admin_colis_actions/', {'action': 'corriger', 'statut': S.ECHEC_LIVRAISON,
                                                              'commentaire': '', 'codes': [livre.code]})
        livre.refresh_from_db()
        self.assertEqual(livre.statut_traitement, S.LIVRE)                 # raison obligatoire
        self.client.post('/management/admin_colis_actions/', {'action': 'corriger', 'statut': S.ECHEC_LIVRAISON,
                                                              'commentaire': 'Livré par erreur', 'codes': [livre.code]})
        livre.refresh_from_db()
        self.assertEqual(livre.statut_traitement, S.ECHEC_LIVRAISON)
        self.assertEqual(livre.get_last_historique().commentaire, 'Correction : Livré par erreur')
        # un colis Unpaid ne se corrige que par le CEO
        livre.statut_traitement = S.LIVRE_PAYE
        livre.save()
        self.assertEqual(statuts_correction(livre, self.comptes[R.MANAGER]), [])
        self.assertTrue(statuts_correction(livre, self.comptes[R.SUPER]))

    def test_filtre_par_statut(self):
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_liste_colis/?statut=en_transit').content.decode()
        self.assertIn(self.colis(S.EN_TRANSIT).code, page)
        self.assertNotIn(self.colis(S.LIVRE).code, page)

    def test_impressions_sans_argent_ni_prestataire(self):
        codes = [a.code for a in Article.objects.filter(vendeur=self.vendeur)[:4]]
        self.client.force_login(self.comptes[R.MANAGER])
        for doc in ('feuille_route', 'preparation', 'etiquettes', 'factures'):
            r = self.client.post('/management/admin_colis_imprimer/', {'doc': doc, 'codes': codes})
            self.assertEqual(r.status_code, 200, doc)
            page = r.content.decode()
            self.assertIn(codes[0], page)
            self.assertIn('ML COD Intérieur', page)
            self.assertNotIn('Frais ML', page)
        export = self.client.post('/management/admin_colis_imprimer/', {'doc': 'export', 'codes': codes})
        contenu = texte_xlsx(export.content)
        self.assertIn(codes[0], contenu)
        self.assertNotIn('Frais ML', contenu)                              # le manager ne voit pas l'argent
        self.client.force_login(self.comptes[R.SUPER])
        export = self.client.post('/management/admin_colis_imprimer/', {'doc': 'export', 'codes': codes})
        self.assertIn('Frais ML', texte_xlsx(export.content))

    def test_seul_le_ceo_modifie_la_commande(self):
        colis = self.colis(S.EN_TRANSIT)
        url = '/management/admin_detail_colis/%s/' % colis.code
        self.client.force_login(self.comptes[R.MANAGER])
        self.assertNotIn('Modifier la commande', self.client.get(url).content.decode())
        self.assertEqual(self.client.post(url, {'submit_modifier_commande': '1', 'nom_destinataire': 'X'}).status_code, 403)
        self.client.force_login(self.comptes[R.SUPER])
        self.assertIn('Modifier la commande', self.client.get(url).content.decode())
        self.client.post(url, {'submit_modifier_commande': '1', 'nom_destinataire': 'Koné', 'valeur_totale': '20000', 'quantite': '1'})
        colis.refresh_from_db()
        self.assertEqual(colis.nom_destinataire, 'Koné')
        self.assertEqual(colis.valeur_totale, Decimal('20000'))
        self.assertEqual(colis.cout_option_encaissement, Decimal('1000'))  # 5 % de 20 000

    def test_detail_avancer_et_corriger(self):
        transit = self.colis(S.EN_TRANSIT)
        url = '/management/admin_detail_colis/%s/' % transit.code
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get(url).content.decode()
        self.assertIn('Corriger le statut', page)
        self.client.post(url, {'submit_new_mouvement': '1', 'mouvement_statut': S.ARRIVE,
                               'last_mouvement': transit.get_last_historique().pk, 'mouvement_date': '',
                               'mouvement_commentaire': ''})
        transit.refresh_from_db()
        self.assertEqual(transit.statut_traitement, S.ARRIVE)

    def test_manager_exporte_toute_la_liste_filtree(self):
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_liste_colis/?type_colis=en_cours').content.decode()
        self.assertIn('Exporter les', page)
        self.assertNotIn('Fichier du prestataire', page)                             # retiré du menu du manager
        r = self.client.post('/management/admin_colis_imprimer/', {'doc': 'export', 'tous': '1', 'filtres': 'type_colis=en_cours'})
        self.assertIn('spreadsheetml', r['Content-Type'])
        lignes = texte_xlsx(r.content).splitlines()
        self.assertTrue(lignes[0].startswith('Commande;'))
        self.assertNotIn('Frais ML', lignes[0])

    def test_manager_corrige_le_format_a_la_reception(self):
        from core.models import FormatArticle
        from management.models import MessageColis, Notification, Tarification
        colis = self.nouveau_depose()
        grand = FormatArticle.objects.create(license=colis.license, nom='Grand test')
        t = colis.tarification
        t.pk, t.format_article, t.montant_frais = None, grand, (colis.montant_frais or 0) + 2000
        t.save()
        avant = colis.montant_frais
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.get('/management/admin_detail_colis/%s/' % colis.code).content.decode()
        self.assertIn('Format vérifié au bureau', page)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/management/admin_colis_actions/', {'action': 'format', 'format': grand.pk, 'codes': [colis.code],
                                                                 'commentaire': 'carton 60 cm'})
        colis.refresh_from_db()
        self.assertEqual(colis.format_article, grand)
        self.assertEqual(colis.montant_frais, avant + 2000)                          # tarif du bon format
        msg = MessageColis.objects.get(article=colis)
        self.assertIn('Grand test', msg.texte)
        self.assertFalse(msg.interne)                                                # le vendeur le voit
        self.assertTrue(Notification.objects.filter(destinataire=self.vendeur.user, titre__startswith='Format corrigé').exists())
        # parti : le manager ne peut plus
        en_route = self.colis(S.EN_TRANSIT)
        if en_route:
            from management.actions_colis import corriger_format
            ok, _ = corriger_format(en_route, grand, self.comptes[R.MANAGER])
            self.assertFalse(ok)
        self.client.force_login(self.comptes[R.AGENT])
        self.assertNotIn('Format vérifié au bureau', self.client.get('/management/admin_detail_colis/%s/' % colis.code).content.decode())

    def test_etiquette_acheminement_paye_ou_zero(self):
        from management.models import Acompte
        paye, rien = self.nouveau_depose(), self.nouveau_depose()
        Acompte.objects.create(article=paye, montant=2000, reseau='wave', reference_depot='T-1', statut='recu', license=paye.license)
        self.client.force_login(self.comptes[R.MANAGER])
        page = self.client.post('/management/admin_colis_imprimer/', {'doc': 'etiquettes', 'codes': [paye.code, rien.code]}).content.decode()
        self.assertIn('PAYÉ · Wave', page)
        self.assertIn('Acheminement 0 F', page)
        facture = self.client.post('/management/admin_colis_imprimer/', {'doc': 'factures', 'codes': [paye.code]}).content.decode()
        self.assertIn('FAC-%s' % paye.code, facture)
        route = self.client.post('/management/admin_colis_imprimer/', {'doc': 'feuille_route', 'codes': [paye.code, rien.code]}).content.decode()
        self.assertIn('FEUILLE DE ROUTE', route)
        for retire in ('Signature client', 'LIVRÉ'):
            self.assertNotIn(retire, route)
        self.assertIn('<th>Ville</th>', route)
        self.assertIn('PAYÉ</span>', route)                                       # colonne acompte : payé…
        self.assertIn('tagp zero">0 F', route)                                     # … ou 0 F

    def test_qr_codes_generes_par_le_serveur(self):
        colis = self.nouveau_depose()
        self.client.force_login(self.comptes[R.MANAGER])
        for doc in ('etiquettes', 'factures', 'feuille_route'):
            page = self.client.post('/management/admin_colis_imprimer/', {'doc': doc, 'codes': [colis.code]}).content.decode()
            self.assertIn('<svg', page, doc)
            self.assertNotIn('cdnjs', page, doc)                                      # plus de dépendance externe
        from management.qrcode_svg import matrice
        self.assertEqual(len(matrice(colis.code)), 21)                                # version 1 pour un code colis
