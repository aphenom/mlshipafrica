from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, Vendeur
from management.forms import VendeurColisForm, VendeurForm
from django.contrib.auth.decorators import login_required
from django.http import Http404

from core.models import Configuration, Localite
from mlshipafrica.enums import StatutTraitement


# Create edition profil vendeur
@login_required
def vendeur_edit_profil(request):
    user = request.user
    form = VendeurForm(instance=None)

    if user.is_authenticated and not user.is_staff:
        try:
            vendeur = Vendeur.objects.get(user=user)
        except Vendeur.DoesNotExist:
            vendeur = Vendeur(user=user)  # On définit déjà l'user ici

        if request.method == 'POST':
            form = VendeurForm(data=(request.POST or None), files=(request.FILES or None), instance=vendeur)
            if form.is_valid():
                vendeur = form.save(commit=False)
                if not vendeur.user:
                    vendeur.user = user
                vendeur.save()
                return redirect('index')
                # Tu peux aussi faire : return redirect('management:vendeur_profil')
        else:
            form = VendeurForm(instance=vendeur)
        return render(request, 'management/vendeur_edit_profil.html', locals())
    return redirect('index')
    

# Create edit colis vendeur.
@login_required
def vendeur_edit_colis(request):
    user = request.user
    form = VendeurColisForm(instance=None)
    current_article = request.GET.get('current_article', None)

    if user.is_authenticated and not user.is_staff:
        try:
            vendeur = Vendeur.objects.get(user=user)
            configuration = Configuration.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False).first()  
            localite_depart = Localite.objects.filter(license=vendeur.license, etat_validation=True, etat_suppression=False, is_depart=True).first()  
            article = Article() if current_article is None else Article.objects.filter(code=current_article, vendeur=vendeur, statut_traitement=StatutTraitement.BROUILLON, etat_validation=False, etat_suppression=False).first()
            article.vendeur = vendeur
            article.license = vendeur.license
            article.config = configuration
            article.localite_depart = localite_depart
            article.etat_validation = False
            article.statut_traitement = StatutTraitement.BROUILLON
            if vendeur.collecte_par_mlship is True:
                article.is_option_encaissement = True
        except Exception as e:
            raise Http404

        if request.method == 'POST':
            form = VendeurColisForm(data=(request.POST or None), files=(request.FILES or None), instance=article)
            if form.is_valid():
                article = form.save(commit=False)
                article.save()
                return redirect('index')
                # Tu peux aussi faire : return redirect('management:vendeur_profil')
        else:
            form = VendeurColisForm(instance=article)
        return render(request, 'management/vendeur_edit_colis.html', locals())
    return redirect('index')

