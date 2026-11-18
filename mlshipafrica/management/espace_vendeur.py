"""
Espace vendeur de la maquette ML COD Plateforme : chiffres du tableau de bord et filtres de Shipping.

Le vendeur ne voit que ses propres colis et ses propres montants (jamais l'acompte, jamais un coût interne).
« À recevoir » vient des mêmes écritures que les relevés : le tableau de bord et Mon argent tombent juste.
"""
from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from management.finance import totaux
from management.models import Article, Ecriture, ProduitStock, Releve
from mlshipafrica.enums import StatutReleve, StatutTraitement as S, TypeEcriture, array_statut_traitement_livre

LIVRES = list(array_statut_traitement_livre)
# Échecs comptés dans le taux de livraison : le colis est parti et n'a pas été livré.
# « Annulé avant expédition » n'en fait pas partie : le colis n'a jamais quitté Abidjan.
ECHECS = [S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN, S.RETOURNE, S.REMIS_EN_STOCK, S.MIS_DE_COTE, S.ABANDONNE]
OBJECTIF = 80
SEUIL_SURVEILLANCE = 75


def taux(livres, echecs):
    return round(livres * 100 / (livres + echecs)) if livres + echecs else None


def niveau(t):
    """→ (libellé, classe du badge) pour un taux de livraison, comme dans la maquette."""
    if t is None:
        return 'En cours', 'b-mute'
    if t >= OBJECTIF:
        return 'Bonne', 'b-ok'
    if t >= SEUIL_SURVEILLANCE:
        return 'À surveiller', 'b-warn'
    return 'Faible', 'b-bad'


def periode(request, jours=30):
    """Dates du filtre « Du … au … » (30 derniers jours par défaut) → (du, au, début, fin) ; fin exclue."""
    aujourdhui = timezone.localdate()
    try:
        au = datetime.strptime(request.GET.get('au', ''), '%Y-%m-%d').date()
    except ValueError:
        au = aujourdhui
    try:
        du = datetime.strptime(request.GET.get('du', ''), '%Y-%m-%d').date()
    except ValueError:
        du = au - timedelta(days=jours - 1)
    if du > au:
        du, au = au, du
    debut = timezone.make_aware(datetime.combine(du, time.min))
    fin = timezone.make_aware(datetime.combine(au + timedelta(days=1), time.min))
    return du, au, debut, fin


def colis_du_vendeur(vendeur):
    return Article.objects.filter(vendeur=vendeur, etat_suppression=False)


def a_recevoir(vendeur):
    """Relevés pas encore versés + écritures pas encore relevées (livrés en attente du prochain relevé)."""
    releves = Releve.objects.filter(vendeur=vendeur, statut=StatutReleve.A_VERSER).aggregate(t=Sum('net'))['t'] or 0
    en_attente = Ecriture.objects.filter(vendeur=vendeur, releve__isnull=True).exclude(type=TypeEcriture.COUT_PRESTATAIRE)
    return releves + totaux(en_attente)['net']


