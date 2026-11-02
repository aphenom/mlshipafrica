"""Tests de fin de lot « Intégrations » : une commande Woura fait tout le parcours, chaque événement arrive une
seule fois chez Woura, un même webhook reçu deux fois ne crée qu'une commande, une signature fausse est rejetée,
le livreur déclaré est toujours « ML COD Intérieur »."""
import json
import time
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from core.models import Localite
from integrations.models import EvenementIntegration as E, IntegrationVendeur
from integrations.service import envoyer_file, signer
from management.models import Article, HistoriqueArticle
from management.tests import base_ancienne, vendeur_pour
from mlshipafrica.enums import StatutTraitement as S

SECRET = 'whsec_woura_test'


def evenement(eid='evt_1', boutique='WSHOP-9', ville='Bouaké'):
    return {'id': eid, 'type': 'shipment.assigned', 'data': {'shipment': {
        'id': 'shp_100', 'store_id': boutique, 'cod_amount': 17500, 'package_size': 'small',
        'recipient': {'name': 'Awa Koné', 'phone': '0708091011', 'city': ville, 'address': 'Quartier Commerce'},
        'items': [{'name': 'Montre', 'quantity': 1}]}}}


class WouraTests(TestCase):
    def setUp(self):
        license, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.vendeur = vendeur_pour(license)
        IntegrationVendeur.objects.create(vendeur=self.vendeur, woura_actif=True, woura_boutique_id='WSHOP-9')

    def poster(self, corps, secret=SECRET):
        brut = json.dumps(corps).encode()
        with mock.patch('integrations.service.config', side_effect=lambda k, default='': SECRET if k == 'WOURA_WEBHOOK_SECRET' else default):
            return self.client.post('/integrations/woura/webhook/', data=brut, content_type='application/json',
                                    HTTP_WOURA_SIGNATURE=signer(secret, brut))

    def test_signature_fausse_rejetee(self):
        self.assertEqual(self.poster(evenement(), secret='mauvais').status_code, 401)
        self.assertFalse(Article.objects.filter(source='woura').exists())

    def test_doublon_une_seule_commande(self):
        self.assertEqual(self.poster(evenement()).status_code, 200)
        self.assertEqual(self.poster(evenement()).status_code, 200)
        self.assertEqual(Article.objects.filter(source='woura').count(), 1)
        a = Article.objects.get(source='woura')
        self.assertEqual((a.reference_externe, a.statut_traitement, a.etat_confirmation, int(a.valeur_totale)),
                         ('shp_100', S.EN_ATTENTE_DEPOT, 'a_confirmer', 17500))

    def test_ville_inconnue_tracee(self):
        self.poster(evenement(eid='evt_2', ville='Paris'))
        ev = E.objects.get(identifiant='woura:in:evt_2')
        self.assertEqual(ev.statut, E.ECHEC)
        self.assertIn('Paris', ev.reponse)

    def test_parcours_complet_evenements_une_seule_fois(self):
        self.poster(evenement())
        a = Article.objects.get(source='woura')
        dernier = a.get_last_historique()
        for statut in (S.DEPOT, S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT, S.LIVRE_PAYE):
            with self.captureOnCommitCallbacks(execute=True):
                Article.objects.filter(pk=a.pk).update(statut_traitement=statut)
                dernier = HistoriqueArticle.objects.create(article=a, statut_traitement=statut, dernier_historique_article=dernier)
        envoyes = []

        def transport(ev):
            envoyes.append(ev.contenu)
            return 200, 'ok'
        envoyer_file(transport=transport)
        envoyer_file(transport=transport)                 # rejouer n'envoie rien de plus
        types = [c['event'] for c in envoyes]
        self.assertEqual(types, ['accepted', 'in_transit', 'in_transit', 'in_transit', 'failed', 'rescheduled', 'delivered'])
        self.assertTrue(all(c['rider_name'] == 'ML COD Intérieur' for c in envoyes))
        self.assertEqual(envoyes[-1]['delivery_fee'], int(a.montant_total_frais))
        self.assertTrue(all('cout' not in json.dumps(c) for c in envoyes))

    def test_reessai_puis_echec(self):
        self.poster(evenement())
        a = Article.objects.get(source='woura')
        with self.captureOnCommitCallbacks(execute=True):
            HistoriqueArticle.objects.create(article=a, statut_traitement=S.DEPOT, dernier_historique_article=a.get_last_historique())
        from django.utils import timezone
        from datetime import timedelta
        maintenant = timezone.now()
        for i in range(6):
            envoyer_file(transport=lambda ev: (503, 'indisponible'), maintenant=maintenant + timedelta(hours=6 * i))
        ev = E.objects.get(sens=E.SORTANT)
        self.assertEqual((ev.statut, ev.tentatives), (E.ECHEC, 5))


