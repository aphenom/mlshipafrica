"""
Tableaux de bord de l'équipe, comme dans la maquette ML COD Plateforme :
pilotage du manager (volumes seulement), pilotage du CEO (volumes + argent), journée de la comptable.

Les montants de la société ne sortent d'ici que par argent_ceo() et journee_comptable(), appelées seulement
pour un compte qui a le droit « argent » (la vue le vérifie). Le pilotage manager ne contient aucun montant.
"""
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from management.espace_vendeur import ECHECS, LIVRES, niveau, taux
from management.models import Acompte, AppelConfirmation, Article, Releve, Vendeur
from management.statuts import STATUTS_SURVEILLES_48H
from mlshipafrica.enums import StatutAcompte, StatutReleve, StatutTraitement as S

HEURES_SANS_APPEL = 2  # « non traitées » : commande jamais appelée 2 h après sa création

# Statuts qui ont leur propre liste dans Shipping (?type_colis=…)
STATUTS_AVEC_LISTE = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.REVENU_ABIDJAN, S.ECHEC_LIVRAISON, S.ANNULE, S.RETOURNE, S.LIVRE)

PERIODES = [('jour', 'Aujourd’hui'), ('7j', '7 jours'), ('mois', 'Ce mois'), ('moisprec', 'Mois dernier')]

# Colis en circulation, regroupés comme dans la maquette
EN_CIRCULATION = [
    ('À déposer / ramasser', (S.EN_ATTENTE_DEPOT, S.EN_ATTENTE_RAMASSAGE)),
    ('Reçus, à expédier', (S.DEPOT, S.RAMASSE, S.SUBSTITUE)),
    ('En transit', (S.EN_TRANSIT, S.ARRIVE)),
    ('En livraison', (S.EN_COURS_LIVRAISON, S.RECONDUIT)),
    ('En retour', (S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN)),
]


def periode_equipe(request):
    """Raccourcis de la maquette (aujourd'hui, 7 jours, ce mois, mois dernier) ou dates libres « du … au … »."""
    from management.espace_vendeur import periode
    aujourdhui = timezone.localdate()
    p = request.GET.get('p', '' if request.GET.get('du') else 'mois')
    if p == 'jour':
        du = au = aujourdhui
    elif p == '7j':
        du, au = aujourdhui - timedelta(days=6), aujourdhui
    elif p == 'mois':
        du, au = aujourdhui.replace(day=1), aujourdhui
    elif p == 'moisprec':
        au = aujourdhui.replace(day=1) - timedelta(days=1)
        du = au.replace(day=1)
    else:
        du, au, debut, fin = periode(request)
        return p, du, au, debut, fin
    debut = timezone.make_aware(datetime.combine(du, time.min))
    fin = timezone.make_aware(datetime.combine(au + timedelta(days=1), time.min))
    return p, du, au, debut, fin


