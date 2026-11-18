"""
Argent : écritures, relevés vendeurs (lundi et jeudi), journal et bénéfice, fichier du prestataire.

Principe : chaque mouvement d'argent est une Ecriture liée au colis, jamais modifiée. Pour chaque colis, on
calcule ce qui DEVRAIT être compté (selon son statut et ses frais) et on écrit la différence avec ce qui l'est
déjà : rejouer ne compte jamais deux fois, et revenir sur un mouvement crée une écriture de correction.

  Livré                → frais ML (+ ramassage) ; si encaissement : collecte (due au vendeur) et frais de collecte
  En retour vers Abidjan → frais de retour (50 %)
  Garde (J11 à J30)    → au fil des jours
  Stockage             → chaque jour (vendeurs en stockage)
  Départ (en transit)  → coût prestataire figé au départ (interne, CEO et comptable)

Relevé vendeur = collecte − frais − frais de collecte − retours − garde − stockage, sur toutes ses écritures pas
encore relevées. Généré le lundi et le jeudi (commande releves_vendeurs). La comptable le marque versé.
"""
import csv
import io
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from management.models import Article, Depart, Ecriture, HistoriqueArticle, Releve
from mlshipafrica.enums import MoyenVersement, StatutReleve, StatutTraitement as S, TypeEcriture as T

LIVRES = (S.LIVRE, S.LIVRE_PAYE, S.PAYE, S.REVERSE)
TYPES_VENDEUR_DEBIT = (T.FRAIS, T.FRAIS_COLLECTE, T.FRAIS_RETOUR, T.GARDE, T.STOCKAGE)
ZERO = Decimal('0')
STATUTS_EN_ROUTE = (S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT, S.EN_RETOUR)


def _d(v):
    return Decimal(str(v or 0))


def configuration(license):
    from core.models import Configuration
    return Configuration.objects.filter(license=license, etat_suppression=False).order_by('-pk').first()


def taux_collecte(license):
    """Taux des frais de collecte (encaissement), réglé par le CEO pour tous les vendeurs. 5 % par défaut."""
    config = configuration(license)
    taux = getattr(config, 'taux_option_encaissement', None)
    return _d(taux) if taux is not None else Decimal('5')


