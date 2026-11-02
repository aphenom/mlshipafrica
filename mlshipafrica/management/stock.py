"""
Stock des vendeurs en stockage (option_stockage).

  Le vendeur annonce un envoi (bordereau) → le manager contrôle et valide les quantités reçues
     → entrées de stock + SMS au vendeur (un par bordereau, avec les écarts dans son espace)
  Le vendeur crée une commande sur un produit en stock → à la validation, le stock est réservé (sortie)
  Commande annulée avant expédition → le stock revient ; relance → il ressort
  Colis revenu en bon état → « Remis en stock » ; abîmé → « Mis de côté » (hors stock disponible)
  Chaque jour : pièces en stock × tarif du jour = coût de stockage, déduit des relevés du vendeur

Chaque variation est une ligne MouvementStock (jamais modifiée) ; ProduitStock garde le total à jour.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from management.models import (Article, EntreeStock, FacturationStockage, HistoriqueArticle, LigneEntreeStock,
                               MouvementStock, ProduitStock, Vendeur)
from mlshipafrica.enums import StatutEntreeStock, StatutTraitement as S, TypeMouvementStock as T


def _mouvement(produit, type_, quantite, user=None, article=None, entree=None, commentaire=''):
    MouvementStock.objects.create(produit=produit, type=type_, quantite=quantite, article=article, entree=entree,
                                  par=user if getattr(user, 'is_authenticated', False) else None,
                                  commentaire=commentaire[:255])
    if type_ == T.MISE_DE_COTE:
        ProduitStock.objects.filter(pk=produit.pk).update(quantite_de_cote=F('quantite_de_cote') + abs(quantite))
    else:
        ProduitStock.objects.filter(pk=produit.pk).update(quantite_disponible=F('quantite_disponible') + quantite)


@transaction.atomic
def annoncer_entree(vendeur, lignes, commentaire=''):
    """lignes : [(reference, designation, quantite)]."""
    lignes = [(r.strip()[:60], (d or r).strip()[:150], int(q)) for r, d, q in lignes if r and r.strip() and int(q or 0) > 0]
    if not lignes:
        raise ValidationError("Ajoutez au moins une ligne avec une référence et une quantité.")
    numero = EntreeStock.objects.filter(vendeur=vendeur).count() + 1
    entree = EntreeStock.objects.create(code='BS-%s-%03d' % (vendeur.code, numero), vendeur=vendeur, commentaire=commentaire)
    for reference, designation, quantite in lignes:
        LigneEntreeStock.objects.create(entree=entree, reference=reference, designation=designation, quantite_annoncee=quantite)
    return entree


@transaction.atomic
def valider_reception(entree, user, quantites_recues):
    """quantites_recues : {ligne_id: quantité réellement reçue}. Crée les produits manquants et les entrées."""
    entree = EntreeStock.objects.select_for_update().get(pk=entree.pk)
    if entree.statut != StatutEntreeStock.ANNONCEE:
        raise ValidationError("Ce bordereau est déjà validé.")
    pieces, references = 0, 0
    for ligne in entree.lignes.all():
        recu = int(quantites_recues.get(ligne.pk, ligne.quantite_annoncee) or 0)
        if recu < 0:
            raise ValidationError("Quantité reçue négative.")
        produit, _ = ProduitStock.objects.get_or_create(vendeur=entree.vendeur, reference=ligne.reference,
                                                        defaults={'designation': ligne.designation})
        ligne.quantite_recue, ligne.produit = recu, produit
        ligne.save()
        if recu:
            _mouvement(produit, T.ENTREE, recu, user, entree=entree, commentaire='Bordereau %s' % entree.code)
            pieces += recu
            references += 1
    entree.statut, entree.date_reception, entree.recu_par = StatutEntreeStock.RECUE, timezone.now(), user
    entree.save()
    vendeur = entree.vendeur

    def sms():
        from sms.service import mettre_en_file
        mettre_en_file('v_stock', vendeur.numero_sms or vendeur.numero_contact,
                       {'nb': pieces, 'refs': references, 'id': entree.code},
                       cle_dedoublonnage='v_stock:%s' % entree.code, vendeur=vendeur)
    transaction.on_commit(sms)
    return entree


@transaction.atomic
def ajuster(produit, user, delta, motif):
    if not motif or not motif.strip():
        raise ValidationError("Indiquez le motif de l'ajustement (inventaire, casse, erreur…).")
    _mouvement(produit, T.AJUSTEMENT, int(delta), user, commentaire=motif)


def reserver_pour_commande(article, user=None):
    """À la validation d'une commande de vendeur en stockage : sort le produit du stock (refus si insuffisant)."""
    if not article.produit_stock_id:
        return
    with transaction.atomic():
        produit = ProduitStock.objects.select_for_update().get(pk=article.produit_stock_id)
        quantite = int(article.quantite or 1)
        if produit.quantite_disponible < quantite:
            raise ValidationError("Stock insuffisant pour %s : %d disponible(s), %d demandé(s)."
                                  % (produit.designation, produit.quantite_disponible, quantite))
        _mouvement(produit, T.SORTIE, -quantite, user, article=article, commentaire='Commande %s' % article.code)


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='stock_selon_mouvement')
def stock_selon_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw') or not created or instance.etat_suppression or not instance.etat_validation:
        return
    article = instance.article
    if not article.produit_stock_id:
        return
    produit = article.produit_stock
    quantite = int(article.quantite or 1)
    precedent = instance.dernier_historique_article
    statut = instance.statut_traitement
    if statut == S.ANNULE:
        deja_sorti = article.mouvements_stock.aggregate(t=Sum('quantite'))['t'] or 0
        if deja_sorti < 0:   # le produit était réservé : il revient
            _mouvement(produit, T.RETOUR_ANNULATION, quantite, article=article, commentaire='Commande annulée avant expédition')
    elif statut in (S.EN_ATTENTE_DEPOT, S.EN_ATTENTE_RAMASSAGE, S.DEPOT, S.RAMASSE) and precedent is not None \
            and precedent.statut_traitement == S.ANNULE:
        _mouvement(produit, T.SORTIE, -quantite, article=article, commentaire='Commande relancée')
    elif statut == S.REMIS_EN_STOCK:
        _mouvement(produit, T.REMISE_STOCK, quantite, article=article, commentaire='Colis revenu en bon état')
    elif statut == S.MIS_DE_COTE:
        _mouvement(produit, T.MISE_DE_COTE, quantite, article=article, commentaire='Colis revenu abîmé')


def facturer_stockage(jour=None):
    """Tâche quotidienne : une ligne par vendeur en stockage et par jour (rejouable)."""
    from core.models import Configuration
    jour = jour or timezone.localdate()
    n = 0
    for vendeur in Vendeur.objects.filter(option_stockage=True, etat_suppression=False):
        pieces = vendeur.produits_stock.filter(quantite_disponible__gt=0).aggregate(t=Sum('quantite_disponible'))['t'] or 0
        if not pieces:
            continue
        config = Configuration.objects.filter(license=vendeur.license, etat_suppression=False).order_by('-pk').first()
        tarif = Decimal(str(getattr(config, 'tarif_stockage_jour', 10) or 0))
        facturation, cree = FacturationStockage.objects.get_or_create(vendeur=vendeur, jour=jour,
                                                                      defaults={'pieces': pieces, 'montant': pieces * tarif})
        from management.finance import ecrire_stockage
        ecrire_stockage(facturation)
        n += cree
    return n
