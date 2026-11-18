"""
Menu latéral, rôle par rôle, comme dans la maquette ML COD Plateforme.

Une entrée du menu est une rubrique (« Shipping », « Finance »…). Ses pages s'affichent en onglets au-dessus
du contenu, comme dans la maquette. Chaque page porte le droit qui l'ouvre (mlshipafrica/droits.py) : une page
dont le rôle n'a pas le droit n'apparaît ni dans le menu ni dans les onglets, et reste de toute façon
protégée côté serveur par @droit_requis. Le gabarit ne fait qu'afficher ce qui est calculé ici.
"""
from django.urls import NoReverseMatch, reverse

from mlshipafrica.droits import droits_de, profil_staff_de
from mlshipafrica.enums import StatutTraitement as S, StatutVendeur as V, TypeProfilStaffChoice as R

M = 'management:management_'


def _p(libelle, nom_url, droit=None, **params):
    """Une page : vue, paramètres d'URL qui la distinguent, droit requis."""
    return {'libelle': libelle, 'url_name': nom_url, 'droit': droit, 'params': params}


def _r(libelle, pages, aussi=()):
    """Une rubrique du menu : ses pages (onglets) et les vues de détail qui l'allument aussi."""
    return {'libelle': libelle, 'pages': pages, 'aussi': tuple(aussi)}


# ----------------------------------------------------------------------------------------- pages de l'équipe

TABLEAU = [_p('Tableau de bord', 'index')]
COLIS = 'colis_voir'
RECEPTION = [_p('En attente de dépôt', M + 'admin_liste_colis', COLIS, type_colis=S.EN_ATTENTE_DEPOT),
             _p('En attente de ramassage', M + 'admin_liste_colis', COLIS, type_colis=S.EN_ATTENTE_RAMASSAGE)]
EN_ROUTE = [_p('En cours', M + 'admin_liste_colis', COLIS, type_colis='en_cours'),
            _p('À sauver (48 h)', M + 'admin_liste_colis', COLIS, type_colis='a_sauver'),
            _p('Échecs', M + 'admin_liste_colis', COLIS, type_colis=S.ECHEC_LIVRAISON),
            _p('Annulés', M + 'admin_liste_colis', COLIS, type_colis=S.ANNULE),
            _p('Livrés', M + 'admin_liste_colis', COLIS, type_colis=S.LIVRE)]
RETOURS = [_p('Revenus à Abidjan', M + 'admin_liste_colis', COLIS, type_colis=S.REVENU_ABIDJAN),
           _p('Retournés', M + 'admin_liste_colis', COLIS, type_colis=S.RETOURNE)]
DETAIL_COLIS = (M + 'admin_detail_colis', M + 'admin_liste_colis_vendeurs')
APPELS = [_p('Commandes à appeler', M + 'admin_confirmations', 'confirmations')]
VENDEURS = [_p('Demandes de collaboration', M + 'admin_liste_vendeurs', 'vendeurs_voir', type_vendeur=V.ATTENTE_APPROBATION),
            _p('Actifs', M + 'admin_liste_vendeurs', 'vendeurs_voir', type_vendeur=V.ACTIF),
            _p('Inactifs', M + 'admin_liste_vendeurs', 'vendeurs_voir', type_vendeur=V.INACTIF),
            _p('Supprimés', M + 'admin_liste_vendeurs', 'vendeurs_supprimer', type_vendeur=V.SUPPRIME)]
FICHE_VENDEUR = (M + 'admin_vendeur_profil', M + 'admin_vendeur_edit_profil')
STOCK = [_p('Stock et produits', M + 'admin_stock', 'stock')]
PRESTATAIRE = [_p('Fichier du prestataire', M + 'admin_fichier_prestataire', 'prestataire')]
MOUVEMENTS = [_p('Mouvements des colis', M + 'admin_mouvements_colis', 'activites_colis')]
FRAIS = [_p('Frais à régler', M + 'admin_liste_paiements', 'paiements', type_paiements='en_attente'),
         _p('Par vendeur', M + 'admin_liste_paiements_vendeurs', 'paiements'),
         _p('Historique', M + 'admin_liste_paiements', 'paiements', type_paiements='historique')]
REVERSEMENTS = [_p('Reversements à faire', M + 'admin_liste_reversements', 'paiements', type_reversements='en_attente'),
                _p('Par vendeur', M + 'admin_liste_reversements_vendeurs', 'paiements'),
                _p('Historique', M + 'admin_liste_reversements', 'paiements', type_reversements='historique')]