def frais_collecte(article, taux=None):
    """Frais de collecte d'un colis avec encaissement : taux global × montant encaissé, arrondi au franc."""
    if not article.is_option_encaissement:
        return ZERO
    taux = taux_collecte(article.license) if taux is None else _d(taux)
    return (_d(article.valeur_totale) * taux / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def recalculer_frais_colis(article, taux=None):
    """Remet à jour les frais de collecte et les totaux du colis (sans toucher au tarif ML figé)."""
    article.taux_option_encaissement = (taux_collecte(article.license) if taux is None else _d(taux)) if article.is_option_encaissement else None
    article.cout_option_encaissement = frais_collecte(article, taux) if article.is_option_encaissement else None
    article.montant_total_frais = _d(article.montant_frais) + _d(article.cout_option_recuperation) + _d(article.cout_option_encaissement)
    article.montant_a_reverser = (_d(article.valeur_totale) - article.montant_total_frais) if article.is_option_encaissement else None
    return article


def colis_a_recalculer(license, inclure_factures=False):
    """Colis avec encaissement concernés par un changement du taux de collecte."""
    qs = Article.objects.filter(license=license, is_option_encaissement=True, etat_suppression=False).exclude(
        statut_traitement=S.BROUILLON)
    if not inclure_factures:
        # Déjà dans une facture de paiement (Paid ou Versé) : on n'y touche pas, sauf demande expresse du CEO
        qs = qs.exclude(ecritures__releve__isnull=False, ecritures__releve__statut__in=(StatutReleve.A_VERSER, StatutReleve.VERSE))
        qs = qs.exclude(etat_reversement=True)
    return qs.distinct()


def appliquer_taux_collecte(license, taux, inclure_factures=False, simuler=False):
    """
    Applique le taux de collecte aux colis existants : frais recalculés, et pour les colis livrés l'écart est écrit
    dans la comptabilité (il entre dans la prochaine facture de paiement). Renvoie (colis modifiés, écart total des
    frais sur les colis livrés).
    """
    taux = _d(taux)
    modifies, ecart = 0, ZERO
    for article in colis_a_recalculer(license, inclure_factures).iterator():
        nouveau = frais_collecte(article, taux)
        if nouveau == _d(article.cout_option_encaissement) and _d(article.taux_option_encaissement) == taux:
            continue
        modifies += 1
        if article.statut_traitement in LIVRES:
            ecart += nouveau - _d(article.cout_option_encaissement)
        if simuler:
            continue
        recalculer_frais_colis(article, taux)
        Article.objects.filter(pk=article.pk).update(
            taux_option_encaissement=article.taux_option_encaissement, cout_option_encaissement=article.cout_option_encaissement,
            montant_total_frais=article.montant_total_frais, montant_a_reverser=article.montant_a_reverser)
        comptabiliser(article)
    return modifies, ecart


def attendu(article):
    """Ce qui doit être compté pour ce colis, par type d'écriture."""
    livre = article.statut_traitement in LIVRES
    encaisse = livre and article.is_option_encaissement
    return {
        T.COLLECTE: _d(article.valeur_totale) if encaisse else ZERO,
        T.FRAIS: (_d(article.montant_frais) + _d(article.cout_option_recuperation)) if livre else ZERO,
        T.FRAIS_COLLECTE: _d(article.cout_option_encaissement) if encaisse else ZERO,
        T.FRAIS_RETOUR: _d(article.frais_retour),
        T.GARDE: _d(article.frais_garde),
    }


def comptabiliser(article):
    """Écrit les différences entre l'attendu et le déjà compté. Renvoie le nombre d'écritures créées."""
    article = Article.objects.get(pk=article.pk)
    deja = {r['type']: r['t'] for r in article.ecritures.exclude(type__in=(T.COUT_PRESTATAIRE, T.STOCKAGE))
            .values('type').annotate(t=Sum('montant'))}
    if not deja and article.etat_reversement:
        return 0  # colis réglé par l'ancien outil avant la mise en service des relevés : on n'y touche pas
    creees = 0
    for type_, montant in attendu(article).items():
        ecart = montant - _d(deja.get(type_))
        if ecart == 0:
            continue
        rang = article.ecritures.filter(type=type_).count() + 1
        try:
            with transaction.atomic():
                Ecriture.objects.create(vendeur=article.vendeur, article=article, type=type_, montant=ecart,
                                        cle='%s:%s:%d' % (type_, article.pk, rang), license=article.license)
            creees += 1
        except IntegrityError:
            pass  # écrite au même instant par un autre processus
    return creees


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='finance_selon_mouvement')
def finance_selon_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    article = instance.article

    def apres():
        if created and not instance.etat_suppression and instance.statut_traitement == S.EN_TRANSIT:
            enregistrer_depart(instance)
        comptabiliser(article)
    transaction.on_commit(apres)


def enregistrer_depart(historique):
    article = historique.article
    tarif = article.tarification
    if tarif is None and article.localite_arrivee_id:
        # Colis sans tarif figé (ancien colis) : tarif général de sa zone et de son format
        from management.models import Tarification
        tarif = (Tarification.objects.filter(license=article.license, vendeur__isnull=True, etat_validation=True,
                                             etat_suppression=False, zone_arrivee=article.localite_arrivee.zone,
                                             format_article=article.format_article).order_by('-pk').first())
    cout = _d(getattr(tarif, 'cout_partenaire', None))
    depart, cree = Depart.objects.get_or_create(historique=historique, defaults={
        'article': article, 'date': historique.date_creation or timezone.now(), 'cout_prevu': cout})
    if cree:
        Ecriture.objects.get_or_create(cle='depart:%s' % historique.pk, defaults={
            'article': article, 'vendeur': article.vendeur, 'type': T.COUT_PRESTATAIRE, 'montant': cout,
            'license': article.license, 'date': depart.date})
    return depart


