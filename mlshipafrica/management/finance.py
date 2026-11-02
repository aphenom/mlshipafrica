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
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from management.models import Article, Depart, Ecriture, HistoriqueArticle, Releve
from mlshipafrica.enums import StatutReleve, StatutTraitement as S, TypeEcriture as T

LIVRES = (S.LIVRE, S.LIVRE_PAYE, S.REVERSE)
TYPES_VENDEUR_DEBIT = (T.FRAIS, T.FRAIS_COLLECTE, T.FRAIS_RETOUR, T.GARDE, T.STOCKAGE)
ZERO = Decimal('0')


def _d(v):
    return Decimal(str(v or 0))


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
        'retours': par_type.get(T.FRAIS_RETOUR, ZERO),
        'garde': par_type.get(T.GARDE, ZERO),
        'stockage': par_type.get(T.STOCKAGE, ZERO),
    }
    t['net'] = t['collecte'] - t['frais'] - t['retours'] - t['garde'] - t['stockage']
    return t


@transaction.atomic
def generer_releves(arrete=None):
    """Un relevé par vendeur ayant des écritures non relevées jusqu'à l'arrêté. Renvoie la liste des relevés."""
    arrete = arrete or timezone.now()
    a_relever = Ecriture.objects.filter(releve__isnull=True, vendeur__isnull=False, date__lte=arrete).exclude(
        type=T.COUT_PRESTATAIRE)
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
            total_retours=t['retours'], total_garde=t['garde'], total_stockage=t['stockage'], net=t['net'])
        lignes.update(releve=releve)
        crees.append(releve)
    return crees


@transaction.atomic
def marquer_verse(releve, user, reference, moyen=''):
    releve = Releve.objects.select_for_update().get(pk=releve.pk)
    if releve.statut == StatutReleve.VERSE:
        raise ValidationError("Ce relevé est déjà versé.")
    if not (reference or '').strip():
        raise ValidationError("Indiquez la référence du versement.")
    releve.statut = StatutReleve.VERSE
    releve.date_versement = timezone.now()
    releve.reference_versement = reference.strip()[:100]
    releve.moyen_versement = moyen or (releve.vendeur.moyen_versement or '')
    releve.verse_par = user
    releve.save()
    # Les colis du relevé sont réglés : frais payés, collecte reversée (statut « Reversé »)
    articles = Article.objects.filter(ecritures__releve=releve).distinct()
    articles.update(etat_reglement=True)
    for article in articles.filter(statut_traitement=S.LIVRE_PAYE):
        dernier = article.get_last_historique()
        Article.objects.filter(pk=article.pk).update(statut_traitement=S.REVERSE, etat_reversement=True)
        HistoriqueArticle.objects.create(article=article, statut_traitement=S.REVERSE, date=timezone.now(),
                                         commentaire='Relevé %s versé' % releve.code, license=article.license,
                                         dernier_historique_article=dernier)
    return releve


# --------------------------------------------------------------------------------------------- journal

def journal(license, debut, fin):
    """Résultat de la période (CEO et comptable) : revenus, coût prestataire, bénéfice, volumes."""
    e = Ecriture.objects.filter(license=license, date__gte=debut, date__lt=fin)
    par_type = {r['type']: _d(r['t']) for r in e.values('type').annotate(t=Sum('montant'))}
    revenus = sum((par_type.get(t, ZERO) for t in TYPES_VENDEUR_DEBIT), ZERO)
    cout = par_type.get(T.COUT_PRESTATAIRE, ZERO)
    livres = HistoriqueArticle.objects.filter(license=license, date_creation__gte=debut, date_creation__lt=fin,
                                              etat_suppression=False, statut_traitement__in=(S.LIVRE, S.LIVRE_PAYE)
                                              ).values('article').distinct().count()
    departs = Depart.objects.filter(article__license=license, date__gte=debut, date__lt=fin)
    en_route = Article.objects.filter(license=license, etat_suppression=False, statut_traitement__in=(
        S.EN_TRANSIT, S.EN_COURS_LIVRAISON, S.ARRIVE, S.ECHEC_LIVRAISON, S.RECONDUIT, S.EN_RETOUR))
    from management.models import Acompte
    acomptes = Acompte.objects.filter(license=license, date_reception__gte=debut, date_reception__lt=fin).aggregate(
        n=Count('id'), t=Sum('montant'))
    return {
        'par_type': [(T(t).label, par_type.get(t, ZERO)) for t in (T.FRAIS, T.FRAIS_COLLECTE, T.FRAIS_RETOUR, T.GARDE, T.STOCKAGE)],
        'revenus': revenus, 'cout_prestataire': cout, 'benefice': revenus - cout,
        'collecte': par_type.get(T.COLLECTE, ZERO), 'livres': livres, 'departs': departs.count(),
        'cout_facture': _d(departs.aggregate(t=Sum('cout_facture'))['t']),
        'ecart_prestataire': _d(departs.filter(cout_facture__isnull=False).aggregate(
            t=Sum('cout_facture'))['t']) - _d(departs.filter(cout_facture__isnull=False).aggregate(t=Sum('cout_prevu'))['t']),
        'engages': en_route.count(), 'acomptes_n': acomptes['n'] or 0, 'acomptes_total': _d(acomptes['t']),
    }


# --------------------------------------------------------------------------------------------- fichier prestataire

def importer_fichier_prestataire(license, fichier):
    """
    CSV (séparateur ; ou ,) avec au moins deux colonnes : la référence du colis (code tracking ou code ML) et le
    montant facturé. Les noms de colonnes reconnus : reference / tracking / code, et montant / cout / total.
    Rattache chaque ligne au dernier départ non encore rapproché du colis. Renvoie un bilan avec les écarts.
    """
    contenu = fichier.read()
    texte = contenu.decode('utf-8-sig', errors='replace') if isinstance(contenu, bytes) else contenu
    dialecte = csv.Sniffer().sniff(texte[:2000], delimiters=';,') if texte.strip() else csv.excel
    lignes = list(csv.DictReader(io.StringIO(texte), dialect=dialecte))
    if not lignes:
        raise ValidationError("Fichier vide.")
    colonnes = {c.lower().strip(): c for c in lignes[0].keys() if c}
    col_ref = next((colonnes[c] for c in colonnes if c in ('reference', 'référence', 'tracking', 'code', 'code_tracking', 'numero', 'numéro')), None)
    col_montant = next((colonnes[c] for c in colonnes if c in ('montant', 'cout', 'coût', 'total', 'prix', 'amount')), None)
    if not col_ref or not col_montant:
        raise ValidationError("Colonnes attendues : une référence (reference, tracking ou code) et un montant (montant, cout ou total).")
    bilan = {'lignes': 0, 'rapprochees': 0, 'inconnues': [], 'ecarts': []}
    for ligne in lignes:
        ref = (ligne.get(col_ref) or '').strip()
        if not ref:
            continue
        bilan['lignes'] += 1
        try:
            montant = Decimal(str(ligne.get(col_montant) or '0').replace(' ', '').replace(' ', '').replace(',', '.'))
        except ArithmeticError:
            bilan['inconnues'].append(ref)
            continue
        depart = (Depart.objects.filter(article__license=license, cout_facture__isnull=True)
                  .filter(Q(article__code_tracking=ref) | Q(article__code=ref)).order_by('date').first())
        if depart is None:
            bilan['inconnues'].append(ref)
            continue
        depart.cout_facture, depart.reference_import = montant, ref
        depart.save()
        bilan['rapprochees'] += 1
        if montant != depart.cout_prevu:
            bilan['ecarts'].append((depart.article.code, depart.cout_prevu, montant))
    return bilan
