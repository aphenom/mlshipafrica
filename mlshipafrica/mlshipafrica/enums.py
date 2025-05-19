# enums.py
from django.db import models


class StatutTraitement(models.TextChoices):
    BROUILLON = 'brouillon', 'Brouillon'
    EN_ATTENTE_RAMASSAGE = 'en_attente_ramassage', 'En attente de ramassage'
    RAMASSE = 'ramasse', 'Ramassé'
    EN_ATTENTE_DEPOT = 'en_attente_depot', 'En attente de dépôt'
    DEPOT = 'depot', 'Déposé'
    EN_TRANSIT = 'en_transit', 'En transit'
    EN_COURS_LIVRAISON = 'en_cours_livraison', 'En cours de livraison'
    ARRIVE = 'arrive', 'Arrivé à destination'
    LIVRE = 'livre', 'Livré'
    LIVRE_PAYE = 'livre_paye', 'Livré et payé'
    EN_RETOURNE = 'en_retour', 'En retour'
    RETOURNE = 'retourne', 'Retourné'


STATUT_TRAITEMENT_COULEURS = {
    'brouillon': 'dark',
    'en_attente_ramassage': 'warning',
    'ramasse': 'secondary',
    'en_attente_depot': 'warning',
    'depot': 'secondary',
    'en_transit': 'primary',
    'en_cours_livraison': 'primary',
    'arrive': 'info',
    'livre': 'success',
    'livre_paye': 'success',
    'en_retour': 'light',
    'retourne': 'dark',
}


class TypeVendeurChoice(models.TextChoices):
    # NA = '', 'Placholede'
    PHYSIQUE = 'physique', 'Physique'
    SOCIETE = 'societe', 'Société'


class DureeActiviteChoice(models.TextChoices):
    DEBUTANT = 'debutant', 'Débutant'
    MOINS_6M = 'moins_6_mois', 'Moins de 6 mois'
    DE_6M_1A = '6m_1a', '6 mois à 1 an'
    PLUS_1A = 'plus_1a', 'Plus d’un an'


class FrequenceEnvoiChoice(models.TextChoices):
    DEBUTANT = 'quotidien', 'Tous les jours'
    DE_2_3SEM = '2_3_sem', '2 à 3 fois par semaine'
    DE_1SEM = '1_sem', '1 fois par semaine'
    OCCASIONNEL = 'occasionnel', 'Occasionnellement'


class NombreColisSemaineChoice(models.TextChoices):
    MOINS_10 = 'moins_10', 'Moins de 10'
    DE_10_50 = '10_50', '10 à 50'
    DE_51_100 = '51_100', '51 à 100'
    PLUS_100 = 'plus_100', 'Plus de 100'


class PlateformeChoice(models.TextChoices): 
    FACEBOOK_INSTAGRAM = 'facebook_instagram', 'Facebook / Instagram'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    ECOMMERCE = 'ecommerce', 'Shopify / YouCan / Storeino'
    AUTRE = 'autre', 'Autre'


class ProduitsChoice(models.TextChoices): 
    COSMETIQUES = 'cosmetiques', 'Cosmétiques'
    MODE = 'mode', 'Mode / Accessoires'
    ECOMMERCE = 'ecommerce', 'Shopify / YouCan / Storeino'
    HIGHTECH = 'hightech', 'High-tech'
    MAISON = 'maison', 'Maison / Cuisine'
    AUTRE = 'autre', 'Autre'


class NatureChoice(models.TextChoices): 
    PETIT = 'petit', 'Petit (moins de 2kg)'
    MOYEN = 'moyen', 'Moyen (entre 3 - 5kg)'
    GROS = 'gros', 'Gros (plus de 10kg)'
    LARGE = 'large', 'Large (plus de 50kg)'


BOOLEAN_CHOICES = (
    (True, 'Oui'),
    (False, 'Non'),
)    