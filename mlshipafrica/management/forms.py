from django.forms import BooleanField, CheckboxSelectMultiple, EmailInput, FileInput, ModelForm, TextInput, DateInput, Select, NumberInput, ClearableFileInput, Textarea, CheckboxInput
from django import forms
from management.models import Article, ProduitStock, ProfilStaff, Tarification, Vendeur
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.widgets import PhoneNumberPrefixWidget

from core.models import FormatArticle, Localite, PartenaireLogistique, Zone
from mlshipafrica.enums import BOOLEAN_CHOICES, NatureChoice, PlateformeChoice, ProduitsChoice, TypeProfilStaffChoice
from django_currentuser.middleware import (
    get_current_user, get_current_authenticated_user)


def libelle_localite_avec_delai(localite):
    """« Bouaké · Zone 3 · J+3 à J+4 » (le délai n'apparaît que s'il est renseigné sur la zone)."""
    morceaux = [localite.nom]
    if localite.zone_id:
        morceaux.append(localite.zone.nom)
        delai = localite.zone.get_delai_display()
        if delai:
            morceaux.append(delai)
    return ' · '.join(morceaux)


# Rôles autorisés à voir et saisir le coût d'achat chez le partenaire logistique (donnée interne)
ROLES_COUT_PARTENAIRE = (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.COMPTABLE)


def peut_voir_cout_partenaire(user):
    profil = getattr(user, 'account_profil_staff', None) if user else None
    return bool(profil and profil.role_profil in ROLES_COUT_PARTENAIRE)

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
        user = get_current_user()
        license = None
        if user and hasattr(user, 'account_vendeur'):
            license = user.account_vendeur.license
        elif user and hasattr(user, 'account_profil_staff'):
            license = user.account_profil_staff.license
        localites = Localite.objects.filter(is_arrivee=True, etat_validation=True, etat_suppression=False).select_related('zone')
        if license is not None:
            localites = localites.filter(license=license)
        self.fields['localite_arrivee'].queryset = localites
        # Le vendeur voit la zone et le délai estimé : « Bouaké · Zone 3 · J+3 à J+4 »
        self.fields['localite_arrivee'].label_from_instance = libelle_localite_avec_delai

        # Seuls les formats qui ont un tarif actif sont proposés (ex. « Grand » tant qu'il n'est pas ouvert)
        formats = FormatArticle.objects.filter(
            etat_validation=True, etat_suppression=False,
            format_articletarification__etat_validation=True,
            format_articletarification__etat_suppression=False,
            format_articletarification__vendeur__isnull=True,
        ).distinct()
        if license is not None:
            formats = formats.filter(license=license)
        self.fields['format_article'].queryset = formats

        # Vendeur en stockage : il choisit le produit à sortir de son stock
        vendeur = getattr(user, 'account_vendeur', None) if user else None
        if vendeur is not None and vendeur.option_stockage:
            self.fields['produit_stock'].queryset = ProduitStock.objects.filter(vendeur=vendeur, actif=True, quantite_disponible__gt=0)
            self.fields['produit_stock'].label = "Produit de mon stock"
            self.fields['produit_stock'].required = False
            self.fields['produit_stock'].widget.attrs.update({'class': 'form-control'})
        else:
            self.fields.pop('produit_stock', None)

    class Meta:
        model = Article
        # exclude = ['code', 'user', 'creation_par', 'modification_par', 'etat_validation', 'etat_suppression', 'date_suppression', 'date_validation', 'date_modification', 'date_creation', 'etat_approbation', 'approbation_par', 'license']
        
        fields = ['valeur', 'quantite', 'designation', 'produits', 'produits_autre',
                  'nom_destinataire', 'prenom_destinataire', 'prenom_destinataire', 
                  'numero_principal_destinataire', 'numero_secondaire_destinataire', 'adresse_destinataire', 
                  'localite_arrivee', 'format_article', 'is_option_recuperation', 'is_option_encaissement', 'produit_stock']

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



class TarificationForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
      	# Extract the user from the view
        # user = kwargs.pop('request')
        # print(get_current_user())
        super(TarificationForm, self).__init__(*args, **kwargs)
        # Filter authors related to the logged-in user
        user = get_current_user()
        profil = getattr(user, 'account_profil_staff', None) if user else None
        if profil is not None and profil.license_id:
            license = profil.license
            self.fields['localite_depart'].queryset = Localite.objects.filter(license=license, etat_validation=True, etat_suppression=False)
            self.fields['localite_arrivee'].queryset = Localite.objects.filter(license=license, etat_validation=True, etat_suppression=False)
            self.fields['zone_depart'].queryset = Zone.objects.filter(license=license, etat_validation=True, etat_suppression=False)
            self.fields['zone_arrivee'].queryset = Zone.objects.filter(license=license, etat_validation=True, etat_suppression=False)
            self.fields['vendeur'].queryset = Vendeur.objects.filter(license=license, etat_validation=True, etat_suppression=False)
            self.fields['partenaire_logistique'].queryset = PartenaireLogistique.objects.filter(license=license, etat_validation=True, etat_suppression=False)
        # Coût d'achat chez le partenaire : seuls le CEO (super administrateur) et la comptable le voient.
        # Pour les autres rôles le champ est retiré du formulaire, donc jamais affiché ni écrasé à l'enregistrement.
        if not peut_voir_cout_partenaire(user):
            self.fields.pop('cout_partenaire', None)

    class Meta:
        model = Tarification
        exclude = ['date_creation', 'date_modification']
        
        fields = ['montant_frais', 'cout_partenaire', 'cout_option_recuperation', 'taux_option_recuperation', 'cout_option_encaissement', 'taux_option_encaissement',
                  'format_article', 'localite_depart', 'localite_arrivee',
                  'zone_depart', 'zone_arrivee', 'vendeur', 'partenaire_logistique', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'montant_frais': NumberInput(attrs={'placeholder':'Le coût du service', 'class':'form-control'}),
            'cout_partenaire': NumberInput(attrs={'placeholder':'Coût d\'achat par colis (interne)', 'class':'form-control'}),
            'cout_option_recuperation': NumberInput(attrs={'data-cible':"id_taux_option_recuperation", 'placeholder':'Le coût fixe option recuperation colis', 'class':'cible_connected form-control'}),
            'taux_option_recuperation': NumberInput(attrs={'data-cible':"id_cout_option_recuperation", 'placeholder':'Le taux option récupération colis', 'class':'cible_connected form-control'}),
            'cout_option_encaissement': NumberInput(attrs={'data-cible':"id_taux_option_encaissement", 'placeholder':'Le coût fixe option encaissement client', 'class':'cible_connected form-control'}),
            'taux_option_encaissement': NumberInput(attrs={'data-cible':"id_cout_option_encaissement", 'placeholder':'Le taux option encaissement client', 'class':'cible_connected form-control'}),
            'format_article': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'localite_depart': Select(attrs={'data-cible':"id_zone_depart", 'class':'cible_connected form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'localite_arrivee': Select(attrs={'data-cible':"id_zone_arrivee", 'class':'cible_connected form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'zone_depart': Select(attrs={'data-cible':"id_localite_depart", 'class':'cible_connected form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'zone_arrivee': Select(attrs={'data-cible':"id_localite_arrivee", 'class':'cible_connected form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'vendeur': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'partenaire_logistique': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }


class ProfilStaffForm(forms.ModelForm):

    numero_contact = PhoneNumberField(
        label="Numéro téléphone",
        widget=TextInput(
            attrs={"class": "form-control", "placeholder": "Entrez le numéro avec l'indicatif, exemple : +2250000000000"},
            ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seul le CEO peut créer ou nommer un compte CEO ou comptable (comptes qui voient l'argent)
        user = get_current_user()
        profil = getattr(user, 'account_profil_staff', None) if user else None
        if not (profil and profil.role_profil == TypeProfilStaffChoice.SUPER):
            reserves = (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.COMPTABLE)
            actuel = self.instance.role_profil if self.instance and self.instance.pk else None
            self.fields['role_profil'].choices = [(v, l) for v, l in self.fields['role_profil'].choices
                                                  if v not in reserves or v == actuel]

    def clean_role_profil(self):
        role = self.cleaned_data.get('role_profil')
        user = get_current_user()
        profil = getattr(user, 'account_profil_staff', None) if user else None
        actuel = self.instance.role_profil if self.instance and self.instance.pk else None
        if role in (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.COMPTABLE) and role != actuel \
                and not (profil and profil.role_profil == TypeProfilStaffChoice.SUPER):
            raise forms.ValidationError("Seul le CEO peut attribuer ce rôle.")
        return role

    class Meta:
        model = ProfilStaff
        exclude = ['date_creation', 'date_modification']
        
        fields = ['email', 'numero_contact', 'observation', 'role_profil', 'license']
        
        #phone2 = PhoneNumberField()
        widgets = {
            'email': EmailInput(attrs={'placeholder':'Email utilisateur', 'class':'form-control', 'required':'required'}),
            'observation': Textarea(attrs={'placeholder':'Observations sur l\'utilisateur', 'class':'form-control'}),
            'role_profil': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace", 'required':'required'}),
            'license': Select(attrs={'class':'form-control form-control-lg js-example-basic-single', 'style':'width:100%', 'data-dropdown-parent': "#MyFormSpace"}),
        }


