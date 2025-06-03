from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, HistoriqueArticle, Vendeur
from management.forms import VendeurColisForm, VendeurForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect

from core.models import Configuration, License, Localite
from mlshipafrica.enums import StatutTraitement, TypeProfilStaffChoice, TypeVendeurChoice
from django.db import transaction


# Create edition profil vendeur
@login_required
def vendeur_edit_profil(request):
    user = request.user
    form = VendeurForm(instance=None)
    current_license = request.GET.get('current_license', None)
    license = License.objects.get(code=current_license, etat_validation=False, etat_suppression=False) if current_license else License.objects.all().first()

    if user.is_authenticated and not user.is_staff:
        try:
            vendeur = Vendeur.objects.get(user=user)
        except Vendeur.DoesNotExist:
            vendeur = Vendeur(user=user)  # On définit déjà l'user ici

        if request.method == 'POST':
            form = VendeurForm(data=(request.POST or None), files=(request.FILES or None), instance=vendeur)
            if form.is_valid():
                vendeur = form.save(commit=False)
                if form.has_changed():
                    vendeur.etat_approbation = False
                if not vendeur.user:
                    vendeur.user = user
                    vendeur.license = license
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
    statut_traitement = StatutTraitement

    if user.is_authenticated and not user.is_staff:
        try:
            with transaction.atomic():
                vendeur = Vendeur.objects.get(user=user)
                configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
                localite_depart = Localite.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False, is_depart=True).first()  
                article = Article() if current_article is None else Article.objects.get(code=current_article, vendeur=vendeur, statut_traitement=StatutTraitement.BROUILLON, etat_validation=False, etat_suppression=False)
                article.vendeur = vendeur
                article.license = vendeur.license
                article.config = configuration
                article.localite_depart = localite_depart
                article.etat_validation = False
                article.statut_traitement = statut_traitement.BROUILLON
                if vendeur.collecte_par_mlship is True and configuration.enable_option_encaissement is True:
                    article.is_option_encaissement = True
        except Exception as e:
            raise Http404

        if request.method == 'POST':
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
        configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        statut_traitement = StatutTraitement
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
        configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        statut_traitement = StatutTraitement
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
        configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_liste_colis.html', locals())


@login_required
def vendeur_liste_colis_reversement(request):
    try:
        user = request.user
        vendeur = Vendeur.objects.get(user=user)
        articles = Article.objects.filter(vendeur=vendeur, etat_suppression=False)
        configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        statut_traitement = StatutTraitement
        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'management/vendeur_liste_colis_reversement.html', locals())


@login_required
def admin_liste_vendeurs(request):
    try:
        type_vendeur = request.GET.get('current_article', None)
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff \
            and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):

            vendeurs = Vendeur.objects.filter(license=profil_staff.license)
            configuration = Configuration.objects.filter(license=profil_staff.license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
            type_profil_staff = TypeProfilStaffChoice
            # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
   
    except Exception as e:
        raise Http404
    return render(request, 'management/admin_liste_vendeurs.html', locals())
