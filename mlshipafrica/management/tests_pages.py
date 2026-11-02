"""Recette : chaque rôle ouvre chaque page, avec des colis dans tous les statuts. Aucune page ne doit renvoyer d'erreur 500."""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from management.models import Article, ProfilStaff
from management.tests import base_ancienne, vendeur_pour
from core.models import Localite
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R

PARCOURS = {
    'livre': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE],
    'echec': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.ECHEC_LIVRAISON],
    'reconduit': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT],
    'retour': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN],
    'retourne': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN, S.RETOURNE],
    'stock': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN, S.REMIS_EN_STOCK],
    'abime': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT, S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN, S.MIS_DE_COTE],
    'annule': [S.EN_ATTENTE_DEPOT, S.ANNULE],
    'ramassage': [S.EN_ATTENTE_RAMASSAGE],
    'transit': [S.EN_ATTENTE_DEPOT, S.DEPOT, S.EN_TRANSIT],
}

PAGES_STAFF = [
    '/', '/management/admin_liste_vendeurs/', '/management/admin_liste_colis/', '/management/admin_liste_colis_vendeurs/',
    '/management/admin_liste_paiements/', '/management/admin_liste_paiements_vendeurs/',
    '/management/admin_liste_reversements/', '/management/admin_liste_reversements_vendeurs/',
    '/management/admin_mouvements_colis/', '/management/admin_activites_paiements/',
    '/management/admin_activites_reversements/', '/management/admin_import_vendeur/',
    '/management/admin_confirmations/', '/management/admin_confirmations/?filtre=a_confirmer',
    '/management/admin_confirmations/?filtre=injoignable', '/management/admin_acomptes/', '/management/admin_stock/',
    '/management/admin_releves/', '/management/admin_benefice/', '/management/admin_benefice/?periode=semaine',
    '/management/admin_benefice/?periode=mois', '/management/admin_commissions/',
    '/management/admin_liste_paiements/?type_paiements=historique',
    '/management/admin_liste_reversements/?type_reversements=historique',
] + ['/management/admin_liste_colis/?type_colis=%s' % t for t in (
    'en_cours', 'a_sauver', S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.REVENU_ABIDJAN, S.ECHEC_LIVRAISON,
    S.ANNULE, S.RETOURNE, S.LIVRE)] + ['/management/admin_liste_vendeurs/?type_vendeur=%s' % t for t in (
    'attente_approbation', 'actif', 'inactif', 'supprime')] + ['/core/_liste/'] + [
    '/core/_liste/?param=%s' % p for p in ('licenses', 'configurations', 'formats_articles', 'zones', 'localites',
                                          'partenaires_logistiques', 'tarifications', 'profils_staff')] + [
    '/core/_new/?param=%s' % p for p in ('zones', 'localites', 'tarifications', 'profils_staff')]

PAGES_VENDEUR = ['/', '/management/vendeur_profil/', '/management/vendeur_edit_profil/', '/management/vendeur_edit_colis/',
                 '/management/vendeur_liste_colis/', '/management/vendeur_liste_colis_reversement/',
                 '/management/vendeur_releves/', '/management/vendeur_stock/', '/integrations/mes-integrations/',
                 '/integrations/api/v1/tarifs/']


@override_settings(DEBUG=False)
class RecettePages(TestCase):
    def setUp(self):
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.vendeur = vendeur_pour(license)
        self.vendeur.option_stockage = True
        self.vendeur.save()
        bouake = Localite.objects.get(nom='Bouaké')
        self.articles = []
        for nom, parcours in PARCOURS.items():
            a = Article(vendeur=self.vendeur, license=license, config=config, localite_depart=abidjan,
                        localite_arrivee=bouake, format_article=petit, valeur=15000, quantite=1,
                        is_option_encaissement=True)
            a.save()
            for statut in parcours:
                a.statut_traitement = statut
                a.save()
            self.articles.append(a)
        self.comptes = {}
        for role in R.values:
            u = User.objects.create(username='u-' + role, email=role + '@test.ci', is_staff=True)
            ProfilStaff.objects.create(user=u, license=license, role_profil=role)
            self.comptes[role] = u
        Article.objects.filter(pk=self.articles[0].pk).update(agent_cod=ProfilStaff.objects.get(role_profil=R.AGENT))
        for cmd in ('retours_quotidien', 'stockage_quotidien', 'releves_vendeurs'):
            try:
                call_command(cmd, stdout=StringIO())
            except Exception as e:  # noqa
                print('COMMANDE EN ERREUR', cmd, repr(e))

    def ouvrir(self, user, url, erreurs, vus):
        self.client.force_login(user)
        try:
            r = self.client.get(url)
            code = r.status_code
        except Exception as e:  # noqa
            erreurs.append('%s %s -> EXCEPTION %r' % (user.username, url, e))
            return
        vus.append(code)
        if code >= 500:
            erreurs.append('%s %s -> %s' % (user.username, url, code))

    def test_toutes_les_pages(self):
        erreurs, vus = [], []
        codes = [a.code for a in self.articles]
        detail_staff = ['/management/admin_detail_colis/%s/' % c for c in codes] + [
            '/management/admin_vendeur_profil/%s/' % self.vendeur.code,
            '/management/admin_vendeur_edit_profil/%s/' % self.vendeur.code]
        for role, user in self.comptes.items():
            for url in PAGES_STAFF + detail_staff:
                self.ouvrir(user, url, erreurs, vus)
        for url in PAGES_VENDEUR + ['/management/vendeur_detail_colis/%s/' % c for c in codes] + [
                '/management/vendeur_facture_colis/%s/' % c for c in codes] + [
                '/management/vendeur_substituer_colis/%s/' % c for c in codes]:
            self.ouvrir(self.vendeur.user, url, erreurs, vus)
        from collections import Counter
        print('\nPAGES OUVERTES :', len(vus), dict(Counter(vus)))
        print('\n'.join(erreurs) or 'AUCUNE ERREUR 500')
        self.assertEqual(erreurs, [])
