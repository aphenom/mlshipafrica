"""
Espace commercial : indicateurs de chaque vendeur (volumes, jamais d'argent de la société), alertes automatiques,
journal de relance, vendeurs à qui proposer le stockage.

  Indicateurs (30 derniers jours, comparés aux 30 jours d'avant) : commandes, livrés, taux de livraison, taux de
  retour, semaines actives sur 4, et un profil : Nouveau, Inactif, En baisse, En hausse, Stable, Irrégulier.
  Alertes (chaque matin, dans la cloche du commercial, une fois par vendeur et par semaine) : inscrit sans commande
  depuis 3 jours, commandes en chute de moitié, retours au-dessus de 35 %, produit épuisé dans son stock.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from management.espace_vendeur import ECHECS, LIVRES, taux
from management.models import Article, ProduitStock, RelanceVendeur, Vendeur
from mlshipafrica.droits import droit_requis
from mlshipafrica.enums import StatutTraitement as S

SEUIL_RETOURS = 35          # % de retours qui déclenche l'alerte
SEUIL_STOCKAGE = 30         # commandes sur 30 jours à partir desquelles on propose le stockage
JOURS_SANS_COMMANDE = 3

PROFILS = {
    'nouveau': ('Nouveau', 'b-info'), 'inactif': ('Inactif', 'b-bad'), 'baisse': ('En baisse', 'b-bad'),
    'hausse': ('En hausse', 'b-ok'), 'stable': ('Stable', 'b-ok'), 'irregulier': ('Irrégulier', 'b-warn'),
}


def indicateurs(vendeurs, maintenant=None):
    """Annotate chaque vendeur : commandes_30, commandes_prec, livres_30, echecs_30, taux_livraison, taux_retour,
    semaines_actives, derniere, profil (clé), profil_libelle, profil_classe. Volumes seulement."""
    maintenant = maintenant or timezone.now()
    j30, j60 = maintenant - timedelta(days=30), maintenant - timedelta(days=60)
    ok = ~Q(vendeur_article__statut_traitement=S.BROUILLON) & Q(vendeur_article__etat_suppression=False)
    sur30 = ok & Q(vendeur_article__date_creation__gte=j30)
    qs = vendeurs.annotate(
        commandes_30=Count('vendeur_article', filter=sur30, distinct=True),
        commandes_prec=Count('vendeur_article', filter=ok & Q(vendeur_article__date_creation__gte=j60,
                                                               vendeur_article__date_creation__lt=j30), distinct=True),
        livres_30=Count('vendeur_article', filter=sur30 & Q(vendeur_article__statut_traitement__in=LIVRES), distinct=True),
        echecs_30=Count('vendeur_article', filter=sur30 & Q(vendeur_article__statut_traitement__in=ECHECS), distinct=True),
        derniere=Max('vendeur_article__date_creation', filter=ok),
        **{'sem%d' % k: Count('vendeur_article', filter=ok & Q(vendeur_article__date_creation__gte=maintenant - timedelta(days=7 * (k + 1)),
                                                               vendeur_article__date_creation__lt=maintenant - timedelta(days=7 * k)), distinct=True)
           for k in range(4)})
    resultat = []
    for v in qs:
        v.taux_livraison = taux(v.livres_30, v.echecs_30)
        termines = v.livres_30 + v.echecs_30
        v.taux_retour = round(v.echecs_30 * 100 / termines) if termines else None
        v.semaines_actives = sum(1 for k in range(4) if getattr(v, 'sem%d' % k))
        v.profil = _profil(v, maintenant)
        v.profil_libelle, v.profil_classe = PROFILS[v.profil]
        v.tendance = (round((v.commandes_30 - v.commandes_prec) * 100 / v.commandes_prec) if v.commandes_prec else None)
        resultat.append(v)
    return resultat


def _profil(v, maintenant):
    approuve = v.date_approbation or v.date_creation
    if approuve and approuve > maintenant - timedelta(days=30) and v.commandes_prec == 0:
        return 'nouveau'
    if v.commandes_30 == 0:
        return 'inactif'
    if v.commandes_prec >= 5 and v.commandes_30 < v.commandes_prec * 0.5:
        return 'baisse'
    if v.commandes_prec >= 5 and v.commandes_30 > v.commandes_prec * 1.5:
        return 'hausse'
    return 'stable' if v.semaines_actives >= 3 else 'irregulier'


def alertes(vendeurs, maintenant=None):
    """[(vendeur, type, titre, détail)] : ce que le commercial doit traiter. Rien n'est écrit."""
    maintenant = maintenant or timezone.now()
    liste = []
    actifs = vendeurs.filter(etat_approbation=True, etat_suppression=False)
    for v in indicateurs(actifs, maintenant):
        approuve = v.date_approbation or v.date_creation
        if v.derniere is None and approuve and approuve < maintenant - timedelta(days=JOURS_SANS_COMMANDE):
            liste.append((v, 'sans_commande', "%s : aucune commande depuis son inscription" % v.nom_store,
                          "Inscrit il y a %d jours. Appelez-le pour lancer sa première commande." % (maintenant - approuve).days))
        elif v.profil == 'baisse':
            liste.append((v, 'chute', "%s : commandes en chute" % v.nom_store,
                          "%d commandes sur 30 jours contre %d avant (%s %%)." % (v.commandes_30, v.commandes_prec, v.tendance)))
        if v.taux_retour is not None and v.taux_retour > SEUIL_RETOURS and v.livres_30 + v.echecs_30 >= 10:
            liste.append((v, 'retours', "%s : %d %% de retours" % (v.nom_store, v.taux_retour),
                          "%d colis non livrés sur %d. Vérifiez ses clients et ses produits." % (v.echecs_30, v.livres_30 + v.echecs_30)))
    for v in actifs.filter(option_stockage=True):
        epuises = [p.reference for p in ProduitStock.objects.filter(vendeur=v, actif=True, quantite_disponible__lte=0)]
        if epuises:
            liste.append((v, 'stock', "%s : stock épuisé (%s)" % (v.nom_store, ', '.join(epuises[:3])),
                          "Proposez-lui un envoi de stock pour ne pas perdre de commandes."))
    return liste


def a_proposer_stockage(vendeurs):
    """Vendeurs actifs, pas en stockage, qui envoient beaucoup : la cible pour vendre le stockage."""
    cibles = [v for v in indicateurs(vendeurs.filter(etat_approbation=True, etat_suppression=False, option_stockage=False))
              if v.commandes_30 >= SEUIL_STOCKAGE]
    return sorted(cibles, key=lambda v: -v.commandes_30)


def rappels_du_jour(user, jour=None):
    jour = jour or timezone.localdate()
    return RelanceVendeur.objects.filter(auteur=user, rappel_fait=False, rappeler_le__lte=jour).select_related('vendeur').order_by('rappeler_le')


def envoyer_alertes(maintenant=None):
    """Chaque matin : une notification par alerte au commercial du vendeur (une fois par semaine et par sujet)."""
    from core.models import License
    from management.notifications import notifier
    maintenant = maintenant or timezone.now()
    semaine = maintenant.strftime('%G-%V')
    n = 0
    for license in License.objects.all():
        vendeurs = Vendeur.objects.filter(license=license, commercial__isnull=False).select_related('commercial__user')
        for v, type_, titre, detail in alertes(vendeurs, maintenant):
            if v.commercial and v.commercial.user_id:
                notifier([v.commercial.user], 'vendeur', titre, detail,
                         reverse('management:management_commercial_suivi', args=[v.code]),
                         'alerte-com:%s:%s:%s' % (type_, v.pk, semaine))
                n += 1
    return n


def _mes_vendeurs(request):
    from management.views import vendeurs_visibles
    return vendeurs_visibles(request.user)


@login_required
@droit_requis('suivi_commercial')
def commercial_suivi(request, code):
    """Fiche de suivi d'un vendeur : indicateurs, alertes, journal de relance."""
    vendeurs = _mes_vendeurs(request)
    try:
        vendeur = vendeurs.get(code=code)
    except Vendeur.DoesNotExist:
        raise Http404
    if request.method == 'POST':
        if request.POST.get('fait'):
            RelanceVendeur.objects.filter(pk=request.POST['fait'], vendeur=vendeur).update(rappel_fait=True)
        else:
            note = (request.POST.get('note') or '').strip()
            if not note:
                messages.error(request, "Écrivez ce qui s'est dit.")
            else:
                rappel = request.POST.get('rappeler_le') or None
                RelanceVendeur.objects.filter(vendeur=vendeur, auteur=request.user, rappel_fait=False).update(rappel_fait=True)
                RelanceVendeur.objects.create(vendeur=vendeur, auteur=request.user, note=note[:2000], rappeler_le=rappel)
                messages.success(request, "Relance notée." + (" Rappel prévu." if rappel else ""))
        return redirect('management:management_commercial_suivi', code=code)
    v = indicateurs(vendeurs.filter(pk=vendeur.pk))[0]
    return render(request, 'management/commercial_suivi.html', {
        'v': v, 'alertes': [a for a in alertes(vendeurs.filter(pk=vendeur.pk))],
        'relances': vendeur.relances.select_related('auteur')[:50], 'seuil_stockage': SEUIL_STOCKAGE,
        'aujourdhui': timezone.localdate(),
    })