def ecrire_stockage(facturation):
    Ecriture.objects.get_or_create(cle='stockage:%s:%s' % (facturation.vendeur_id, facturation.jour.isoformat()), defaults={
        'vendeur': facturation.vendeur, 'type': T.STOCKAGE, 'montant': facturation.montant,
        'license': facturation.vendeur.license})


# --------------------------------------------------------------------------------------------- relevés

def totaux(ecritures):
    par_type = {r['type']: _d(r['t']) for r in ecritures.values('type').annotate(t=Sum('montant'))}
    t = {
        'collecte': par_type.get(T.COLLECTE, ZERO),
        'frais': par_type.get(T.FRAIS, ZERO) + par_type.get(T.FRAIS_COLLECTE, ZERO),
        'frais_livraison': par_type.get(T.FRAIS, ZERO),
        'frais_collecte': par_type.get(T.FRAIS_COLLECTE, ZERO),
        'retours': par_type.get(T.FRAIS_RETOUR, ZERO),
        'garde': par_type.get(T.GARDE, ZERO),
        'stockage': par_type.get(T.STOCKAGE, ZERO),
    }
    t['net'] = t['collecte'] - t['frais'] - t['retours'] - t['garde'] - t['stockage']
    return t


def ecritures_a_payer(license=None, vendeurs=None, arrete=None):
    """
    Lignes qui peuvent entrer dans une facture de paiement : pas encore facturées, et pour un colis livré avec
    encaissement, seulement une fois passé en « Unpaid » par la comptable (l'argent du client est bien chez nous).
    """
    qs = Ecriture.objects.filter(releve__isnull=True, vendeur__isnull=False).exclude(type=T.COUT_PRESTATAIRE)
    qs = qs.exclude(article__statut_traitement=S.LIVRE, article__is_option_encaissement=True)
    if license is not None:
        qs = qs.filter(vendeur__license=license)
    if vendeurs is not None:
        qs = qs.filter(vendeur__in=vendeurs)
    if arrete is not None:
        qs = qs.filter(date__lte=arrete)
    return qs


def livres_a_valider(license=None, vendeur=None):
    """Colis livrés avec encaissement pas encore passés en « Unpaid » (argent pas encore confirmé)."""
    qs = Article.objects.filter(etat_suppression=False, statut_traitement=S.LIVRE, is_option_encaissement=True)
    if license is not None:
        qs = qs.filter(license=license)
    if vendeur is not None:
        qs = qs.filter(vendeur=vendeur)
    return qs


def a_payer_par_vendeur(license):
    """Vendeurs à payer : totaux de leurs lignes payables, et ce qui bloque le paiement."""
    from management.models import Vendeur
    lignes = ecritures_a_payer(license)
    resultat = []
    ids = list(lignes.values_list('vendeur', flat=True).distinct())
    for vendeur in Vendeur.objects.filter(pk__in=ids).order_by('nom_store'):
        sienne = lignes.filter(vendeur=vendeur)
        t = totaux(sienne)
        if not any(t.values()):
            continue
        t['vendeur'] = vendeur
        t['colis'] = sienne.exclude(article__isnull=True).values('article').distinct().count()
        t['bloque'] = ''
        if t['net'] > 0 and not (vendeur.versement_valide and vendeur.compte_valide):
            t['bloque'] = "Numéro de paiement à valider" if vendeur.compte_versement else "Pas de numéro de paiement"
        t['frais_versement'] = frais_versement(vendeur.moyen_valide, t['net']) if not t['bloque'] else ZERO
        resultat.append(t)
    return resultat


def jour_de_paiement(jour=None):
    """Lundi et jeudi : la plateforme pré-coche les vendeurs à payer."""
    jour = jour or timezone.localdate()
    return jour.weekday() in (0, 3)


