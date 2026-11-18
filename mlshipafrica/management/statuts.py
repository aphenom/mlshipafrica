"""
Circuit des statuts d'un colis : la seule source de vérité pour savoir quel statut peut suivre lequel.

La vue d'administration propose uniquement les statuts renvoyés par `statuts_suivants`, et refuse
côté serveur tout autre statut posté (un bouton masqué ne suffit pas).

Ordre logique (le colis quitte Abidjan pour la ville du client) ; l'équipe peut sauter des étapes vers l'avant :
    En attente ─► Ramassé / Déposé ─► En transit ─► Arrivé (ville du client) ─► En cours de livraison ─► Livré
    Échec ─► Reconduit ─► En cours de livraison ─► Livré | Échec … ─► En retour vers Abidjan ─► Revenu à Abidjan
    Revenu à Abidjan ─► Substitué | Retourné au vendeur | Remis en stock | Abandonné (après 30 jours)
    Avant le départ, tout colis peut être « Annulé avant expédition », puis relancé.

Argent (comptable et CEO seulement) : Livré ─► Unpaid (livré, en attente de versement) ─► Reversé (relevé versé).
Correction (manager et CEO) : n'importe quel statut, motif obligatoire ; un colis Unpaid ou Reversé : CEO seulement.
"""
from django.utils import timezone

from mlshipafrica.enums import StatutTraitement as S

_APRES_DEPART = (S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE)

# Statut actuel → statuts suivants possibles
TRANSITIONS = {
    S.EN_ATTENTE_RAMASSAGE: (S.RAMASSE, S.ANNULE),
    S.EN_ATTENTE_DEPOT: (S.DEPOT, S.ANNULE),
    S.RAMASSE: _APRES_DEPART + (S.ANNULE,),
    S.DEPOT: _APRES_DEPART + (S.ANNULE,),
    S.EN_TRANSIT: (S.ARRIVE, S.EN_COURS_LIVRAISON, S.LIVRE, S.EN_RETOUR),
    S.ARRIVE: (S.EN_COURS_LIVRAISON, S.LIVRE, S.ECHEC_LIVRAISON, S.EN_RETOUR),
    S.EN_COURS_LIVRAISON: (S.LIVRE, S.ECHEC_LIVRAISON, S.EN_RETOUR),
    S.ECHEC_LIVRAISON: (S.RECONDUIT, S.EN_COURS_LIVRAISON, S.LIVRE, S.EN_RETOUR),
    S.RECONDUIT: (S.EN_COURS_LIVRAISON, S.LIVRE, S.ECHEC_LIVRAISON, S.EN_RETOUR),
    S.LIVRE: (S.LIVRE_PAYE,),                    # Unpaid : comptable et CEO
    S.EN_RETOUR: (S.REVENU_ABIDJAN,),
    S.REVENU_ABIDJAN: (S.SUBSTITUE, S.RETOURNE, S.REMIS_EN_STOCK, S.MIS_DE_COTE, S.ABANDONNE),
    S.SUBSTITUE: (S.DEPOT,),                     # tout colis repasse par la préparation avant de repartir
    S.ANNULE: (),                                # relance : voir statuts_suivants
}

# Ordre d'affichage des statuts (filtres, listes)
ORDRE = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.RAMASSE, S.DEPOT, S.EN_TRANSIT, S.ARRIVE, S.EN_COURS_LIVRAISON,
         S.ECHEC_LIVRAISON, S.RECONDUIT, S.LIVRE, S.LIVRE_PAYE, S.REVERSE, S.EN_RETOUR, S.REVENU_ABIDJAN, S.SUBSTITUE,
         S.RETOURNE, S.REMIS_EN_STOCK, S.MIS_DE_COTE, S.ABANDONNE, S.ANNULE)

# Statuts d'argent : seuls la comptable et le CEO les posent
STATUTS_ARGENT = (S.LIVRE_PAYE, S.REVERSE)

# Statuts « pas encore expédié » : une annulation y est possible et donne « Annulé avant expédition »
STATUTS_AVANT_EXPEDITION = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.RAMASSE, S.DEPOT)

# Décisions réservées au manager (et à la direction) : retour validé à Abidjan, sortie définitive du colis
STATUTS_RESERVES_RETOURS = (S.REVENU_ABIDJAN, S.RETOURNE, S.REMIS_EN_STOCK, S.MIS_DE_COTE, S.ABANDONNE)

# Alerte si un colis reste 48 h sans mouvement dans ces statuts (onglet « À sauver »)
STATUTS_SURVEILLES_48H = (S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT)

JOURS_AVANT_ABANDON = 30


def date_revenu_abidjan(article):
    histo = (article.article_historiquearticles.filter(statut_traitement=S.REVENU_ABIDJAN, etat_suppression=False)
             .order_by('-date_creation').first())
    return histo.date_creation if histo else None


