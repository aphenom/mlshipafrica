from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, Encaissement, HistoriqueArticle, ProduitStock, ProfilStaff, ReglementArticle, Reversement, Vendeur
from management.forms import VendeurColisForm, VendeurForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages as django_messages

from core.models import Configuration, License, Localite

from mlshipafrica.enums import EtatConfirmation, StatutTraitement, StatutVendeur, TypeProfilStaffChoice, TypeVendeurChoice, array_statut_traitement_retour, array_statut_traitement_en_cours, array_statut_traitement_livre

from mlshipafrica.shared import get_articles_stats_by_vendeur, get_global_article_stats, get_global_vendeurs_stats, get_top_n_vendeurs

from django.db import transaction
from tablib import Dataset

from management.resources import VendeurResource
from management.statuts import ORDRE as ORDRE_STATUTS, appliquer_mouvement, statuts_correction, statuts_suivants
from mlshipafrica.droits import a_le_droit, droit_requis, droits_de

from django.utils import timezone

from django.db.models import Q, Count, Max, Sum, F, ExpressionWrapper, DecimalField, Value
from datetime import timedelta
import datetime
import logging
from django.db.models.functions import Coalesce
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


def vendeurs_visibles(user):
    """Vendeurs de la licence ; un commercial ne voit que les siens et ceux en attente d'approbation."""
    profil = user.account_profil_staff
    vendeurs = Vendeur.objects.filter(license=profil.license)
    if profil.role_profil == TypeProfilStaffChoice.COMMERCIAL:
        vendeurs = vendeurs.filter(Q(commercial=profil) | Q(commercial__isnull=True, etat_approbation=False))
    return vendeurs


# Create edition profil vendeur
@login_required
def vendeur_edit_profil(request):
    user = request.user
    form = VendeurForm(instance=None)
    current_license = request.GET.get('current_license', None)
    license = License.objects.get(code=current_license, etat_validation=False, etat_suppression=False) if current_license and current_license != 'None' else License.objects.all().first()

    if user.is_authenticated and not user.is_staff:
        try:
            vendeur = Vendeur.objects.get(user=user)
        except Vendeur.DoesNotExist:
            vendeur = Vendeur(user=user)  # On définit déjà l'user ici
            vendeur.license = license if license and license.pk else License.objects.all().first()

        if request.method == 'POST':
            form = VendeurForm(data=(request.POST or None), files=(request.FILES or None), instance=vendeur)
            if form.is_valid():
                vendeur = form.save(commit=False)
                if form.has_changed():
                    vendeur.etat_approbation = False
                if not vendeur.user:
                    vendeur.user = user
                    vendeur.license = license if license and license.pk else License.objects.all().first()
                vendeur.save()
                return redirect('index')
                # Tu peux aussi faire : return redirect('management:vendeur_profil')
        else:
            form = VendeurForm(instance=vendeur)
        return render(request, 'management/vendeur_edit_profil.html', locals())
    return redirect('index')


@login_required
def vendeur_profil(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        type_vendeur = TypeVendeurChoice
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_profil.html', locals())

    

# Create edit colis vendeur.
@login_required
@transaction.atomic
def vendeur_edit_colis(request):
    user = request.user
    form = VendeurColisForm(instance=None)
    current_article = request.GET.get('current_article', None)
    # statut_traitement = StatutTraitement

    if user.is_authenticated and not user.is_staff:
        try:
                vendeur = Vendeur.objects.get(user=user)
                configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
                localite_depart = Localite.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False, is_depart=True).first()  
                article = Article() if current_article is None else Article.objects.get(code=current_article, vendeur=vendeur, statut_traitement=StatutTraitement.BROUILLON, etat_validation=False, etat_suppression=False)
                article.vendeur = vendeur
                article.license = vendeur.license
                article.config = configuration
                article.localite_depart = localite_depart
                article.etat_validation = False
                article.statut_traitement = StatutTraitement.BROUILLON
                if vendeur.collecte_par_mlship is True and configuration.enable_option_encaissement is True:
                    article.is_option_encaissement = True
        except Exception as e:
            raise Http404

        if request.method == 'POST' and not request.POST.get('type_colis'):
            # Envoi sans le choix (ancien formulaire) : on suit les champs envoyés, jamais « stock » par défaut
            type_colis = ('stock' if request.POST.get('produit_stock') else
                          'ramassage' if request.POST.get('is_option_recuperation') == 'True' else 'depot')
        else:
            type_colis = request.POST.get('type_colis') or (
                'stock' if article.produit_stock_id else 'ramassage' if article.is_option_recuperation
                else 'stock' if (vendeur.option_stockage and not article.pk) else 'depot')
        if type_colis == 'stock' and not vendeur.option_stockage:
            type_colis = 'depot'
        if request.method == 'POST':
            donnees = request.POST.copy()
            donnees['is_option_recuperation'] = 'True' if type_colis == 'ramassage' else 'False'
            if type_colis != 'stock':
                donnees['produit_stock'] = ''
            with transaction.atomic():
                if "submit_suppression" in request.POST and request.POST["submit_suppression"]:
                    # rediriger vers details colis
                    article.etat_suppression =  True
                    article.save()
                    return redirect('index')
                form = VendeurColisForm(data=donnees, files=(request.FILES or None), instance=article)
                if form.is_valid() and type_colis == 'stock' and not form.cleaned_data.get('produit_stock'):
                    form.add_error(None, "Choisissez le produit de votre stock, ou un autre type de colis.")
                if form.is_valid():
                    article = form.save(commit=False)
                    if article.produit_stock_id and not article.designation:
                        article.designation = article.produit_stock.designation[:100]
                    try:
                        with transaction.atomic():
                            article.save()
                            if request.POST.get('action') == 'valider':
                                valider_commande_vendeur(article, user)
                    except ValidationError as erreur:
                        # Pas de tarif pour cette destination / ce format : on le dit au vendeur
                        form.add_error(None, erreur.messages)
                        contexte = locals()
                        _ecran_commande(form, vendeur, localite_depart, contexte)
                        return render(request, 'management/vendeur_edit_colis.html', contexte)
                    if request.POST.get('action') == 'valider':
                        django_messages.success(request, "Commande %s enregistrée et envoyée. Saisissez la suivante." % article.code)
                        return HttpResponseRedirect(reverse('management:management_vendeur_edit_colis') + '?apres=' + article.code)
                    return redirect('management:management_vendeur_facture_colis', article.code)
        else:
            form = VendeurColisForm(instance=article)
        contexte = locals()
        _ecran_commande(form, vendeur, localite_depart, contexte)
        return render(request, 'management/vendeur_edit_colis.html', contexte)
    return redirect('index')


def valider_commande_vendeur(article, user):
    """Le vendeur valide sa commande : le produit sort de son stock (s'il y en a un) et la commande part."""
    from management.stock import reserver_pour_commande
    reserver_pour_commande(article, user)
    article.statut_traitement = StatutTraitement.EN_ATTENTE_RAMASSAGE if article.is_option_recuperation is True else StatutTraitement.EN_ATTENTE_DEPOT
    article.save()


def _ecran_commande(form, vendeur, localite_depart, contexte):
    """Données du récapitulatif en direct de la maquette : frais par destination et format, taux par ville."""
    from management.espace_vendeur import grille_vendeur, taux_par_ville
    contexte['grille'] = grille_vendeur(vendeur, localite_depart, form.fields['localite_arrivee'].queryset,
                                        form.fields['format_article'].queryset)
    contexte['taux_villes'] = taux_par_ville(vendeur)


@login_required
def vendeur_facture_colis(request, code):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        article = Article.objects.get(code=code, vendeur=vendeur, etat_suppression=False)
        # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # statut_traitement = StatutTraitement
        if request.method == 'POST':
            if "submit_validation" in request.POST and request.POST["submit_validation"] and article.statut_traitement == StatutTraitement.BROUILLON:
                # Vendeur en stockage : le produit sort du stock à la validation (refusé si stock insuffisant)
                from management.stock import reserver_pour_commande
                try:
                    with transaction.atomic():
                        valider_commande_vendeur(article, user)
                except ValidationError as erreur:
                    django_messages.error(request, ' '.join(erreur.messages))
                    return redirect('management:management_vendeur_facture_colis', article.code)
                django_messages.success(request, "Commande %s créée : elle part en préparation." % article.code)
                if request.POST.get("submit_validation") == "continuer":
                    return HttpResponseRedirect(reverse('management:management_vendeur_edit_colis') + '?apres=' + article.code)
                return redirect('management:management_vendeur_liste_colis')
            if "submit_modification" in request.POST and request.POST["submit_modification"]:
                return HttpResponseRedirect(reverse('management:management_vendeur_edit_colis') + '?current_article=' + code) 
            if "submit_impression" in request.POST and request.POST["submit_impression"]:
                pass

            return redirect('management:management_vendeur_facture_colis', article.code)
        from management.finance import configuration, taux_collecte
        from mlshipafrica.enums import array_statut_traitement_livre
        statuts_livres = [str(x) for x in array_statut_traitement_livre]
        taux_collecte = taux_collecte(vendeur.license)
        taux_retour = getattr(configuration(vendeur.license), 'taux_frais_retour', 50)
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_facture_colis.html', locals())


