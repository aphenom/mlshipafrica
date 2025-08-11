from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, Encaissement, HistoriqueArticle, ReglementArticle, Reversement, Vendeur
from management.forms import VendeurColisForm, VendeurForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect

from core.models import Configuration, License, Localite

from mlshipafrica.enums import StatutTraitement, StatutVendeur, TypeProfilStaffChoice, TypeVendeurChoice, array_statut_traitement_retour, array_statut_traitement_en_cours, array_statut_traitement_livre

from mlshipafrica.shared import get_articles_stats_by_vendeur, get_global_article_stats, get_global_vendeurs_stats, get_top_n_vendeurs

from django.db import transaction
from tablib import Dataset

from management.resources import VendeurResource

from django.utils import timezone

from django.db.models import Q, Count, Sum, F, ExpressionWrapper, DecimalField, Value
from datetime import timedelta
from django.db.models.functions import Coalesce
from decimal import Decimal

# Create edition profil vendeur
@login_required
def vendeur_edit_profil(request):
    user = request.user
    form = VendeurForm(instance=None)
    current_license = request.GET.get('current_license', None)
    license = License.objects.get(code=current_license, etat_validation=False, etat_suppression=False) if current_license and current_license.pk else License.objects.all().first()

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
                    article.save()
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
            if "submit_validation" in request.POST and request.POST["submit_validation"]:
                # rediriger vers details colis
                article.statut_traitement =  StatutTraitement.EN_ATTENTE_RAMASSAGE if article.is_option_recuperation is True else StatutTraitement.EN_ATTENTE_DEPOT
                article.save()
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
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_detail_colis.html', locals())


@login_required
def vendeur_liste_colis(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        articles = Article.objects.filter(vendeur=vendeur, etat_suppression=False)
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
        articles = Article.objects.filter(vendeur=vendeur, etat_suppression=False, etat_encaissement=True)
        # configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_liste_colis_reversement.html', locals())


@login_required
def admin_liste_vendeurs(request):
    try:
        type_vendeur = request.GET.get('type_vendeur', StatutVendeur.ACTIF)
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeurs = Vendeur.objects.filter(license=profil_staff.license)
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
def admin_vendeur_edit_profil(request, code):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeur = Vendeur.objects.get(code=code)
            configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
            if request.method == 'POST':
                form = VendeurForm(data=(request.POST or None), files=(request.FILES or None), instance=vendeur)
                if "submit_approbation" in request.POST and request.POST["submit_approbation"]:
                    vendeur.etat_approbation = True
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
                return redirect('management:management_admin_vendeur_edit_profil', vendeur.code)

            else:
                form = VendeurForm(instance=vendeur)

    except Exception as e:
        raise Http404
    return render(request, 'management/admin_vendeur_edit_profil.html', locals())



@login_required
def admin_vendeur_profil(request, code):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeur = Vendeur.objects.get(code=code)
            type_vendeur = TypeVendeurChoice
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_vendeur_profil.html', locals())


@login_required
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
            dd(result)
            if not result.has_errors():
                resource.import_data(imported_data, dry_run=False) # Actual import
                # return redirect('success_url') # Redirect to a success page
            else:
                errors = result.errors
                # Handle errors, e.g., display them on the template
                #return render(request, 'myapp/import_form.html', {'errors': result.errors})

    return render(request, 'management/admin_import_vendeur_form.html', locals())

    
@login_required
def admin_liste_colis(request):
    try:
        type_colis = request.GET.get('type_colis', "en_cours")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False)
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
                    StatutTraitement.EN_RETOUR
                ])
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

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_colis.html', locals())


@login_required
def admin_liste_colis_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-nombre_articles_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_colis_vendeurs.html', locals())


