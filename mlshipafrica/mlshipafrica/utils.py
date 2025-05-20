
import string
import random
from django.utils import timezone
from django.apps import apps
from decimal import Decimal
import string
import random
from django.conf import settings
from django.urls import resolve
from django.utils import timezone
from django.db.models import Q, Sum

# from core.models import Config, TauxCommission, TauxTransaction
# from .enums import Genre, TypeTransaction

# import requests
# import json
# from django.core.mail import send_mail




'''generateur code de reference'''
def CodeGenerator(model, start_by_text=None, end_by_text=None):

    start_by_text = "{:%y}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='License'): 
        start_by_text = "LIC{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())       

    if model == apps.get_model(app_label='core', model_name='AchatLicense'): 
        start_by_text = "AL{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='Configuration'): 
        start_by_text = "CONF{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='PartenaireLogistique'): 
        start_by_text = "PL{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='Zone'): 
        start_by_text = "ZO{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='Localite'): 
        start_by_text = "LOC{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='core', model_name='FormatArticle'): 
        start_by_text = "FA{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='Vendeur'): 
        start_by_text = "V{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='Tarification'): 
        start_by_text = "TAR{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='Article'): 
        start_by_text = "A{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='HistoriqueArticle'): 
        start_by_text = "HA{:%y}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='ReglementArticle'): 
        start_by_text = "RA{:%y}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='Encaissement'): 
        start_by_text = "ENC{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if model == apps.get_model(app_label='management', model_name='Reversement'): 
        start_by_text = "REV{:%y}".format(timezone.now())
        end_by_text = "{:%m}".format(timezone.now())

    if end_by_text is None:
        end_by_text = "{:%m%d}".format(timezone.now())       

    #CodeGenerator(Partie, "J{:%y}".format(timezone.now()), "{:%m%d}".format(timezone.now()))

    # Simuler un 'do-while' avec 'while True' et un 'break'
    while True:
        letters_and_digits = string.ascii_uppercase # + string.digits  # 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        code_letters = ''.join(random.choice(letters_and_digits) for _ in range(4))
        code = str(start_by_text) + str(code_letters) + str(end_by_text)
        count = model.objects.filter(code=code).count()
        if count > 0:
            pass
        else:
            return code
        

"""
# gestion de [profil]
def checking_user(request, user):
    try:
        # Récupération des données Facebook si présentes
        email = user.email
        nom = prenom = id_facebook = None

        # Recherche du profil lié à l'utilisateur
        profil = Profil.objects.filter(user=user).first()

        if profil:
            # Mise à jour des informations du profil existant
            updated = False
            if email and profil.email != email:
                profil.email = email
                updated = True
            if nom and profil.nom != nom:
                profil.nom = nom
                updated = True
            if prenom and profil.prenom != prenom:
                profil.prenom = prenom
                updated = True
            if id_facebook and profil.id_facebook != id_facebook:
                profil.id_facebook = id_facebook
                updated = True
            if updated:
                profil.save()

        else:
            # Création d’un nouveau profil
            profil = Profil(
                user=user,
                email=email or '',
                nom=nom or '',
                prenom=prenom or '',
                id_facebook=id_facebook or '',
                date_validation=timezone.now()
            )

            # Traitement du code d’invitation
            if code_invitation:
                profil.code_invite_par = code_invitation
                invite_par = Profil.objects.filter(code=code_invitation, etat_suppression=False).first()
                if invite_par:
                    profil.invite_par = invite_par
                else:
                    profil.code_invite_par = ""

            profil.save()

    except Exception as e:
        # Log du message d’erreur
        messages.error(request, f"Une erreur est survenue lors de la configuration du profil : {str(e)}")
"""


"""Get current config pour les variables en contexte
def ContextConfig(request):
    
    try:  
        config = Config.objects.filter(etat_validation=True, etat_suppression=False).first()  
    except:
        config = None

    user = request.user

    try:  
        my_current_url = resolve(request.path_info).url_name 
    except:
        my_current_url = None

    code_invitation = request.session.get('code_invitation', '')

    next = request.session.get('next', '')

    minimum_depot = config.minimum_depot if config and config.minimum_depot else 100

    minimum_retrait = config.minimum_retrait if config and config.minimum_retrait else 1000

    profil = None
    complement_genre = ""
    if user.is_authenticated:
        try:
            # Récupérer les données de l'utilisateur à partir du modèle SocialAccount
            profil = Profil.objects.get(user=user)
            if profil.genre == Genre.Feminin:
                complement_genre = "e"
        except Profil.DoesNotExist:
            print("L'utilisateur n'a pas de compte social lié à Facebook")

    total_transactions = Transaction.objects.filter(profil=profil).filter(Q((Q(type=TypeTransaction.Retrait) | Q(type=TypeTransaction.Mise)), etat_suppression=False) 
                                       | Q((Q(type=TypeTransaction.Depot) | Q(type=TypeTransaction.Gain)), etat_validation=True)).aggregate(
                                           solde=Sum('montant'), depot=Sum('depot'), mise=Sum('mise'), gain=Sum('gain'), retrait=Sum('retrait')
                                           )

    solde = total_transactions["solde"] if total_transactions and total_transactions["solde"] else 0
    total_depot = total_transactions["depot"] if total_transactions and total_transactions["depot"] else 0
    total_mise = total_transactions["mise"] if total_transactions and total_transactions["mise"] else 0
    total_gain = total_transactions["gain"] if total_transactions and total_transactions["gain"] else 0
    total_retrait = total_transactions["retrait"] if total_transactions and total_transactions["retrait"] else 0

    solde_retirable = (total_gain - total_retrait) if (total_depot - total_mise) >= 0 else ((total_gain - total_retrait) + (total_depot - total_mise))
    #total_depot = 
    
    notifications_attentes = None
    if profil:
        notifications_attentes = HistoriqueNotification.objects.filter(profil=profil, etat_lecture=False, etat_validation=True, etat_suppression=False)

    partie_encours = None
    if profil:
        partie_encours = Participation.objects.filter(profil = profil, partie__etat_fin = False, partie__etat_validation=True, partie__etat_suppression=False, etat_fin=False, etat_exclusion=False, etat_validation=True, etat_suppression=False).first()


    return {
        'config' : config, 
        'profil' : profil, 
        'notifications_attentes' : notifications_attentes, 
        'complement_genre' : complement_genre, 
        'my_current_url' : my_current_url, 
        'code_invitation' : code_invitation, 
        'next' : next,
        'solde' : solde,
        'solde_retirable' : solde_retirable,
        'total_depot' : total_depot,
        'total_mise' : total_mise,
        'total_gain' : total_gain,
        'total_retrait' : total_retrait,
        'minimum_depot' : minimum_depot,
        'minimum_retrait' : minimum_retrait,
        'partie_encours' : partie_encours
        }      
    # return {'config' : config, 'costum_parallax' : costum_parallax, 'my_current_url':my_current_url, 'notification_messages':notification_messages, 'gtag':settings.GTAG}      

def CurrentConfig():
    try:  
        return Configuration.objects.filter(etat_validation=True, etat_suppression=False).order_by("-pk").first()
    except:
        return None
    """


    