@login_required
def vendeur_detail_colis(request, code):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        article = Article.objects.all().exclude(statut_traitement=StatutTraitement.BROUILLON).get(code=code, vendeur=vendeur, etat_suppression=False)
        # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
        historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(
            statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
        # Frise de la maquette : étapes passées (rouges si échec ou retour), puis celles qui restent sur le parcours normal
        from management.espace_vendeur import ECHECS, etapes_a_venir
        statuts_echec = [str(x) for x in ECHECS] + [StatutTraitement.ANNULE]
        a_venir = etapes_a_venir(article)
        if article.statut_traitement == StatutTraitement.REVENU_ABIDJAN:
            from management.forms import libelle_localite_avec_delai
            from management.retours import jours_a_abidjan
            jours_retour = jours_a_abidjan(article)
            localites_substitution = [(l.pk, libelle_localite_avec_delai(l)) for l in Localite.objects.filter(
                license=vendeur.license, is_arrivee=True, etat_validation=True, etat_suppression=False).select_related('zone')]
    except Exception as e:
        raise Http404
    from management.notifications import messages_visibles
    fil = messages_visibles(request.user, article=article)
    return render(request, 'management/vendeur_detail_colis.html', locals())


@login_required
def vendeur_liste_colis(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
    except Vendeur.DoesNotExist:
        raise Http404
    # Shipping de la maquette : puces par statut, ville, recherche, période facultative, pages de 50 colis
    from django.core.paginator import Paginator
    from management.espace_vendeur import periode, shipping
    etape = request.GET.get('etape', '')
    ville = request.GET.get('ville', '')
    q = request.GET.get('q', '').strip()
    debut = fin = None
    if request.GET.get('du') or request.GET.get('au'):
        du, au, debut, fin = periode(request)
    colis, puces = shipping(vendeur, etape, ville, q, debut, fin)
    villes = (Article.objects.filter(vendeur=vendeur, etat_suppression=False, localite_arrivee__isnull=False)
              .values_list('localite_arrivee__nom', flat=True).distinct().order_by('localite_arrivee__nom'))
    page = Paginator(colis, 50).get_page(request.GET.get('page'))
    filtres = request.GET.copy()
    filtres.pop('page', None)
    filtres = filtres.urlencode()
    aujourdhui = timezone.localdate()
    hier, semaine = aujourdhui - timedelta(days=1), aujourdhui - timedelta(days=6)
    return render(request, 'management/vendeur_liste_colis.html', locals())


@login_required
def vendeur_liste_colis_reversement(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        articles = Article.objects.filter(vendeur=vendeur, etat_suppression=False, etat_encaissement=True).select_related('localite_arrivee')
        # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_liste_colis_reversement.html', locals())


@login_required
@droit_requis('vendeurs_voir')
def admin_liste_vendeurs(request):
    try:
        type_vendeur = request.GET.get('type_vendeur', StatutVendeur.ACTIF)
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff:

            vendeurs = vendeurs_visibles(user)
            suite_breadcrumb = "" 
            if type_vendeur == StatutVendeur.ATTENTE_APPROBATION:
                suite_breadcrumb = "En attente approbation" 
                vendeurs = vendeurs.filter(etat_approbation=False, etat_suppression=False, etat_validation=True)
            if type_vendeur == StatutVendeur.ACTIF:
                suite_breadcrumb = "Actifs" 
                vendeurs = vendeurs.filter(etat_approbation=True, etat_suppression=False, etat_validation=True)
            if type_vendeur == StatutVendeur.INACTIF:
                suite_breadcrumb = "Inactifs" 
                vendeurs = vendeurs.filter(etat_approbation=True, etat_suppression=False, etat_validation=False)
            if type_vendeur == StatutVendeur.SUPPRIME:
                suite_breadcrumb = "Supprimés" 
                vendeurs = vendeurs.filter(etat_suppression=True)
            type_profil_staff = TypeProfilStaffChoice
            # Vendeurs de la maquette : recherche, équipe qui suit, volumes sur 30 jours (jamais de montant)
            q = request.GET.get('q', '').strip()
            if q:
                vendeurs = vendeurs.filter(Q(code__icontains=q) | Q(nom_store__icontains=q) | Q(nom_contact__icontains=q)
                                           | Q(numero_contact__icontains=q) | Q(email__icontains=q))
            depuis = timezone.now() - timedelta(days=30)
            vendeurs = (vendeurs.select_related('commercial__user', 'agent_cod__user')
                        .annotate(commandes_30=Count('vendeur_article', filter=Q(vendeur_article__date_creation__gte=depuis,
                                                                                vendeur_article__etat_suppression=False)
                                                     & ~Q(vendeur_article__statut_traitement=StatutTraitement.BROUILLON)),
                                  derniere_commande=Max('vendeur_article__date_creation', filter=~Q(vendeur_article__statut_traitement=StatutTraitement.BROUILLON)))
                        .order_by('-date_creation'))

    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_vendeurs.html', locals())


@login_required
@droit_requis('vendeurs_voir')
def admin_vendeur_edit_profil(request, code):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff:

            vendeur = vendeurs_visibles(user).get(code=code)
            configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
            agents_cod = ProfilStaff.objects.filter(license=profil_staff.license, role_profil=TypeProfilStaffChoice.AGENT,
                                                    etat_validation=True, etat_suppression=False).select_related('user')
            commerciaux = ProfilStaff.objects.filter(license=profil_staff.license, role_profil=TypeProfilStaffChoice.COMMERCIAL,
                                                     etat_validation=True, etat_suppression=False).select_related('user')
            peut_approuver = a_le_droit(user, 'vendeurs_approuver')
            peut_supprimer = a_le_droit(user, 'vendeurs_supprimer')
            if request.method == 'POST':
                # Chaque action est vérifiée côté serveur selon le rôle
                actions_approbation = ("submit_approbation", "submit_activation", "submit_desactivation", "submit_affectation")
                if any(request.POST.get(a) for a in actions_approbation) and not peut_approuver:
                    raise PermissionDenied("Votre rôle ne permet pas de modifier ce vendeur.")
                if request.POST.get("submit_suppression") and not peut_supprimer:
                    raise PermissionDenied("Seule la direction peut supprimer un vendeur.")
                if "submit_approbation" in request.POST and request.POST["submit_approbation"]:
                    vendeur.etat_approbation = True
                    # Le commercial qui active le vendeur le suit, sauf s'il est déjà affecté
                    if vendeur.commercial_id is None and profil_staff.role_profil == TypeProfilStaffChoice.COMMERCIAL:
                        vendeur.commercial = profil_staff
                    vendeur.save()
                if "submit_activation" in request.POST and request.POST["submit_activation"]:
                    vendeur.etat_validation = True
                    vendeur.etat_suppression = False
                    vendeur.save()
                if "submit_desactivation" in request.POST and request.POST["submit_desactivation"]:
                    vendeur.etat_validation = False
                    vendeur.save()
                if "submit_suppression" in request.POST and request.POST["submit_suppression"]:
                    vendeur.etat_suppression = True
                    vendeur.save()
                if "submit_affectation" in request.POST and request.POST["submit_affectation"]:
                    vendeur.agent_cod = agents_cod.filter(code=request.POST.get("agent_cod")).first()
                    vendeur.option_stockage = bool(request.POST.get("option_stockage"))
                    if profil_staff.role_profil != TypeProfilStaffChoice.COMMERCIAL:
                        vendeur.commercial = commerciaux.filter(code=request.POST.get("commercial")).first()
                    vendeur.save()
                django_messages.success(request, "Vendeur %s mis à jour." % (vendeur.nom_store or vendeur.code))
                return redirect('management:management_admin_vendeur_edit_profil', vendeur.code)

            else:
                form = VendeurForm(instance=vendeur)
            from management.espace_vendeur import volumes_vendeur
            vol = volumes_vendeur(vendeur)
            type_vendeur = TypeVendeurChoice

    except PermissionDenied:
        raise
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_vendeur_edit_profil.html', locals())



@login_required
@droit_requis('vendeurs_voir')
def admin_vendeur_profil(request, code):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff:
            vendeur = vendeurs_visibles(user).get(code=code)
    except Exception as e:
        raise Http404
    # Une seule fiche vendeur (maquette) : informations, volumes, suivi par l'équipe et actions selon les droits
    return admin_vendeur_edit_profil(request, vendeur.code)


@login_required
@droit_requis('vendeurs_importer')
def admin_import_vendeur(request):
    type_vendeur = request.GET.get('type_vendeur', StatutVendeur.ACTIF)
    user = request.user
    profil_staff = user.account_profil_staff
    if user.is_authenticated and user.is_staff:
        if request.method == 'POST':
            dataset = Dataset()
            new_data = request.FILES['import_vendeur_file'] # Assuming 'myfile' is the name of your file input in the form

            # You can choose the format based on the file extension or a form selection
            if new_data.name.endswith('.xls') or new_data.name.endswith('.xlsx'):
                imported_data = dataset.load(new_data.read(), format='xlsx')
            # Add more formats as needed

            resource = VendeurResource()
            result = resource.import_data(imported_data, dry_run=True) # dry_run for previewing changes
            if not result.has_errors():
                resource.import_data(imported_data, dry_run=False) # Actual import
                # return redirect('success_url') # Redirect to a success page
            else:
                errors = result.errors
                # Handle errors, e.g., display them on the template
                #return render(request, 'myapp/import_form.html', {'errors': result.errors})

    return render(request, 'management/admin_import_vendeur_form.html', locals())

    
@login_required
@droit_requis('colis_voir')
def admin_liste_colis(request):
    from django.core.paginator import Paginator
    from management.actions_colis import filtrer_colis, statuts_groupes
    user = request.user
    profil_staff = user.account_profil_staff
    articles, ctx = filtrer_colis(profil_staff.license, request.GET)
    type_colis, suite_breadcrumb, jours_historique = ctx['type_colis'], ctx['suite_breadcrumb'], ctx.get('jours_historique')
    q, vendeur_filtre, ville, statut_filtre = ctx['q'], ctx['vendeur_filtre'], ctx['ville'], ctx['statut_filtre']
    du, au = ctx['du'], ctx['au']
    vendeurs_liste = Vendeur.objects.filter(license=profil_staff.license, etat_suppression=False, etat_approbation=True).order_by('nom_store').values_list('code', 'nom_store')
    villes = (Article.objects.filter(license=profil_staff.license, etat_suppression=False, localite_arrivee__isnull=False)
              .values_list('localite_arrivee__nom', flat=True).distinct().order_by('localite_arrivee__nom'))
    statuts_filtre = [(v, l) for v, l in ORDRE_STATUTS_LIBELLES()]
    page = Paginator(articles, 50).get_page(request.GET.get('page'))
    filtres = request.GET.copy()
    filtres.pop('page', None)
    filtres = filtres.urlencode()
    groupes_statuts = statuts_groupes(user)
    peut_bouger = a_le_droit(user, 'colis_mouvements')
    peut_corriger = a_le_droit(user, 'colis_corriger')
    peut_unpaid = a_le_droit(user, 'paiements')
    peut_imprimer = a_le_droit(user, 'colis_imprimer')
    return render(request, 'management/admin_liste_colis.html', locals())


def ORDRE_STATUTS_LIBELLES():
    libelles = dict(StatutTraitement.choices)
    return [(v, libelles[v]) for v in ORDRE_STATUTS]


@login_required
@droit_requis('colis_voir', 'vendeurs_voir')
def admin_liste_colis_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-nombre_articles_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_colis_vendeurs.html', locals())


@login_required
@droit_requis('colis_voir')
def admin_detail_colis(request, code):

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:
            #vendeur = Vendeur.objects.get(user=user)
            # Un colis d'une autre licence n'existe pas pour cet utilisateur
            article = Article.objects.filter(license=profil_staff.license).exclude(statut_traitement=StatutTraitement.BROUILLON).select_related(
                'vendeur', 'localite_arrivee', 'localite_arrivee__zone', 'format_article').get(code=code)
            peut_bouger = a_le_droit(user, 'colis_mouvements') or a_le_droit(user, 'paiements')
            peut_annuler_mouvement = a_le_droit(user, 'colis_annuler_mouvement')
            peut_payer = a_le_droit(user, 'paiements')
            acomptes_article = article.acomptes.all().order_by('-date_reception')
            from management.retours import jours_a_abidjan
            jours_retour = jours_a_abidjan(article)
            appels_article = article.appels.select_related('agent').order_by('-date')[:20]
            # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
            # statut_traitement = StatutTraitement
            # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
            historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).order_by("date_creation")
            reglement_articles = article.article_reglementarticles.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation")
            encaissement_articles = article.article_encaissements.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation")
            reversement_articles = article.article_reversements.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation")
            reglement_article = reglement_articles.filter(montant_restant=0).first() if reglement_articles else None 
            encaissement_article = encaissement_articles.first() if encaissement_articles else None 
            reversement_article = reversement_articles.filter(montant_restant=0).first() if reversement_articles else None 
                
            # Statuts proposés : table de transitions unique (management/statuts.py), vérifiée aussi au POST
            dernier_historique = article.get_last_historique()
            statut_traitement_applicables = statuts_suivants(article, dernier_historique, user) if peut_bouger else []
            statuts_corrigibles = statuts_correction(article, user)
            peut_modifier_commande = a_le_droit(user, 'colis_modifier')
            from management.notifications import messages_visibles
            fil = messages_visibles(user, article=article)

            # print(statut_traitement_applicables)

            if request.method == 'POST':
                # Droits vérifiés côté serveur, action par action
                if request.POST.get("submit_new_mouvement") and not peut_bouger:
                    raise PermissionDenied("Votre rôle ne permet pas de changer le statut d'un colis.")
                if request.POST.get("submit_annuler_last_mouvement") and not peut_annuler_mouvement:
                    raise PermissionDenied("Seuls le manager et la direction peuvent annuler un mouvement.")
                if any(request.POST.get(a) for a in ("submit_new_reglement", "submit_annuler_reglement",
                                                     "submit_new_reversement", "submit_annuler_reversement")) and not peut_payer:
                    raise PermissionDenied("Seules la comptable et la direction gèrent les paiements.")

                if "submit_annuler_last_mouvement" in request.POST and request.POST["submit_annuler_last_mouvement"]:
                    if str(article.get_last_historique().id) == request.POST["last_mouvement"]:
                        if article.statut_traitement in (StatutTraitement.BROUILLON, StatutTraitement.EN_ATTENTE_DEPOT, StatutTraitement.EN_ATTENTE_RAMASSAGE):
                            article.statut_traitement = StatutTraitement.BROUILLON
                            article.etat_validation = False
                        else:
                            article.statut_traitement = article.get_last_historique().dernier_historique_article.statut_traitement 
                        
                        if article.etat_encaissement is True and article.get_last_historique().statut_traitement == StatutTraitement.LIVRE_PAYE:
                            encaissement_a_supprime = article.get_last_encaissement()
                            encaissement_a_supprime.etat_suppression = True
                            encaissement_a_supprime.save()
                            article.etat_encaissement = False

                        historique_a_supprime = article.get_last_historique()
                        historique_a_supprime.etat_suppression = True
                        # historique_a_supprime.etat_validation = False
                        historique_a_supprime.save()
                        article.save()
                        
                if request.POST.get("submit_modifier_commande"):
                    if not a_le_droit(user, 'colis_modifier'):
                        raise PermissionDenied("Seul le CEO modifie les données d'une commande.")
                    from management.finance import comptabiliser, recalculer_frais_colis
                    for champ in ('nom_destinataire', 'prenom_destinataire', 'numero_principal_destinataire',
                                  'numero_secondaire_destinataire', 'adresse_destinataire', 'designation', 'reference_externe'):
                        if champ in request.POST:
                            setattr(article, champ, (request.POST.get(champ) or '').strip() or None)
                    try:
                        quantite = max(1, int(request.POST.get('quantite') or article.quantite or 1))
                        valeur = Decimal(str(request.POST.get('valeur_totale') or article.valeur_totale or 0).replace(' ', '').replace(',', '.'))
                        if valeur < 0:
                            raise InvalidOperation
                    except (ValueError, InvalidOperation):
                        django_messages.error(request, "Quantité ou montant invalide.")
                    else:
                      nouvelle_ref = article.reference_externe
                      if nouvelle_ref and Article.objects.filter(vendeur=article.vendeur, source=article.source, reference_externe=nouvelle_ref).exclude(pk=article.pk).exists():
                        django_messages.error(request, "La référence %s est déjà utilisée par une autre commande de ce vendeur." % nouvelle_ref)
                      else:
                        article.quantite = quantite
                        if valeur != (article.valeur_totale or 0):
                            article.valeur_totale = valeur
                            recalculer_frais_colis(article)
                        article.save()
                        comptabiliser(article)
                        django_messages.success(request, "Commande modifiée (l'ancienne et la nouvelle valeur sont gardées dans le journal d'audit).")

                if request.POST.get("submit_correction"):
                    if _id_dernier(article) != request.POST.get("last_mouvement", ""):
                        django_messages.error(request, "Le colis a bougé entre-temps : rechargez la page.")
                    else:
                        ok, raison = appliquer_mouvement(article, request.POST.get("correction_statut"), user,
                                                         request.POST.get("correction_motif"), correction=True)
                        if ok:
                            django_messages.success(request, "Statut corrigé.")
                        else:
                            django_messages.error(request, raison)

                if "submit_new_mouvement" in request.POST and request.POST["submit_new_mouvement"]:
                    if _id_dernier(article) != request.POST.get("last_mouvement", ""):
                        django_messages.error(request, "Le colis a bougé entre-temps : rechargez la page.")
                    else:
                        if not article.code_tracking and request.POST.get("mouvement_code_tracking"):
                            article.code_tracking = request.POST["mouvement_code_tracking"]
                        ok, raison = appliquer_mouvement(article, request.POST.get("mouvement_statut"), user,
                                                         request.POST.get("mouvement_commentaire"),
                                                         date=request.POST.get("mouvement_date") or None)
                        if not ok:
                            django_messages.error(request, raison)

                if "submit_annuler_reglement" in request.POST and request.POST["submit_annuler_reglement"]:
                    if str(article.get_last_reglement().id) == request.POST["last_reglement"]:

                        reglement_a_supprime = article.get_last_reglement()
                        reglement_a_supprime.etat_suppression = True
                        reglement_a_supprime.save()
                        
                        article.etat_reglement = False
                        article.save()
                        
                if "submit_new_reglement" in request.POST and request.POST["submit_new_reglement"]:
                    if article.etat_reglement is False and (int(request.POST["paiement_montant"]) + int(request.POST["paiement_reduction"])) == int(article.montant_total_frais) :
                        reglement = ReglementArticle()
                        reglement.article = article
                        reglement.date = request.POST["paiement_date"]
                        reglement.reference = request.POST["paiement_reference"]
                        reglement.montant_reglement = request.POST["paiement_montant"]
                        reglement.montant_reduction = request.POST["paiement_reduction"]
                        reglement.save()
                        
                    # rediriger vers details colis
                    # article.statut_traitement =  StatutTraitement.EN_ATTENTE_RAMASSAGE if article.is_option_recuperation is True else StatutTraitement.EN_ATTENTE_DEPOT
                    # article.save()


                if "submit_annuler_reversement" in request.POST and request.POST["submit_annuler_reversement"]:
                    if str(article.get_last_reversement().id) == request.POST["last_reversement"]:
                        if article.etat_encaissement is True and article.get_last_historique().statut_traitement == StatutTraitement.REVERSE:
                            reversement_a_supprime = article.get_last_reversement()
                            reversement_a_supprime.etat_suppression = True
                            reversement_a_supprime.save()

                            article.statut_traitement = article.get_last_historique().dernier_historique_article.statut_traitement 
                            article.etat_reversement = False

                            historique_a_supprime = article.get_last_historique()
                            historique_a_supprime.etat_suppression = True
                            # historique_a_supprime.etat_validation = False
                            historique_a_supprime.save()

                            article.save()

                            # article = delete_reglement(article)
                        
                if request.POST.get("submit_new_reversement") and article.ecritures.exclude(type='cout_prestataire').exists():
                    # Colis suivi par les relevés du lundi et du jeudi : pas de reversement à l'unité (double paiement)
                    django_messages.error(request, "Ce colis est versé par les factures de paiement (menu Paiements vendeurs), pas à l'unité.")
                elif "submit_new_reversement" in request.POST and request.POST["submit_new_reversement"]:             
                    if str(article.get_last_encaissement().pk) == request.POST["last_encaissement"] and article.is_option_encaissement is True and  article.statut_traitement == article.get_last_historique().statut_traitement and article.statut_traitement == StatutTraitement.LIVRE_PAYE:
                        new_reversement = Reversement()
                        new_reversement.article = article
                        new_reversement.encaissement = article.get_last_encaissement()
                        new_reversement.date = request.POST["reversement_date"]
                        new_reversement.reference = request.POST["reversement_reference"]
                        new_reversement.montant_reversement = request.POST["reversement_montant"]
                        new_reversement.save()

                        # if article.etat_reglement:
                        #    reglement = do_reglement(article, request.POST["reversement_date"], request.POST["reversement_reference"], article.montant_total_frais, None)
                        #    new_encaissement.save()
                        #    article.etat_encaissement = True
                        #    article.save()
                            
                if article.etat_suppression is True:
                    return HttpResponseRedirect(reverse('management:management_admin_liste_colis')) 
                return redirect('management:management_admin_detail_colis', article.code)
                
    except PermissionDenied:
        raise
    except Exception:
        # Ne jamais afficher le détail de l'erreur à l'écran (dd() exposait les données en production)
        logger.exception("admin_detail_colis %s", code)
        raise Http404
    from management.espace_vendeur import ECHECS
    statuts_echec = [str(x) for x in ECHECS] + [StatutTraitement.ANNULE]
    return render(request, 'management/admin_detail_colis.html', locals())

def _id_dernier(article):
    dernier = article.get_last_historique()
    return str(dernier.pk) if dernier else ''


def do_reglement(article, paiement_date, paiement_reference, paiement_montant, paiement_reduction):
    reglement = ReglementArticle()
    reglement.article = article
    reglement.date = paiement_date
    reglement.reference = paiement_reference
    reglement.montant_reglement = paiement_montant
    reglement.montant_reduction = paiement_reduction
    reglement.save()
    return reglement

def delete_reglement(article):
    reglement_a_supprime = article.get_last_reglement()
    reglement_a_supprime.etat_suppression = True
    reglement_a_supprime.save()
    
    article.etat_reglement = False
    article.save()
    return article


@login_required
@droit_requis('paiements')
def admin_liste_paiements(request):
    try:
        type_paiements = request.GET.get('type_paiements', "en_attente")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).select_related('vendeur', 'localite_arrivee')
            suite_breadcrumb = "" 
            if type_paiements == "en_attente":
                suite_breadcrumb = "En attente" 
                articles = articles.filter(etat_reglement=False)
            if type_paiements == "historique":
                suite_breadcrumb = "Historique"
                articles = articles.filter(etat_reglement=True)

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_paiements.html', locals())


@login_required
@droit_requis('paiements')
def admin_liste_paiements_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-montant_frais_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_paiements_vendeurs.html', locals())


@login_required
@droit_requis('paiements')
def admin_liste_reversements(request):
    try:
        type_reversements = request.GET.get('type_reversements', "en_attente")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False, etat_encaissement=True).exclude(statut_traitement=StatutTraitement.BROUILLON).exclude(statut_traitement__in=array_statut_traitement_retour).select_related('vendeur', 'localite_arrivee')
            suite_breadcrumb = "" 
            if type_reversements == "en_attente":
                suite_breadcrumb = "En attente" 
                articles = articles.filter(etat_reversement=False)
            if type_reversements == "historique":
                suite_breadcrumb = "Historique"
                articles = articles.filter(etat_reversement=True)

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_reversements.html', locals())


