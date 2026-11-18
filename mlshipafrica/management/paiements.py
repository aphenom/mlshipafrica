"""
Paiement des vendeurs : la comptable pilote, la plateforme propose.

    1. Livré (l'agent)  →  2. Unpaid : la comptable coche les livrés de la période (argent bien reçu)
    3. Paid : le jour de paiement elle coche les vendeurs et génère leurs factures de paiement (le vendeur les voit)
    4. Versé : l'argent est envoyé, elle note la référence (frais Mobile Money déduits, à la charge du vendeur)

Seuls la comptable et le CEO gèrent ce circuit. Une facture générée par erreur s'annule avant versement (motif).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from management.finance import (a_payer_par_vendeur, annuler_releve, enregistrer_coordonnees, frais_versement,
                                generer_releves, jour_de_paiement, lignes_releve, livres_a_valider, marquer_verse,
                                ecritures_a_payer, totaux)
from management.models import Releve, Vendeur
from mlshipafrica.droits import a_le_droit, droit_requis
from mlshipafrica.enums import MoyenVersement, StatutReleve

ETAPES = (('unpaid', '1 · Livrés à valider'), ('a_payer', '2 · À payer'), ('factures', '3 · Factures à verser'),
          ('verses', '4 · Versés'), ('stockage', 'Stockage du mois'))


@login_required
@droit_requis('releves')
def admin_paiements(request):
    user = request.user
    license = user.account_profil_staff.license
    releves = Releve.objects.filter(vendeur__license=license).select_related('vendeur', 'verse_par', 'genere_par')
    if request.method == 'POST':
        action = request.POST.get('action') or ('verser' if request.POST.get('releve') else '')
        try:
            if action == 'generer':
                vendeurs = Vendeur.objects.filter(license=license, code__in=request.POST.getlist('vendeurs'))
                if not vendeurs:
                    raise ValidationError("Cochez au moins un vendeur.")
                crees = generer_releves(vendeurs=vendeurs, license=license, par=user)
                from management.notifications import releves_emis
                releves_emis(crees, user)
                messages.success(request, "%d facture%s de paiement générée%s : les vendeurs les voient dans « Mon argent »." % (
                    len(crees), 's' if len(crees) > 1 else '', 's' if len(crees) > 1 else ''))
                return redirect(reverse('management:management_admin_releves') + '?etape=factures')
            if action == 'stockage':
                from datetime import datetime as dt_
                from management.stock import nom_mois, valider_stockage_mois
                try:
                    mois = dt_.strptime(request.POST.get('mois', ''), '%Y-%m').date()
                except ValueError:
                    mois = timezone.localdate().replace(day=1)
                faites = valider_stockage_mois(license, request.POST.getlist('vendeurs'), user, mois)
                if not faites:
                    raise ValidationError("Cochez au moins un vendeur.")
                messages.success(request, "Stockage de %s chargé pour %d vendeur%s (%s F) : déduit de leur prochaine facture." % (
                    nom_mois(mois), len(faites), 's' if len(faites) > 1 else '',
                    '{:,.0f}'.format(sum(l['montant'] for l in faites)).replace(',', '\u202f')))
                from management.stock import mois_a_charger
                reste = mois_a_charger(license)
                return redirect(reverse('management:management_admin_releves') + ('?etape=stockage' if reste else '?etape=a_payer'))
            releve = releves.get(pk=request.POST.get('releve'))
            if action == 'annuler':
                annuler_releve(releve, user, request.POST.get('motif', ''))
                messages.success(request, "Facture %s annulée : ses colis repassent dans « À payer »." % releve.code)
            else:
                releve = marquer_verse(releve, user, request.POST.get('reference', ''), request.POST.get('moyen', ''))
                from management.notifications import releve_verse
                releve_verse(releve)
                messages.success(request, "Facture %s marquée versée." % releve.code)
        except (ValidationError, Releve.DoesNotExist) as erreur:
            messages.error(request, ' '.join(getattr(erreur, 'messages', ["Facture introuvable."])))
        return redirect(reverse('management:management_admin_releves') + '?' + request.GET.urlencode())

    a_verser = releves.filter(statut=StatutReleve.A_VERSER)
    etape = request.GET.get('etape') or ('factures' if a_verser.exists() else 'a_payer')
    if request.GET.get('statut') == StatutReleve.VERSE:
        etape = 'verses'
    ctx = {'etape': etape, 'etapes': ETAPES, 'jour_paiement': jour_de_paiement()}

    a_valider = livres_a_valider(license)
    ctx['kpi_a_valider'] = a_valider.aggregate(n=Count('id'), t=Sum('valeur_totale'))
    lignes_payables = ecritures_a_payer(license)
    ctx['kpi_a_payer'] = totaux(lignes_payables)
    ctx['kpi_a_payer_vendeurs'] = lignes_payables.values('vendeur').distinct().count()
    ctx['kpi_a_verser'] = a_verser.filter(net__gt=0).aggregate(t=Sum('net'), n=Count('id'))
    ctx['kpi_sans_coordonnees'] = Vendeur.objects.filter(license=license, etat_suppression=False).filter(
        Q(versement_valide=False) & ~Q(compte_versement=None) & ~Q(compte_versement='')).count()
    debut_mois = timezone.make_aware(timezone.datetime.combine(timezone.localdate().replace(day=1), timezone.datetime.min.time()))
    from management.stock import mois_a_charger
    _mois = mois_a_charger(license)
    ctx['kpi_stockage_vendeurs'] = sum(len(l) for _, l, _ in _mois)
    ctx['kpi_stockage_retard'] = any(r for _, _, r in _mois)
    ctx['kpi_verses_mois'] = releves.filter(statut=StatutReleve.VERSE, date_versement__gte=debut_mois).aggregate(
        t=Sum('montant_verse'), n=Count('id'))

    if etape == 'unpaid':
        from management.actions_colis import filtrer_colis
        params = request.GET.copy()
        params['statut'] = 'livre'
        articles, filtre = filtrer_colis(license, params)
        articles = articles.filter(is_option_encaissement=True)
        ctx.update(filtre)
        ctx['total_selection'] = articles.aggregate(n=Count('id'), t=Sum('valeur_totale'))
        ctx['page'] = Paginator(articles, 100).get_page(request.GET.get('page'))
        f = params.copy()
        f.pop('page', None)
        f.pop('etape', None)
        ctx['filtres'] = f.urlencode()
        ctx['vendeurs_liste'] = Vendeur.objects.filter(license=license, etat_suppression=False, etat_approbation=True).order_by(
            'nom_store').values_list('code', 'nom_store')
    elif etape == 'a_payer':
        ctx['vendeurs_a_payer'] = a_payer_par_vendeur(license)
        ctx['total_a_payer'] = sum((v['net'] for v in ctx['vendeurs_a_payer'] if v['net'] > 0 and not v['bloque']), 0)
    elif etape == 'stockage':
        from management.stock import mois_a_charger, nom_mois
        ctx['stockage_mois'] = [{'debut': d, 'cle': d.strftime('%Y-%m'), 'nom': nom_mois(d), 'lignes': l, 'retard': r,
                                 'total': sum((x['montant'] for x in l), 0)} for d, l, r in mois_a_charger(license)]
        ctx['stockage_mois_nom'] = nom_mois(timezone.localdate())
    elif etape in ('factures', 'verses'):
        liste = (a_verser if etape == 'factures' else releves.filter(statut__in=(StatutReleve.VERSE, StatutReleve.ANNULE)))
        # Période : date d'émission pour les factures à verser, date de versement pour l'historique
        from management.tableaux_equipe import PERIODES, periode_equipe
        if request.GET.get('p') or request.GET.get('du'):
            p, du, au, debut, fin = periode_equipe(request)
            if etape == 'factures':
                liste = liste.filter(date_arrete__gte=debut, date_arrete__lt=fin)
            else:
                liste = liste.filter(Q(date_versement__gte=debut, date_versement__lt=fin) |
                                     Q(statut=StatutReleve.ANNULE, date_annulation__gte=debut, date_annulation__lt=fin))
            ctx.update({'p': p, 'du': du, 'au': au})
        ctx['periodes'] = PERIODES
        ctx['total_liste'] = liste.aggregate(n=Count('id'), net=Sum('net'), envoye=Sum('montant_verse'))
        liste = list(liste[:500])
        for r in liste:
            if r.statut == StatutReleve.A_VERSER:
                r.frais_estimes = frais_versement(r.vendeur.moyen_valide, r.net) if r.vendeur.versement_valide else 0
                r.a_envoyer = max(r.net - r.frais_estimes, 0) if r.net > 0 else 0
        ctx['releves'] = liste
    code = request.GET.get('releve')
    if code:
        ctx['releve_detail'] = Releve.objects.filter(vendeur__license=license, code=code).select_related('vendeur').first()
        if ctx['releve_detail']:
            ctx['lignes'], ctx['autres'] = lignes_releve(ctx['releve_detail'])
            from management.notifications import messages_visibles
            ctx['fil'] = messages_visibles(user, releve=ctx['releve_detail'])
    ctx['moyens'] = MoyenVersement.choices
    return render(request, 'management/paiements_vendeurs.html', ctx)


def _releve_autorise(request, code):
    user = request.user
    if user.is_staff:
        if not a_le_droit(user, 'releves'):
            raise PermissionDenied
        qs = Releve.objects.filter(vendeur__license=user.account_profil_staff.license)
    else:
        vendeur = Vendeur.objects.filter(user=user).first()
        if vendeur is None:
            raise Http404
        qs = Releve.objects.filter(vendeur=vendeur).exclude(statut=StatutReleve.ANNULE)
    releve = qs.select_related('vendeur').filter(code=code).first()
    if releve is None:
        raise Http404
    return releve


@login_required
def facture_paiement(request, code):
    """Facture de paiement imprimable, ligne par ligne (vendeur, comptable, CEO)."""
    releve = _releve_autorise(request, code)
    lignes, autres = lignes_releve(releve)
    from management.notifications import messages_visibles
    return render(request, 'management/facture_paiement.html', {'fil': messages_visibles(request.user, releve=releve),
        'releve': releve, 'lignes': lignes, 'autres': autres, 'vendeur': releve.vendeur,
        'retour': reverse('management:management_admin_releves') + '?etape=factures' if request.user.is_staff
        else reverse('management:management_vendeur_releves')})


# --------------------------------------------------------------------------------------------- vendeur

def _vendeur(request):
    vendeur = Vendeur.objects.filter(user=request.user).first()
    if vendeur is None or request.user.is_staff:
        raise Http404
    return vendeur


@login_required
def vendeur_releves(request):
    """Mon argent : où en est mon argent, mes factures de paiement, ligne par ligne."""
    vendeur = _vendeur(request)
    a_valider = livres_a_valider(vendeur=vendeur)
    kpi_a_valider = a_valider.aggregate(n=Count('id'), t=Sum('valeur_totale'))
    prochain = ecritures_a_payer(vendeurs=[vendeur])
    prochain_totaux = totaux(prochain)
    prochain_lignes, prochain_autres = lignes_releve(prochain)
    releves = vendeur.releves.exclude(statut=StatutReleve.ANNULE)
    en_cours = releves.filter(statut=StatutReleve.A_VERSER)
    kpi_en_cours = en_cours.aggregate(t=Sum('net'), n=Count('id'))
    dernier_verse = releves.filter(statut=StatutReleve.VERSE).order_by('-date_versement').first()
    facture = releves.filter(code=request.GET.get('facture')).first() if request.GET.get('facture') else None
    from management.notifications import messages_visibles
    return render(request, 'management/vendeur_releves.html', {
        'facture': facture, 'fil': messages_visibles(request.user, releve=facture) if facture else None,
        'vendeur': vendeur, 'kpi_a_valider': kpi_a_valider, 'prochain': prochain_totaux,
        'prochain_lignes': prochain_lignes[:300], 'prochain_autres': prochain_autres, 'releves': releves[:200],
        'kpi_en_cours': kpi_en_cours, 'dernier_verse': dernier_verse,
        'frais_estimes': frais_versement(vendeur.moyen_valide, prochain_totaux['net']) if vendeur.versement_valide else 0,
    })


@login_required
def vendeur_paiement(request):
    """Paramètres › Numéro de paiement : le vendeur saisit où recevoir son argent (procuration obligatoire)."""
    vendeur = _vendeur(request)
    if request.method == 'POST':
        moyen = request.POST.get('moyen_versement')
        try:
            changement = enregistrer_coordonnees(vendeur, moyen, request.POST.get('compte_versement'),
                                                 request.POST.get('titulaire_versement'), request.FILES.get('procuration_versement'))
        except ValidationError as erreur:
            messages.error(request, ' '.join(erreur.messages))
        else:
            if changement and not vendeur.versement_valide:
                from management.notifications import numero_a_valider
                numero_a_valider(vendeur)
            if changement:
                # Sécurité : le vendeur est prévenu de tout changement de ses coordonnées de versement
                from sms.service import mettre_en_file
                transaction.on_commit(lambda: mettre_en_file(
                    'moyen', vendeur.numero_sms or vendeur.numero_contact, {'moyen': MoyenVersement(moyen).label},
                    cle_dedoublonnage='moyen:%s:%s' % (vendeur.code, timezone.now().strftime('%Y%m%d%H%M%S')), vendeur=vendeur))
            messages.success(request, "Coordonnées enregistrées. La comptabilité vérifie votre procuration : les versements reprennent dès la validation."
                             if changement and not vendeur.versement_valide else "Coordonnées enregistrées.")
        return redirect('management:management_vendeur_paiement')
    from management.models import FraisVersement
    return render(request, 'management/vendeur_paiement.html', {
        'vendeur': vendeur, 'moyens': MoyenVersement.choices, 'frais_versement_regles': FraisVersement.objects.filter(taux__gt=0)})


# --------------------------------------------------------------------------------------------- réglages (CEO)

REGLAGES = (
    ('taux_option_encaissement', "Frais de collecte (% du montant encaissé)", "Prélevé dès que le colis est livré.", '5'),
    ('taux_frais_retour', "Frais de retour (% des frais de livraison)", "Facturé quand le colis n'est pas livré et revient.", '50'),
    ('garde_par_jour', "Garde par colis et par jour (F)", "Colis revenu à Abidjan et pas repris.", '500'),
    ('garde_premier_jour', "Premier jour de garde payante (J+)", "", '11'),
    ('garde_plafond', "Plafond de la garde par colis (F)", "", '10000'),
    ('tarif_stockage_mois', "Stockage par pièce et par mois (F)", "Compté dès l'entrée du stock, puis chaque mois pour les pièces restantes.", '300'),
    ('montant_acompte', "Acompte client demandé à la confirmation (F, interne)", "Jamais affiché au vendeur.", '2000'),
)


@login_required
@droit_requis('parametres_configuration')
def admin_reglages_frais(request):
    """Le CEO règle les frais pour tous les vendeurs, d'un seul endroit. Le taux de collecte peut être appliqué aux colis existants."""
    from decimal import Decimal, InvalidOperation
    from management.finance import appliquer_taux_collecte, configuration, taux_collecte
    license = request.user.account_profil_staff.license
    config = configuration(license)
    if config is None:
        raise Http404("Aucune configuration pour cette licence.")
    if request.method == 'POST':
        ancien_taux = taux_collecte(license)
        try:
            for champ, libelle, _, _ in REGLAGES:
                brut = (request.POST.get(champ) or '').replace(' ', '').replace(' ', '').replace(',', '.').strip()
                if brut == '':
                    continue
                valeur = Decimal(brut)
                if valeur < 0 or (champ.startswith('taux') and valeur > 100):
                    raise ValidationError("Valeur hors limites : %s." % libelle)
                setattr(config, champ, int(valeur) if champ == 'garde_premier_jour' else valeur)
            config.save()
        except (InvalidOperation, ValidationError) as erreur:
            messages.error(request, ' '.join(getattr(erreur, 'messages', ["Nombre invalide."])))
            return redirect('management:management_admin_reglages_frais')
        nouveau_taux = taux_collecte(license)
        if request.POST.get('appliquer') == '1':
            inclure = request.POST.get('inclure_factures') == '1'
            n, ecart = appliquer_taux_collecte(license, nouveau_taux, inclure_factures=inclure)
            messages.success(request, "Réglages enregistrés. Frais de collecte à %s %% appliqués à %d colis (écart sur les colis livrés : %s F, repris dans les prochaines factures de paiement)." % (
                nouveau_taux.normalize(), n, '{:,.0f}'.format(ecart).replace(',', ' ')))
        else:
            messages.success(request, "Réglages enregistrés." + (" Le nouveau taux de collecte vaut pour les prochaines commandes ; vous pouvez l'appliquer aux colis existants ci-dessous." if nouveau_taux != ancien_taux else ''))
        return redirect('management:management_admin_reglages_frais')
    taux = taux_collecte(license)
    simulation = appliquer_taux_collecte(license, taux, simuler=True)
    simulation_tout = appliquer_taux_collecte(license, taux, inclure_factures=True, simuler=True)
    champs = [(c, l, aide, getattr(config, c) if getattr(config, c) is not None else defaut) for c, l, aide, defaut in REGLAGES]
    return render(request, 'management/admin_reglages_frais.html', {
        'champs': champs, 'taux': taux, 'simulation': simulation, 'simulation_tout': simulation_tout})