def tableau_de_bord(vendeur, debut, fin, filtre_villes='all'):
    tous = colis_du_vendeur(vendeur).exclude(statut_traitement=S.BROUILLON)
    sur_periode = tous.filter(date_creation__gte=debut, date_creation__lt=fin)
    c = sur_periode.aggregate(
        total=Count('id'),
        livres=Count('id', filter=Q(statut_traitement__in=LIVRES)),
        echecs=Count('id', filter=Q(statut_traitement__in=ECHECS)),
        en_cours=Count('id', filter=~Q(statut_traitement__in=LIVRES + ECHECS + [S.ANNULE])),
    )
    t = taux(c['livres'], c['echecs'])
    maintenant = tous.aggregate(
        echec=Count('id', filter=Q(statut_traitement=S.ECHEC_LIVRAISON)),
        revenus=Count('id', filter=Q(statut_traitement=S.REVENU_ABIDJAN)),
        ramassage=Count('id', filter=Q(statut_traitement=S.EN_ATTENTE_RAMASSAGE)),
        depot=Count('id', filter=Q(statut_traitement=S.EN_ATTENTE_DEPOT)),
    )
    brouillons = colis_du_vendeur(vendeur).filter(statut_traitement=S.BROUILLON).count()
    argent = a_recevoir(vendeur)
    # Montants de la période choisie (date de livraison ou de retour) : ils suivent le filtre de dates
    argent_periode = totaux(Ecriture.objects.filter(vendeur=vendeur, date__gte=debut, date__lt=fin)
                            .exclude(type=TypeEcriture.COUT_PRESTATAIRE))

    stock = None
    if vendeur.option_stockage:
        produits = ProduitStock.objects.filter(vendeur=vendeur, actif=True)
        epuises = [p for p in produits if p.quantite_disponible <= 0]
        stock = {'pieces': sum(max(p.quantite_disponible, 0) for p in produits), 'epuises': epuises}

    # À faire : ce qui demande une action du vendeur, le plus urgent d'abord
    a_faire = []
    if maintenant['echec']:
        a_faire.append(('t-bad', '%d commande(s) en échec de livraison' % maintenant['echec'],
                        'Le client n’a pas été livré : donnez une consigne à ML COD Intérieur (nouvelle tentative ou retour).',
                        'shipping', S.ECHEC_LIVRAISON, 'Voir les échecs'))
    if maintenant['revenus']:
        a_faire.append(('t-bad', '%d colis revenu(s) à Abidjan' % maintenant['revenus'],
                        'Donnez un nouveau client ou venez le reprendre : la garde de 500 F par jour démarre à J11.',
                        'shipping', S.REVENU_ABIDJAN, 'Voir les colis'))
    if maintenant['ramassage']:
        a_faire.append(('t-warn', '%d commande(s) en attente de ramassage' % maintenant['ramassage'],
                        'ML COD Intérieur passe les récupérer : gardez-les emballées avec l’étiquette.',
                        'shipping', S.EN_ATTENTE_RAMASSAGE, 'Voir la liste'))
    if maintenant['depot']:
        a_faire.append(('t-warn', '%d commande(s) en attente de dépôt' % maintenant['depot'],
                        'Déposez-les au bureau ML COD Intérieur avec leur bordereau.',
                        'shipping', S.EN_ATTENTE_DEPOT, 'Voir la liste'))
    if brouillons:
        a_faire.append(('t-warn', '%d commande(s) en brouillon' % brouillons,
                        'Elles ne partiront pas tant qu’elles ne sont pas validées.',
                        'shipping', S.BROUILLON, 'Les terminer'))
    if stock and stock['epuises']:
        a_faire.append(('t-warn', '%d produit(s) épuisé(s)' % len(stock['epuises']),
                        ' · '.join(p.designation for p in stock['epuises'][:5]), 'stock', '', 'Réapprovisionner'))
    if argent > 0:
        a_faire.append(('t-ok', None, 'Livrés, en attente de votre prochaine facture de paiement (lundi ou jeudi).', 'argent', '', 'Voir mon argent'))

    # Taux par ville : le vendeur comparé à la moyenne du réseau dans la même ville, sur la même période
    par_ville = list(sur_periode.values('localite_arrivee__nom').annotate(
        n=Count('id'), l=Count('id', filter=Q(statut_traitement__in=LIVRES)),
        e=Count('id', filter=Q(statut_traitement__in=ECHECS))))
    noms = [v['localite_arrivee__nom'] for v in par_ville if v['localite_arrivee__nom']]
    reseau = {r['localite_arrivee__nom']: taux(r['l'], r['e']) for r in Article.objects.filter(
        license=vendeur.license, etat_suppression=False, date_creation__gte=debut, date_creation__lt=fin,
        localite_arrivee__nom__in=noms).values('localite_arrivee__nom').annotate(
        l=Count('id', filter=Q(statut_traitement__in=LIVRES)), e=Count('id', filter=Q(statut_traitement__in=ECHECS)))}
    villes = []
    for v in par_ville:
        tv = taux(v['l'], v['e'])
        lib, cls = niveau(tv)
        villes.append({'nom': v['localite_arrivee__nom'] or 'Ville inconnue', 'n': v['n'], 'taux': tv,
                       'reseau': reseau.get(v['localite_arrivee__nom']), 'niveau': lib, 'classe': cls})
    villes.sort(key=lambda v: (v['taux'] is None, -(v['taux'] or 0), v['nom']))
    garder = {'good': 'Bonne', 'watch': 'À surveiller', 'low': 'Faible'}.get(filtre_villes)
    if garder:
        villes = [v for v in villes if v['niveau'] == garder]

    return {'commandes': c['total'], 'en_cours': c['en_cours'], 'livres': c['livres'], 'echecs': c['echecs'],
            'taux': t, 'taux_classe': 't-ok' if t is not None and t >= OBJECTIF else 't-warn' if t is not None and t >= SEUIL_SURVEILLANCE else 't-bad' if t is not None else '',
            'a_recevoir': argent, 'argent_periode': argent_periode, 'stock': stock, 'a_faire': a_faire, 'villes': villes, 'filtre_villes': filtre_villes}