@login_required
@droit_requis('paiements')
def admin_liste_reversements_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-montant_reversement_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_reversements_vendeurs.html', locals())


@login_required
@droit_requis('activites_colis')
def admin_mouvements_colis(request):
    try:
        statut_traitement_selected = request.GET.get('statut_traitement_selected', None)
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            historiques = HistoriqueArticle.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).select_related('article', 'article__vendeur', 'creation_par__account_profil_staff').order_by("-date_creation")
            vendeurs = Vendeur.objects.filter(license=profil_staff.license, vendeur_article__article_historiquearticle__isnull=False).exclude(vendeur_article__article_historiquearticle__statut_traitement=StatutTraitement.BROUILLON).distinct().order_by("-nom_store")
            statut_traitement_applicables = [
                (value, label) for value, label in StatutTraitement.choices
                if value != StatutTraitement.BROUILLON
            ]
            suite_breadcrumb = "" 
            if statut_traitement_selected:
                historiques = historiques.filter(statut_traitement=statut_traitement_selected)
            if vendeur_selected:
                historiques = historiques.filter(article__vendeur__code=vendeur_selected)
            if debut_selected:
                historiques = historiques.filter(date_creation__date__gte=debut_selected)
            if fin_selected:
                historiques = historiques.filter(date_creation__date__lte=fin_selected)
            if debut_selected is None and fin_selected is None:
                debut_selected = timezone.now().strftime("%Y-%m-%d")
                fin_selected = timezone.now().strftime("%Y-%m-%d")
                historiques = historiques.filter(date_creation__date__gte=debut_selected, date_creation__date__lte=fin_selected)

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_mouvements_colis.html', locals())