@transaction.atomic
def generer_releves(arrete=None, vendeurs=None, license=None, par=None):
    """Une facture de paiement par vendeur avec ses lignes payables jusqu'à l'arrêté. Renvoie la liste créée."""
    arrete = arrete or timezone.now()
    a_relever = ecritures_a_payer(license, vendeurs, arrete)
    crees = []
    for vendeur_id in a_relever.values_list('vendeur', flat=True).distinct():
        lignes = a_relever.filter(vendeur_id=vendeur_id)
        t = totaux(lignes)
        if not any(t.values()):
            continue
        vendeur = lignes.first().vendeur
        numero = Releve.objects.filter(vendeur=vendeur).count() + 1
        releve = Releve.objects.create(
            code='RL-%s-%s-%03d' % (timezone.localtime(arrete).strftime('%y%m%d'), vendeur.code, numero),
            vendeur=vendeur, date_arrete=arrete, total_collecte=t['collecte'], total_frais=t['frais'],
            total_retours=t['retours'], total_garde=t['garde'], total_stockage=t['stockage'], net=t['net'], genere_par=par)
        lignes.update(releve=releve)
        _statut_colis_du_releve(releve, S.LIVRE_PAYE, S.PAYE, 'Facture de paiement %s émise' % releve.code)
        crees.append(releve)
    return crees


def _statut_colis_du_releve(releve, avant, apres, commentaire, ecritures=None):
    """Fait suivre le statut des colis encaissés d'une facture : Unpaid → Paid (émise), Paid → Unpaid (annulée)."""
    ids = (ecritures if ecritures is not None else releve.ecritures).filter(article__isnull=False).values_list('article', flat=True)
    for article in Article.objects.filter(pk__in=list(ids), statut_traitement=avant):
        dernier = article.get_last_historique()
        Article.objects.filter(pk=article.pk).update(statut_traitement=apres)
        HistoriqueArticle.objects.create(article=article, statut_traitement=apres, date=timezone.now(), commentaire=commentaire,
                                         license=article.license, dernier_historique_article=dernier)


@transaction.atomic
def annuler_releve(releve, par, motif):
    """Facture générée par erreur : annulée avant versement, ses lignes redeviennent payables."""
    releve = Releve.objects.select_for_update().get(pk=releve.pk)
    if releve.statut != StatutReleve.A_VERSER:
        raise ValidationError("Seule une facture pas encore versée peut être annulée.")
    if not (motif or '').strip():
        raise ValidationError("Indiquez le motif de l'annulation.")
    lignes = Ecriture.objects.filter(pk__in=list(releve.ecritures.values_list('pk', flat=True)))
    releve.ecritures.update(releve=None)
    _statut_colis_du_releve(releve, S.PAYE, S.LIVRE_PAYE, 'Facture %s annulée : %s' % (releve.code, motif.strip()[:200]), lignes)
    releve.statut, releve.annule_par, releve.date_annulation = StatutReleve.ANNULE, par, timezone.now()
    releve.motif_annulation = motif.strip()[:300]
    releve.save()
    return releve


def lignes_releve(releve_ou_ecritures):
    """
    Facture de paiement ligne par ligne : une ligne par colis (encaissé, frais de livraison, frais de collecte,
    retour, garde, net), puis les lignes sans colis (stockage). Renvoie (lignes, autres).
    """
    ecritures = releve_ou_ecritures.ecritures.all() if isinstance(releve_ou_ecritures, Releve) else releve_ou_ecritures
    ecritures = ecritures.exclude(type=T.COUT_PRESTATAIRE).select_related('article', 'article__localite_arrivee')
    par_colis, autres = {}, []
    for e in ecritures.order_by('date'):
        if e.article_id is None:
            autres.append(e)
            continue
        l = par_colis.setdefault(e.article_id, {'article': e.article, 'date': e.date, 'collecte': ZERO, 'frais': ZERO,
                                                'frais_collecte': ZERO, 'retour': ZERO, 'garde': ZERO, 'stockage': ZERO})
        cle = {T.COLLECTE: 'collecte', T.FRAIS: 'frais', T.FRAIS_COLLECTE: 'frais_collecte', T.FRAIS_RETOUR: 'retour',
               T.GARDE: 'garde', T.STOCKAGE: 'stockage'}.get(e.type)
        if cle:
            l[cle] += _d(e.montant)
        l['date'] = max(l['date'], e.date)
    lignes = sorted(par_colis.values(), key=lambda l: l['date'])
    for l in lignes:
        l['etat'] = 'Livré' if l['article'].statut_traitement in LIVRES else 'Non livré · retour'
        l['net'] = l['collecte'] - l['frais'] - l['frais_collecte'] - l['retour'] - l['garde'] - l['stockage']
    return lignes, autres


