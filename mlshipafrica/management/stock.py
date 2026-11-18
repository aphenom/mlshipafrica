"""
Stock des vendeurs en stockage (option_stockage).

  Le vendeur annonce un envoi (bordereau) → le manager contrôle et valide les quantités reçues
     → entrées de stock + SMS au vendeur (un par bordereau, avec les écarts dans son espace)
  Le vendeur crée une commande sur un produit en stock → à la validation, le stock est réservé (sortie)
  Commande annulée avant expédition → le stock revient ; relance → il ressort
  Colis revenu en bon état → « Remis en stock » ; abîmé → « Mis de côté » (hors stock disponible)
  Stockage : 300 F par pièce et par mois dès l'entrée (1er mois à la réception, puis à chaque date anniversaire
  pour les pièces du lot encore en stock), déduit des factures de paiement du vendeur

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
    """lignes : [(reference, designation, quantite)] ou [(reference, designation, quantite, photo)]. En attente du manager."""
    propres = []
    for ligne in lignes:
        r, d, q = ligne[0], ligne[1], ligne[2]
        photo = ligne[3] if len(ligne) > 3 else None
        if r and r.strip() and int(q or 0) > 0:
            propres.append((r.strip()[:60], (d or r).strip()[:150], int(q), photo))
    if not propres:
        raise ValidationError("Ajoutez au moins une ligne avec une référence et une quantité.")
    numero = EntreeStock.objects.filter(vendeur=vendeur).count() + 1
    entree = EntreeStock.objects.create(code='BS-%s-%03d' % (vendeur.code, numero), vendeur=vendeur, commentaire=commentaire)
    for reference, designation, quantite, photo in propres:
        if photo is None:
            # Produit déjà connu : on reprend sa photo
            connu = ProduitStock.objects.filter(vendeur=vendeur, reference=reference).exclude(photo='').exclude(photo=None).first()
            photo = connu.photo if connu else None
        LigneEntreeStock.objects.create(entree=entree, reference=reference, designation=designation, quantite_annoncee=quantite,
                                        photo=photo)
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
        if ligne.photo and not produit.photo:
            produit.photo = ligne.photo
            produit.save(update_fields=['photo'])
        ligne.quantite_recue, ligne.produit = recu, produit
        ligne.save()
        if recu:
            _mouvement(produit, T.ENTREE, recu, user, entree=entree, commentaire='Bordereau %s' % entree.code)
            pieces += recu
            references += 1
    entree.statut, entree.date_reception, entree.recu_par = StatutEntreeStock.RECUE, timezone.now(), user
    entree.save()
    # Premier mois de stockage dès l'entrée : pièces reçues × tarif mensuel
    tarif = tarif_stockage_mois(entree.vendeur)
    for ligne in entree.lignes.select_related('entree__vendeur').filter(quantite_recue__gt=0):
        facturer_lot(ligne, 0, timezone.localdate(), ligne.quantite_recue, tarif)
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


def _ajouter_mois(d, k):
    import calendar
    from datetime import date
    total = d.month - 1 + k
    annee, mois = d.year + total // 12, total % 12 + 1
    return date(annee, mois, min(d.day, calendar.monthrange(annee, mois)[1]))


def tarif_stockage_mois(vendeur):
    from core.models import Configuration
    config = Configuration.objects.filter(license=vendeur.license, etat_suppression=False).order_by('-pk').first()
    return Decimal(str(getattr(config, 'tarif_stockage_mois', 300) or 0))


def pieces_par_lot(produit):
    """Pièces encore en stock de chaque lot reçu : les sorties consomment les lots les plus anciens d'abord."""
    lots = list(LigneEntreeStock.objects.filter(produit=produit, entree__statut=StatutEntreeStock.RECUE, quantite_recue__gt=0)
                .select_related('entree').order_by('-entree__date_reception', '-pk'))
    reste, parts = max(produit.quantite_disponible, 0), {}
    for lot in lots:                                  # le stock restant appartient aux lots les plus récents
        parts[lot.pk] = min(reste, lot.quantite_recue)
        reste -= parts[lot.pk]
    return lots, parts


def facturer_lot(ligne, rang, jour, pieces, tarif):
    """Un mois de stockage d'un lot (rang 0 = mois de l'entrée). Rejouable : une seule écriture par lot et par mois."""
    from django.db.models import F
    from management.models import Ecriture
    from mlshipafrica.enums import TypeEcriture
    if pieces <= 0:
        return False
    vendeur = ligne.entree.vendeur
    _, cree = Ecriture.objects.get_or_create(cle='stockage:lot:%s:%s' % (ligne.pk, rang), defaults={
        'vendeur': vendeur, 'type': TypeEcriture.STOCKAGE, 'montant': pieces * tarif, 'license': vendeur.license})
    if cree:
        facturation, _ = FacturationStockage.objects.get_or_create(vendeur=vendeur, jour=jour, defaults={'pieces': 0, 'montant': 0})
        FacturationStockage.objects.filter(pk=facturation.pk).update(pieces=F('pieces') + pieces, montant=F('montant') + pieces * tarif)
    return cree


def facturer_stockage(jour=None):
    """
    Stockage : 300 F (réglé par le CEO) par pièce et par mois, dès l'entrée du stock. Le premier mois est compté à la
    réception ; ensuite, à chaque date anniversaire de l'entrée, les pièces de ce lot encore en stock sont comptées
    pour un nouveau mois. Tâche quotidienne, rejouable (rattrape les mois manqués). Renvoie le nombre de mois comptés.
    """
    jour = jour or timezone.localdate()
    n = 0
    for vendeur in Vendeur.objects.filter(option_stockage=True, etat_suppression=False):
        tarif = tarif_stockage_mois(vendeur)
        for produit in vendeur.produits_stock.all():
            lots, parts = pieces_par_lot(produit)
            for lot in lots:
                debut = timezone.localtime(lot.entree.date_reception).date()
                rang = 1
                while _ajouter_mois(debut, rang) <= jour:
                    n += facturer_lot(lot, rang, _ajouter_mois(debut, rang), parts.get(lot.pk, 0), tarif)
                    rang += 1
    return n