@login_required
@droit_requis('activites_argent')
def admin_activites_paiements(request):
    try:
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            reglements = ReglementArticle.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).select_related('article', 'vendeur', 'creation_par__account_profil_staff').order_by("-date_creation")
            vendeurs = Vendeur.objects.filter(license=profil_staff.license, vendeur_reglementarticle__isnull=False).distinct().order_by("-nom_store")
            
            suite_breadcrumb = "" 
            if vendeur_selected:
                reglements = reglements.filter(article__vendeur__code=vendeur_selected)
            if debut_selected:
                reglements = reglements.filter(date_creation__date__gte=debut_selected)
            if fin_selected:
                reglements = reglements.filter(date_creation__date__lte=fin_selected)

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_activites_paiements.html', locals())


@login_required
@droit_requis('activites_argent')
def admin_activites_reversements(request):
    try:
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            reversements = Reversement.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).select_related('article', 'vendeur', 'creation_par__account_profil_staff').order_by("-date_creation")
            vendeurs = Vendeur.objects.filter(license=profil_staff.license, vendeur_reversement__isnull=False).distinct().order_by("-nom_store")
            
            suite_breadcrumb = "" 
            if vendeur_selected:
                reversements = reversements.filter(article__vendeur__code=vendeur_selected)
            if debut_selected:
                reversements = reversements.filter(date_creation__date__gte=debut_selected)
            if fin_selected:
                reversements = reversements.filter(date_creation__date__lte=fin_selected)

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_activites_reversements.html', locals())