def statuts_suivants(article, dernier_historique, user=None):
    """Liste des (valeur, libellé) que l'on peut appliquer maintenant à ce colis (et par cet utilisateur)."""
    # Des colis repris par import n'ont pas d'historique : on part alors du statut du colis
    actuel = dernier_historique.statut_traitement if dernier_historique is not None else article.statut_traitement
    if actuel in (None, S.BROUILLON):
        return []
    possibles = list(TRANSITIONS.get(actuel, ()))

    if actuel == S.ANNULE:
        # Relance : on revient au statut d'avant l'annulation (ex. « Déposé » si le colis est chez nous)
        precedent = dernier_historique.dernier_historique_article if dernier_historique else None
        if precedent is not None and precedent.statut_traitement in STATUTS_AVANT_EXPEDITION:
            possibles = [precedent.statut_traitement]

    # Unpaid : seulement un colis avec encaissement (l'argent du client est chez nous), et seulement la comptable / le CEO
    if not article.is_option_encaissement:
        possibles = [x for x in possibles if x != S.LIVRE_PAYE]
    # Au départ : ramassage chez le vendeur ou dépôt au hub, jamais les deux
    if actuel in (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT):
        possibles = [s for s in possibles if s != (S.DEPOT if article.is_option_recuperation else S.RAMASSE)]
    # Remise en stock : seulement pour un vendeur en stockage
    if not getattr(article.vendeur, 'option_stockage', False):
        possibles = [s for s in possibles if s not in (S.REMIS_EN_STOCK, S.MIS_DE_COTE)]
    # Abandon : seulement après 30 jours à Abidjan
    if S.ABANDONNE in possibles:
        revenu = date_revenu_abidjan(article)
        if revenu is None or (timezone.now() - revenu).days < JOURS_AVANT_ABANDON:
            possibles.remove(S.ABANDONNE)
    # Décisions de retour : manager et direction seulement
    if user is not None:
        from mlshipafrica.droits import a_le_droit
        if not a_le_droit(user, 'colis_retours'):
            possibles = [x for x in possibles if x not in STATUTS_RESERVES_RETOURS]
        if not a_le_droit(user, 'paiements'):
            possibles = [x for x in possibles if x not in STATUTS_ARGENT]
        if not a_le_droit(user, 'colis_mouvements'):
            possibles = [x for x in possibles if x in STATUTS_ARGENT]

    libelles = dict(S.choices)
    return [(s, libelles[s]) for s in possibles]


def transition_autorisee(article, dernier_historique, nouveau_statut, user=None):
    return any(valeur == nouveau_statut for valeur, _ in statuts_suivants(article, dernier_historique, user))


def statuts_correction(article, user):
    """Correction (erreur de saisie) : manager et CEO, vers n'importe quel statut, motif obligatoire."""
    from mlshipafrica.droits import a_le_droit
    if user is None or not a_le_droit(user, 'colis_corriger'):
        return []
    ceo = a_le_droit(user, 'colis_corriger_argent')
    if article.statut_traitement in STATUTS_ARGENT and not ceo:
        return []
    libelles = dict(S.choices)
    exclus = {article.statut_traitement, S.BROUILLON, S.REVERSE}
    if not ceo:
        exclus.update(STATUTS_ARGENT)
    if not article.is_option_encaissement:
        exclus.add(S.LIVRE_PAYE)
    return [(x, libelles[x]) for x in ORDRE if x not in exclus]


def appliquer_mouvement(article, nouveau, user, commentaire='', date=None, correction=False):
    """
    Pose un statut (vue de détail, actions groupées). Vérifie le circuit côté serveur, crée l'historique, et si l'équipe
    saute « En transit » l'étape est enregistrée quand même (c'est elle qui fige le coût du transport).
    Renvoie (True, '') ou (False, raison).
    """
    from django.db import transaction
    from management.models import Encaissement, HistoriqueArticle
    from mlshipafrica.enums import EtatConfirmation
    commentaire = (commentaire or '').strip()
    dernier = article.get_last_historique()
    if correction:
        if not commentaire:
            return False, "Indiquez la raison de la correction."
        if not any(v == nouveau for v, _ in statuts_correction(article, user)):
            return False, "Correction non autorisée pour ce colis."
        commentaire = 'Correction : ' + commentaire
    else:
        if not transition_autorisee(article, dernier, nouveau, user):
            return False, "%s ne peut pas passer à « %s »." % (article.code, dict(S.choices).get(nouveau, nouveau))
        if nouveau == S.ANNULE and not commentaire:
            return False, "Indiquez le motif de l'annulation."
        if nouveau in _APRES_DEPART and article.statut_traitement in STATUTS_AVANT_EXPEDITION \
                and article.etat_confirmation != EtatConfirmation.CONFIRME and not commentaire:
            return False, "%s n'est pas confirmé par le client : indiquez le motif de l'expédition." % article.code
    date = date or timezone.now()
    with transaction.atomic():
        if not correction and nouveau in _APRES_DEPART[1:] and article.statut_traitement in STATUTS_AVANT_EXPEDITION:
            dernier = HistoriqueArticle.objects.create(article=article, statut_traitement=S.EN_TRANSIT, date=date,
                                                       commentaire='Étape enregistrée automatiquement',
                                                       license=article.license, dernier_historique_article=dernier)
        article._historique_manuel = True   # l'historique est créé ici, pas par Article.save
        article.statut_traitement = nouveau
        article.etat_validation = True
        article.save()
        HistoriqueArticle.objects.create(article=article, statut_traitement=nouveau, date=date, commentaire=commentaire,
                                         license=article.license, dernier_historique_article=dernier)
        if nouveau == S.LIVRE_PAYE and article.is_option_encaissement and not article.etat_encaissement:
            Encaissement.objects.create(article=article)
            article.etat_encaissement = True
            article.save()
    return True, ''