# ----------------------------------------------------------------------------------------- Shipping

def shipping(vendeur, etape='', ville='', recherche='', debut=None, fin=None):
    """Colis du vendeur filtrés comme dans la maquette, avec le compte par statut pour les puces."""
    tous = colis_du_vendeur(vendeur)
    if debut is not None:
        tous = tous.filter(date_creation__gte=debut, date_creation__lt=fin)
    if ville:
        tous = tous.filter(localite_arrivee__nom=ville)
    if recherche:
        mots = Q()
        for champ in ('code', 'code_tracking', 'nom_destinataire', 'prenom_destinataire', 'numero_principal_destinataire',
                      'designation', 'reference_externe'):
            mots |= Q(**{champ + '__icontains': recherche})
        tous = tous.filter(mots)
    comptes = dict(tous.values_list('statut_traitement').annotate(n=Count('id')))
    puces = [{'cle': '', 'libelle': 'Toutes', 'n': sum(comptes.values()), 'classe': ''}] + [
        {'cle': valeur, 'libelle': libelle, 'n': comptes[valeur], 'classe': 'st'}
        for valeur, libelle in S.choices if comptes.get(valeur)]
    liste = tous.filter(statut_traitement=etape) if etape else tous
    return liste.select_related('localite_arrivee', 'zone_arrivee', 'produit_stock').order_by('-date_creation'), puces


# ----------------------------------------------------------------------------------------- Nouvelle commande

def _priorite(tarif):
    """Même ordre que Article.save : order_by('-vendeur', '-format_article', '-localite_arrivee', '-zone_depart',
    '-zone_arrivee') ; en MySQL un tri décroissant met les valeurs vides en dernier."""
    return tuple((1, 0) if x is None else (0, -x) for x in (
        tarif.vendeur_id, tarif.format_article_id, tarif.localite_arrivee_id, tarif.zone_depart_id, tarif.zone_arrivee_id))