# ---------------------------------------------------------------------------
# Confirmation des commandes (agents COD) et acomptes (comptable)
# ---------------------------------------------------------------------------

@login_required
@droit_requis('confirmations')
def admin_confirmations(request):
    """File d'appels de l'agent COD : confirmer, noter injoignable, ou annuler avec motif."""
    from management.confirmation import enregistrer_appel, file_de_confirmation
    from mlshipafrica.enums import ReseauPaiement, ResultatAppel
    user = request.user
    profil_staff = user.account_profil_staff
    configuration = Configuration.objects.filter(license=profil_staff.license, etat_validation=True,
                                                 etat_suppression=False).order_by("-pk").first()
    montant_acompte = configuration.montant_acompte if configuration else 2000

    if request.method == 'POST':
        article = file_de_confirmation(profil_staff).filter(code=request.POST.get('article')).first()
        if article is None:
            django_messages.error(request, "Ce colis n'est plus dans votre file.")
        else:
            resultat = request.POST.get('resultat')
            acompte = None
            if resultat == ResultatAppel.CONFIRME and request.POST.get('acompte_reference'):
                acompte = {'montant': montant_acompte, 'reseau': request.POST.get('acompte_reseau'),
                           'reference_depot': request.POST.get('acompte_reference'),
                           'numero_depot': request.POST.get('acompte_numero', '')}
            # Motif d'annulation choisi dans la liste de la maquette, précisé par le commentaire
            commentaire = ' · '.join(x for x in (request.POST.get('motif', '').strip(), request.POST.get('commentaire', '').strip()) if x)
            try:
                if resultat not in ResultatAppel.values:
                    raise ValidationError("Résultat d'appel inconnu.")
                enregistrer_appel(article, user, resultat, commentaire, acompte)
                django_messages.success(request, "Colis %s : %s." % (article.code, ResultatAppel(resultat).label.lower()))
            except ValidationError as erreur:
                django_messages.error(request, "Colis %s : %s" % (article.code, ' '.join(erreur.messages)))
        return redirect(reverse('management:management_admin_confirmations') + '?' + request.GET.urlencode())

    articles = file_de_confirmation(profil_staff)
    filtre = request.GET.get('filtre', 'tous')
    if filtre in ('a_confirmer', 'injoignable'):
        articles = articles.filter(etat_confirmation=filtre)
    agent_selected = request.GET.get('agent')
    if agent_selected and profil_staff.role_profil != TypeProfilStaffChoice.AGENT:
        articles = articles.filter(agent_cod__code=agent_selected) if agent_selected != 'aucun' else articles.filter(agent_cod__isnull=True)
    agents = ProfilStaff.objects.filter(license=profil_staff.license, role_profil=TypeProfilStaffChoice.AGENT,
                                        etat_suppression=False).select_related('user')
    reseaux = ReseauPaiement.choices
    resultat_appel = ResultatAppel
    # Écran de la maquette : à appeler / confirmées en attente de réception, et les compteurs du jour
    from management.confirmation import MOTIFS_ANNULATION, confirmees_en_attente
    file_complete = file_de_confirmation(profil_staff)
    nb_jamais = file_complete.filter(etat_confirmation='a_confirmer').count()
    nb_rappeler = file_complete.filter(etat_confirmation='injoignable').count()
    en_attente = confirmees_en_attente(profil_staff)
    debut_jour = timezone.make_aware(datetime.datetime.combine(timezone.localdate(), datetime.time.min))
    confirmees_jour = Article.objects.filter(license=profil_staff.license, etat_confirmation='confirme', date_confirmation__gte=debut_jour)
    if profil_staff.role_profil == TypeProfilStaffChoice.AGENT:
        confirmees_jour = confirmees_jour.filter(Q(agent_cod=profil_staff) | Q(confirme_par=user))
    nb_confirmees_jour = confirmees_jour.count()
    vue = 'attente' if request.GET.get('vue') == 'attente' else 'appel'
    if vue == 'attente':
        articles = en_attente
    motifs = MOTIFS_ANNULATION
    # Cartes de résultats du mois (volumes seulement) si une commission active concerne cet agent
    from management.commissions import cartes_pour
    cartes_resultats = cartes_pour(profil_staff, timezone.make_aware(datetime.datetime.combine(timezone.localdate().replace(day=1), datetime.time.min)),
                                   timezone.now() + timedelta(seconds=1))
    suite_breadcrumb = "Confirmations"
    return render(request, 'management/admin_confirmations.html', locals())


@login_required
@droit_requis('acomptes')
def admin_acomptes(request):
    """Acomptes des clients : à rembourser (annulés avant expédition), reçus, remboursés."""
    from management.confirmation import marquer_rembourse
    from management.models import Acompte
    from mlshipafrica.enums import StatutAcompte
    user = request.user
    profil_staff = user.account_profil_staff
    acomptes = Acompte.objects.filter(license=profil_staff.license).select_related(
        'article', 'article__vendeur', 'recu_par', 'rembourse_par')

    if request.method == 'POST':
        acompte = acomptes.filter(pk=request.POST.get('acompte')).first()
        try:
            if acompte is None:
                raise ValidationError("Acompte introuvable.")
            marquer_rembourse(acompte, user, request.POST.get('reference', ''))
            django_messages.success(request, "Acompte du colis %s marqué remboursé." % acompte.article.code)
        except ValidationError as erreur:
            django_messages.error(request, ' '.join(erreur.messages))
        return redirect(reverse('management:management_admin_acomptes') + '?' + request.GET.urlencode())

    statut_selected = request.GET.get('statut', StatutAcompte.A_REMBOURSER)
    if statut_selected in StatutAcompte.values:
        acomptes = acomptes.filter(statut=statut_selected)
    compteurs = {s: Acompte.objects.filter(license=profil_staff.license, statut=s).count() for s in StatutAcompte.values}
    # Indicateurs de la maquette : total par statut et répartition par réseau (rapprochement Wave, Orange, MTN, Moov)
    tous_acomptes = Acompte.objects.filter(license=profil_staff.license)
    totaux_statut = [{'cle': v, 'libelle': l, 'n': compteurs.get(v, 0),
                      'total': tous_acomptes.filter(statut=v).aggregate(t=Sum('montant'))['t'] or 0} for v, l in StatutAcompte.choices]
    par_reseau = list(acomptes.values('reseau').annotate(n=Count('id'), t=Sum('montant')).order_by('-n'))
    from mlshipafrica.enums import ReseauPaiement
    for r in par_reseau:
        r['libelle'] = ReseauPaiement(r['reseau']).label if r['reseau'] in ReseauPaiement.values else r['reseau']
    statuts_acompte = StatutAcompte
    suite_breadcrumb = "Acomptes"
    return render(request, 'management/admin_acomptes.html', locals())


