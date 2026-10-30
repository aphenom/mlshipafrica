"""Tests du module SMS.    python manage.py test sms"""
import json
from datetime import datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Localite
from management.models import Article, HistoriqueArticle
from management.tests import base_ancienne, vendeur_pour
from mlshipafrica.enums import StatutTraitement as S
from sms.hsms import ClientHsms, ErreurHsms, extraire_tickets
from sms.models import SmsMessage, SmsModele, SmsParametres
from sms.service import appliquer_accuse, envoyer_file, mettre_en_file, prochaine_heure_autorisee
from sms.telephone import normaliser_ci
from sms.texte import montant_f, preparer

ABIDJAN = ZoneInfo('Africa/Abidjan')
MIDI = datetime(2026, 11, 2, 12, 0, tzinfo=ABIDJAN)  # lundi


class FauxClient:
    """Remplace HSMS : enregistre les envois, peut lever une erreur à la demande."""
    configure = True

    def __init__(self, erreurs=None):
        self.envois = []
        self.erreurs = list(erreurs or [])

    def envoyer(self, telephone, message, unicode=False):
        if self.erreurs:
            raise self.erreurs.pop(0)
        self.envois.append((telephone, message, unicode))
        return ['T%d' % len(self.envois)], {'success': True, 'ticket': 'T%d' % len(self.envois)}


class TexteEtNumeroTests(TestCase):
    def test_nettoyage_gsm7(self):
        texte, unicode, segments = preparer('Votre colis est arrivé à Bouaké’ — prêt ?')
        self.assertFalse(unicode)
        self.assertNotIn('’', texte)
        self.assertEqual(segments, 1)

    def test_montant(self):
        self.assertEqual(montant_f(12500), '12 500 F')

    def test_numeros(self):
        self.assertEqual(normaliser_ci('07 08 09 10 11')[0], '2250708091011')
        self.assertEqual(normaliser_ci('+225 05 01 02 03 04')[0], '2250501020304')
        self.assertIsNone(normaliser_ci('27 22 35 16 19')[0])      # fixe : pas de SMS
        self.assertIsNone(normaliser_ci('0708')[0])

    def test_tickets(self):
        self.assertEqual(extraire_tickets({'ticket': 'A1'}), ['A1'])
        self.assertEqual(extraire_tickets({'data': [{'ticket': 'A1'}, {'ticket': 'A2'}]}), ['A1', 'A2'])


class HeuresCalmesTests(TestCase):
    def test_nuit_reportee_a_7h(self):
        p = SmsParametres.charger()
        soir = datetime(2026, 11, 2, 22, 30, tzinfo=ABIDJAN)
        self.assertEqual(prochaine_heure_autorisee(soir, p), datetime(2026, 11, 3, 7, 0, tzinfo=ABIDJAN))
        matin = datetime(2026, 11, 3, 5, 0, tzinfo=ABIDJAN)
        self.assertEqual(prochaine_heure_autorisee(matin, p), datetime(2026, 11, 3, 7, 0, tzinfo=ABIDJAN))
        self.assertEqual(prochaine_heure_autorisee(MIDI, p), MIDI)