class ApiVendeurTests(TestCase):
    def setUp(self):
        license, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.vendeur = vendeur_pour(license)
        self.integration = IntegrationVendeur.objects.create(vendeur=self.vendeur, api_actif=True)

    def appel(self, methode, url, cle, corps=None):
        return getattr(self.client, methode)(url, data=json.dumps(corps) if corps else None, content_type='application/json',
                                             HTTP_AUTHORIZATION='Bearer ' + cle)

    def test_creer_lire_lister_tarifs(self):
        cle = self.integration.cle_live
        r = self.appel('post', '/integrations/api/v1/colis/', cle, {'reference': 'WC-1001', 'nom': 'Yao', 'telephone': '0505050505',
                                                                     'ville': 'Korhogo', 'montant': 12000})
        self.assertEqual(r.status_code, 201)
        code = r.json()['code']
        self.assertEqual(r.json()['frais_livraison'], 3481)
        self.assertEqual(self.appel('post', '/integrations/api/v1/colis/', cle, {'reference': 'WC-1001', 'telephone': '0505050505',
                                                                                  'ville': 'Korhogo', 'montant': 12000}).status_code, 200)
        self.assertEqual(Article.objects.filter(reference_externe='WC-1001').count(), 1)
        self.assertEqual(self.appel('get', '/integrations/api/v1/colis/%s/' % code, cle).json()['statut'], S.EN_ATTENTE_DEPOT)
        self.assertEqual(len(self.appel('get', '/integrations/api/v1/colis/', cle).json()['colis']), 1)
        tarifs = self.appel('get', '/integrations/api/v1/tarifs/', cle).json()
        self.assertEqual(len(tarifs['localites']), 275)
        self.assertNotIn('cout', json.dumps(tarifs))

    def test_cle_de_test_ne_part_jamais(self):
        r = self.appel('post', '/integrations/api/v1/colis/', self.integration.cle_test,
                       {'reference': 'T-1', 'telephone': '0505050505', 'ville': 'Bouaké', 'montant': 5000})
        self.assertTrue(r.json()['test'])
        self.assertEqual(Article.objects.get(reference_externe='test:T-1').statut_traitement, S.BROUILLON)

    def test_cle_invalide_et_ville_inconnue(self):
        self.assertEqual(self.appel('get', '/integrations/api/v1/colis/', 'mlc_live_faux').status_code, 401)
        r = self.appel('post', '/integrations/api/v1/colis/', self.integration.cle_live, {'reference': 'X', 'telephone': '0505050505', 'ville': 'Abidjan'})
        self.assertEqual(r.status_code, 422)

    def test_webhook_vendeur_signe(self):
        from integrations.service import verifier_signature
        self.integration.webhook_url = 'https://boutique.ci/hook'
        self.integration.save()
        r = self.appel('post', '/integrations/api/v1/colis/', self.integration.cle_live, {'reference': 'W-9', 'telephone': '0505050505', 'ville': 'Bouaké', 'montant': 9000})
        a = Article.objects.get(code=r.json()['code'])
        with self.captureOnCommitCallbacks(execute=True):
            HistoriqueArticle.objects.create(article=a, statut_traitement=S.DEPOT, dernier_historique_article=a.get_last_historique())
        appels = []

        def faux_post(url, corps, entetes, delai=15):
            appels.append((url, corps, entetes))
            return 200, 'ok'
        with mock.patch('integrations.service._post', side_effect=faux_post):
            envoyer_file()
        url, corps, entetes = appels[-1]
        self.assertEqual(url, 'https://boutique.ci/hook')
        self.assertTrue(verifier_signature(self.integration.webhook_secret, entetes['X-MLCOD-Signature'], corps))

    def test_page_vendeur(self):
        self.client.force_login(self.vendeur.user)
        self.assertEqual(self.client.get('/integrations/mes-integrations/').status_code, 200)