@login_required
@transaction.atomic
def vendeur_substituer_colis(request, code):
    """Le vendeur donne un nouveau client pour son colis revenu à Abidjan."""
    from management.retours import substituer
    user = request.user
    try:
        vendeur = Vendeur.objects.get(user=user)
        article = Article.objects.get(code=code, vendeur=vendeur, etat_suppression=False)
    except (Vendeur.DoesNotExist, Article.DoesNotExist):
        raise Http404
    if request.method == 'POST':
        localite = Localite.objects.filter(pk=request.POST.get('localite'), license=vendeur.license, is_arrivee=True,
                                           etat_validation=True, etat_suppression=False).first()
        valeur = request.POST.get('valeur')
        try:
            substituer(article, user, {
                'nom': request.POST.get('nom', '')[:100], 'prenom': request.POST.get('prenom', '')[:255],
                'numero_principal': request.POST.get('numero_principal', '').strip(),
                'numero_secondaire': request.POST.get('numero_secondaire', '').strip(),
                'adresse': request.POST.get('adresse', '')[:255], 'localite': localite,
                'valeur': Decimal(valeur) if valeur not in (None, '') else None,
            })
            django_messages.success(request, "Nouveau client enregistré : le colis repart en préparation.")
        except (ValidationError, ArithmeticError) as erreur:
            django_messages.error(request, ' '.join(getattr(erreur, 'messages', [str(erreur)])))
    return redirect('management:management_vendeur_detail_colis', article.code)


# ---------------------------------------------------------------------------
# Stock (vendeurs en stockage)
# ---------------------------------------------------------------------------

@login_required
def vendeur_stock(request):
    """Le vendeur voit son stock, ses mouvements, son coût de stockage, et annonce un envoi."""
    from management.models import EntreeStock, FacturationStockage, MouvementStock
    from management.stock import annoncer_entree
    try:
        vendeur = Vendeur.objects.get(user=request.user)
    except Vendeur.DoesNotExist:
        raise Http404
    if not vendeur.option_stockage:
        # Pas encore en stockage : on explique l'offre et le vendeur peut la demander
        if request.method == 'POST' and request.POST.get('demander_stockage'):
            if not vendeur.demande_stockage_le:
                vendeur.demande_stockage_le = timezone.now()
                vendeur.save(update_fields=['demande_stockage_le'])
                from management.notifications import stockage_demande
                stockage_demande(vendeur)
            django_messages.success(request, "Demande envoyée : votre commercial vous rappelle pour activer le stockage.")
            return redirect('management:management_vendeur_stock')
        from management.finance import configuration
        tarif_stockage = getattr(configuration(vendeur.license), 'tarif_stockage_jour', None)
        return render(request, 'management/vendeur_stock_offre.html', locals())
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'creer_produit':
            reference = (request.POST.get('reference') or '').strip()[:60]
            designation = (request.POST.get('designation') or '').strip()[:150]
            if not reference or not designation:
                django_messages.error(request, "Indiquez la référence et le nom du produit.")
            elif ProduitStock.objects.filter(vendeur=vendeur, reference__iexact=reference).exists():
                django_messages.error(request, "La référence %s existe déjà dans vos produits." % reference)
            else:
                ProduitStock.objects.create(vendeur=vendeur, reference=reference, designation=designation,
                                            photo=request.FILES.get('photo') or None)
                django_messages.success(request, "Produit %s créé. Faites un envoi de stock pour le remplir." % designation)
            return redirect('management:management_vendeur_stock')
        if action == 'envoi':
            produits_choisis = {str(p.pk): p for p in vendeur.produits_stock.filter(actif=True)}
            lignes = []
            try:
                for pid, q in zip(request.POST.getlist('produit'), request.POST.getlist('quantite')):
                    if pid in produits_choisis and int(q or 0) > 0:
                        p = produits_choisis[pid]
                        lignes.append((p.reference, p.designation, int(q), p.photo or None))
                entree = annoncer_entree(vendeur, lignes, request.POST.get('commentaire', ''))
            except (ValidationError, ValueError) as erreur:
                django_messages.error(request, ' '.join(getattr(erreur, 'messages', ["Quantité invalide."])))
                return redirect('management:management_vendeur_stock')
            from management.notifications import stock_annonce
            stock_annonce(entree)
            django_messages.success(request, "Envoi %s créé : imprimez le bordereau en 2 exemplaires et remettez-le avec vos produits." % entree.code)
            return redirect('management:management_vendeur_bordereau_stock', entree.code)
        return redirect('management:management_vendeur_stock')
    from management.models import Ecriture, LigneEntreeStock
    from mlshipafrica.enums import StatutEntreeStock, StatutReleve, TypeEcriture
    produits = list(vendeur.produits_stock.filter(actif=True).order_by('designation'))
    en_route = dict(LigneEntreeStock.objects.filter(entree__vendeur=vendeur, entree__statut=StatutEntreeStock.ANNONCEE)
                    .values_list('reference').annotate(t=Sum('quantite_annoncee')))
    for p in produits:
        p.en_route = en_route.get(p.reference, 0)
    entrees = EntreeStock.objects.filter(vendeur=vendeur).prefetch_related('lignes')[:30]
    mouvements = MouvementStock.objects.filter(produit__vendeur=vendeur).select_related('produit', 'article')[:50]
    debut_mois = timezone.localdate().replace(day=1)
    stockage_mois = FacturationStockage.objects.filter(vendeur=vendeur, jour__gte=debut_mois).aggregate(t=Sum('montant'))['t'] or 0
    # Stockage déjà déduit : lignes de stockage du mois reprises sur une facture de paiement (non annulée)
    debut_mois_dt = timezone.make_aware(datetime.datetime.combine(debut_mois, datetime.time.min))
    lignes_stockage = Ecriture.objects.filter(vendeur=vendeur, type=TypeEcriture.STOCKAGE, date__gte=debut_mois_dt)
    stockage_deduit = lignes_stockage.filter(releve__isnull=False).exclude(releve__statut=StatutReleve.ANNULE).aggregate(t=Sum('montant'))['t'] or 0
    stockage_a_deduire = max((stockage_mois or 0) - stockage_deduit, 0)
    dernier_releve_stockage = (lignes_stockage.filter(releve__isnull=False).exclude(releve__statut=StatutReleve.ANNULE)
                               .select_related('releve').order_by('-releve__date_creation').first())
    from management.finance import configuration
    tarif_stockage = getattr(configuration(vendeur.license), 'tarif_stockage_jour', None)
    pieces = sum(max(p.quantite_disponible, 0) for p in produits)
    epuises = sum(1 for p in produits if p.quantite_disponible <= 0)
    de_cote = sum(p.quantite_de_cote for p in produits)
    envois_en_attente = sum(1 for e in entrees if e.statut == StatutEntreeStock.ANNONCEE)
    return render(request, 'management/vendeur_stock.html', locals())


@login_required
@droit_requis('stock')
def admin_stock(request):
    """Manager : réceptions de stock à contrôler, inventaire par vendeur, ajustements."""
    from management.models import EntreeStock, ProduitStock
    from management.stock import ajuster, valider_reception
    from mlshipafrica.enums import StatutEntreeStock
    user = request.user
    profil_staff = user.account_profil_staff
    if request.method == 'POST':
        try:
            if request.POST.get('valider_entree'):
                entree = EntreeStock.objects.get(pk=request.POST['valider_entree'], vendeur__license=profil_staff.license)
                quantites = {int(k.split('_')[1]): int(v or 0) for k, v in request.POST.items() if k.startswith('recu_')}
                valider_reception(entree, user, quantites)
                from management.notifications import stock_valide
                stock_valide(entree)
                django_messages.success(request, "Bordereau %s validé, le vendeur est prévenu par SMS." % entree.code)
            elif request.POST.get('ajuster_produit'):
                produit = ProduitStock.objects.get(pk=request.POST['ajuster_produit'], vendeur__license=profil_staff.license)
                ajuster(produit, user, int(request.POST.get('delta') or 0), request.POST.get('motif', ''))
                django_messages.success(request, "Stock de %s ajusté." % produit.designation)
        except (ValidationError, ValueError, EntreeStock.DoesNotExist, ProduitStock.DoesNotExist) as erreur:
            django_messages.error(request, ' '.join(getattr(erreur, 'messages', ["Saisie invalide."])))
        return redirect(reverse('management:management_admin_stock') + '?' + request.GET.urlencode())
    entrees_a_recevoir = (EntreeStock.objects.filter(vendeur__license=profil_staff.license, statut=StatutEntreeStock.ANNONCEE)
                          .select_related('vendeur').prefetch_related('lignes'))
    vendeurs_stockage = Vendeur.objects.filter(license=profil_staff.license, option_stockage=True, etat_suppression=False)
    vendeur_selected = request.GET.get('vendeur')
    produits = ProduitStock.objects.filter(vendeur__license=profil_staff.license).select_related('vendeur')
    if vendeur_selected:
        produits = produits.filter(vendeur__code=vendeur_selected)
    # Indicateurs de la maquette
    kpi_pieces = produits.aggregate(t=Sum('quantite_disponible'))['t'] or 0
    kpi_epuises = produits.filter(actif=True, quantite_disponible__lte=0).count()
    kpi_de_cote = produits.aggregate(t=Sum('quantite_de_cote'))['t'] or 0
    from management.models import MouvementStock
    mouvements = MouvementStock.objects.filter(produit__vendeur__license=profil_staff.license).select_related('produit__vendeur', 'article', 'par')
    if vendeur_selected:
        mouvements = mouvements.filter(produit__vendeur__code=vendeur_selected)
    mouvements = mouvements.order_by('-date')[:30]
    suite_breadcrumb = "Stock"
    return render(request, 'management/admin_stock.html', locals())