def frais_versement(moyen, net):
    """Frais Mobile Money à la charge du vendeur, arrondis au franc (taux et plafond réglés par le CEO)."""
    from management.models import FraisVersement
    net = _d(net)
    if net <= 0 or not moyen:
        return ZERO
    regle = FraisVersement.objects.filter(moyen=moyen).first()
    if regle is None or not regle.taux:
        return ZERO
    frais = (net * regle.taux / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if regle.plafond is not None:
        frais = min(frais, _d(regle.plafond))
    return frais


@transaction.atomic
def enregistrer_coordonnees(vendeur, moyen, compte, titulaire='', procuration=None):
    """
    Le vendeur saisit ou change ses coordonnées de versement. Un changement de moyen ou de numéro bloque les
    versements jusqu'à ce que la comptable valide la procuration : on continue à n'utiliser que les dernières
    coordonnées validées. Renvoie True s'il y a eu un changement.
    """
    compte, titulaire = (compte or '').strip()[:60], (titulaire or '').strip()[:100]
    if moyen not in MoyenVersement.values or not compte:
        raise ValidationError("Choisissez un moyen de versement et indiquez le numéro ou le RIB.")
    changement = (moyen, compte) != (vendeur.moyen_versement, vendeur.compte_versement)
    if changement and not procuration and not (vendeur.procuration_versement and (moyen, compte) == (vendeur.moyen_valide, vendeur.compte_valide)):
        raise ValidationError("Joignez la procuration signée (photo ou PDF) : elle est obligatoire pour tout nouveau numéro.")
    vendeur.moyen_versement, vendeur.compte_versement, vendeur.titulaire_versement = moyen, compte, titulaire
    if procuration:
        vendeur.procuration_versement = procuration
    if changement:
        vendeur.versement_modifie_le = timezone.now()
        vendeur.versement_refus_motif = ''
        # Revenir aux coordonnées déjà validées ne demande pas de nouvelle validation
        vendeur.versement_valide = (moyen, compte) == (vendeur.moyen_valide, vendeur.compte_valide) and bool(vendeur.compte_valide)
    vendeur.save()
    return changement


@transaction.atomic
def valider_coordonnees(vendeur, par):
    if not vendeur.compte_versement or not vendeur.moyen_versement:
        raise ValidationError("Ce vendeur n'a pas de coordonnées à valider.")
    if not vendeur.procuration_versement:
        raise ValidationError("Pas de procuration jointe : demandez-la au vendeur avant de valider.")
    vendeur.moyen_valide, vendeur.compte_valide = vendeur.moyen_versement, vendeur.compte_versement
    vendeur.titulaire_valide = vendeur.titulaire_versement or ''
    vendeur.versement_valide, vendeur.versement_valide_le, vendeur.versement_valide_par = True, timezone.now(), par
    vendeur.versement_refus_motif = ''
    vendeur.save()


@transaction.atomic
def refuser_coordonnees(vendeur, par, motif):
    """Refus : on revient aux dernières coordonnées validées (s'il y en a), le vendeur voit le motif."""
    if not (motif or '').strip():
        raise ValidationError("Indiquez le motif du refus : le vendeur le verra.")
    vendeur.versement_refus_motif = motif.strip()[:200]
    if vendeur.compte_valide:
        vendeur.moyen_versement, vendeur.compte_versement = vendeur.moyen_valide, vendeur.compte_valide
        vendeur.titulaire_versement = vendeur.titulaire_valide
        vendeur.versement_valide = True
    else:
        vendeur.versement_valide = False
    vendeur.save()


@transaction.atomic
def marquer_verse(releve, user, reference, moyen=''):
    """Versement d'un relevé : uniquement sur les coordonnées validées, frais de versement déduits du net."""
    releve = Releve.objects.select_for_update().select_related('vendeur').get(pk=releve.pk)
    if releve.statut == StatutReleve.VERSE:
        raise ValidationError("Ce relevé est déjà versé.")
    if not (reference or '').strip():
        raise ValidationError("Indiquez la référence du versement.")
    vendeur = releve.vendeur
    if releve.net > 0 and not (vendeur.versement_valide and vendeur.compte_valide and vendeur.moyen_valide):
        raise ValidationError("Coordonnées de versement de %s non validées : validez sa procuration dans « Moyens de paiement » avant de verser." % (
            vendeur.nom_store or vendeur.code))
    releve.statut = StatutReleve.VERSE
    releve.date_versement = timezone.now()
    releve.reference_versement = reference.strip()[:100]
    releve.moyen_versement = vendeur.moyen_valide or moyen or ''
    releve.compte_verse, releve.titulaire_verse = vendeur.compte_valide, vendeur.titulaire_valide
    releve.frais_versement = frais_versement(releve.moyen_versement, releve.net)
    releve.montant_verse = max(releve.net - releve.frais_versement, ZERO) if releve.net > 0 else ZERO
    releve.verse_par = user
    releve.save()
    # Les colis du relevé sont réglés : frais payés, collecte reversée (statut « Reversé »)
    articles = Article.objects.filter(ecritures__releve=releve).distinct()
    articles.update(etat_reglement=True)
    for article in articles.filter(statut_traitement__in=(S.LIVRE_PAYE, S.PAYE)):
        dernier = article.get_last_historique()
        Article.objects.filter(pk=article.pk).update(statut_traitement=S.REVERSE, etat_reversement=True)
        HistoriqueArticle.objects.create(article=article, statut_traitement=S.REVERSE, date=timezone.now(),
                                         commentaire='Facture de paiement %s versée (réf. %s)' % (releve.code, releve.reference_versement), license=article.license,
                                         dernier_historique_article=dernier)
    return releve


# --------------------------------------------------------------------------------------------- journal

def journal(license, debut, fin):
    """Résultat de la période (CEO et comptable) : revenus, coût prestataire, bénéfice, volumes."""
    e = Ecriture.objects.filter(license=license, date__gte=debut, date__lt=fin)
    par_type = {r['type']: _d(r['t']) for r in e.values('type').annotate(t=Sum('montant'))}
    revenus = sum((par_type.get(t, ZERO) for t in TYPES_VENDEUR_DEBIT), ZERO)
    cout = par_type.get(T.COUT_PRESTATAIRE, ZERO)
    # Le coût prestataire est compté au départ, les frais ML à la livraison : le coût des colis encore en route est
    # « engagé », il ne pèse pas sur le bénéfice réalisé tant que le colis n'est pas terminé.
    cout_engage = _d(e.filter(type=T.COUT_PRESTATAIRE, article__statut_traitement__in=STATUTS_EN_ROUTE).aggregate(t=Sum('montant'))['t'])
    livres = HistoriqueArticle.objects.filter(license=license, date_creation__gte=debut, date_creation__lt=fin,
                                              etat_suppression=False, statut_traitement__in=(S.LIVRE, S.LIVRE_PAYE)
                                              ).values('article').distinct().count()
    departs = Depart.objects.filter(article__license=license, date__gte=debut, date__lt=fin)
    en_route = Article.objects.filter(license=license, etat_suppression=False, statut_traitement__in=STATUTS_EN_ROUTE)
    from management.models import Acompte
    acomptes = Acompte.objects.filter(license=license, date_reception__gte=debut, date_reception__lt=fin).aggregate(
        n=Count('id'), t=Sum('montant'))
    return {
        'par_type': [(T(t).label, par_type.get(t, ZERO)) for t in (T.FRAIS, T.FRAIS_COLLECTE, T.FRAIS_RETOUR, T.GARDE, T.STOCKAGE)],
        'revenus': revenus, 'cout_prestataire': cout, 'benefice': revenus - cout,
        'cout_engage': cout_engage, 'cout_realise': cout - cout_engage, 'benefice_realise': revenus - (cout - cout_engage),
        'collecte': par_type.get(T.COLLECTE, ZERO), 'livres': livres, 'departs': departs.count(),
        'cout_facture': _d(departs.aggregate(t=Sum('cout_facture'))['t']),
        'ecart_prestataire': _d(departs.filter(cout_facture__isnull=False).aggregate(
            t=Sum('cout_facture'))['t']) - _d(departs.filter(cout_facture__isnull=False).aggregate(t=Sum('cout_prevu'))['t']),
        'engages': en_route.count(), 'acomptes_n': acomptes['n'] or 0, 'acomptes_total': _d(acomptes['t']),
    }


# --------------------------------------------------------------------------------------------- fichier prestataire

def importer_fichier_prestataire(license, fichier, par=None, onglet=''):
    """
    Lit le fichier du prestataire (Excel ou CSV, tel qu'il l'envoie : voir management/fichier_prestataire.py),
    enregistre chaque commande avec son statut, sa date de retrait et ses commentaires de suivi, et la relie à
    notre colis par son numéro (code colis, code tracking ou référence externe).

    Le coût facturé n'est rapproché des départs que si le fichier a une colonne coût / frais / facturé : la
    colonne « Montant » du prestataire est ce que le client paie, pas ce qu'il nous facture.
    Renvoie un bilan : lignes, rapprochées, inconnues, écarts de coût, et l'import créé.
    """
    from management.fichier_prestataire import lire, masquer
    from management.models import ImportPrestataire, LignePrestataire
    contenu = fichier.read()
    nom = getattr(fichier, 'name', '') or ''
    try:
        nom_onglet, commandes = lire(nom, contenu, onglet)
    except ValueError as erreur:
        raise ValidationError(str(erreur))
    refs = {c['numero'] for c in commandes}
    articles = {}
    for a in (Article.objects.filter(license=license)
              .filter(Q(code__in=refs) | Q(code_tracking__in=refs) | Q(reference_externe__in=refs)).order_by('pk')):
        for ref in (a.reference_externe, a.code_tracking, a.code):
            if ref in refs:
                articles[ref] = a
    bilan = {'lignes': 0, 'rapprochees': 0, 'inconnues': [], 'ecarts': []}
    with transaction.atomic():
        imp = ImportPrestataire.objects.create(license=license, nom_fichier=masquer(nom)[:255], onglet=nom_onglet[:100], par=par)
        lignes = []
        for c in commandes:
            article, depart = articles.get(c['numero']), None
            bilan['lignes'] += 1
            if article is None:
                bilan['inconnues'].append(c['numero'])
            else:
                bilan['rapprochees'] += 1
                if c['cout'] is not None:
                    depart = article.departs.filter(cout_facture__isnull=True).order_by('date').first()
                    if depart is not None:
                        depart.cout_facture, depart.reference_import = c['cout'], c['numero']
                        depart.save()
                        if c['cout'] != depart.cout_prevu:
                            bilan['ecarts'].append((article.code, depart.cout_prevu, c['cout']))
            lignes.append(LignePrestataire(import_fichier=imp, article=article, depart=depart, **{k: v for k, v in c.items()}))
        LignePrestataire.objects.bulk_create(lignes, batch_size=500)
        imp.nb_lignes, imp.nb_rapprochees = bilan['lignes'], bilan['rapprochees']
        imp.save()
    bilan['import'] = imp
    return bilan


def supprimer_import_prestataire(imp, par):
    """Fichier importé par erreur (CEO) : les coûts qu'il avait rapprochés sont remis à zéro, ses lignes retirées.
    L'import reste listé comme supprimé (qui, quand), et le journal d'audit garde la trace."""
    with transaction.atomic():
        for ligne in imp.lignes.filter(depart__isnull=False).select_related('depart'):
            depart = ligne.depart
            depart.cout_facture, depart.reference_import = None, ''
            depart.save()
        n = imp.lignes.count()
        imp.lignes.all().delete()
        imp.supprime, imp.date_suppression, imp.supprime_par = True, timezone.now(), par
        imp.save()
    return n

