"""Menu par rôle (maquette ML COD Plateforme) : chaque rôle ne voit que ses pages, et chaque lien du menu et des onglets s'ouvre."""
import re

from management import tests_pages
from mlshipafrica.enums import TypeProfilStaffChoice as R


def liens_de(page, bloc):
    trouve = re.search(r'<nav class="%s[^"]*"[^>]*>(.*?)</nav>' % bloc, page, re.S)
    if not trouve:
        return []
    return [l.replace('&amp;', '&') for l in re.findall(r'href="([^"]+)"', trouve.group(1)) if 'logout' not in l]


class MenuParRole(tests_pages.RecettePages):
    test_toutes_les_pages = None  # la recette complète tourne déjà dans tests_pages

    def toutes_les_adresses(self, user):
        """Liens du menu, puis onglets de chaque rubrique ouverte."""
        self.client.force_login(user)
        menu = liens_de(self.client.get('/').content.decode(), 'side')
        self.assertTrue(menu, 'menu absent pour %s' % user.username)
        adresses = list(menu)
        for url in menu:
            reponse = self.client.get(url)
            self.assertIn(reponse.status_code, (200, 302), '%s : %s → %s' % (user.username, url, reponse.status_code))
            adresses += [o for o in liens_de(reponse.content.decode(), 'ctabs') if o not in adresses]
        return adresses

    def test_chaque_lien_du_menu_et_des_onglets_s_ouvre(self):
        for user in list(self.comptes.values()) + [self.vendeur.user]:
            for url in self.toutes_les_adresses(user):
                code = self.client.get(url).status_code
                self.assertIn(code, (200, 302), '%s : %s → %s' % (user.username, url, code))

    def test_aucune_page_d_argent_pour_manager_agent_commercial(self):
        for role in (R.MANAGER, R.AGENT, R.COMMERCIAL):
            adresses = ' '.join(self.toutes_les_adresses(self.comptes[role]))
            for page in ('admin_benefice', 'admin_releves', 'admin_liste_paiements', 'admin_acomptes', 'admin_commissions'):
                self.assertNotIn(page, adresses, '%s voit %s' % (role, page))

    def test_rubrique_et_onglet_actifs(self):
        self.client.force_login(self.comptes[R.SUPER])
        page = self.client.get('/management/admin_liste_colis/?type_colis=a_sauver').content.decode()
        rubrique = re.findall(r'<a href="[^"]+" aria-current="page"><span>([^<]+)</span>', page)
        onglet = re.findall(r'<a href="([^"]+)" aria-selected="true">', page)
        self.assertEqual(rubrique, ['Shipping'])
        self.assertEqual(onglet, ['/management/admin_liste_colis/?type_colis=a_sauver'])
        # Une fiche de détail allume sa rubrique, sans onglet sélectionné
        page = self.client.get('/management/admin_detail_colis/%s/' % self.articles[0].code).content.decode()
        self.assertEqual(re.findall(r'aria-current="page"><span>([^<]+)</span>', page), ['Shipping'])
        self.assertNotIn('aria-selected="true"', page)
