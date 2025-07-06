# myapp/resources.py
from import_export import resources
from .models import Vendeur # Replace MyModel with your actual model

class VendeurResource(resources.ModelResource):
    class Meta:
        model = Vendeur
        # Optionally, specify fields to import/export, exclude fields, etc.
        fields = ('nom_entreprise', 'immatriculation', 'nom_gerant', 'nom_store', 'logo', 'email', 'adresse', 
                  'nom_contact', 'prenom_contact', 'fonction_contact', 'numero_contact', 'numero_sms', 'email_notification',
                  'type_vendeur', 'type_piece_identite', 'piece_identite', 'dfe', 'rccm', 'duree_activite',
                  'plateformes', 'plateformes_autre', 'type_produits_vendus', 'produits', 'produits_autre',
                  'nature_colis', 'frequence_envoi', 'nombre_colis_semaine', 'cod_actif', 'collecte_par_mlship')
        # exclude = ('created_at', 'updated_at',)