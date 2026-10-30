"""
Circuit des statuts d'un colis : la seule source de vérité pour savoir quel statut peut suivre lequel.

La vue d'administration propose uniquement les statuts renvoyés par `statuts_suivants`, et refuse
côté serveur tout autre statut posté (un bouton masqué ne suffit pas).
"""
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
    S.ECHEC_LIVRAISON: (S.LIVRE, S.LIVRE_PAYE, S.EN_RETOUR),
    S.EN_RETOUR: (S.RETOURNE,),
    # Relance après une annulation : le colis reprend là où il était (voir statuts_suivants)
    S.ANNULE: (),
}

# Statuts « pas encore expédié » : une annulation y est possible et donne « Annulé avant expédition »
STATUTS_AVANT_EXPEDITION = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.RAMASSE, S.DEPOT)


def statuts_suivants(article, dernier_historique):
    """Liste des (valeur, libellé) que l'on peut appliquer maintenant à ce colis."""
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
    # Ramassage chez le vendeur ou dépôt au hub, jamais les deux
    if article.is_option_recuperation:
        possibles = [s for s in possibles if s != S.DEPOT]
    else:
        possibles = [s for s in possibles if s != S.RAMASSE]

    libelles = dict(S.choices)
    return [(s, libelles[s]) for s in possibles]


def transition_autorisee(article, dernier_historique, nouveau_statut):
    return any(valeur == nouveau_statut for valeur, _ in statuts_suivants(article, dernier_historique))
