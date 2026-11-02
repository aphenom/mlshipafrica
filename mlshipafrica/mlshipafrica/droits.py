"""
Rôles et droits : la seule table qui dit qui peut faire quoi.

Chaque vue vérifie son droit côté serveur avec @droit_requis(...). Masquer un bouton ne suffit pas :
un appel direct à l'URL d'un autre rôle est refusé (page 403).
Les gabarits reçoivent `droits` (ensemble des droits de l'utilisateur) : {% if 'argent' in droits %}.

Règle de la direction : seuls le CEO et la comptable voient l'argent de la société (frais, coûts, marge,
règlements, reversements, chiffre). Manager, agents COD et commerciaux travaillent en volumes.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from mlshipafrica.enums import TypeProfilStaffChoice as R

CEO = R.SUPER
COMPTABLE = R.COMPTABLE
MANAGER = R.MANAGER
AGENT = R.AGENT
COMMERCIAL = R.COMMERCIAL
ADMIN_TECH = R.ADMINISTRATEUR

DROITS = {
    # Argent de la société : frais, règlements, reversements, montants du tableau de bord, coût partenaire
    'argent': {CEO, COMPTABLE},
    'paiements': {CEO, COMPTABLE},                     # régler les frais, reverser aux vendeurs
    'activites_argent': {CEO, COMPTABLE},              # journaux des paiements et reversements

    # Colis
    'colis_voir': {CEO, COMPTABLE, MANAGER, AGENT},
    'colis_mouvements': {CEO, MANAGER, AGENT},         # faire avancer un statut
    'colis_annuler_mouvement': {CEO, MANAGER},         # revenir sur le dernier mouvement
    'activites_colis': {CEO, COMPTABLE, MANAGER},      # journal des mouvements

    # Vendeurs
    'vendeurs_voir': {CEO, COMPTABLE, COMMERCIAL, MANAGER},
    'vendeurs_approuver': {CEO, COMMERCIAL},           # approuver, activer, désactiver, affecter
    'vendeurs_supprimer': {CEO},
    'vendeurs_importer': {CEO, ADMIN_TECH},

    # Paramètres
    'parametres': {CEO, ADMIN_TECH},                   # zones, localités, formats
    'parametres_tarifs': {CEO},                        # prix ML et coût partenaire
    'parametres_partenaires': {CEO},                   # nom du prestataire : CEO seulement
    'parametres_comptes': {CEO, ADMIN_TECH},           # comptes de l'équipe
    'parametres_configuration': {CEO},
    'licenses': {CEO},
    'journal_audit': {CEO},
}

# Module des écrans core/_liste, _new, _edit → droit requis
DROIT_PAR_PARAMETRE = {
    'licenses': 'licenses',
    'configurations': 'parametres_configuration',
    'formats_articles': 'parametres',
    'zones': 'parametres',
    'localites': 'parametres',
    'partenaires_logistiques': 'parametres_partenaires',
    'tarifications': 'parametres_tarifs',
    'profils_staff': 'parametres_comptes',
}


def profil_staff_de(user):
    if user is None or not getattr(user, 'is_authenticated', False) or not user.is_staff:
        return None
    return getattr(user, 'account_profil_staff', None)


def droits_de(user):
    profil = profil_staff_de(user)
    if profil is None or not profil.etat_validation or profil.etat_suppression:
        return frozenset()
    return frozenset(nom for nom, roles in DROITS.items() if profil.role_profil in roles)


def a_le_droit(user, droit):
    return droit in droits_de(user)


def verifier(user, droit):
    if not a_le_droit(user, droit):
        raise PermissionDenied("Votre rôle ne permet pas cette action.")


def droit_requis(*droits_possibles):
    """La vue est réservée à l'équipe ayant AU MOINS UN de ces droits. Sinon : connexion ou 403."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('account_login')
            mes_droits = droits_de(request.user)
            if not any(d in mes_droits for d in droits_possibles):
                raise PermissionDenied("Votre rôle ne permet pas d'ouvrir cette page.")
            return vue(request, *args, **kwargs)
        return enveloppe
    return decorateur