# ---------------------------------------------------------------------------
# Argent : relevés, bénéfice, fichier prestataire
# ---------------------------------------------------------------------------

def _periode(request):
    """jour (défaut), semaine, mois ou dates libres ?du=AAAA-MM-JJ&au=AAAA-MM-JJ → (début, fin, libellé)."""
    from datetime import datetime, time as dtime
    aujourd_hui = timezone.localdate()
    periode = request.GET.get('periode', 'jour')
    if periode == 'semaine':
        debut = aujourd_hui - timedelta(days=aujourd_hui.weekday())
        fin = aujourd_hui + timedelta(days=1)
    elif periode == 'mois':
        debut, fin = aujourd_hui.replace(day=1), aujourd_hui + timedelta(days=1)
    elif periode == 'dates':
        try:
            debut = datetime.strptime(request.GET.get('du', ''), '%Y-%m-%d').date()
            fin = datetime.strptime(request.GET.get('au', ''), '%Y-%m-%d').date() + timedelta(days=1)
        except ValueError:
            periode, debut, fin = 'jour', aujourd_hui, aujourd_hui + timedelta(days=1)
    else:
        periode, debut, fin = 'jour', aujourd_hui, aujourd_hui + timedelta(days=1)
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(debut, dtime.min), tz), timezone.make_aware(datetime.combine(fin, dtime.min), tz),
            periode, debut, fin - timedelta(days=1))


@login_required
@droit_requis('moyens_versement')
def admin_moyens_versement(request):
    """
    Moyens de paiement des vendeurs : la comptable vérifie la procuration de chaque nouveau numéro avant tout
    versement (validé / refusé avec motif). Le CEO règle les frais de versement, à la charge du vendeur.
    """
    from management.finance import refuser_coordonnees, valider_coordonnees
    from management.models import FraisVersement
    from mlshipafrica.enums import MoyenVersement
    user = request.user
    profil_staff = user.account_profil_staff
    peut_regler_frais = a_le_droit(user, 'frais_versement_regler')
    vendeurs = Vendeur.objects.filter(license=profil_staff.license, etat_suppression=False)
    if request.method == 'POST':
        try:
            if request.POST.get('frais'):
                if not peut_regler_frais:
                    raise PermissionDenied("Seul le CEO règle les frais de versement.")
                for moyen in MoyenVersement.values:
                    taux = (request.POST.get('taux_' + moyen) or '0').replace(',', '.').strip()
                    plafond = (request.POST.get('plafond_' + moyen) or '').replace(' ', '').strip()
                    regle, _ = FraisVersement.objects.get_or_create(moyen=moyen)
                    regle.taux = Decimal(taux or '0')
                    regle.plafond = Decimal(plafond) if plafond else None
                    if regle.taux < 0 or regle.taux > 10:
                        raise ValidationError("Un taux de frais doit être entre 0 et 10 %.")
                    regle.save()
                django_messages.success(request, "Frais de versement enregistrés.")
            else:
                vendeur = vendeurs.get(code=request.POST.get('vendeur'))
                if request.POST.get('action') == 'valider':
                    valider_coordonnees(vendeur, user)
                    django_messages.success(request, "Coordonnées de %s validées : les versements peuvent reprendre." % (vendeur.nom_store or vendeur.code))
                else:
                    refuser_coordonnees(vendeur, user, request.POST.get('motif', ''))
                    django_messages.success(request, "Changement de %s refusé." % (vendeur.nom_store or vendeur.code))
        except (ValidationError, Vendeur.DoesNotExist, InvalidOperation) as erreur:
            django_messages.error(request, ' '.join(getattr(erreur, 'messages', ["Valeur invalide."])))
        return redirect('management:management_admin_moyens_versement')
    a_valider = vendeurs.filter(versement_valide=False).exclude(compte_versement__isnull=True).exclude(compte_versement='').order_by('versement_modifie_le')
    valides = vendeurs.filter(versement_valide=True).select_related('versement_valide_par').order_by('nom_store')
    sans = vendeurs.filter(etat_approbation=True).filter(Q(compte_versement__isnull=True) | Q(compte_versement='')).order_by('nom_store')
    regles = {f.moyen: f for f in FraisVersement.objects.all()}
    frais = [(v, l, regles.get(v)) for v, l in MoyenVersement.choices]
    return render(request, 'management/admin_moyens_versement.html', locals())


@login_required
@droit_requis('benefice')
def admin_benefice(request):
    from management.finance import journal
    from management.models import ImportPrestataire
    user = request.user
    profil_staff = user.account_profil_staff
    debut, fin, periode, jour_debut, jour_fin = _periode(request)
    resultat = journal(profil_staff.license, debut, fin)
    marge_colis = (resultat['benefice'] / resultat['livres']) if resultat['livres'] else None
    dernier_import = ImportPrestataire.objects.filter(license=profil_staff.license, supprime=False).first()
    return render(request, 'management/admin_benefice.html', locals())


FAMILLES_NOTRE_STATUT = {
    StatutTraitement.LIVRE: 'livre', StatutTraitement.LIVRE_PAYE: 'livre', StatutTraitement.PAYE: 'livre', StatutTraitement.REVERSE: 'livre',
    StatutTraitement.EN_TRANSIT: 'transit', StatutTraitement.ARRIVE: 'arrive', StatutTraitement.EN_COURS_LIVRAISON: 'livraison',
    StatutTraitement.RECONDUIT: 'livraison', StatutTraitement.ECHEC_LIVRAISON: 'echec', StatutTraitement.EN_RETOUR: 'retour',
    StatutTraitement.REVENU_ABIDJAN: 'retour', StatutTraitement.RETOURNE: 'retour', StatutTraitement.REMIS_EN_STOCK: 'retour',
    StatutTraitement.MIS_DE_COTE: 'retour', StatutTraitement.ABANDONNE: 'retour', StatutTraitement.ANNULE: 'annule',
}


