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
    'suivi_commercial': {CEO, COMMERCIAL},
    'messages_auto': {CEO},                            # SMS et e-mails automatiques : textes, informations, activer/désactiver           # indicateurs vendeurs (volumes), alertes, journal de relance
    'paiements': {CEO, COMPTABLE},                     # régler les frais, reverser aux vendeurs
    'activites_argent': {CEO, COMPTABLE},              # journaux des paiements et reversements
    'releves': {CEO, COMPTABLE},                       # relevés vendeurs, versements
    'moyens_versement': {CEO, COMPTABLE},              # valider les numéros de versement des vendeurs (procuration)
    'frais_versement_regler': {CEO},                   # taux des frais de versement Mobile Money (à la charge du vendeur)
    'benefice': {CEO, COMPTABLE},                      # journal en temps réel, bénéfice, frais et coût du fichier prestataire
    'prestataire': {CEO, COMPTABLE},                   # retiré au manager COD (18/11)          # fichier hebdomadaire du prestataire : commandes, statuts, commentaires
    'prestataire_supprimer': {CEO},                    # supprimer un fichier importé par erreur
    'commissions_regler': {CEO},                       # paramétrer les commissions
    'commissions_voir': {CEO, COMPTABLE},              # montants des commissions

    # Colis
    'colis_voir': {CEO, COMPTABLE, MANAGER, AGENT},
    'colis_mouvements': {CEO, MANAGER, AGENT},         # faire avancer un statut
    'colis_annuler_mouvement': {CEO, MANAGER},         # revenir sur le dernier mouvement
    'colis_retours': {CEO, MANAGER},                   # revenu à Abidjan, retourné, remis en stock, abandonné
    'colis_corriger': {CEO, MANAGER},                  # corriger un statut posté par erreur (motif obligatoire)
    'colis_corriger_argent': {CEO},                    # corriger un colis Unpaid ou Reversé
    'colis_modifier': {CEO},                           # modifier les données d'une commande (client, montant, produit…)
    'colis_format': {CEO, MANAGER},                    # corriger le format (petit, moyen, grand) vérifié à la réception
    'colis_imprimer': {CEO, COMPTABLE, MANAGER, AGENT},  # bordereaux, feuilles de route, étiquettes, factures, export
    'stock': {CEO, MANAGER},                           # réceptions de stock, inventaire
    'confirmations': {CEO, MANAGER, AGENT},            # appeler les clients, valider l'acompte
    'acomptes': {CEO, COMPTABLE},                      # rembourser les acomptes
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
