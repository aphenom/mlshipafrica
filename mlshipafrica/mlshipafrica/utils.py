
import string
import random
from django.utils import timezone
from django.apps import apps




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