RELEVES = [_p('Paiements vendeurs', M + 'admin_releves', 'releves')]
FACTURE_PAIEMENT = (M + 'facture_paiement',)
REGLAGES = [_p('Frais et réglages', M + 'admin_reglages_frais', 'parametres_configuration')]
MOYENS = [_p('Moyens de paiement', M + 'admin_moyens_versement', 'moyens_versement')]
# Ancien circuit (colis par colis) : seulement l'historique, pour consultation. Les vendeurs sont payés par les factures de paiement.
ANCIENS_PAIEMENTS = [_p('Anciens frais réglés', M + 'admin_liste_paiements', 'paiements', type_paiements='historique'),
                     _p('Anciens reversements', M + 'admin_liste_reversements', 'paiements', type_reversements='historique')]
ACOMPTES = [_p('Acomptes clients', M + 'admin_acomptes', 'acomptes')]
BENEFICE = [_p('Journal et bénéfice', M + 'admin_benefice', 'benefice')]
COMMISSIONS = [_p('Commissions', M + 'admin_commissions', 'commissions_voir')]
JOURNAUX_ARGENT = [_p('Journal des paiements', M + 'admin_activites_paiements', 'activites_argent'),
                   _p('Journal des reversements', M + 'admin_activites_reversements', 'activites_argent')]
PARAMETRES = [_p('Zones et tarifs', 'core:core_zones_tarifs', 'parametres_tarifs'),
              _p('Tarifs', 'core:core_liste', 'parametres_tarifs', param='tarifications'),
              _p('Zones', 'core:core_liste', 'parametres', param='zones'),
              _p('Localités', 'core:core_liste', 'parametres', param='localites'),
              _p('Formats', 'core:core_liste', 'parametres', param='formats_articles'),
              _p('Partenaires', 'core:core_liste', 'parametres_partenaires', param='partenaires_logistiques'),
              _p('Configuration', 'core:core_liste', 'parametres_configuration', param='configurations'),
              _p('Utilisateurs', 'core:core_liste', 'parametres_comptes', param='profils_staff'),
              _p('Licence', 'core:core_liste', 'licenses', param='licenses'),
              _p('Importer des vendeurs', M + 'admin_import_vendeur', 'vendeurs_importer')]
FICHE_PARAMETRE = ('core:core_new', 'core:core_edit')

# Rubriques et libellés de la maquette (MENUS), avec les pages qui existent déjà côté serveur.
MENUS_EQUIPE = {
    R.AGENT: [
        _r('Mes commandes à appeler', APPELS),
        _r('Shipping', EN_ROUTE + RECEPTION + RETOURS, DETAIL_COLIS),
    ],
    R.MANAGER: [
        _r('Tableau de bord', TABLEAU),
        _r('Réception des colis', RECEPTION),
        _r('Retours', RETOURS),
        _r('Shipping', EN_ROUTE, DETAIL_COLIS),
        _r('Agents COD', APPELS),
        _r('Vendeurs', VENDEURS, FICHE_VENDEUR),
        _r('Stock et produits', STOCK),
        _r('Fichier du prestataire', PRESTATAIRE),
        _r('Mouvements des colis', MOUVEMENTS),
    ],
    R.COMPTABLE: [
        _r('Aujourd’hui', TABLEAU),
        _r('Shipping', EN_ROUTE + RECEPTION + RETOURS, DETAIL_COLIS),
        _r('Paiements vendeurs', RELEVES + MOYENS + ACOMPTES + ANCIENS_PAIEMENTS, FACTURE_PAIEMENT),
        _r('Contrôle prestataire', PRESTATAIRE),
        _r('Rapports', BENEFICE + COMMISSIONS + JOURNAUX_ARGENT + MOUVEMENTS),
        _r('Vendeurs', VENDEURS, FICHE_VENDEUR),
    ],
    R.COMMERCIAL: [
        _r('Tableau de bord', TABLEAU),
        _r('Demandes de collaboration', VENDEURS[:1], FICHE_VENDEUR),
        _r('Mes vendeurs', VENDEURS[1:]),
    ],
    R.SUPER: [
        _r('Tableau de bord', TABLEAU),
        _r('Finance', BENEFICE + ACOMPTES + COMMISSIONS),
        _r('Paiements', RELEVES + MOYENS + ANCIENS_PAIEMENTS + JOURNAUX_ARGENT, FACTURE_PAIEMENT),
        _r('Prestataire', PRESTATAIRE),
        _r('Commercial', VENDEURS, FICHE_VENDEUR),
        _r('Shipping', APPELS + EN_ROUTE + RECEPTION + RETOURS + STOCK + MOUVEMENTS, DETAIL_COLIS),
        _r('Paramètres', REGLAGES + PARAMETRES, FICHE_PARAMETRE),
    ],
    R.ADMINISTRATEUR: [
        _r('Tableau de bord', TABLEAU),
        _r('Paramètres', PARAMETRES, FICHE_PARAMETRE),
    ],
}


