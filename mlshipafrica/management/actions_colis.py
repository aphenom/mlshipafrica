"""
Shipping : filtres de la liste des colis et actions sur une sélection (cocher des colis, puis agir).

Actions :
  - avancer   : passer la sélection à un statut (agent, manager, CEO) — le circuit est vérifié colis par colis ;
  - unpaid    : passer les colis livrés en « Unpaid » (comptable, CEO) ;
  - corriger  : corriger le statut (manager, CEO), raison obligatoire ;
  - imprimer  : feuille de route (bordereau), fiche de préparation, étiquettes, factures client ;
  - exporter  : fichier Excel (CSV).
Aucun document imprimé ne montre le nom du prestataire ni l'argent de la société : le livreur est « ML COD Intérieur ».
"""
import csv
from datetime import datetime, time, timedelta
from urllib.parse import parse_qs

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from management.models import Article
from management.statuts import ORDRE, STATUTS_ARGENT, STATUTS_RESERVES_RETOURS, appliquer_mouvement
from mlshipafrica.droits import a_le_droit, droit_requis
from mlshipafrica.enums import StatutTraitement as S

MAX_SELECTION = 2000

ONGLETS = {
    S.EN_ATTENTE_RAMASSAGE: ("En attente de ramassage", (S.EN_ATTENTE_RAMASSAGE,)),
    S.EN_ATTENTE_DEPOT: ("En attente de dépôt", (S.EN_ATTENTE_DEPOT,)),
    'en_cours': ("En cours", (S.RAMASSE, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.ECHEC_LIVRAISON,
                              S.RECONDUIT, S.EN_RETOUR)),
    S.REVENU_ABIDJAN: ("Revenus à Abidjan", (S.REVENU_ABIDJAN,)),
    S.ECHEC_LIVRAISON: ("Échecs de livraison", (S.ECHEC_LIVRAISON,)),
    S.ANNULE: ("Annulés avant expédition", (S.ANNULE,)),
    S.RETOURNE: ("Retournés", (S.RETOURNE,)),
    S.LIVRE: ("Livrés", (S.LIVRE, S.LIVRE_PAYE, S.REVERSE)),
}


