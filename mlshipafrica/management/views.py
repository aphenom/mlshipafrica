from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, Encaissement, HistoriqueArticle, ProfilStaff, ReglementArticle, Reversement, Vendeur
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
from management.statuts import statuts_suivants
from mlshipafrica.droits import a_le_droit, droit_requis, droits_de

from django.utils import timezone

from django.db.models import Q, Count, Sum, F, ExpressionWrapper, DecimalField, Value
from datetime import timedelta
import logging
from django.db.models.functions import Coalesce
from decimal import Decimal

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

        if request.method == 'POST':
            with transaction.atomic():
                if "submit_suppression" in request.POST and request.POST["submit_suppression"]:
                    # rediriger vers details colis
                    article.etat_suppression =  True
                    article.save()
                    return redirect('index')
                form = VendeurColisForm(data=(request.POST or None), files=(request.FILES or None), instance=article)
                if form.is_valid():
                    article = form.save(commit=False)
                    try:
                        with transaction.atomic():
                            article.save()
                    except ValidationError as erreur:
                        # Pas de tarif pour cette destination / ce format : on le dit au vendeur
                        form.add_error(None, erreur.messages)
                        return render(request, 'management/vendeur_edit_colis.html', locals())
                    return redirect('management:management_vendeur_facture_colis', article.code)
                    # Tu peux aussi faire : return redirect('management:vendeur_profil')
        else:
            form = VendeurColisForm(instance=article)
        return render(request, 'management/vendeur_edit_colis.html', locals())
    return redirect('index')


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
                        reserver_pour_commande(article, user)
                        article.statut_traitement =  StatutTraitement.EN_ATTENTE_RAMASSAGE if article.is_option_recuperation is True else StatutTraitement.EN_ATTENTE_DEPOT
                        article.save()
                except ValidationError as erreur:
                    django_messages.error(request, ' '.join(erreur.messages))
                    return redirect('management:management_vendeur_facture_colis', article.code)
                return redirect('management:management_vendeur_detail_colis', article.code)
            if "submit_modification" in request.POST and request.POST["submit_modification"]:
                return HttpResponseRedirect(reverse('management:management_vendeur_edit_colis') + '?current_article=' + code) 
            if "submit_impression" in request.POST and request.POST["submit_impression"]:
                pass

            return redirect('management:management_vendeur_facture_colis', article.code)
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
        historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).order_by("date_creation")
        if article.statut_traitement == StatutTraitement.REVENU_ABIDJAN:
            from management.forms import libelle_localite_avec_delai
            from management.retours import jours_a_abidjan
            jours_retour = jours_a_abidjan(article)
            localites_substitution = [(l.pk, libelle_localite_avec_delai(l)) for l in Localite.objects.filter(
                license=vendeur.license, is_arrivee=True, etat_validation=True, etat_suppression=False).select_related('zone')]
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_detail_colis.html', locals())


