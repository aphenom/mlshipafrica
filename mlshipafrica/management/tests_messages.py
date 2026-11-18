"""Messages sur les commandes et les factures, cloche de notifications par rôle."""
from management import tests_pages
from management.models import Article, MessageColis, Notification, ProfilStaff, Releve
from management.statuts import appliquer_mouvement
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R


class MessagesEtCloche(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def colis(self, statut):
        return Article.objects.filter(vendeur=self.vendeur, statut_traitement=statut).first()

    def test_message_vendeur_vers_agent_puis_reponse(self):
        colis = self.colis(S.EN_TRANSIT)
        Article.objects.filter(pk=colis.pk).update(agent_cod=ProfilStaff.objects.get(role_profil=R.AGENT))
        self.client.force_login(self.vendeur.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/management/message/', {'article': colis.code, 'texte': 'Le client demande demain matin',
                                                      'retour': '/management/vendeur_detail_colis/%s/' % colis.code})
        agent = self.comptes[R.AGENT]
        self.assertTrue(Notification.objects.filter(destinataire=agent, type='message').exists())
        self.client.force_login(agent)
        page = self.client.get('/management/admin_detail_colis/%s/' % colis.code).content.decode()
        self.assertIn('Le client demande demain matin', page)
        self.assertIn('pastille', page)                                  # la cloche compte la notification
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/management/message/', {'article': colis.code, 'texte': 'Note : client difficile', 'interne': '1'})
            self.client.post('/management/message/', {'article': colis.code, 'texte': 'C’est noté, livraison demain'})
        self.assertEqual(Notification.objects.filter(destinataire=self.vendeur.user, type='message').count(), 1)
        self.client.force_login(self.vendeur.user)
        page = self.client.get('/management/vendeur_detail_colis/%s/' % colis.code).content.decode()
        self.assertIn('livraison demain', page)
        self.assertNotIn('client difficile', page)                       # la note interne reste dans l'équipe

    def test_un_vendeur_ne_peut_pas_ecrire_sur_la_commande_d_un_autre(self):
        from management.tests import vendeur_pour
        autre = vendeur_pour(self.vendeur.license, 'Autre')
        self.client.force_login(autre.user)
        r = self.client.post('/management/message/', {'article': self.articles[0].code, 'texte': 'x'})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(MessageColis.objects.exists())

    def test_mouvements_notifient_le_vendeur_et_l_equipe(self):
        colis = self.colis(S.ARRIVE) or self.colis(S.EN_TRANSIT)
        with self.captureOnCommitCallbacks(execute=True):
            appliquer_mouvement(colis, S.ECHEC_LIVRAISON if colis.statut_traitement == S.ARRIVE else S.ARRIVE, self.comptes[R.AGENT])
        colis.refresh_from_db()
        if colis.statut_traitement == S.ARRIVE:
            with self.captureOnCommitCallbacks(execute=True):
                appliquer_mouvement(colis, S.ECHEC_LIVRAISON, self.comptes[R.AGENT])
        self.assertTrue(Notification.objects.filter(destinataire=self.vendeur.user, titre__startswith='Échec').exists())
        self.assertTrue(Notification.objects.filter(destinataire=self.comptes[R.MANAGER], type='echec').exists())
        self.assertFalse(Notification.objects.filter(destinataire=self.comptes[R.COMMERCIAL]).exists())

    def test_contestation_d_une_facture(self):
        releve = Releve.objects.create(code='RL-C-1', vendeur=self.vendeur, date_arrete=self.vendeur.date_creation, net=1000)
        self.client.force_login(self.vendeur.user)
        page = self.client.get('/management/vendeur_releves/?facture=RL-C-1').content.decode()
        self.assertIn('Je conteste cette facture', page)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/management/message/', {'releve': 'RL-C-1', 'texte': 'Le colis X a été retourné', 'contester': '1'})
        releve.refresh_from_db()
        self.assertTrue(releve.contestation_ouverte)
        self.assertTrue(Notification.objects.filter(destinataire=self.comptes[R.COMPTABLE], type='contestation').exists())
        self.assertTrue(Notification.objects.filter(destinataire=self.comptes[R.SUPER], type='contestation').exists())
        self.client.force_login(self.comptes[R.COMPTABLE])
        page = self.client.get('/management/admin_releves/?etape=factures').content.decode()
        self.assertIn('contestée', page)
        self.client.post('/management/message/', {'releve': 'RL-C-1', 'texte': 'Corrigé', 'resolu': '1'})
        releve.refresh_from_db()
        self.assertFalse(releve.contestation_ouverte)

    def test_page_notifications_et_ouverture(self):
        n = Notification.objects.create(destinataire=self.vendeur.user, type='statut', titre='Colis livré', url='/management/vendeur_releves/')
        self.client.force_login(self.vendeur.user)
        self.assertIn('Colis livré', self.client.get('/management/notifications/').content.decode())
        r = self.client.get('/management/notifications/?ouvrir=%d' % n.pk)
        self.assertEqual(r['Location'], '/management/vendeur_releves/')
        n.refresh_from_db()
        self.assertTrue(n.lue)
