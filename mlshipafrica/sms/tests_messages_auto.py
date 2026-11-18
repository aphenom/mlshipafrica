"""Messages automatiques réglés par le CEO : bienvenue, approbation, statuts, e-mails au vendeur, page de réglage."""
from django.core import mail

from management import tests_pages
from management.models import Article, Vendeur
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R
from sms.models import EmailAuto, SmsMessage, SmsModele


class MessagesAuto(tests_pages.RecettePages):
    test_toutes_les_pages = None

    def test_nouveaux_messages_desactives_au_deploiement(self):
        nouveaux = ('v_bienvenue', 'v_approuve', 'cl_transit', 'cl_en_livraison', 'cl_livre', 'v_recu', 'v_livre', 'v_facture', 'v_verse', 'v_stockage')
        self.assertFalse(SmsModele.objects.filter(cle__in=nouveaux, actif=True).exists())
        self.assertFalse(SmsModele.objects.filter(cle__in=nouveaux, email_actif=True).exists())
        self.assertTrue(SmsModele.objects.get(cle='cl_recu').actif)                   # l'existant ne change pas

    def test_bienvenue_puis_approbation_par_sms_et_email(self):
        from django.contrib.auth.models import User
        SmsModele.objects.filter(cle__in=('v_bienvenue', 'v_approuve')).update(actif=True, email_actif=True)
        u = User.objects.create(username='nouveau', email='nouveau@test.ci')
        with self.captureOnCommitCallbacks(execute=True):
            v = Vendeur.objects.create(user=u, nom_store='Boutique Neuve', license=self.vendeur.license,
                                       numero_sms='+2250707000099', etat_approbation=False)
        self.assertTrue(SmsMessage.objects.filter(modele_cle='v_bienvenue', vendeur=v).exists())
        self.assertIn("en cours d'approbation", SmsMessage.objects.get(modele_cle='v_bienvenue', vendeur=v).texte)
        self.assertEqual(mail.outbox[-1].to, ['nouveau@test.ci'])
        self.assertIn('Boutique Neuve', mail.outbox[-1].body)
        with self.captureOnCommitCallbacks(execute=True):
            v.etat_approbation = True
            v.save()
        self.assertTrue(SmsMessage.objects.filter(modele_cle='v_approuve', vendeur=v).exists())
        self.assertEqual(EmailAuto.objects.filter(vendeur=v, modele_cle='v_approuve').count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            v.save()                                                                  # pas de 2e message
        self.assertEqual(SmsMessage.objects.filter(modele_cle='v_approuve', vendeur=v).count(), 1)

    def test_le_ceo_regle_un_message_et_choisit_les_informations(self):
        self.client.force_login(self.comptes[R.SUPER])
        page = self.client.get('/sms/messages-automatiques/').content.decode()
        self.assertIn('Messages automatiques', page)
        self.assertIn('Nom du client', page)
        self.assertIn('Référence produit (SKU)', page)
        self.assertNotIn("ACME", page.upper())
        self.client.post('/sms/messages-automatiques/', {'cle': 'v_livre', 'actif': 'on', 'email_actif': 'on',
                                                         'texte': 'MLCOD : {ref} livre a {client}, {produit} ({sku}) {montant}',
                                                         'email_objet': 'Livré : {ref}', 'email_texte': 'Bonjour {vendeur}, {ref} livré à {client}.'})
        m = SmsModele.objects.get(cle='v_livre')
        self.assertTrue(m.actif and m.email_actif)
        colis = Article.objects.filter(vendeur=self.vendeur, statut_traitement=S.EN_COURS_LIVRAISON).first()
        if colis is None:
            colis = Article.objects.filter(vendeur=self.vendeur).first()
            Article.objects.filter(pk=colis.pk).update(statut_traitement=S.EN_COURS_LIVRAISON)
            colis.refresh_from_db()
        from management.statuts import appliquer_mouvement
        with self.captureOnCommitCallbacks(execute=True):
            ok, raison = appliquer_mouvement(colis, S.LIVRE, self.comptes[R.AGENT])
        self.assertTrue(ok, raison)
        sms = SmsMessage.objects.filter(modele_cle='v_livre', article=colis).first()
        self.assertIsNotNone(sms)
        self.assertIn(colis.code, sms.texte)
        self.assertNotIn('{', sms.texte)
        self.assertTrue(EmailAuto.objects.filter(modele_cle='v_livre').exists())
        # désactivé : rien ne part
        self.client.post('/sms/messages-automatiques/', {'cle': 'cl_livre', 'texte': 'x'})
        self.assertFalse(SmsModele.objects.get(cle='cl_livre').actif)
        self.assertFalse(SmsMessage.objects.filter(modele_cle='cl_livre').exists())

    def test_reserve_au_ceo(self):
        for role in (R.MANAGER, R.COMPTABLE, R.COMMERCIAL):
            self.client.force_login(self.comptes[role])
            self.assertNotEqual(self.client.get('/sms/messages-automatiques/').status_code, 200, role)
