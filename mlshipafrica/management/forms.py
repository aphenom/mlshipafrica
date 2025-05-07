from django.forms import EmailInput, FileInput, ModelForm, TextInput, DateInput, Select, NumberInput, ClearableFileInput, Textarea, CheckboxInput
from django import forms
from management.models import Vendeur
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.widgets import PhoneNumberPrefixWidget

'''formulaire pour remplir informations avant et servant pour la validation'''
class VendeurForm(forms.ModelForm):

    numero_contact = PhoneNumberField(
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000",'required':'required'},
            )
    )

    numero_sms = PhoneNumberField(
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000",'required':'required'},
            )
    )
        
    class Meta:
        model = Vendeur
        exclude = ['code', 'user', 'creation_par', 'modification_par', 'etat_validation', 'etat_suppression', 'date_suppression', 'date_validation', 'date_modification', 'date_creation', 'etat_approbation', 'approbation_par', 'license']
        
        fields = ['nom', 'logo', 'adresse', 'nom_contact', 'prenom_contact', 'fonction_contact', 'numero_contact', 'numero_sms', 'email_notification']

        widgets = {
            'nom': TextInput(attrs={'placeholder':'Votre nom de vendeur', 'class':'form-control','required':'required'}),
            'logo': FileInput(attrs={'placeholder':'Votre logo', 'class':'form-control'}),
            'adresse': TextInput(attrs={'placeholder':'Votre adresse', 'class':'form-control'}),
            'nom_contact': TextInput(attrs={'placeholder':'Le nom de la personne à contacter', 'class':'form-control'}),
            'prenom_contact': TextInput(attrs={'placeholder':'Le(s) prénom(s) de la personne à contacter', 'class':'form-control'}),
            'fonction_contact': TextInput(attrs={'placeholder':'Le rôle de la personne à contacter', 'class':'form-control'}),
            # 'pays_residence': Select(attrs={'class':'form-control select2', 'data-select' : 'true'}),
            'email_notification': EmailInput(attrs={'placeholder':"Votre adresse mail de réception des notifications", 'class':'form-control','required':'required'}),
            # "contact": PhoneNumberPrefixWidget(
            #     attrs={"class": "p2 col-md-6 col-12", "placeholder": "0000000000"},
            # ),
        }

