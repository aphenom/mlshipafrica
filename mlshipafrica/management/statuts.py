"""
Circuit des statuts d'un colis : la seule source de vérité pour savoir quel statut peut suivre lequel.

La vue d'administration propose uniquement les statuts renvoyés par `statuts_suivants`, et refuse
côté serveur tout autre statut posté (un bouton masqué ne suffit pas).

    En attente ─► Ramassé / Déposé (reçu chez nous) ─► En transit ─► En cours de livraison ─► Arrivé
    Arrivé ─► Livré | Échec ─► Reconduit ─► Livré | Échec … ─► En retour vers Abidjan ─► Revenu à Abidjan
    Revenu à Abidjan ─► Substitué (nouveau client, repart en préparation) | Retourné au vendeur
                      | Remis en stock (vendeurs en stockage) | Abandonné (après 30 jours)
    Avant le départ, tout colis peut être « Annulé avant expédition », puis relancé.
"""
from django.utils import timezone

from mlshipafrica.enums import StatutTraitement as S

# Statut actuel → statuts suivants possibles
TRANSITIONS = {
    S.EN_ATTENTE_RAMASSAGE: (S.RAMASSE, S.ANNULE),
    S.EN_ATTENTE_DEPOT: (S.DEPOT, S.ANNULE),
    S.RAMASSE: (S.EN_TRANSIT, S.ANNULE),
    S.DEPOT: (S.EN_TRANSIT, S.ANNULE),
    S.EN_TRANSIT: (S.EN_COURS_LIVRAISON,),
    S.EN_COURS_LIVRAISON: (S.ARRIVE,),
    S.ARRIVE: (S.LIVRE, S.LIVRE_PAYE, S.ECHEC_LIVRAISON, S.EN_RETOUR),
    S.ECHEC_LIVRAISON: (S.RECONDUIT, S.LIVRE, S.LIVRE_PAYE, S.EN_RETOUR),
    S.RECONDUIT: (S.LIVRE, S.LIVRE_PAYE, S.ECHEC_LIVRAISON, S.EN_RETOUR),
    S.EN_RETOUR: (S.REVENU_ABIDJAN,),
    S.REVENU_ABIDJAN: (S.SUBSTITUE, S.RETOURNE, S.REMIS_EN_STOCK, S.ABANDONNE),
    S.SUBSTITUE: (S.DEPOT,),                     # tout colis repasse par la préparation avant de repartir
    S.ANNULE: (),                                # relance : voir statuts_suivants
}

# Statuts « pas encore expédié » : une annulation y est possible et donne « Annulé avant expédition »
STATUTS_AVANT_EXPEDITION = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.RAMASSE, S.DEPOT)

# Décisions réservées au manager (et à la direction) : retour validé à Abidjan, sortie définitive du colis
STATUTS_RESERVES_RETOURS = (S.REVENU_ABIDJAN, S.RETOURNE, S.REMIS_EN_STOCK, S.ABANDONNE)

# Alerte si un colis reste 48 h sans mouvement dans ces statuts (onglet « À sauver »)
STATUTS_SURVEILLES_48H = (S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT)

JOURS_AVANT_ABANDON = 30


def date_revenu_abidjan(article):
    histo = (article.article_historiquearticles.filter(statut_traitement=S.REVENU_ABIDJAN, etat_suppression=False)
             .order_by('-date_creation').first())
    return histo.date_creation if histo else None


def statuts_suivants(article, dernier_historique, user=None):
    """Liste des (valeur, libellé) que l'on peut appliquer maintenant à ce colis (et par cet utilisateur)."""
    if dernier_historique is None:
        return []
    actuel = dernier_historique.statut_traitement
    possibles = list(TRANSITIONS.get(actuel, ()))

    if actuel == S.ANNULE:
        # Relance : on revient au statut d'avant l'annulation (ex. « Déposé » si le colis est chez nous)
        precedent = dernier_historique.dernier_historique_article
        if precedent is not None and precedent.statut_traitement in STATUTS_AVANT_EXPEDITION:
            possibles = [precedent.statut_traitement]

    # Un colis avec encaissement passe par « Livré et payé », sans encaissement par « Livré »
    if article.is_option_encaissement:
        possibles = [s for s in possibles if s != S.LIVRE]
    else:
        possibles = [s for s in possibles if s != S.LIVRE_PAYE]
    # Au départ : ramassage chez le vendeur ou dépôt au hub, jamais les deux
    if actuel in (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT):
        possibles = [s for s in possibles if s != (S.DEPOT if article.is_option_recuperation else S.RAMASSE)]
    # Remise en stock : seulement pour un vendeur en stockage
    if not getattr(article.vendeur, 'option_stockage', False):
        possibles = [s for s in possibles if s != S.REMIS_EN_STOCK]
    # Abandon : seulement après 30 jours à Abidjan
    if S.ABANDONNE in possibles:
        revenu = date_revenu_abidjan(article)
        if revenu is None or (timezone.now() - revenu).days < JOURS_AVANT_ABANDON:
            possibles.remove(S.ABANDONNE)
    # Décisions de retour : manager et direction seulement
    if user is not None:
        from mlshipafrica.droits import a_le_droit
        if not a_le_droit(user, 'colis_retours'):
            possibles = [s for s in possibles if s not in STATUTS_RESERVES_RETOURS]

    libelles = dict(S.choices)
    return [(s, libelles[s]) for s in possibles]


def transition_autorisee(article, dernier_historique, nouveau_statut, user=None):
    return any(valeur == nouveau_statut for valeur, _ in statuts_suivants(article, dernier_historique, user))
