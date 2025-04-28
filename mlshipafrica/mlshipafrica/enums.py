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
