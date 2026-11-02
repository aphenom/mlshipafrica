"""
Tests du lot « zones, tarifs, statuts ».    python manage.py test management sms
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import Configuration, FormatArticle, License, Localite, Zone
from management.grille_ml_cod import LOCALITES, TARIFS_ML
from management.models import Article, HistoriqueArticle, Tarification, Vendeur
from management.statuts import statuts_suivants, transition_autorisee
from mlshipafrica.enums import StatutTraitement as S


def base_ancienne():
    """Reproduit la base actuelle (seed_tarifs) : zones 1 à 5 ancienne numérotation, Zone A Abidjan."""
    license = License.objects.create()
    config = Configuration.objects.create(app_nom='ML COD', license=license, monnaie='FCFA')
    zone_a = Zone.objects.create(nom='Zone A', is_depart=True, is_arrivee=True, license=license)
    abidjan = Localite.objects.create(nom='Abidjan', is_depart=True, is_arrivee=True, zone=zone_a, license=license)
    z1 = Zone.objects.create(nom='Zone 1', is_depart=False, is_arrivee=True, license=license)
    z2 = Zone.objects.create(nom='Zone 2', is_depart=False, is_arrivee=True, license=license)
    for nom, zone in (('Grand Lahou', z1), ('Bouaké', z2), ('Odiénné', z2), ('Andé', z2), ('Zouan-Houien', z2)):
        Localite.objects.create(nom=nom, is_depart=False, is_arrivee=True, zone=zone, license=license)
    petit = FormatArticle.objects.create(nom='Petit', license=license)
    moyen = FormatArticle.objects.create(nom='Moyen', license=license)
    grand = FormatArticle.objects.create(nom='Grand', license=license)
    for zone, fmt, montant in ((z1, petit, 3234), (z1, moyen, 4851), (z2, petit, 3381), (z2, grand, 20250)):
        Tarification.objects.create(localite_depart=abidjan, zone_depart=zone_a, zone_arrivee=zone, format_article=fmt,
                                    montant_frais=montant, config=config, license=license)
    return license, config, abidjan, petit, moyen, grand


def vendeur_pour(license, nom='Melina Shop'):
    user = User.objects.create(username='v-%s' % nom, email='%s@test.ci' % nom.replace(' ', ''))
    return Vendeur.objects.create(user=user, nom_store=nom, license=license, numero_sms='+2250707000001',
                                  etat_approbation=True, collecte_par_mlship=True)


class GrilleMlCodTests(TestCase):
    def setUp(self):
        self.license, self.config, self.abidjan, self.petit, self.moyen, self.grand = base_ancienne()

    def appliquer(self, *args):
        sortie = StringIO()
        call_command('appliquer_grille_ml_cod', *args, stdout=sortie)
        return sortie.getvalue()

    def test_dry_run_n_ecrit_rien(self):
        avant = (Zone.objects.count(), Localite.objects.count(), Tarification.objects.count())
        self.appliquer('--dry-run')
        self.assertEqual(avant, (Zone.objects.count(), Localite.objects.count(), Tarification.objects.count()))
        self.assertFalse(Zone.objects.filter(numero__isnull=False).exists())

    def test_applique_zones_localites_tarifs(self):
        import json, tempfile
        couts = {str(z): {'Petit': 1000 + z, 'Moyen': 2000 + z} for z in range(2, 7)}
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(couts, f)
        self.appliquer('--couts', f.name)
        zones = {z.numero: z for z in Zone.objects.filter(numero__isnull=False)}
        self.assertEqual(sorted(zones), [2, 3, 4, 5, 6])
        self.assertEqual(zones[2].get_delai_display(), 'J+2 à J+3')
        self.assertEqual(zones[6].get_delai_display(), 'J+3 à J+4')
        # 275 localités officielles d'arrivée, rattachées à la bonne zone
        officielles = Localite.objects.filter(is_arrivee=True, zone__numero__isnull=False)
        self.assertEqual(officielles.count(), sum(len(v) for v in LOCALITES.values()))
        self.assertEqual(Localite.objects.get(nom='Bouaké').zone.numero, 3)
        self.assertEqual(Localite.objects.get(nom='Grand-Lahou').zone.numero, 4)       # « Grand Lahou » reconnu
        self.assertEqual(Localite.objects.get(nom='Zouan-Hounien').zone.numero, 3)     # faute d'orthographe corrigée
        self.assertEqual(Localite.objects.filter(nom__in=['Odienné', 'Odiénné']).count(), 1)
        self.assertFalse(Localite.objects.get(nom='Andé').is_arrivee)                  # hors liste officielle
        self.assertTrue(Localite.objects.get(nom='Abidjan').is_depart)                 # départ intact
        # Tarifs : prix ML + coût partenaire, Grand non ouvert
        for numero, prix in TARIFS_ML.items():
            for nom_format, montant in prix.items():
                t = Tarification.objects.get(zone_arrivee=zones[numero], format_article__nom=nom_format, etat_validation=True)
                self.assertEqual(t.montant_frais, montant)
                self.assertEqual(t.cout_partenaire, couts[str(numero)][nom_format])
        self.assertFalse(Tarification.objects.filter(etat_validation=True, zone_arrivee__numero__isnull=True,
                                                     zone_arrivee__is_depart=False).exists())
        self.assertFalse(Zone.objects.filter(nom='Zone 1', etat_validation=True).exists())

    def test_rejouable_sans_doublon(self):
        self.appliquer()
        compte = (Zone.objects.count(), Localite.objects.count(), Tarification.objects.count())
        sortie = self.appliquer()
        self.assertEqual(compte, (Zone.objects.count(), Localite.objects.count(), Tarification.objects.count()))
        self.assertIn('Tarifs créés : 0', sortie)

    def test_sans_fichier_les_couts_existants_sont_gardes(self):
        self.appliquer()
        t = Tarification.objects.filter(zone_arrivee__numero=3, format_article__nom='Petit', etat_validation=True).get()
        t.cout_partenaire = 1234
        t.save()
        sortie = self.appliquer()
        t.refresh_from_db()
        self.assertEqual(t.cout_partenaire, 1234)
        self.assertIn('Tarifs sans coût partenaire', sortie)

    def test_tarifs_vendeur_listes_a_revoir_sans_modification(self):
        vendeur = vendeur_pour(self.license)
        special = Tarification.objects.create(vendeur=vendeur, montant_frais=2000, license=self.license)
        sortie = self.appliquer()
        special.refresh_from_db()
        self.assertTrue(special.etat_validation)
        self.assertIn('À REVOIR', sortie)

    def test_colis_prend_le_nouveau_tarif(self):
        self.appliquer()
        vendeur = vendeur_pour(self.license)
        article = Article(vendeur=vendeur, license=self.license, config=self.config, localite_depart=self.abidjan,
                          localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=self.petit,
                          valeur=15000, quantite=1, is_option_encaissement=True)
        article.save()
        self.assertEqual(article.montant_frais, 3481)
        self.assertEqual(article.montant_a_reverser, 15000 - 3481)

    def test_sans_tarif_message_clair(self):
        self.appliquer()
        vendeur = vendeur_pour(self.license)
        article = Article(vendeur=vendeur, license=self.license, config=self.config, localite_depart=self.abidjan,
                          localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=self.grand,
                          valeur=15000, quantite=1)
        with self.assertRaises(ValidationError):
            article.save()


class StatutsTests(TestCase):
    def setUp(self):
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.article = Article(vendeur=vendeur_pour(license), license=license, config=config, localite_depart=abidjan,
                               localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=petit,
                               valeur=10000, quantite=1, is_option_encaissement=True)
        self.article.save()
        self.dernier = None

    def mouvement(self, statut):
        self.dernier = HistoriqueArticle.objects.create(article=self.article, statut_traitement=statut,
                                                        dernier_historique_article=self.dernier)
        return self.dernier

    def suivants(self):
        return [s for s, _ in statuts_suivants(self.article, self.dernier)]

    def test_parcours_normal_et_echec(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.assertEqual(self.suivants(), [S.DEPOT, S.ANNULE])        # pas de ramassage : option non choisie
        for statut in (S.DEPOT, S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE):
            self.assertTrue(transition_autorisee(self.article, self.dernier, statut))
            self.mouvement(statut)
        self.assertIn(S.ECHEC_LIVRAISON, self.suivants())
        self.assertNotIn(S.LIVRE, self.suivants())                    # encaissement → « Livré et payé »
        self.mouvement(S.ECHEC_LIVRAISON)
        self.assertEqual(self.suivants(), [S.LIVRE_PAYE, S.EN_RETOUR])

    def test_annulation_impossible_apres_expedition(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        self.mouvement(S.EN_TRANSIT)
        self.assertFalse(transition_autorisee(self.article, self.dernier, S.ANNULE))

    def test_relance_apres_annulation(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.mouvement(S.DEPOT)
        self.mouvement(S.ANNULE)
        self.assertEqual(self.suivants(), [S.DEPOT])                  # le colis est chez nous : il reprend « Déposé »

    def test_statut_inconnu_refuse(self):
        self.mouvement(S.EN_ATTENTE_DEPOT)
        self.assertFalse(transition_autorisee(self.article, self.dernier, S.LIVRE_PAYE))
        self.assertFalse(transition_autorisee(self.article, self.dernier, 'nimporte_quoi'))


class ChargeListesTests(TestCase):
    """1 000 colis par jour : le nombre de requêtes d'une liste ne doit pas grandir avec le nombre de colis."""

    def setUp(self):
        from management.models import ProfilStaff
        from mlshipafrica.enums import TypeProfilStaffChoice
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.license, self.config, self.abidjan, self.petit = license, config, abidjan, petit
        staff = User.objects.create(username='agent', email='agent@test.ci', is_staff=True)
        ProfilStaff.objects.create(user=staff, license=license, role_profil=TypeProfilStaffChoice.MANAGER)
        self.staff = staff
        self.bouake = Localite.objects.get(nom='Bouaké')
        self.vendeurs = [vendeur_pour(license, 'Boutique %d' % i) for i in range(5)]

    def creer_colis(self, n):
        for i in range(n):
            a = Article(vendeur=self.vendeurs[i % 5], license=self.license, config=self.config, localite_depart=self.abidjan,
                        localite_arrivee=self.bouake, format_article=self.petit, valeur=10000, quantite=1)
            a.save()
            Article.objects.filter(pk=a.pk).update(statut_traitement=S.EN_TRANSIT)

    def requetes_liste(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.client.force_login(self.staff)
        with CaptureQueriesContext(connection) as ctx:
            reponse = self.client.get('/management/admin_liste_colis/?type_colis=en_cours')
        self.assertEqual(reponse.status_code, 200)
        return len(ctx.captured_queries)

    def test_requetes_constantes(self):
        self.creer_colis(10)
        petit_volume = self.requetes_liste()
        self.creer_colis(490)
        self.assertEqual(self.requetes_liste(), petit_volume)


class RolesEtDroitsTests(TestCase):
    """Chaque rôle n'ouvre que ses pages ; l'argent de la société n'est visible que du CEO et de la comptable."""

    def setUp(self):
        from management.models import ProfilStaff
        from mlshipafrica.enums import TypeProfilStaffChoice as R
        license, config, abidjan, petit, *_ = base_ancienne()
        call_command('appliquer_grille_ml_cod', stdout=StringIO())
        self.vendeur = vendeur_pour(license)
        self.article = Article(vendeur=self.vendeur, license=license, config=config, localite_depart=abidjan,
                               localite_arrivee=Localite.objects.get(nom='Bouaké'), format_article=petit,
                               valeur=15000, quantite=1, is_option_encaissement=True)
        self.article.save()
        self.article.statut_traitement = S.EN_ATTENTE_DEPOT
        self.article.save()  # sans utilisateur connecté : l'historique est créé automatiquement
        self.comptes = {}
        for role in R.values:
            u = User.objects.create(username='u-' + role, email=role + '@test.ci', is_staff=True)
            ProfilStaff.objects.create(user=u, license=license, role_profil=role)
            self.comptes[role] = u

    def statut(self, role, url, methode='get', donnees=None):
        self.client.force_login(self.comptes[role])
        reponse = getattr(self.client, methode)(url, donnees or {})
        return reponse.status_code

    def test_matrice_des_pages(self):
        attendus = {
            '/management/admin_liste_colis/?type_colis=en_cours': {'super', 'comptable', 'manager', 'agent'},
            '/management/admin_liste_paiements/': {'super', 'comptable'},
            '/management/admin_liste_reversements/': {'super', 'comptable'},
            '/management/admin_activites_paiements/': {'super', 'comptable'},
            '/management/admin_mouvements_colis/': {'super', 'comptable', 'manager'},
            '/management/admin_liste_vendeurs/': {'super', 'comptable', 'commercial', 'manager'},
            '/core/_liste/?param=tarifications': {'super'},
            '/core/_liste/?param=partenaires_logistiques': {'super'},
            '/core/_liste/?param=zones': {'super', 'administrateur'},
        }
        for url, autorises in attendus.items():
            for role in self.comptes:
                code = self.statut(role, url)
                if role in autorises:
                    self.assertEqual(code, 200, '%s doit ouvrir %s' % (role, url))
                else:
                    self.assertEqual(code, 403, '%s ne doit pas ouvrir %s' % (role, url))

    def test_argent_invisible_pour_agent_et_manager(self):
        url = '/management/admin_detail_colis/%s/' % self.article.code
        frais = '{:,}'.format(int(self.article.montant_total_frais)).replace(',', ' ')
        for role in ('agent', 'manager'):
            self.client.force_login(self.comptes[role])
            page = self.client.get(url).content.decode()
            self.assertNotIn('Total frais de service', page)
            self.assertNotIn('Comptabilité', page)
            self.assertNotIn(str(int(self.article.montant_total_frais)), page)
        self.client.force_login(self.comptes['comptable'])
        self.assertIn('Total frais de service', self.client.get(url).content.decode())

    def test_agent_ne_peut_pas_payer_ni_annuler(self):
        url = '/management/admin_detail_colis/%s/' % self.article.code
        dernier = self.article.get_last_historique()
        self.assertEqual(self.statut('agent', url, 'post', {'submit_new_reglement': '1', 'paiement_montant': '0',
                                                             'paiement_reduction': '0'}), 403)
        self.assertEqual(self.statut('agent', url, 'post', {'submit_annuler_last_mouvement': '1',
                                                             'last_mouvement': str(dernier.pk)}), 403)
        self.assertEqual(self.statut('commercial', url, 'post', {'submit_new_mouvement': '1'}), 403)

    def test_agent_fait_avancer_un_colis(self):
        url = '/management/admin_detail_colis/%s/' % self.article.code
        dernier = self.article.get_last_historique()
        self.statut('agent', url, 'post', {'submit_new_mouvement': '1', 'last_mouvement': str(dernier.pk),
                                           'mouvement_statut': S.DEPOT, 'mouvement_date': '2026-11-02 10:00',
                                           'mouvement_commentaire': '', 'mouvement_code_tracking': ''})
        self.article.refresh_from_db()
        self.assertEqual(self.article.statut_traitement, S.DEPOT)

    def test_transition_interdite_refusee_par_le_serveur(self):
        url = '/management/admin_detail_colis/%s/' % self.article.code
        dernier = self.article.get_last_historique()
        self.statut('super', url, 'post', {'submit_new_mouvement': '1', 'last_mouvement': str(dernier.pk),
                                           'mouvement_statut': S.LIVRE_PAYE, 'mouvement_date': '2026-11-02 10:00',
                                           'mouvement_commentaire': '', 'mouvement_code_tracking': ''})
        self.article.refresh_from_db()
        self.assertEqual(self.article.statut_traitement, S.EN_ATTENTE_DEPOT)

    def test_commercial_ne_voit_que_ses_vendeurs(self):
        from management.models import Vendeur
        autre = vendeur_pour(self.vendeur.license, 'Autre Boutique')
        Vendeur.objects.filter(pk=self.vendeur.pk).update(commercial=self.comptes['commercial'].account_profil_staff)
        Vendeur.objects.filter(pk=autre.pk).update(commercial=None)  # approuvé, suivi par personne
        self.client.force_login(self.comptes['commercial'])
        self.assertEqual(self.client.get('/management/admin_vendeur_profil/%s/' % self.vendeur.code).status_code, 200)
        self.assertEqual(self.client.get('/management/admin_vendeur_profil/%s/' % autre.code).status_code, 404)

    def test_admin_technique_ne_peut_pas_nommer_un_ceo(self):
        from django_currentuser.middleware import _set_current_user
        from management.forms import ProfilStaffForm
        _set_current_user(self.comptes['administrateur'])
        try:
            form = ProfilStaffForm(data={'email': 'x@test.ci', 'role_profil': 'super'})
            self.assertFalse(form.is_valid())
        finally:
            _set_current_user(None)

    def test_journal_d_audit(self):
        from core.models import JournalAudit
        t = Tarification.objects.filter(etat_validation=True).first()
        t.montant_frais = 9999
        t.save()
        ligne = JournalAudit.objects.filter(modele='Tarification', objet_id=str(t.pk), action='modification').latest('date')
        self.assertEqual(int(ligne.apres['montant_frais']), 9999)
        self.assertTrue(JournalAudit.objects.filter(modele='Article', objet_code=self.article.code).exists())

    def test_tableau_de_bord_sans_argent_hors_direction(self):
        for role in self.comptes:
            self.client.force_login(self.comptes[role])
            page = self.client.get('/').content.decode()
            if role in ('super', 'comptable'):
                self.assertIn('Paiements (', page)
            else:
                self.assertNotIn('Paiements (', page, role)
                self.assertNotIn('Reversements (', page, role)