@login_required
def vendeur_liste_colis(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        articles = Article.objects.filter(vendeur=vendeur, etat_suppression=False).select_related('localite_arrivee')
        # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
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
            #configuration = Configuration.objects.filter(license=profil_staff.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
            type_profil_staff = TypeProfilStaffChoice
            # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
   
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
                return redirect('management:management_admin_vendeur_edit_profil', vendeur.code)

            else:
                form = VendeurForm(instance=vendeur)

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
            type_vendeur = TypeVendeurChoice
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_vendeur_profil.html', locals())


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
    try:
        type_colis = request.GET.get('type_colis', "en_cours")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            # select_related : 1 requête pour toute la liste au lieu de 2 par colis (vendeur, localité)
            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False).select_related('vendeur', 'localite_arrivee')
            suite_breadcrumb = "" 
            if type_colis == StatutTraitement.EN_ATTENTE_RAMASSAGE:
                suite_breadcrumb = "En attente de ramassage" 
                articles = articles.filter(statut_traitement=StatutTraitement.EN_ATTENTE_RAMASSAGE)
            if type_colis == StatutTraitement.EN_ATTENTE_DEPOT:
                suite_breadcrumb = "En attente de dépôt" 
                articles = articles.filter(statut_traitement=StatutTraitement.EN_ATTENTE_DEPOT)
            if type_colis == "en_cours":
                suite_breadcrumb = "En cours" 
                articles = articles.filter(statut_traitement__in=[
                    StatutTraitement.RAMASSE,
                    StatutTraitement.DEPOT,
                    StatutTraitement.EN_TRANSIT,
                    StatutTraitement.EN_COURS_LIVRAISON,
                    StatutTraitement.ARRIVE,
                    StatutTraitement.ECHEC_LIVRAISON,
                    StatutTraitement.EN_RETOUR
                ])
            if type_colis == "a_sauver":
                # Colis sans mouvement depuis 48 h alors qu'ils sont en route ou chez le client
                from django.db.models import Max
                from management.statuts import STATUTS_SURVEILLES_48H
                suite_breadcrumb = "À sauver (48 h sans mouvement)"
                articles = (articles.filter(statut_traitement__in=STATUTS_SURVEILLES_48H)
                            .annotate(dernier_mouvement=Max('article_historiquearticle__date_creation',
                                                            filter=Q(article_historiquearticle__etat_suppression=False)))
                            .filter(dernier_mouvement__lt=timezone.now() - timedelta(hours=48)))
            if type_colis == StatutTraitement.REVENU_ABIDJAN:
                suite_breadcrumb = "Revenus à Abidjan"
                articles = articles.filter(statut_traitement=StatutTraitement.REVENU_ABIDJAN)
            if type_colis == StatutTraitement.ECHEC_LIVRAISON:
                suite_breadcrumb = "Échecs de livraison"
                articles = articles.filter(statut_traitement=StatutTraitement.ECHEC_LIVRAISON)
            if type_colis == StatutTraitement.ANNULE:
                suite_breadcrumb = "Annulés avant expédition"
                articles = articles.filter(statut_traitement=StatutTraitement.ANNULE)
            if type_colis == StatutTraitement.RETOURNE:
                articles = articles.filter(statut_traitement=StatutTraitement.RETOURNE)
                suite_breadcrumb = "Retournés"  
            if type_colis == StatutTraitement.LIVRE:
                suite_breadcrumb = "Historique" 
                articles = articles.filter(statut_traitement__in=[
                    StatutTraitement.LIVRE,
                    StatutTraitement.LIVRE_PAYE,
                    StatutTraitement.REVERSE
                ])
                # L'historique grossit de ~1 000 colis par jour : 60 derniers jours par défaut, ?jours=N pour élargir
                try:
                    jours_historique = max(1, int(request.GET.get('jours', 60)))
                except ValueError:
                    jours_historique = 60
                articles = articles.filter(date_creation__gte=timezone.now() - timedelta(days=jours_historique))

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_colis.html', locals())


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
            peut_bouger = a_le_droit(user, 'colis_mouvements')
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
                        
                if "submit_new_mouvement" in request.POST and request.POST["submit_new_mouvement"]:
                    nouveau_statut = request.POST.get("mouvement_statut")
                    commentaire_mouvement = (request.POST.get("mouvement_commentaire") or "").strip()
                    # Règles du cahier des charges : motif écrit obligatoire pour annuler, et pour expédier un colis non confirmé
                    if nouveau_statut == StatutTraitement.ANNULE and not commentaire_mouvement:
                        erreur_mouvement = "Indiquez le motif de l'annulation dans le commentaire."
                    elif nouveau_statut == StatutTraitement.EN_TRANSIT and article.etat_confirmation != EtatConfirmation.CONFIRME and not commentaire_mouvement:
                        erreur_mouvement = "Ce colis n'est pas confirmé par le client : indiquez le motif de l'expédition dans le commentaire."
                    else:
                        erreur_mouvement = None
                    if erreur_mouvement:
                        django_messages.error(request, erreur_mouvement)
                    elif str(article.get_last_historique().id) == request.POST["last_mouvement"] and any(value == request.POST["mouvement_statut"] for value, _ in statut_traitement_applicables):
                        if (article.code_tracking is None or article.code_tracking == "") and request.POST["mouvement_code_tracking"]:
                            article.code_tracking = request.POST["mouvement_code_tracking"]
                        article.statut_traitement = request.POST["mouvement_statut"]
                        article.etat_validation = True
                        article.save()

                        histo_article = HistoriqueArticle()
                        histo_article.article = article
                        histo_article.date = request.POST["mouvement_date"]
                        histo_article.statut_traitement = request.POST["mouvement_statut"]
                        histo_article.commentaire = request.POST["mouvement_commentaire"]
                        histo_article.license = article.license
                        histo_article.dernier_historique_article = article.get_last_historique()
                        histo_article.save()

                        if article.etat_encaissement is False and request.POST["mouvement_statut"] == StatutTraitement.LIVRE_PAYE and article.is_option_encaissement is True:
                            new_encaissement = Encaissement()
                            new_encaissement.article = article
                            new_encaissement.save()
                            article.etat_encaissement = True
                            article.save()
                
        
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
                        
                if "submit_new_reversement" in request.POST and request.POST["submit_new_reversement"]:             
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
    return render(request, 'management/admin_detail_colis.html', locals())

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
            try:
                if resultat not in ResultatAppel.values:
                    raise ValidationError("Résultat d'appel inconnu.")
                enregistrer_appel(article, user, resultat, request.POST.get('commentaire', ''), acompte)
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
        raise Http404
    if request.method == 'POST':
        lignes = list(zip(request.POST.getlist('reference'), request.POST.getlist('designation'), request.POST.getlist('quantite')))
        try:
            lignes = [(r, d, int(q or 0)) for r, d, q in lignes]
            entree = annoncer_entree(vendeur, lignes, request.POST.get('commentaire', ''))
            django_messages.success(request, "Envoi %s annoncé : il sera contrôlé à la réception." % entree.code)
        except (ValidationError, ValueError) as erreur:
            django_messages.error(request, ' '.join(getattr(erreur, 'messages', ["Quantité invalide."])))
        return redirect('management:management_vendeur_stock')
    produits = vendeur.produits_stock.filter(actif=True)
    entrees = EntreeStock.objects.filter(vendeur=vendeur).prefetch_related('lignes')[:20]
    mouvements = MouvementStock.objects.filter(produit__vendeur=vendeur).select_related('produit', 'article')[:50]
    debut_mois = timezone.localdate().replace(day=1)
    stockage_mois = FacturationStockage.objects.filter(vendeur=vendeur, jour__gte=debut_mois).aggregate(t=Sum('montant'))['t'] or 0
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
    suite_breadcrumb = "Stock"
    return render(request, 'management/admin_stock.html', locals())