class DeclencheursTests(TestCase):
    def setUp(self):
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.vendeur = vendeur_pour(license)
        self.article = Article(vendeur=self.vendeur, license=license, config=config, localite_depart=abidjan,
                               localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=petit,
                               valeur=15000, quantite=1, is_option_encaissement=True,
                               numero_principal_destinataire='+2250708091011')
        self.article.save()
        self.dernier = None

    def mouvement(self, statut):
        with self.captureOnCommitCallbacks(execute=True):
            self.dernier = HistoriqueArticle.objects.create(article=self.article, statut_traitement=statut,
                                                            dernier_historique_article=self.dernier)
        return self.dernier

    def test_plan_valide(self):
        for statut in (S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE,
                       S.ECHEC_LIVRAISON, S.LIVRE_PAYE):
            self.mouvement(statut)
        cles = list(SmsMessage.objects.order_by('id').values_list('modele_cle', flat=True))
        self.assertEqual(cles, ['cl_recu', 'cl_arrive', 'cl_echec'])   # rien pour transit, livraison, livré
        recu = SmsMessage.objects.get(modele_cle='cl_recu')
        self.assertEqual(recu.destinataire, '2250708091011')
        self.assertIn('Melina Shop : commande confirmee. A payer a la livraison : 15 000 F', recu.texte)
        self.assertIn('Livraison prevue a Bouaké', recu.texte.replace('Bouake', 'Bouaké'))
        self.assertIn('27 22 35 16 19', recu.texte)
        self.assertNotIn('{', recu.texte)

    def test_echec_une_seule_fois(self):
        for statut in (S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON):
            self.mouvement(statut)
        self.mouvement(S.ECHEC_LIVRAISON)
        self.assertEqual(SmsMessage.objects.filter(modele_cle='cl_echec').count(), 1)

    def test_annulation_client_et_vendeur(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        self.mouvement(S.ANNULE)
        self.assertEqual(SmsMessage.objects.filter(modele_cle='cl_annule').count(), 1)
        vendeur = SmsMessage.objects.get(modele_cle='v_annule_av')
        self.assertEqual(vendeur.destinataire, '2250707000001')
        self.assertIn(self.article.code, vendeur.texte)

    def test_deja_paye(self):
        self.article.is_option_encaissement = False
        self.article.save()
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        self.assertIn('Deja payee, rien a regler', SmsMessage.objects.get(modele_cle='cl_recu').texte)

    def test_modele_desactive(self):
        SmsModele.objects.filter(cle='cl_recu').update(actif=False)
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        self.assertFalse(SmsMessage.objects.exists())

    def test_numero_invalide_trace_mais_pas_envoye(self):
        self.article.numero_principal_destinataire = '+22527223516 19'.replace(' ', '')
        self.article.save()
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        message = SmsMessage.objects.get(modele_cle='cl_recu')
        self.assertEqual(message.statut, SmsMessage.ECHEC)
        self.assertIn('Numéro refusé', message.erreur)

    def test_mouvement_annule_dans_l_admin_annule_le_sms(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        histo = self.mouvement(S.DEPOT)
        with self.captureOnCommitCallbacks(execute=True):
            histo.etat_suppression = True
            histo.save()
        self.assertEqual(SmsMessage.objects.get(modele_cle='cl_recu').statut, SmsMessage.ANNULE)


class EnvoiTests(TestCase):
    def setUp(self):
        p = SmsParametres.charger()
        p.actif = True
        p.save()

    def message(self, cle='m1', **kw):
        return mettre_en_file('cl_annule', '0708091011', {'boutique': 'Test', 'ref': 'A1'}, cle, maintenant=MIDI, **kw)

    def test_inactif_rien_ne_part(self):
        SmsParametres.objects.filter(pk=1).update(actif=False)
        self.message()
        client = FauxClient()
        envoyer_file(client=client, maintenant=MIDI)
        self.assertEqual(client.envois, [])
        self.assertEqual(SmsMessage.objects.get().statut, SmsMessage.EN_FILE)

    def test_envoi_et_dedoublonnage(self):
        self.assertIsNotNone(self.message())
        self.assertIsNone(self.message())               # même clé : refusé
        client = FauxClient()
        bilan = envoyer_file(client=client, maintenant=MIDI)
        self.assertEqual(bilan['envoyes'], 1)
        m = SmsMessage.objects.get()
        self.assertEqual((m.statut, m.ticket), (SmsMessage.ENVOYE, 'T1'))
        envoyer_file(client=client, maintenant=MIDI + timedelta(minutes=1))
        self.assertEqual(len(client.envois), 1)          # jamais renvoyé

    def test_panne_reseau_reessai_puis_abandon(self):
        self.message()
        client = FauxClient(erreurs=[ErreurHsms('coupure', 'reseau')] * 5)
        moment = MIDI
        for _ in range(5):
            envoyer_file(client=client, maintenant=moment)
            moment += timedelta(hours=2)
        m = SmsMessage.objects.get()
        self.assertEqual((m.statut, m.tentatives), (SmsMessage.ECHEC, 5))

    def test_solde_epuise_met_en_pause_sans_perdre_le_message(self):
        self.message('a')
        self.message('b')
        client = FauxClient(erreurs=[ErreurHsms('Solde insuffisant', 'solde_insuffisant')])
        bilan = envoyer_file(client=client, maintenant=MIDI)
        self.assertTrue(bilan['pause'])
        self.assertEqual(SmsMessage.objects.filter(statut=SmsMessage.EN_FILE, tentatives=0).count(), 2)
        self.assertTrue(envoyer_file(client=client, maintenant=MIDI + timedelta(minutes=5))['pause'])
        envoyer_file(client=client, maintenant=MIDI + timedelta(minutes=20))
        self.assertEqual(len(client.envois), 2)

    def test_numero_invalide_pas_de_reessai(self):
        self.message()
        envoyer_file(client=FauxClient(erreurs=[ErreurHsms('numero invalide', 'numero_invalide')]), maintenant=MIDI)
        self.assertEqual(SmsMessage.objects.get().statut, SmsMessage.ECHEC)

    def test_message_bloque_en_envoi_recupere(self):
        m = self.message()
        SmsMessage.objects.filter(pk=m.pk).update(statut=SmsMessage.ENVOI, verrou='x', date_verrou=MIDI - timedelta(hours=1))
        client = FauxClient()
        envoyer_file(client=client, maintenant=MIDI)
        self.assertEqual(len(client.envois), 1)

    def test_nuit_attend_7h(self):
        nuit = datetime(2026, 11, 2, 23, 0, tzinfo=ABIDJAN)
        mettre_en_file('cl_annule', '0708091011', {'boutique': 'T', 'ref': 'A'}, 'nuit', maintenant=nuit)
        client = FauxClient()
        envoyer_file(client=client, maintenant=nuit + timedelta(minutes=30))
        self.assertEqual(client.envois, [])
        envoyer_file(client=client, maintenant=datetime(2026, 11, 3, 7, 1, tzinfo=ABIDJAN))
        self.assertEqual(len(client.envois), 1)


class AccusesTests(TestCase):
    def setUp(self):
        SmsParametres.objects.filter(pk=1).update(actif=True)
        mettre_en_file('cl_annule', '0708091011', {'boutique': 'T', 'ref': 'A'}, 'k', maintenant=MIDI)
        envoyer_file(client=FauxClient(), maintenant=MIDI)

    def test_accuses_monotones(self):
        self.assertTrue(appliquer_accuse('T1', 2))
        self.assertTrue(appliquer_accuse('T1', 3))
        self.assertFalse(appliquer_accuse('T1', 2))            # en retard : ignoré
        self.assertEqual(SmsMessage.objects.get().statut, SmsMessage.DELIVRE)

    @override_settings(ROOT_URLCONF='mlshipafrica.urls')
    def test_webhook(self):
        with mock.patch('sms.views.config', return_value='s3cret'):
            mauvais = self.client.post(reverse('sms:sms_accuses_hsms', args=['faux']), data='{}', content_type='application/json')
            self.assertEqual(mauvais.status_code, 403)
            ok = self.client.post(reverse('sms:sms_accuses_hsms', args=['s3cret']),
                                  data=json.dumps({'ticket': 'T1', 'status': 5, 'status_label': 'Non délivré'}),
                                  content_type='application/json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(SmsMessage.objects.get().statut, SmsMessage.NON_DELIVRE)


class ClientHsmsTests(TestCase):
    def test_jeton_renouvele_sur_401(self):
        appels = []

        def transport(url, corps, entetes):
            appels.append(url.rsplit('/api', 1)[1])
            if url.endswith('/token/'):
                return 200, json.dumps({'token': 'J%d' % len(appels)})
            if entetes.get('Authorization') == 'Bearer ancien':
                return 401, '{}'
            return 200, json.dumps({'success': True, 'data': {'ticket': 'X9'}})

        memo = []
        c = ClientHsms('a@b.ci', 'p', 'id', 'sec', jeton='ancien', sur_nouveau_jeton=memo.append, transport=transport)
        tickets, _ = c.envoyer('2250708091011', 'test')
        self.assertEqual(tickets, ['X9'])
        self.assertEqual(appels, ['/envoi-sms', '/token/', '/envoi-sms'])
        self.assertEqual(len(memo), 1)

    def test_solde_insuffisant_classe(self):
        c = ClientHsms('a', 'p', 'i', 's', jeton='j',
                       transport=lambda u, c, e: (400, json.dumps({'success': False, 'message': 'Solde insuffisant'})))
        with self.assertRaises(ErreurHsms) as ctx:
            c.envoyer('2250708091011', 'x')
        self.assertTrue(ctx.exception.met_en_pause)
