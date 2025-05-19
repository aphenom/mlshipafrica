from django.forms import BooleanField, CheckboxSelectMultiple, EmailInput, FileInput, ModelForm, TextInput, DateInput, Select, NumberInput, ClearableFileInput, Textarea, CheckboxInput
from django import forms
from management.models import Vendeur
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.widgets import PhoneNumberPrefixWidget

from mlshipafrica.enums import BOOLEAN_CHOICES, NatureChoice, PlateformeChoice, ProduitsChoice

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

    plateformes = forms.MultipleChoiceField(
        label="Plateformes utilisées",
        choices=PlateformeChoice.choices,
        widget=CheckboxSelectMultiple(),
        required=True,
    )
    
    produits = forms.MultipleChoiceField(
        label="Type de produits à expédier",
        choices=ProduitsChoice.choices,
        widget=CheckboxSelectMultiple(),
        required=True,
    )

    nature_colis = forms.MultipleChoiceField(
        label="Nature moyenne des colis",
        choices=NatureChoice.choices,
        widget=CheckboxSelectMultiple(),
        required=True,
    )

    cod_actif = forms.TypedChoiceField(
        label="Souhaitez-vous activer le paiement à la livraison pour vos clients ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    collecte_par_mlship = forms.TypedChoiceField(
        label="Souhaitez-vous que ML SHIP Africa collecte l’argent et vous le reverse ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )
            
    class Meta:
        model = Vendeur
        exclude = ['code', 'user', 'creation_par', 'modification_par', 'etat_validation', 'etat_suppression', 'date_suppression', 'date_validation', 'date_modification', 'date_creation', 'etat_approbation', 'approbation_par', 'license']
        
        fields = ['nom_entreprise', 'immatriculation', 'nom_gerant', 'nom_store', 'logo', 'email', 'adresse', 
                  'nom_contact', 'prenom_contact', 'fonction_contact', 'numero_contact', 'numero_sms', 'email_notification',
                  'type_vendeur', 'cni', 'permis', 'passeport', 'dfe', 'rccm', 'duree_activite',
                  'plateformes', 'plateformes_autre', 'type_produits_vendus', 'produits', 'produits_autre',
                  'nature_colis', 'frequence_envoi', 'nombre_colis_semaine', 'cod_actif', 'collecte_par_mlship']

        widgets = {
            'nom_entreprise': TextInput(attrs={'placeholder':'Le nom de votre entreprise', 'class':'form-control'}),
            'immatriculation': TextInput(attrs={'placeholder':'Le RCCM / Numéro d\'immatriculation de votre entreprise', 'class':'form-control'}),
            'nom_gerant': TextInput(attrs={'placeholder':'Le nom du gérant de votre entreprise', 'class':'form-control'}),
            'nom_store': TextInput(attrs={'placeholder':'Le nom de votre boutique / store', 'class':'form-control', 'required':'required'}),
            'logo': FileInput(attrs={'placeholder':'Le logo de votre entreprise', 'class':'form-control'}),
            'email': EmailInput(attrs={'placeholder':'L\'adresse mail de votre entreprise', 'class':'form-control'}),
            'adresse': TextInput(attrs={'placeholder':'L\'adresse de votre entreprise', 'class':'form-control'}),
            'nom_contact': TextInput(attrs={'placeholder':'Le nom de la personne à contacter', 'class':'form-control'}),
            'prenom_contact': TextInput(attrs={'placeholder':'Le(s) prénom(s) de la personne à contacter', 'class':'form-control'}),
            'fonction_contact': TextInput(attrs={'placeholder':'Le rôle de la personne à contacter', 'class':'form-control'}),
            'email_notification': EmailInput(attrs={'placeholder':"Votre adresse mail de réception des notifications", 'class':'form-control','required':'required'}),
            'type_vendeur': Select(attrs={'placeholder':'Sélectionnez le type qui correspond à votre profil vendeur', 'class':'form-control', 'required':'required'}),
            'cni': FileInput(attrs={'placeholder':'La CNI du gérant de votre entreprise', 'class':'form-control'}),
            'permis': FileInput(attrs={'placeholder':'Le permis du gérant votre entreprise', 'class':'form-control'}),
            'passeport': FileInput(attrs={'placeholder':'Le passeport du gérant de votre entreprise', 'class':'form-control'}),
            'dfe': FileInput(attrs={'placeholder':'La DFE de votre entreprise', 'class':'form-control'}),
            'rccm': FileInput(attrs={'placeholder':'Le RCCM de votre entreprise', 'class':'form-control'}),
            'duree_activite': Select(attrs={'placeholder':'Depuis combien de temps vendez-vous en ligne ?', 'class':'form-control', 'required':'required'}),
            'plateformes_autre': TextInput(attrs={'placeholder':'Autres plateformes utilisés', 'class':'form-control'}),
            'type_produits_vendus': TextInput(attrs={'placeholder':'Décrivez les produits que vous vendez', 'class':'form-control', 'required':'required'}),
            'produits_autre': TextInput(attrs={'placeholder':'Autres produits vendus', 'class':'form-control'}),
            'frequence_envoi': Select(attrs={'placeholder':'Sélectionnez votre fréquence d’envoi', 'class':'form-control', 'required':'required'}),
            'nombre_colis_semaine': Select(attrs={'placeholder':'Sélectionnez le nombre moyen de colis livré par semaine', 'class':'form-control', 'required':'required'}),
        }