def _date(valeur):
    try:
        return datetime.strptime((valeur or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def filtrer_colis(license, params):
    """Même filtre pour la liste, les actions groupées, les impressions et l'export. Renvoie (queryset, contexte)."""
    type_colis = params.get('type_colis', 'en_cours')
    statut = params.get('statut', '')
    q = (params.get('q') or '').strip()
    vendeur, ville = params.get('vendeur', ''), params.get('ville', '')
    du, au = _date(params.get('du')), _date(params.get('au'))
    ctx = {'type_colis': type_colis, 'statut_filtre': statut, 'q': q, 'vendeur_filtre': vendeur, 'ville': ville,
           'du': du, 'au': au, 'suite_breadcrumb': 'Tous les colis', 'jours_historique': None}
    articles = (Article.objects.filter(license=license, etat_suppression=False).exclude(statut_traitement=S.BROUILLON)
                .select_related('vendeur', 'localite_arrivee', 'zone_arrivee', 'agent_cod__user', 'format_article'))
    if statut:
        # Un statut choisi l'emporte sur l'onglet : on cherche dans tous les colis
        articles = articles.filter(statut_traitement=statut)
        ctx['suite_breadcrumb'] = dict(S.choices).get(statut, statut)
    elif type_colis == 'a_sauver':
        from management.statuts import STATUTS_SURVEILLES_48H
        ctx['suite_breadcrumb'] = "À sauver (48 h sans mouvement)"
        articles = (articles.filter(statut_traitement__in=STATUTS_SURVEILLES_48H)
                    .annotate(dernier_mouvement=Max('article_historiquearticle__date_creation',
                                                    filter=Q(article_historiquearticle__etat_suppression=False)))
                    .filter(dernier_mouvement__lt=timezone.now() - timedelta(hours=48)))
    elif type_colis in ONGLETS:
        ctx['suite_breadcrumb'], statuts = ONGLETS[type_colis]
        articles = articles.filter(statut_traitement__in=statuts)
        if type_colis == S.LIVRE and not (du or au):
            # ~1 000 colis livrés par jour : 60 derniers jours par défaut, ?jours=N pour élargir
            try:
                jours = max(1, int(params.get('jours', 60)))
            except ValueError:
                jours = 60
            ctx['jours_historique'] = jours
            articles = articles.filter(date_creation__gte=timezone.now() - timedelta(days=jours))
    if q:
        articles = articles.filter(Q(code__icontains=q) | Q(code_tracking__icontains=q) | Q(reference_externe__icontains=q)
                                   | Q(nom_destinataire__icontains=q) | Q(prenom_destinataire__icontains=q)
                                   | Q(numero_principal_destinataire__icontains=q))
    if vendeur:
        articles = articles.filter(vendeur__code=vendeur)
    if ville:
        articles = articles.filter(localite_arrivee__nom=ville)
    # Période : date du dernier mouvement (ex. « livrés du 10 au 16 »), sinon date de création
    if du or au:
        tz = timezone.get_current_timezone()
        champ = 'date_modification'
        if du:
            articles = articles.filter(**{champ + '__gte': timezone.make_aware(datetime.combine(du, time.min), tz)})
        if au:
            articles = articles.filter(**{champ + '__lt': timezone.make_aware(datetime.combine(au + timedelta(days=1), time.min), tz)})
    return articles.order_by('-date_modification'), ctx


def statuts_groupes(user):
    """Statuts proposés dans la barre d'actions selon le rôle (le circuit est revérifié pour chaque colis)."""
    libelles = dict(S.choices)
    proposes = [x for x in ORDRE if x not in STATUTS_ARGENT and x not in (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT)]
    if not a_le_droit(user, 'colis_retours'):
        proposes = [x for x in proposes if x not in STATUTS_RESERVES_RETOURS]
    return [(x, libelles[x]) for x in proposes]


def _selection(request, license):
    """Colis cochés, ou toute la liste filtrée si « tous » est demandé."""
    if request.POST.get('tous') == '1':
        params = {k: v[-1] for k, v in parse_qs(request.POST.get('filtres', '')).items()}
        articles, _ = filtrer_colis(license, params)
    else:
        codes = request.POST.getlist('codes')
        articles = (Article.objects.filter(license=license, etat_suppression=False, code__in=codes)
                    .select_related('vendeur', 'localite_arrivee', 'zone_arrivee', 'agent_cod__user', 'format_article')
                    .order_by('localite_arrivee__nom', 'code'))
    return list(articles[:MAX_SELECTION + 1])


def _retour(request):
    filtres = request.POST.get('filtres', '')
    return redirect('/management/admin_liste_colis/' + ('?' + filtres if filtres else ''))


@login_required
@require_POST
@droit_requis('colis_mouvements', 'colis_corriger', 'paiements')
def admin_colis_actions(request):
    user = request.user
    license = user.account_profil_staff.license
    action = request.POST.get('action')
    articles = _selection(request, license)
    if not articles:
        messages.error(request, "Cochez au moins un colis.")
        return _retour(request)
    if len(articles) > MAX_SELECTION:
        messages.error(request, "Plus de %d colis : affinez les filtres (période, vendeur, ville)." % MAX_SELECTION)
        return _retour(request)
    commentaire = request.POST.get('commentaire', '')
    if action == 'avancer':
        if not a_le_droit(user, 'colis_mouvements'):
            raise PermissionDenied
        statut, correction = request.POST.get('statut'), False
    elif action == 'unpaid':
        if not a_le_droit(user, 'paiements'):
            raise PermissionDenied
        statut, correction = S.LIVRE_PAYE, False
    elif action == 'corriger':
        if not a_le_droit(user, 'colis_corriger'):
            raise PermissionDenied
        statut, correction = request.POST.get('statut'), True
        if not commentaire.strip():
            messages.error(request, "Indiquez la raison de la correction.")
            return _retour(request)
    else:
        messages.error(request, "Action inconnue.")
        return _retour(request)
    faits, refus = 0, []
    for article in articles:
        if action == 'unpaid' and (article.statut_traitement != S.LIVRE or not article.is_option_encaissement):
            if article.statut_traitement != S.LIVRE_PAYE:
                refus.append("%s (%s)" % (article.code, article.get_statut_traitement_display()))
            continue
        ok, raison = appliquer_mouvement(article, statut, user, commentaire, correction=correction)
        if ok:
            faits += 1
        else:
            refus.append(raison if correction else "%s (%s)" % (article.code, article.get_statut_traitement_display()))
    libelle = dict(S.choices).get(statut, statut)
    if faits:
        messages.success(request, "%d colis passé%s à « %s »." % (faits, 's' if faits > 1 else '', libelle))
    if refus:
        messages.warning(request, "%d colis non modifié%s : le circuit ne permet pas ce statut pour eux — %s%s" % (
            len(refus), 's' if len(refus) > 1 else '', ', '.join(refus[:15]), '…' if len(refus) > 15 else ''))
    return _retour(request)


# ------------------------------------------------------------------------------------------- impressions

DOCUMENTS = {
    'feuille_route': "Feuille de route (bordereau)",
    'preparation': "Fiche de préparation",
    'etiquettes': "Étiquettes colis",
    'factures': "Factures client",
}


@login_required
@require_POST
@droit_requis('colis_imprimer')
def admin_colis_imprimer(request):
    user = request.user
    license = user.account_profil_staff.license
    doc = request.POST.get('doc')
    articles = _selection(request, license)[:MAX_SELECTION]
    if doc == 'export':
        return _export(articles, a_le_droit(user, 'argent'))
    if doc not in DOCUMENTS or not articles:
        messages.error(request, "Cochez au moins un colis.")
        return _retour(request)
    articles.sort(key=lambda a: ((a.localite_arrivee.nom if a.localite_arrivee else 'zzz'), a.code))
    a_encaisser = sum((a.valeur_totale or 0) for a in articles if a.is_option_encaissement)
    villes = {}
    for a in articles:
        villes.setdefault(a.localite_arrivee.nom if a.localite_arrivee else 'Sans ville', []).append(a)
    produits = {}
    for a in articles:
        cle = (a.designation or 'Sans désignation', a.format_article.nom if a.format_article else '')
        p = produits.setdefault(cle, {'designation': cle[0], 'format': cle[1], 'quantite': 0, 'codes': []})
        p['quantite'] += a.quantite or 1
        p['codes'].append(a.code)
    return render(request, 'management/imprimer_colis.html', {
        'doc': doc, 'titre': DOCUMENTS[doc], 'articles': articles, 'a_encaisser': a_encaisser,
        'villes': sorted(villes.items()), 'produits': sorted(produits.values(), key=lambda p: -p['quantite']),
        'quantite_totale': sum(p['quantite'] for p in produits.values()), 'maintenant': timezone.now(),
        'par': user.get_full_name() or user.email,
    })


def _export(articles, avec_argent):
    reponse = HttpResponse(content_type='text/csv; charset=utf-8')
    reponse['Content-Disposition'] = 'attachment; filename="colis-%s.csv"' % timezone.localtime().strftime('%Y%m%d-%H%M')
    reponse.write('﻿')  # Excel lit les accents
    w = csv.writer(reponse, delimiter=';')
    entete = ['Commande', 'Créée le', 'Tracking', 'Réf. vendeur', 'Vendeur', 'Client', 'Téléphone', 'Téléphone 2', 'Ville',
              'Zone', 'Adresse', 'Produit', 'Quantité', 'À encaisser', 'Statut', 'Confirmation', 'Agent', 'Mis à jour']
    if avec_argent:
        entete += ['Frais ML', 'Frais de collecte', 'Frais de retour', 'Garde']
    w.writerow(entete)
    for a in articles:
        ligne = [a.code, timezone.localtime(a.date_creation).strftime('%d/%m/%Y %H:%M') if a.date_creation else '',
                 a.code_tracking or '', a.reference_externe or '', a.vendeur.nom_store if a.vendeur else '',
                 ('%s %s' % (a.nom_destinataire or '', a.prenom_destinataire or '')).strip(), a.numero_principal_destinataire or '',
                 a.numero_secondaire_destinataire or '', a.localite_arrivee.nom if a.localite_arrivee else '',
                 a.zone_arrivee.nom if a.zone_arrivee else '', a.adresse_destinataire or '', a.designation or '', a.quantite or 1,
                 int(a.valeur_totale or 0) if a.is_option_encaissement else 0, a.get_statut_traitement_display(),
                 a.get_etat_confirmation_display(),
                 (a.agent_cod.user.get_full_name() or a.agent_cod.user.email) if a.agent_cod and a.agent_cod.user else '',
                 timezone.localtime(a.date_modification).strftime('%d/%m/%Y %H:%M') if a.date_modification else '']
        if avec_argent:
            ligne += [int(a.montant_frais or 0), int(a.cout_option_encaissement or 0), int(a.frais_retour or 0), int(a.frais_garde or 0)]
        w.writerow(ligne)
    return reponse
