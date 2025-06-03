import json
import os
import signal
# import psutil
import subprocess
from django.utils import timezone
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.conf import settings
# from allauth.socialaccount.models import SocialAccount
from django.urls import reverse
# import requests

# from core.models import Mise
# from .my_enum import TypeTransaction, Visibilite
# from .utils import ContextConfig, CurrentConfig, CurrentTauxCommission, DetermineCagnotte, DetermineCommission, send_notification_to_device
# from player.models import Participation, Partie, Profil, Transaction, Visiteur
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django_dump_die.middleware import dd
from urllib.parse import urlencode
from django.template.defaultfilters import floatformat
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth import get_user_model
from django.db import transaction
from allauth.account.views import SignupView

from management.models import ProfilStaff, Vendeur


#@login_required
# index de la plateforme
def index(request):
    user = request.user
    # dd(user)
    if user.is_authenticated:
        if user.is_staff is True:
            user_is_staff = True
            profil_staff_pk = None
            try:
                profil_staff = ProfilStaff.objects.get(user=request.user)
                profil_staff_pk = profil_staff.pk
            except ProfilStaff.DoesNotExist:
                profil_staff_pk = None
                profil_staff = None
        else:
            user_is_staff = False
                
        if user_is_staff is False:
            vendeur_pk = None
            try:
                vendeur = Vendeur.objects.get(user=request.user)
                vendeur_pk = vendeur.pk
            except Vendeur.DoesNotExist:
                member_pk = None
                vendeur = None
                return redirect(reverse('management:management_vendeur_edit_profil'))

    else:
        return redirect(reverse('account_login'))
    
    return render(request, 'dashboard.html', locals())


    """

    # send_notification_to_device("6d37c0e08f34c443388e8f32005290525e9632a7", "welcome", "to you ohhh")
    # 6735cbb21c7c97cdebc3110ead81e0c81daa3604 mac
    # print("notif")

    # Récupérer les paramètres de `state` dans la requête
    next_url = request.GET.get('next', ContextConfig(request)['next'])
    code_invitation = request.GET.get('code_invitation', ContextConfig(request)['code_invitation'])
    
    # pour rejoindre une partie privee /?rejoindre_partie_code=code
    rejoindre_partie_code = request.GET.get('rejoindre_partie_code', "")
    
    # pour rejoindre une partie privee /?public_partie_code=code
    public_partie_code = request.GET.get('public_partie_code', "")

    # Récupérer l'utilisateur connecté
    user = request.user

    # a supprimer en prod
    # user = User.objects.all().first()
    # login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

    # Exemple d'utilisation : récupérer l'utilisateur connecté via Facebook
    if user.is_authenticated:
        try:
            social_account = SocialAccount.objects.get(user=user, provider='facebook')
            checking_user(request, user, social_account, code_invitation)

            # Ajoute ici tes traitements en fonction de `custom_variable` ou des données utilisateur
        except SocialAccount.DoesNotExist:
            checking_user(request, user, None, code_invitation)
            # dd(user)
            # return HttpResponse("Erreur: aucun compte Facebook trouvé.", status=404)

        if 'next' in request.session:
                del request.session['next']
        if 'code_invitation' in request.session:
                del request.session['code_invitation']              
   
    # dd(request)
    # determinons l'ensemble des mises possibles
    liste_mises = Mise.objects.filter(etat_validation=True, etat_suppression=False)

    # parcourons les mises pour creer des parties ou recuperons celles en attentes en fonction et determinons les choix possibles pour les parties privees
    choix_parties_privees = generation_parties(request)
        
    #trions les choix pour les parties privees 
    choix_parties_privees_triees = sorted(choix_parties_privees, key=lambda x: x['montant_cagnotte'], reverse=True)
    # dd(choix_parties_privees)

    # recuperons les parties valides pretes a recevoir des joueurs
    liste_parties = Partie.objects.filter(visibilite = Visibilite.Public, etat_demarrage = False, etat_validation=True, etat_suppression=False).order_by("-montant_cagnotte")

    # partie privee pour utilisateur connecté
    # Si l'utilisateur est authentifié via Facebook
    if user.is_authenticated:
        try:
            # Récupérer les données de l'utilisateur à partir du modèle SocialAccount
            profil = Profil.objects.get(user=user)

            partie_privee = Partie.objects.filter(organise_par=profil, visibilite = Visibilite.Privee, etat_demarrage = False, etat_validation=True, etat_suppression=False).first()

            participation_en_cours = Participation.objects.filter(profil = profil, partie__etat_fin = False, partie__etat_validation=True, partie__etat_suppression=False, etat_fin=False, etat_exclusion=False, etat_validation=True, etat_suppression=False).first()
            
            if participation_en_cours:
                partie_en_cours = participation_en_cours.partie
                return redirect(reverse('index_partie', args=[timezone.now().strftime('%d%m%Y%H%M%S%f'), partie_en_cours.code]))
            
            # Afficher les informations du compte social
            # print(profil)


        except Profil.DoesNotExist:
            print("L'utilisateur n'a pas de compte social lié à Facebook")

    if next_url != '/' and next_url != '':
        return redirect(next_url)
    
    # messages.error(request, "La partie n'existe pas.")
    """

    return render(request, 'dashboard.html', locals())



