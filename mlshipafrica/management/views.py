from django.shortcuts import render

from management.models import Vendeur
from management.forms import VendeurForm


# Create your views here.
def vendeur_edit_profil(request):
   # Récupérer l'utilisateur connecté
    user = request.user
    form = VendeurForm(instance=None) # Nous créons un formulaire prérempli 
    # Si l'utilisateur est authentifié via Facebook
    if user.is_authenticated and user.is_staff is False:
        try:
            # Récupérer les données de l'utilisateur à partir du modèle SocialAccount
            vendeur = Vendeur.objects.get(user=user)
        except Vendeur.DoesNotExist:
            pass

        if request.method == 'POST': # S'il s'agit d'une requête POST
            form = VendeurForm(request.POST, request.FILES, instance=vendeur) # Nous reprenons les données
            if form.is_valid() : # Nous vérifions que les données envoyées sont valides
                pass
            """
                form = form.save(commit=False)
                if profil.invite_par is None and form.code_invite_par:
                    invite_par = Profil.objects.filter(code=form.code_invite_par, etat_suppression=False).exclude(pk=profil.pk).filter()
                    if invite_par:
                        form.invite_par = invite_par
                    else:
                        form.code_invite_par = None
                form.save()
                return HttpResponseRedirect(reverse('management:vendeur_profil'))"""

        else: # Si ce n'est pas du POST, c'est probablement une requête     GET
            form = VendeurForm(instance=vendeur) # Nous créons un formulaire prérempli 
    return render(request, 'management/vendeur_edit_profil.html', locals())
