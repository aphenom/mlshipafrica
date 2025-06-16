from django.forms import PasswordInput, EmailInput, ModelForm, TextInput, DateInput, Select, NumberInput, ClearableFileInput, Textarea, CheckboxInput, DecimalField
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import AbstractUser, User
from datetime import datetime
import uuid
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm

from django.contrib.auth.forms import AuthenticationForm

from core.models import Configuration, FormatArticle, License, Localite, PartenaireLogistique, Zone
from mlshipafrica.enums import BOOLEAN_CHOICES
from django_currentuser.middleware import (
    get_current_user, get_current_authenticated_user)
from phonenumber_field.formfields import PhoneNumberField



#User = get_user_model()


class LicenseForm(forms.ModelForm):
    class Meta:
        model = License
        exclude = ['date_creation', 'date_modification']
        
        fields = []#['filiale', 'libelle', 'taux', 'sens', 'status']
        
        #phone2 = PhoneNumberField()
        """
        widgets = {
            'filiale': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'libelle': TextInput(attrs={'placeholder':'', 'class':'form-control'}),
            'taux': NumberInput(attrs={'placeholder':'', 'class':'form-control'}),
            'sens': Select(attrs={'class':'form-control'}, choices = Sens),
            'status': Select(attrs={'class':'form-control'}, choices = Status),
        }
        """


class ConfigurationForm(forms.ModelForm):
    
    enable_option_recuperation = forms.TypedChoiceField(
        label="Souhaitez-vous permettre l'option recuperation colis ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    enable_option_encaissement = forms.TypedChoiceField(
        label="Souhaitez-vous permettre l'option encaissement client ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    class Meta:
        model = Configuration
        exclude = ['date_creation', 'date_modification']
        
        fields = ['app_nom', 'slogan', 'email', 'monnaie', 'contact', 'cout_option_recuperation',
                  'taux_option_recuperation', 'cout_option_encaissement', 'taux_option_encaissement',
                  'license', 'url_api_sms', 'key_api_sms', 'id_api_sms', 'json_api_sms', 'logo',
                  'logo_symbol', 'favicon', 'enable_option_recuperation', 'enable_option_encaissement']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'app_nom': TextInput(attrs={'placeholder':'Le nom de la plateforme', 'class':'form-control'}),
            'slogan': TextInput(attrs={'placeholder':'Le slogan', 'class':'form-control'}),
            'email': EmailInput(attrs={'placeholder':'L\'adresse email', 'class':'form-control'}),
            'monnaie': TextInput(attrs={'placeholder':'La monnaie', 'class':'form-control'}),
            'contact': TextInput(attrs={'placeholder':'Le(s) contact(s)', 'class':'form-control'}),
            'cout_option_recuperation': NumberInput(attrs={'placeholder':'Le coût fixe option recuperation colis', 'class':'form-control'}),
            'taux_option_recuperation': NumberInput(attrs={'placeholder':'Le taux option récupération colis', 'class':'form-control'}),
            'cout_option_encaissement': NumberInput(attrs={'placeholder':'Le coût fixe option encaissement client', 'class':'form-control'}),
            'taux_option_encaissement': NumberInput(attrs={'placeholder':'Le taux option encaissement client', 'class':'form-control'}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'url_api_sms': TextInput(attrs={'placeholder':'SMS Base URL', 'class':'form-control'}),
            'key_api_sms': TextInput(attrs={'placeholder':'SMS API KEY', 'class':'form-control'}),
            'id_api_sms': TextInput(attrs={'placeholder':'SMS API ID', 'class':'form-control'}),
            'json_api_sms': Textarea(attrs={'placeholder':'JSON API SMS', 'class':'form-control'}),
            'logo': ClearableFileInput(attrs={'placeholder':"Chargez le logo", 'class':'form-control-file', 'accept':'image/jpeg,image/png'}),
            'logo_symbol': ClearableFileInput(attrs={'placeholder':"Chargez le symbole du logo", 'class':'form-control-file', 'accept':'image/jpeg,image/png'}),
            'favicon': ClearableFileInput(attrs={'placeholder':"Chargez le favicon", 'class':'form-control-file', 'accept':'image/jpeg,image/png,image/ico'}),
        }


class FormatArticleForm(forms.ModelForm):

    class Meta:
        model = FormatArticle
        exclude = ['date_creation', 'date_modification']
        
        fields = ['nom', 'caracteristique', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'nom': TextInput(attrs={'placeholder':'Le nom du format', 'class':'form-control'}),
            'caracteristique': TextInput(attrs={'placeholder':'Les caractéristiques du format', 'class':'form-control'}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }

        
class ZoneForm(forms.ModelForm):

    is_depart = forms.TypedChoiceField(
        label="Souhaitez-vous permettre le départ depuis cette zone ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    is_arrivee = forms.TypedChoiceField(
        label="Souhaitez-vous permettre l'arrivée dans cette zone ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    class Meta:
        model = Zone
        exclude = ['date_creation', 'date_modification']
        
        fields = ['nom', 'is_depart', 'is_arrivee', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'nom': TextInput(attrs={'placeholder':'Le nom de la zone', 'class':'form-control'}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }

        
class LocaliteForm(forms.ModelForm):

    is_depart = forms.TypedChoiceField(
        label="Souhaitez-vous permettre le départ depuis cette localité ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    is_arrivee = forms.TypedChoiceField(
        label="Souhaitez-vous permettre l'arrivée dans cette localité ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    def __init__(self, *args, **kwargs):
      	# Extract the user from the view
        # user = kwargs.pop('request')
        # print(get_current_user())
        super(LocaliteForm, self).__init__(*args, **kwargs)
        # Filter authors related to the logged-in user
        user = get_current_user()
        if user and hasattr(user, 'profil_staff'):
            self.fields['zone'].queryset = Localite.objects.filter(license=user.profil_staff.license, etat_validation=True, etat_suppression=False)


    class Meta:
        model = Localite
        exclude = ['date_creation', 'date_modification']
        
        fields = ['nom', 'is_depart', 'is_arrivee', 'zone', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'nom': TextInput(attrs={'placeholder':'Le nom de la localité', 'class':'form-control'}),
            'zone': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }


class PartenaireLogistiqueForm(forms.ModelForm):

    contact = PhoneNumberField(
        label="Numéro téléphone",
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000"},
            ),
        required=False,
    )

    class Meta:
        model = PartenaireLogistique
        exclude = ['date_creation', 'date_modification']
        
        fields = ['nom', 'email', 'contact', 'adresse', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'nom': TextInput(attrs={'placeholder':'Le nom du partenaire logistique', 'class':'form-control'}),
            'email': EmailInput(attrs={'placeholder':'L\'adresse email du partenaire logistique', 'class':'form-control'}),
            'adresse': TextInput(attrs={'placeholder':'L\'adresse du partenaire logistique', 'class':'form-control'}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }

