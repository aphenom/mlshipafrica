"""
Commissions de l'équipe : réglées par le CEO, désactivées par défaut.

Les comptes concernés voient une carte de résultats en VOLUMES seulement (jamais de montant).
Le CEO et la comptable voient les montants calculés pour la période.

  Agents COD  : commandes confirmées ; colis livrés parmi leurs confirmations (taux de livraison)
  Manager     : colis livrés
  Commerciaux : vendeurs activés ; colis livrés de leurs vendeurs
"""
from decimal import Decimal

from django.db.models import Q

from management.models import AppelConfirmation, CommissionConfig, HistoriqueArticle, Vendeur
from mlshipafrica.enums import IndicateurCommission as I, ResultatAppel, StatutTraitement as S

LIVRE = (S.LIVRE, S.LIVRE_PAYE)


def volumes(profil, debut, fin):
    """Volumes d'un compte sur la période (tous les indicateurs utiles à son rôle)."""
    user = profil.user
    livres = HistoriqueArticle.objects.filter(etat_suppression=False, statut_traitement__in=LIVRE,
                                              date_creation__gte=debut, date_creation__lt=fin, article__license=profil.license)
    v = {}
    confirmees = AppelConfirmation.objects.filter(agent=user, resultat=ResultatAppel.CONFIRME, date__gte=debut, date__lt=fin)
    v[I.CONFIRMEES] = confirmees.values('article').distinct().count()
    v[I.LIVRES_CONFIRMES] = livres.filter(article__confirme_par=user).values('article').distinct().count()
    v['taux_livraison'] = round(100 * v[I.LIVRES_CONFIRMES] / v[I.CONFIRMEES]) if v[I.CONFIRMEES] else 0
    v[I.LIVRES] = livres.values('article').distinct().count()
    v[I.VENDEURS_ACTIVES] = Vendeur.objects.filter(commercial=profil, etat_approbation=True,
                                                   date_approbation__gte=debut, date_approbation__lt=fin).count()
    v[I.LIVRES_VENDEURS] = livres.filter(article__vendeur__commercial=profil).values('article').distinct().count()
    return v


def montant(config, vols):
    quantite = vols.get(config.indicateur, 0)
    if config.taux_livraison_minimum and vols.get('taux_livraison', 0) < config.taux_livraison_minimum \
            and config.indicateur in (I.CONFIRMEES, I.LIVRES_CONFIRMES):
        return Decimal('0')
    if config.type == 'fixe':
        return Decimal(str(config.montant_unitaire or 0)) * quantite
    gagne = Decimal('0')
    for palier in sorted(config.paliers or [], key=lambda p: p.get('seuil', 0)):
        if quantite >= int(palier.get('seuil', 0)):
            gagne = Decimal(str(palier.get('montant', 0)))
    return gagne


def cartes_pour(profil, debut, fin):
    """Cartes de résultats (volumes) pour ce compte, s'il est concerné par une commission active."""
    configs = CommissionConfig.objects.filter(actif=True, comptes=profil)
    if not configs.exists():
        return []
    vols = volumes(profil, debut, fin)
    return [{'nom': c.nom, 'indicateur': c.get_indicateur_display(), 'valeur': vols.get(c.indicateur, 0),
             'taux': vols['taux_livraison'] if c.indicateur in (I.CONFIRMEES, I.LIVRES_CONFIRMES) else None,
             'taux_min': c.taux_livraison_minimum,
             'prochain_seuil': next((p['seuil'] for p in sorted(c.paliers or [], key=lambda p: p.get('seuil', 0))
                                     if vols.get(c.indicateur, 0) < int(p.get('seuil', 0))), None) if c.type == 'objectif' else None}
            for c in configs]


def tableau(license, debut, fin):
    """Montants par compte et par commission active (CEO et comptable)."""
    lignes = []
    for c in CommissionConfig.objects.filter(license=license, actif=True).prefetch_related('comptes__user'):
        for profil in c.comptes.all():
            vols = volumes(profil, debut, fin)
            lignes.append({'commission': c, 'compte': profil, 'quantite': vols.get(c.indicateur, 0),
                           'taux': vols['taux_livraison'], 'montant': montant(c, vols)})
    return lignes