@login_required
def admin_detail_colis(request, code):

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff:
            #vendeur = Vendeur.objects.get(user=user)
            article = Article.objects.all().exclude(statut_traitement=StatutTraitement.BROUILLON).get(code=code)
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
                
            statuts_exclus = [
                    StatutTraitement.BROUILLON, 
                    StatutTraitement.EN_ATTENTE_DEPOT,
                    StatutTraitement.EN_ATTENTE_RAMASSAGE,
                    StatutTraitement.REVERSE
                ]
            
            if article.is_option_recuperation is True:
                statuts_exclus.append(StatutTraitement.DEPOT)
            else:
                statuts_exclus.append(StatutTraitement.RAMASSE)

            if article.is_option_encaissement is True:
                statuts_exclus.append(StatutTraitement.LIVRE)
            else:
                statuts_exclus.append(StatutTraitement.LIVRE_PAYE)

            for historique in historique_articles:
                if historique.statut_traitement not in statuts_exclus:
                    statuts_exclus.append(historique.statut_traitement)

            statut_traitement_applicables = [
                (value, label) for value, label in StatutTraitement.choices
                if value not in statuts_exclus and \
                ( \
                        (article.get_last_historique().statut_traitement == StatutTraitement.EN_ATTENTE_RAMASSAGE and value == StatutTraitement.RAMASSE)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.EN_ATTENTE_DEPOT and value == StatutTraitement.DEPOT)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.RAMASSE and value == StatutTraitement.EN_TRANSIT)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.DEPOT and value == StatutTraitement.EN_TRANSIT)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.EN_TRANSIT and value == StatutTraitement.EN_COURS_LIVRAISON)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.EN_COURS_LIVRAISON and value == StatutTraitement.ARRIVE)
                        or (article.get_last_historique().statut_traitement == StatutTraitement.ARRIVE and (value == StatutTraitement.LIVRE or value == StatutTraitement.LIVRE_PAYE or value == StatutTraitement.EN_RETOUR))
                        or (article.get_last_historique().statut_traitement == StatutTraitement.EN_RETOUR and value == StatutTraitement.RETOURNE) \
                )
            ]
            
            # print(statut_traitement_applicables)

            if request.method == 'POST':

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
                    if str(article.get_last_historique().id) == request.POST["last_mouvement"] and any(value == request.POST["mouvement_statut"] for value, _ in statut_traitement_applicables):
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
                
    except Exception as e:
        dd(e)
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
def admin_liste_paiements(request):
    try:
        type_paiements = request.GET.get('type_paiements', "en_attente")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON)
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
def admin_liste_paiements_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-montant_frais_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_paiements_vendeurs.html', locals())


@login_required
def admin_liste_reversements(request):
    try:
        type_reversements = request.GET.get('type_reversements', "en_attente")
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False, etat_encaissement=True).exclude(statut_traitement=StatutTraitement.BROUILLON).exclude(statut_traitement__in=array_statut_traitement_retour)
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
def admin_liste_reversements_vendeurs(request):
    user = request.user
    profil_staff = user.account_profil_staff
    #statut_traitement = StatutTraitement

    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeurs = get_articles_stats_by_vendeur(request)
            vendeurs = vendeurs.order_by("-montant_reversement_total") if vendeurs else None
            suite_breadcrumb = "" 

        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        print(e)
        raise Http404
    return render(request, 'management/admin_liste_reversements_vendeurs.html', locals())


@login_required
def admin_mouvements_colis(request):
    try:
        statut_traitement_selected = request.GET.get('statut_traitement_selected', None)
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            historiques = HistoriqueArticle.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("-date_creation")
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
def admin_activites_paiements(request):
    try:
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            reglements = ReglementArticle.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).order_by("-date_creation")
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
def admin_activites_reversements(request):
    try:
        vendeur_selected = request.GET.get('vendeur_selected', None)
        debut_selected = request.GET.get('debut_selected', None)
        fin_selected = request.GET.get('fin_selected', None)
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            reversements = Reversement.objects.filter(license=profil_staff.license, etat_suppression=False, article__etat_suppression=False).order_by("-date_creation")
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