def pilotage(license, debut, fin):
    """Volumes de la période et état du moment : jamais de montant de la société."""
    tous = Article.objects.filter(license=license, etat_suppression=False).exclude(statut_traitement=S.BROUILLON)
    sur_periode = tous.filter(date_creation__gte=debut, date_creation__lt=fin)
    c = sur_periode.aggregate(
        total=Count('id'), livres=Count('id', filter=Q(statut_traitement__in=LIVRES)),
        echecs=Count('id', filter=Q(statut_traitement__in=ECHECS)),
        annules=Count('id', filter=Q(statut_traitement=S.ANNULE)))
    t = taux(c['livres'], c['echecs'])
    maintenant = timezone.now()
    non_traitees = tous.filter(etat_confirmation='a_confirmer', statut_traitement__in=(S.EN_ATTENTE_DEPOT, S.EN_ATTENTE_RAMASSAGE),
                               date_creation__lt=maintenant - timedelta(hours=HEURES_SANS_APPEL)).count()
    bloques = (tous.filter(statut_traitement__in=STATUTS_SURVEILLES_48H)
               .annotate(dernier=Max('article_historiquearticle__date_creation', filter=Q(article_historiquearticle__etat_suppression=False)))
               .filter(dernier__lt=maintenant - timedelta(hours=48)).count())
    acomptes = Acompte.objects.filter(article__license=license, date_reception__gte=debut, date_reception__lt=fin).count()
    confirmees = sur_periode.filter(etat_confirmation='confirme').count()

    comptes = dict(tous.values_list('statut_traitement').annotate(n=Count('id')))
    par_statut = [{'cle': v, 'libelle': l, 'n': comptes.get(v, 0), 'lien': v in STATUTS_AVEC_LISTE}
                  for v, l in S.choices if v != S.BROUILLON and comptes.get(v)]
    circulation = [{'libelle': lib, 'n': sum(comptes.get(s, 0) for s in statuts), 'i': i} for i, (lib, statuts) in enumerate(EN_CIRCULATION)]
    total_circulation = sum(x['n'] for x in circulation) or 0

    zones = []
    for z in sur_periode.values('localite_arrivee__zone__nom').annotate(n=Count('id'), l=Count('id', filter=Q(statut_traitement__in=LIVRES)),
                                                              e=Count('id', filter=Q(statut_traitement__in=ECHECS))).order_by('localite_arrivee__zone__nom'):
        tz = taux(z['l'], z['e'])
        zones.append({'nom': z['localite_arrivee__zone__nom'] or 'Sans zone', 'n': z['n'], 'taux': tz})

    villes = []
    for v in sur_periode.values('localite_arrivee__nom').annotate(n=Count('id'), l=Count('id', filter=Q(statut_traitement__in=LIVRES)),
                                                                  e=Count('id', filter=Q(statut_traitement__in=ECHECS))):
        tv = taux(v['l'], v['e'])
        lib, cls = niveau(tv)
        villes.append({'nom': v['localite_arrivee__nom'] or 'Ville inconnue', 'n': v['n'], 'taux': tv, 'niveau': lib, 'classe': cls})
    villes.sort(key=lambda v: (v['taux'] is None, v['taux'] if v['taux'] is not None else 0, -v['n']))  # les plus faibles d'abord

    top = []
    for v in sur_periode.values('vendeur__code', 'vendeur__nom_store').annotate(
            n=Count('id'), l=Count('id', filter=Q(statut_traitement__in=LIVRES)),
            e=Count('id', filter=Q(statut_traitement__in=ECHECS))).order_by('-n')[:10]:
        top.append({'code': v['vendeur__code'], 'nom': v['vendeur__nom_store'] or v['vendeur__code'], 'n': v['n'],
                    'livres': v['l'], 'taux': taux(v['l'], v['e'])})
    top_max = max([x['n'] for x in top] or [1])

    motifs = {}
    for commentaire in AppelConfirmation.objects.filter(article__license=license, resultat='annule', date__gte=debut,
                                                        date__lt=fin).values_list('commentaire', flat=True):
        cle = (commentaire or 'Sans motif').split(' · ')[0].strip()[:60] or 'Sans motif'
        motifs[cle] = motifs.get(cle, 0) + 1
    total_motifs = sum(motifs.values()) or 1
    motifs = [{'motif': k, 'n': n, 'pct': round(n * 100 / total_motifs)} for k, n in sorted(motifs.items(), key=lambda x: -x[1])]

    vendeurs = Vendeur.objects.filter(license=license, etat_suppression=False)
    return {
        'commandes': c['total'], 'livres': c['livres'], 'echecs': c['echecs'], 'annules': c['annules'], 'taux': t,
        'taux_classe': 't-ok' if t is not None and t >= 80 else 't-warn' if t is not None and t >= 75 else 't-bad' if t is not None else '',
        'non_traitees': non_traitees, 'heures_sans_appel': HEURES_SANS_APPEL, 'bloques': bloques, 'acomptes': acomptes,
        'confirmees': confirmees, 'par_statut': par_statut, 'circulation': circulation, 'total_circulation': total_circulation,
        'zones': zones, 'villes': villes[:12], 'top': top, 'top_max': top_max, 'motifs': motifs,
        'vendeurs_actifs': vendeurs.filter(etat_approbation=True, etat_validation=True).count(),
        'demandes': vendeurs.filter(etat_approbation=False).count(),
    }


