from django.forms import BooleanField, CheckboxSelectMultiple, EmailInput, FileInput, ModelForm, TextInput, DateInput, Select, NumberInput, ClearableFileInput, Textarea, CheckboxInput
from django import forms
from management.models import Article, Vendeur
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.widgets import PhoneNumberPrefixWidget

from core.models import Localite
from mlshipafrica.enums import BOOLEAN_CHOICES, NatureChoice, PlateformeChoice, ProduitsChoice

'''formulaire pour remplir informations avant et servant pour la validation du vendeur'''
class VendeurForm(forms.ModelForm):

    numero_contact = PhoneNumberField(
        label="Numéro",
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000",'required':'required'},
            )
    )

    numero_sms = PhoneNumberField(
        label="Numéro SMS",
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
                  'type_vendeur', 'type_piece_identite', 'piece_identite', 'dfe', 'rccm', 'duree_activite',
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
            'nom_contact': TextInput(attrs={'placeholder':'votre nom', 'class':'form-control'}),
            'prenom_contact': TextInput(attrs={'placeholder':'Votre(s) prénom(s)', 'class':'form-control'}),
            'fonction_contact': TextInput(attrs={'placeholder':'Votre rôle', 'class':'form-control'}),
            'email_notification': EmailInput(attrs={'placeholder':"Votre adresse mail de réception des notifications", 'class':'form-control','required':'required'}),
            'type_vendeur': Select(attrs={'placeholder':'Sélectionnez le type qui correspond à votre profil vendeur', 'class':'form-control', 'required':'required'}),
            'type_piece_identite': Select(attrs={'placeholder':'Sélectionnez le type de pièce d\'identité que vous avez', 'class':'form-control', 'required':'required'}),
            'piece_identite': FileInput(attrs={'placeholder':'Votre pièce d\'identité', 'class':'form-control', 'required':'required'}),
            'dfe': FileInput(attrs={'placeholder':'La DFE de votre entreprise', 'class':'form-control'}),
            'rccm': FileInput(attrs={'placeholder':'Le RCCM de votre entreprise', 'class':'form-control'}),
            'duree_activite': Select(attrs={'placeholder':'Depuis combien de temps vendez-vous en ligne ?', 'class':'form-control', 'required':'required'}),
            'plateformes_autre': TextInput(attrs={'placeholder':'Autres plateformes utilisés', 'class':'form-control'}),
            'type_produits_vendus': TextInput(attrs={'placeholder':'Décrivez les produits que vous vendez', 'class':'form-control', 'required':'required'}),
            'produits_autre': TextInput(attrs={'placeholder':'Autres produits vendus', 'class':'form-control'}),
            'frequence_envoi': Select(attrs={'placeholder':'Sélectionnez votre fréquence d’envoi', 'class':'form-control', 'required':'required'}),
            'nombre_colis_semaine': Select(attrs={'placeholder':'Sélectionnez le nombre moyen de colis livré par semaine', 'class':'form-control', 'required':'required'}),
        }


'''formulaire pour remplir les infos du colis (article)'''
class VendeurColisForm(forms.ModelForm):

    numero_principal_destinataire = PhoneNumberField(
        label="Numéro principal",
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000",'required':'required'},
            )
    )

    numero_secondaire_destinataire = PhoneNumberField(
        label="Numéro secondaire",
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000"},
            ),
        required=False,
    )

    produits = forms.MultipleChoiceField(
        label="Type de produits",
        choices=ProduitsChoice.choices,
        widget=CheckboxSelectMultiple(),
        required=True,
    )

    is_option_recuperation = forms.TypedChoiceField(
        label="Souhaitez-vous que ML SHIP Africa vienne récuperer directement avec vous ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    is_option_encaissement = forms.TypedChoiceField(
        label="Souhaitez-vous que ML SHIP Africa collecte l’argent auprès du client et vous le reverse ?",
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
        required=True,
    )

    def __init__(self, *args, **kwargs):
      	# Extract the user from the view
        # user = kwargs.pop('user')
        super(VendeurColisForm, self).__init__(*args, **kwargs)
        # Filter authors related to the logged-in user
        self.fields['localite_arrivee'].queryset = Localite.objects.filter(is_arrivee=True)
            
    class Meta:
        model = Article
        # exclude = ['code', 'user', 'creation_par', 'modification_par', 'etat_validation', 'etat_suppression', 'date_suppression', 'date_validation', 'date_modification', 'date_creation', 'etat_approbation', 'approbation_par', 'license']
        
        fields = ['valeur', 'quantite', 'designation', 'produits', 'produits_autre',
                  'nom_destinataire', 'prenom_destinataire', 'prenom_destinataire', 
                  'numero_principal_destinataire', 'numero_secondaire_destinataire', 'adresse_destinataire', 
                  'localite_arrivee', 'format_article', 'is_option_recuperation', 'is_option_encaissement']

        widgets = {
            'valeur': TextInput(attrs={'placeholder':'La valeur unitaire de votre produit', 'class':'form-control', 'required':'required'}),
            'quantite': NumberInput(attrs={'placeholder':'La quantité du produit', 'class':'form-control', 'required':'required'}),
            'designation': TextInput(attrs={'placeholder':'La désignation de votre produit', 'class':'form-control', 'required':'required'}),
            'produits_autre': TextInput(attrs={'placeholder':'Autres produits', 'class':'form-control'}),
            'nom_destinataire': TextInput(attrs={'placeholder':'Le nom du destinataire', 'class':'form-control', 'required':'required'}),
            'prenom_destinataire': TextInput(attrs={'placeholder':'Le(s) prénom(s) du destinataire', 'class':'form-control'}),
            'adresse_destinataire': TextInput(attrs={'placeholder':'L\'adresse du destinataire', 'class':'form-control', 'required':'required'}),
            'localite_arrivee': Select(attrs={'placeholder':'Sélectionnez la localité de destination', 'class':'form-control', 'data-select' : 'true', 'required':'required'}),
            'format_article': Select(attrs={'placeholder':'Sélectionnez le format de votre colis', 'class':'form-control ', 'required':'required'}),
        }