@login_required
@droit_requis('prestataire')
def admin_fichier_prestataire(request):
    """Fichier hebdomadaire du prestataire : chaque commande avec nos IDs, le produit, les frais et les commentaires de suivi."""
    import csv
    from django.http import HttpResponse
    from management.fichier_prestataire import famille_prestataire
    from management.finance import importer_fichier_prestataire
    from management.models import ImportPrestataire
    user = request.user
    profil_staff = user.account_profil_staff
    voir_argent = a_le_droit(user, 'benefice')
    peut_supprimer = a_le_droit(user, 'prestataire_supprimer')

    if request.method == 'POST' and request.POST.get('supprimer'):
        from management.finance import supprimer_import_prestataire
        if not peut_supprimer:
            raise PermissionDenied("Seul le CEO peut supprimer un fichier importé.")
        cible = ImportPrestataire.objects.filter(license=profil_staff.license, supprime=False, pk=request.POST.get('supprimer')).first()
        if cible is None:
            django_messages.error(request, "Ce fichier n'existe plus ou a déjà été supprimé.")
        else:
            n = supprimer_import_prestataire(cible, user)
            django_messages.success(request, "Fichier du %s supprimé : %d ligne(s) retirée(s). Vous pouvez réimporter le bon fichier." % (
                cible.date.strftime('%d/%m/%Y %H:%M'), n))
        return redirect('management:management_admin_fichier_prestataire')

    if request.method == 'POST':
        if not request.FILES.get('fichier'):
            django_messages.error(request, "Choisissez le fichier du prestataire (Excel ou CSV).")
            return redirect('management:management_admin_fichier_prestataire')
        try:
            bilan = importer_fichier_prestataire(profil_staff.license, request.FILES['fichier'], par=user,
                                                 onglet=request.POST.get('onglet', '').strip())
        except ValidationError as erreur:
            django_messages.error(request, ' '.join(erreur.messages))
            return redirect('management:management_admin_fichier_prestataire')
        imp = bilan['import']
        message = "Onglet « %s » : %d commande(s), %d reliée(s) à nos colis, %d inconnue(s)." % (
            imp.onglet, bilan['lignes'], bilan['rapprochees'], len(bilan['inconnues']))
        if voir_argent and bilan['ecarts']:
            message += " %d écart(s) de coût." % len(bilan['ecarts'])
        django_messages.success(request, message)
        return redirect(reverse('management:management_admin_fichier_prestataire') + '?import=%d' % imp.pk)

    imports = ImportPrestataire.objects.filter(license=profil_staff.license, supprime=False)[:30]
    supprimes = ImportPrestataire.objects.filter(license=profil_staff.license, supprime=True).select_related('supprime_par')[:10]
    imp = None
    if request.GET.get('import'):
        imp = ImportPrestataire.objects.filter(license=profil_staff.license, supprime=False, pk=request.GET.get('import')).first()
    imp = imp or (imports[0] if imports else None)
    filtre = request.GET.get('filtre', 'tous')
    q = request.GET.get('q', '').strip()
    lignes, compteurs = [], {'tous': 0, 'inconnues': 0, 'statut': 0, 'montant': 0, 'commentaires': 0}
    if imp:
        qs = imp.lignes.select_related('article__vendeur', 'article__localite_arrivee', 'article__zone_arrivee',
                                       'article__format_article', 'article__produit_stock').prefetch_related('article__departs')
        from collections import Counter
        doublons = {n for n, k in Counter(imp.lignes.values_list('numero', flat=True)).items() if k > 1}
        for l in qs:
            l.doublon = l.numero in doublons
            a = l.article
            l.famille = famille_prestataire(l.statut)
            l.notre_famille = FAMILLES_NOTRE_STATUT.get(a.statut_traitement, 'avant') if a else ''
            l.alerte_statut = bool(a and l.famille and l.famille != 'autre' and l.famille != l.notre_famille)
            l.livre_pas_chez_nous = bool(a and l.famille == 'livre' and l.notre_famille != 'livre')
            l.a_encaisser = a.valeur_totale if (a and a.is_option_encaissement) else (Decimal('0') if a else None)
            l.ecart_montant = (l.montant - l.a_encaisser) if (a and l.montant is not None and l.a_encaisser is not None) else None
            if a:
                l.produit_affiche = (a.produit_stock.designation if a.produit_stock_id and hasattr(a.produit_stock, 'designation')
                                     else (a.designation or a.produits_autre or ''))
                departs = list(a.departs.all())
                l.cout_partenaire = departs[0].cout_prevu if departs else None
                l.frais_ml = (a.montant_frais or Decimal('0')) + (a.cout_option_recuperation or Decimal('0'))
                l.frais_collecte = a.cout_option_encaissement or Decimal('0')
                l.marge = (l.frais_ml + l.frais_collecte - l.cout_partenaire) if l.cout_partenaire is not None else None
            compteurs['tous'] += 1
            compteurs['inconnues'] += a is None
            compteurs['statut'] += l.alerte_statut
            compteurs['montant'] += bool(l.ecart_montant)
            compteurs['commentaires'] += bool(l.commentaires)
            garder = {'inconnues': a is None, 'statut': l.alerte_statut, 'montant': bool(l.ecart_montant),
                      'commentaires': bool(l.commentaires)}.get(filtre, True)
            if garder and q:
                texte = ' '.join([l.numero, l.agent, l.statut, l.infos, ' '.join(l.commentaires),
                                  a.code if a else '', (a.code_tracking or '') if a else '',
                                  (a.vendeur.nom_store or '') if a and a.vendeur else '']).lower()
                garder = q.lower() in texte
            if garder:
                lignes.append(l)

        if request.GET.get('export') == 'csv':
            reponse = HttpResponse(content_type='text/csv; charset=utf-8')
            reponse['Content-Disposition'] = 'attachment; filename="fichier-prestataire-%s.csv"' % imp.date.strftime('%Y-%m-%d')
            reponse.write('\ufeff')
            ecrire = csv.writer(reponse, delimiter=';')
            entetes = ['Ligne', 'N° commande (fichier)', 'ID colis', 'Code tracking', 'ID vendeur', 'Vendeur', 'Produit', 'Ville',
                       'Agent', 'Montant à encaisser (fichier)', 'Montant à encaisser (nous)', 'Statut (fichier)', 'Notre statut',
                       'Date de retrait']
            if voir_argent:
                entetes += ['Frais ML', 'Frais de collecte', 'Coût partenaire', 'Marge']
            ecrire.writerow(entetes + ['Infos', 'Commentaires de suivi'])
            for l in lignes:
                a = l.article
                ligne = [l.rang, l.numero, a.code if a else '', (a.code_tracking or '') if a else '',
                         a.vendeur.code if a and a.vendeur else '', a.vendeur.nom_store if a and a.vendeur else '',
                         getattr(l, 'produit_affiche', '') or l.produit, a.localite_arrivee.nom if a and a.localite_arrivee else l.ville,
                         l.agent, l.montant if l.montant is not None else '', l.a_encaisser if l.a_encaisser is not None else '',
                         l.statut, a.get_statut_traitement_display() if a else 'Inconnu chez nous',
                         l.date_retrait.strftime('%d/%m/%Y') if l.date_retrait else '']
                if voir_argent:
                    ligne += [getattr(l, 'frais_ml', ''), getattr(l, 'frais_collecte', ''),
                              '' if getattr(l, 'cout_partenaire', None) is None else l.cout_partenaire,
                              '' if getattr(l, 'marge', None) is None else l.marge]
                ecrire.writerow(ligne + [l.infos, ' | '.join(l.commentaires)])
            return reponse

    suite_breadcrumb = "Fichier du prestataire"
    return render(request, 'management/admin_fichier_prestataire.html', locals())


# ---------------------------------------------------------------------------
# Commissions (réglées par le CEO ; montants pour le CEO et la comptable)
# ---------------------------------------------------------------------------

@login_required
@droit_requis('commissions_voir')
def admin_commissions(request):
    import json
    from management.commissions import tableau
    from management.models import CommissionConfig
    from mlshipafrica.enums import DepartementCommission, IndicateurCommission, TypeCommission
    user = request.user
    profil_staff = user.account_profil_staff
    peut_regler = a_le_droit(user, 'commissions_regler')
    configs = CommissionConfig.objects.filter(license=profil_staff.license).prefetch_related('comptes__user')
    comptes_equipe = ProfilStaff.objects.filter(license=profil_staff.license, etat_suppression=False,
                                                role_profil__in=(TypeProfilStaffChoice.AGENT, TypeProfilStaffChoice.MANAGER,
                                                                 TypeProfilStaffChoice.COMMERCIAL)).select_related('user')
    if request.method == 'POST':
        if not peut_regler:
            raise PermissionDenied("Seul le CEO règle les commissions.")
        try:
            config = configs.filter(pk=request.POST.get('config')).first() or CommissionConfig(license=profil_staff.license)
            if request.POST.get('basculer'):
                config.actif = not config.actif
                config.save()
            else:
                config.nom = (request.POST.get('nom') or '').strip()[:100] or 'Commission'
                config.departement = request.POST.get('departement')
                config.type = request.POST.get('type')
                config.indicateur = request.POST.get('indicateur')
                if config.departement not in DepartementCommission.values or config.type not in TypeCommission.values \
                        or config.indicateur not in IndicateurCommission.values:
                    raise ValidationError("Département, type ou indicateur inconnu.")
                config.montant_unitaire = Decimal(request.POST.get('montant_unitaire') or 0)
                config.taux_livraison_minimum = int(request.POST.get('taux_livraison_minimum') or 0)
                paliers = []
                for ligne in (request.POST.get('paliers') or '').splitlines():
                    if ':' in ligne:
                        seuil, montant_palier = ligne.split(':', 1)
                        paliers.append({'seuil': int(seuil.strip()), 'montant': int(montant_palier.strip().replace(' ', ''))})
                config.paliers = paliers
                config.save()
                config.comptes.set(comptes_equipe.filter(code__in=request.POST.getlist('comptes'),
                                                         role_profil=config.departement))
            django_messages.success(request, "Commission « %s » enregistrée." % config.nom)
        except (ValidationError, ValueError, ArithmeticError) as erreur:
            django_messages.error(request, ' '.join(getattr(erreur, 'messages', ["Saisie invalide (paliers : une ligne « seuil : montant »)."])))
        return redirect(reverse('management:management_admin_commissions') + '?' + request.GET.urlencode())
    debut, fin, periode, jour_debut, jour_fin = _periode(request) if request.GET.get('periode') else _periode_mois()
    lignes = tableau(profil_staff.license, debut, fin)
    total = sum((l['montant'] for l in lignes), Decimal('0'))
    departements, types, indicateurs = DepartementCommission.choices, TypeCommission.choices, IndicateurCommission.choices
    nb_actives = sum(1 for c in configs if c.actif)
    return render(request, 'management/admin_commissions.html', locals())


def _periode_mois():
    from datetime import datetime, time as dtime
    aujourd_hui = timezone.localdate()
    debut = aujourd_hui.replace(day=1)
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(debut, dtime.min), tz),
            timezone.make_aware(datetime.combine(aujourd_hui + timedelta(days=1), dtime.min), tz), 'mois', debut, aujourd_hui)
