from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Vendeur
from management.forms import VendeurForm


# Create your views here.
def vendeur_edit_profil(request):
    user = request.user
    form = VendeurForm(instance=None)

    #dd(user)

    if user.is_authenticated is False:
        return redirect(reverse('account_login'))

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
    