def grille_vendeur(vendeur, localite_depart, localites, formats):
    """
    Frais que le serveur facturera, pour chaque destination et chaque format proposés au vendeur :
    {localite_id: {'zone', 'delai', 'formats': {format_id: {'frais', 'enc_cout', 'enc_taux', 'rec_cout', 'rec_taux'}}}}.
    Une seule requête sur les tarifs ; le choix suit exactement Article.save (le formulaire reste la référence).
    Seuls les tarifs ML du vendeur : jamais le coût du partenaire.
    """
    from management.models import Tarification
    tarifs = list(Tarification.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False)
                  .filter(Q(vendeur=vendeur) | Q(vendeur__isnull=True)).select_related('config'))
    zone_depart = localite_depart.zone_id if localite_depart else None
    depart = localite_depart.pk if localite_depart else None
    from management.finance import taux_collecte
    taux_global = float(taux_collecte(vendeur.license))   # frais de collecte : un seul taux, réglé par le CEO
    grille = {}
    for loc in localites:
        par_format = {}
        for fmt in formats:
            possibles = [t for t in tarifs
                         if t.localite_depart_id in (depart, None) and t.localite_arrivee_id in (loc.pk, None)
                         and t.zone_depart_id in (zone_depart, None) and t.zone_arrivee_id in (loc.zone_id, None)
                         and t.format_article_id in (fmt.pk, None)]
            if not possibles:
                continue
            t = min(possibles, key=_priorite)
            par_format[fmt.pk] = {
                'frais': int(t.montant_frais or 0),
                'enc_cout': 0,
                'enc_taux': taux_global,
                'rec_cout': int(t.get_final_cout_option_recuperation() or 0) if t.config_id else int(t.cout_option_recuperation or 0),
                'rec_taux': float(t.get_final_taux_option_recuperation() or 0) if t.config_id else float(t.taux_option_recuperation or 0),
            }
        grille[loc.pk] = {'nom': loc.nom, 'zone': loc.zone.nom if loc.zone_id else '',
                          'delai': loc.zone.get_delai_display() if loc.zone_id else '', 'formats': par_format}
    return grille


def taux_par_ville(vendeur, jours=90):
    """Taux de livraison du vendeur et du réseau par ville, sur les 90 derniers jours (note sous la ville choisie)."""
    depuis = timezone.now() - timedelta(days=jours)
    def calcul(qs):
        return {r['localite_arrivee']: taux(r['l'], r['e']) for r in qs.filter(date_creation__gte=depuis)
                .values('localite_arrivee').annotate(l=Count('id', filter=Q(statut_traitement__in=LIVRES)),
                                                     e=Count('id', filter=Q(statut_traitement__in=ECHECS)))}
    return {'vendeur': calcul(colis_du_vendeur(vendeur)),
            'reseau': calcul(Article.objects.filter(license=vendeur.license, etat_suppression=False))}


def etapes_a_venir(article):
    """Étapes qui restent sur le parcours normal (attente → reçu → transit → arrivé → livraison → livré → versé)."""
    parcours = [S.EN_ATTENTE_RAMASSAGE if article.is_option_recuperation else S.EN_ATTENTE_DEPOT,
                S.RAMASSE if article.is_option_recuperation else S.DEPOT,
                S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE, S.LIVRE_PAYE, S.PAYE, S.REVERSE]
    if article.statut_traitement not in parcours:
        return []
    return [S(s).label for s in parcours[parcours.index(article.statut_traitement) + 1:]]


def prochain_releve(maintenant=None):
    """Prochain relevé : lundi ou jeudi à 6 h (tâche releves_vendeurs)."""
    maintenant = timezone.localtime(maintenant or timezone.now())
    for j in range(0, 8):
        jour = (maintenant + timedelta(days=j)).date()
        if jour.weekday() in (0, 3):
            moment = timezone.make_aware(datetime.combine(jour, time(6, 0)))
            if moment > maintenant:
                return moment
    return None


def volumes_vendeur(vendeur, jours=30):
    """Fiche vendeur vue par l'équipe : volumes des 30 derniers jours, jamais de montant."""
    depuis = timezone.now() - timedelta(days=jours)
    qs = colis_du_vendeur(vendeur).exclude(statut_traitement=S.BROUILLON)
    c = qs.filter(date_creation__gte=depuis).aggregate(
        total=Count('id'), livres=Count('id', filter=Q(statut_traitement__in=LIVRES)),
        echecs=Count('id', filter=Q(statut_traitement__in=ECHECS)))
    c['taux'] = taux(c['livres'], c['echecs'])
    c['niveau'], c['classe'] = niveau(c['taux'])
    c['en_cours'] = qs.exclude(statut_traitement__in=LIVRES + ECHECS + [S.ANNULE]).count()
    c['derniere'] = qs.order_by('-date_creation').values_list('date_creation', flat=True).first()
    return c
