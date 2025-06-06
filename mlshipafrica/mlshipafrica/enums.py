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
    REVERSE = 'reverse', 'Reversé'
    EN_RETOUR = 'en_retour', 'En retour'
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
    'reverse': 'dark',
    'en_retour': 'light',
    'retourne': 'dark',
}


STATUT_TRAITEMENT_ICONES = {
    'brouillon': 'dark',
    'en_attente_ramassage': 'hourglass-half',
    'ramasse': 'cart-arrow-down',
    'en_attente_depot': 'hourglass-half',
    'depot': 'building',
    'en_transit': 'truck',
    'en_cours_livraison': 'primary',
    'arrive': 'map-pin',
    'livre': 'check-circle',
    'livre_paye': 'check-circle',
    'reverse': 'money',
    'en_retour': 'light',
    'retourne': 'dark',
}


STATUT_TRAITEMENT_COMMENTAIRES = {
    'brouillon': 'La commande est en cours de préparation par le vendeur. Elle n\'a pas encore été validée pour le ramassage.',
    'en_attente_ramassage': 'La commande est prête chez le vendeur. Notre équipe est en route pour effectuer le ramassage à l’adresse indiquée.',
    'ramasse': 'Le colis a été récupéré avec succès. Il est maintenant en direction de notre centre logistique pour traitement.',
    'en_attente_depot': 'Le colis est attendu à notre hub. Il sera pris en charge dès qu\'il sera déposé par le vendeur.',
    'depot': 'Le colis est enregistré dans notre hub. Il sera préparé pour l’expédition selon la destination du client.',
    'en_transit': 'Le colis est actuellement en cours d’acheminement vers la ville ou la zone de livraison finale.',
    'en_cours_livraison': 'Le colis est en cours de livraison chez le client. Notre livreur est en route.',
    'arrive': 'Le colis est arrivé dans la zone de livraison. Il est en attente de retrait par le client.',
    'livre': 'Le client a reçu son colis.',
    'livre_paye': 'Le client a reçu son colis et a réglé le montant à la livraison. La transaction est confirmée.',
    'reverse': 'Le montant collecté a été reversé au vendeur selon le mode de paiement convenu.',
    'en_retour': 'Le colis est en cours de retour vers le vendeur suite à un échec de livraison ou une demande du client.',
    'retourne': 'Le colis est retourné au vendeur avec succès.',
}


class TypeVendeurChoice(models.TextChoices):
    # NA = '', 'Placholede'
    PARTICULIER = 'particulier', 'Particulier'
    SOCIETE = 'societe', 'Société'


class TypePieceIdentiteChoice(models.TextChoices):
    # NA = '', 'Placholede'
    CNI = 'cni', 'Carte nationale d\'identité'
    PERMIS = 'permis', 'Permis'
    Passeport = 'passeport', 'Passeport'


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
    FACEBOOK = 'facebook', 'Facebook'
    INSTAGRAM = 'instagram', 'Instagram'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    SHOPIFY = 'shopify', 'Shopify'
    YOUCAN = 'youcan', 'YouCan'
    ECOMMERCE = 'storeino', 'Storeino'
    AUTRE = 'autre', 'Autre'


class ProduitsChoice(models.TextChoices): 
    COSMETIQUES = 'cosmetiques', 'Cosmétiques'
    MODE = 'mode', 'Mode / Accessoires'
    SANTE = 'sante', 'Santé / Bien-être'
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


class TypeProfilStaffChoice(models.TextChoices):
    # NA = '', 'Placholede'
    AGENT = 'agent', 'Agent'
    COMPTABLE = 'comptable', 'Comptable'
    ADMINISTRATEUR = 'administrateur', 'Administrateur'
    SUPER = 'super', 'Super Administrateur'


class StatutVendeur(models.TextChoices):
    # NA = '', 'Placholede'
    ATTENTE_APPROBATION = 'attente_approbation', 'Attente approbation'
    ACTIF = 'actif', 'Actif'
    INACTIF = 'inactif', 'Inactif'
    SUPPRIME = 'supprime', 'Supprimé'

STATUT_VENDEUR_COULEURS = {
    'attente_approbation': 'warning',
    'actif': 'success',
    'inactif': 'black',
    'supprime': 'danger',
}