def _menu_vendeur(vendeur):
    """Groupes du menu vendeur de la maquette : Accueil, Commandes, Stock, Argent, Compte."""
    if not vendeur.etat_approbation:
        return [('Accueil', [_r('Tableau de bord', TABLEAU)]),
                ('Compte', [_r('Compléter mon profil', [_p('Compléter mon profil', M + 'vendeur_edit_profil')])])]
    groupes = [
        ('Accueil', [_r('Tableau de bord', TABLEAU)]),
        ('Commandes', [_r('Nouvelle commande', [_p('Nouvelle commande', M + 'vendeur_edit_colis')]),
                       _r('Shipping', [_p('Shipping', M + 'vendeur_liste_colis')],
                          (M + 'vendeur_detail_colis', M + 'vendeur_facture_colis', M + 'vendeur_substituer_colis'))]),
    ]
    if vendeur.option_stockage:
        groupes.append(('Stock', [_r('Mon stock', [_p('Mon stock', M + 'vendeur_stock')])]))
    groupes += [
        ('Argent', [_r('Mon argent', [_p('Mes factures de paiement', M + 'vendeur_releves'),
                                      _p('Anciens reversements', M + 'vendeur_liste_colis_reversement')],
                       (M + 'facture_paiement',))]),
        ('Compte', [_r('Intégrations', [_p('Intégrations', 'integrations:vendeur_integrations')]),
                    _r('Paramètres', [_p('Mon profil', M + 'vendeur_profil'), _p('Numéro de paiement', M + 'vendeur_paiement')],
                       (M + 'vendeur_edit_profil',))]),
    ]
    return groupes


def _url(page):
    try:
        url = reverse(page['url_name'])
    except NoReverseMatch:
        return None
    if page['params']:
        url += '?' + '&'.join('%s=%s' % (k, v) for k, v in page['params'].items())
    return url


def _vue(request):
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return None
    return '%s:%s' % (match.namespace, match.url_name) if match.namespace else match.url_name


def _score(page, vue, request):
    """Page ouverte : même vue et tous ses paramètres présents. La plus précise gagne (−1 : pas elle)."""
    if vue != page['url_name'] or any(request.GET.get(k) != str(v) for k, v in page['params'].items()):
        return -1
    return 10 + len(page['params'])


def menu_de(request):
    """
    → {'espace': libellé du rôle,
       'groupes': [{'titre', 'entrees': [{'libelle', 'url', 'actif'}]}],
       'onglets': [{'libelle', 'url', 'actif'}] de la rubrique ouverte (vide s'il n'y a qu'une page)}
    """
    user = request.user
    if not user.is_authenticated:
        return None
    profil = profil_staff_de(user)
    vendeur = getattr(user, 'account_vendeur', None) if profil is None else None
    if profil is not None:
        espace = R(profil.role_profil).label if profil.role_profil in R.values else 'Équipe'
        groupes_bruts = [(espace, MENUS_EQUIPE.get(profil.role_profil, [_r('Tableau de bord', TABLEAU)]))]
        droits = droits_de(user)
    elif vendeur is not None:
        espace, groupes_bruts, droits = 'Vendeur', _menu_vendeur(vendeur), None
    else:
        return None

    vue = _vue(request)
    groupes, meilleure = [], (0, None, None)
    for titre, rubriques in groupes_bruts:
        entrees = []
        for rubrique in rubriques:
            onglets = []
            for page in rubrique['pages']:
                if droits is not None and page['droit'] and page['droit'] not in droits:
                    continue
                url = _url(page)
                if url is None:
                    continue
                onglets.append({'libelle': page['libelle'], 'url': url, 'actif': False, '_score': _score(page, vue, request)})
            if not onglets:
                continue
            entree = {'libelle': rubrique['libelle'], 'url': onglets[0]['url'], 'actif': False, 'onglets': onglets}
            entrees.append(entree)
            score = max(o['_score'] for o in onglets)
            if score < 0 and vue in rubrique['aussi']:
                score = 1
            if score > meilleure[0]:
                meilleure = (score, entree, max(onglets, key=lambda o: o['_score']))
        if entrees:
            groupes.append({'titre': titre, 'entrees': entrees})

    onglets = []
    _, entree, onglet = meilleure
    if entree is not None:
        entree['actif'] = True
        if onglet['_score'] >= 0:
            onglet['actif'] = True
        if len(entree['onglets']) > 1:
            onglets = entree['onglets']
    return {'espace': espace, 'groupes': groupes, 'onglets': onglets}