def argent_ceo(license, debut, fin):
    """Bénéfice de la période comparé à la période précédente de même durée, et trésorerie à venir."""
    from management.finance import journal
    j = journal(license, debut, fin)
    duree = fin - debut
    precedent = journal(license, debut - duree, debut)
    a_verser = Releve.objects.filter(vendeur__license=license, statut=StatutReleve.A_VERSER).aggregate(t=Sum('net'), n=Count('id'))
    a_rembourser = Acompte.objects.filter(article__license=license, statut=StatutAcompte.A_REMBOURSER).aggregate(t=Sum('montant'), n=Count('id'))
    variation = None
    if precedent['benefice']:
        variation = round((j['benefice'] - precedent['benefice']) * 100 / abs(precedent['benefice']))
    return {'journal': j, 'precedent': precedent, 'variation': variation,
            'marge_colis': (j['benefice'] / j['livres']) if j['livres'] else 0,
            'a_verser': a_verser['t'] or 0, 'releves_a_verser': a_verser['n'] or 0,
            'a_rembourser': a_rembourser['t'] or 0, 'acomptes_a_rembourser': a_rembourser['n'] or 0}


def journee_comptable(license):
    """La journée de la comptable : ce qu'il faut faire, le résultat du jour, les 7 prochains jours."""
    from management.finance import journal
    aujourdhui = timezone.localdate()
    debut = timezone.make_aware(datetime.combine(aujourdhui, time.min))
    jour = journal(license, debut, debut + timedelta(days=1))
    releves = Releve.objects.filter(vendeur__license=license, statut=StatutReleve.A_VERSER)
    sans_coordonnees = releves.filter(Q(vendeur__compte_versement__isnull=True) | Q(vendeur__compte_versement='')).count()
    acomptes = Acompte.objects.filter(article__license=license, statut=StatutAcompte.A_REMBOURSER)
    livres_non_valides = Article.objects.filter(license=license, etat_suppression=False, statut_traitement=S.LIVRE).count()
    a_faire = []
    if releves.exists():
        t = releves.aggregate(t=Sum('net'))['t'] or 0
        a_faire.append(('bad', '%d relevé(s) à verser aux vendeurs' % releves.count(), t,
                        ('dont %d sans coordonnées de versement' % sans_coordonnees) if sans_coordonnees else 'coordonnées renseignées',
                        'management:management_admin_releves', 'Verser'))
    if acomptes.exists():
        a_faire.append(('warn', '%d acompte(s) à rembourser' % acomptes.count(), acomptes.aggregate(t=Sum('montant'))['t'] or 0,
                        'commandes annulées avant le départ', 'management:management_admin_acomptes', 'Rembourser'))
    if livres_non_valides:
        a_faire.append(('warn', '%d colis livré(s) à valider pour paiement' % livres_non_valides, None,
                        'passent « Livré et payé » avant le prochain relevé', 'management:management_admin_liste_colis', 'Ouvrir'))
    calendrier = []
    for i in range(1, 8):
        d = aujourdhui + timedelta(days=i)
        evenements = []
        if d.weekday() in (0, 3):
            evenements.append(('Relevés', 'warn'))
        if d.weekday() == 1:
            evenements.append(('Prestataire', 'info'))
        if d.day == 1:
            evenements.append(('Stockage', 'ok'))
        calendrier.append({'date': d, 'evenements': evenements})
    return {'jour': jour, 'a_faire': a_faire, 'calendrier': calendrier}
