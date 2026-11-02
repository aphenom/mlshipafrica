"""
Confirmation des commandes par l'agent COD, acompte du client final et remboursement.

Règles (cahier des charges, lot « Commandes et confirmation ») :
  - le vendeur valide sa commande → elle entre dans la file de confirmation de son agent COD ;
  - l'agent appelle le client : confirmé (avec ou sans acompte), injoignable (à rappeler) ou annulé ;
  - une annulation avant le départ donne « Annulé avant expédition » et l'acompte reçu passe « à rembourser » ;
  - après le départ (en transit), il n'y a plus de remboursement ;
  - la comptable rembourse et note la référence ;
  - un colis non confirmé ne part en transit qu'avec un motif écrit.

L'acompte est une méthode interne : il n'apparaît dans aucun écran vendeur, aucun SMS, aucun export vendeur.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from management.models import Acompte, AppelConfirmation, Article, HistoriqueArticle
from management.statuts import STATUTS_AVANT_EXPEDITION, transition_autorisee
from mlshipafrica.enums import EtatConfirmation, ResultatAppel, StatutAcompte, StatutTraitement as S

STATUTS_FILE_CONFIRMATION = (S.EN_ATTENTE_RAMASSAGE, S.EN_ATTENTE_DEPOT, S.RAMASSE, S.DEPOT)


def file_de_confirmation(profil_staff):
    """Colis à appeler. Un agent voit les siens et ceux sans agent ; manager et direction voient tout."""
    from mlshipafrica.enums import TypeProfilStaffChoice as R
    qs = (Article.objects.filter(license=profil_staff.license, etat_suppression=False,
                                 statut_traitement__in=STATUTS_FILE_CONFIRMATION,
                                 etat_confirmation__in=(EtatConfirmation.A_CONFIRMER, EtatConfirmation.INJOIGNABLE))
          .select_related('vendeur', 'localite_arrivee', 'localite_arrivee__zone', 'agent_cod__user')
          .order_by('date_creation'))
    if profil_staff.role_profil == R.AGENT:
        qs = qs.filter(Q(agent_cod=profil_staff) | Q(agent_cod__isnull=True))
    return qs


def changer_statut(article, nouveau, user, commentaire=''):
    """Applique un mouvement comme la vue d'administration : historique + statut, après contrôle du circuit."""
    dernier = article.get_last_historique()
    if not transition_autorisee(article, dernier, nouveau, user):
        raise ValidationError("Ce changement de statut n'est pas permis pour ce colis.")
    article.statut_traitement = nouveau
    article.etat_validation = True
    article.save()
    HistoriqueArticle.objects.create(article=article, statut_traitement=nouveau, date=timezone.now(),
                                     commentaire=commentaire, license=article.license,
                                     dernier_historique_article=dernier)


@transaction.atomic
def enregistrer_appel(article, user, resultat, commentaire='', acompte=None):
    """
    resultat : ResultatAppel. acompte : dict(montant, reseau, reference_depot, numero_depot) ou None.
    Lève ValidationError avec un message lisible si la saisie est incomplète.
    """
    article = Article.objects.select_for_update().get(pk=article.pk)
    if article.statut_traitement not in STATUTS_FILE_CONFIRMATION:
        raise ValidationError("Ce colis est déjà parti ou annulé : il ne se confirme plus.")
    if resultat == ResultatAppel.ANNULE and not commentaire.strip():
        raise ValidationError("Indiquez le motif de l'annulation.")

    AppelConfirmation.objects.create(article=article, agent=user, resultat=resultat, commentaire=commentaire)
    article.nombre_appels += 1

    if resultat == ResultatAppel.CONFIRME:
        if acompte:
            reference = (acompte.get('reference_depot') or '').strip()
            if not reference or not acompte.get('reseau'):
                raise ValidationError("Pour un acompte, indiquez le réseau et la référence du dépôt.")
            if Acompte.objects.filter(reseau=acompte['reseau'], reference_depot=reference).exists():
                raise ValidationError("Cette référence de dépôt est déjà utilisée pour une autre commande.")
            Acompte.objects.create(article=article, montant=acompte['montant'], reseau=acompte['reseau'],
                                   reference_depot=reference, numero_depot=(acompte.get('numero_depot') or '')[:30],
                                   recu_par=user, license=article.license)
        article.etat_confirmation = EtatConfirmation.CONFIRME
        article.date_confirmation = timezone.now()
        article.confirme_par = user
        article.save()
    elif resultat == ResultatAppel.INJOIGNABLE:
        article.etat_confirmation = EtatConfirmation.INJOIGNABLE
        article.save()
    elif resultat == ResultatAppel.ANNULE:
        article.etat_confirmation = EtatConfirmation.ANNULE
        article.save()
        changer_statut(article, S.ANNULE, user, commentaire='Annulé par le client : ' + commentaire.strip())
    return article


@transaction.atomic
def marquer_rembourse(acompte, user, reference, date=None):
    acompte = Acompte.objects.select_for_update().get(pk=acompte.pk)
    if acompte.statut != StatutAcompte.A_REMBOURSER:
        raise ValidationError("Cet acompte n'est pas à rembourser.")
    if not (reference or '').strip():
        raise ValidationError("Indiquez la référence du remboursement.")
    acompte.statut = StatutAcompte.REMBOURSE
    acompte.reference_remboursement = reference.strip()[:100]
    acompte.date_remboursement = date or timezone.now()
    acompte.rembourse_par = user
    acompte.save()
    return acompte


def dernier_acompte(article):
    return article.acomptes.order_by('-date_reception', '-pk').first()


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='acompte_selon_mouvement')
def acompte_selon_mouvement(sender, instance, created, **kwargs):
    """Annulation avant expédition → acompte à rembourser ; relance → nouvelle confirmation."""
    if kwargs.get('raw') or not created or instance.etat_suppression or not instance.etat_validation:
        return
    article = instance.article
    if instance.statut_traitement == S.ANNULE:
        precedent = instance.dernier_historique_article
        avant_depart = precedent is None or precedent.statut_traitement in STATUTS_AVANT_EXPEDITION
        if avant_depart:
            article.acomptes.filter(statut=StatutAcompte.RECU).update(
                statut=StatutAcompte.A_REMBOURSER, date_demande_remboursement=timezone.now())
        if article.etat_confirmation != EtatConfirmation.ANNULE:
            Article.objects.filter(pk=article.pk).update(etat_confirmation=EtatConfirmation.ANNULE)
    elif instance.statut_traitement in STATUTS_AVANT_EXPEDITION:
        precedent = instance.dernier_historique_article
        if precedent is not None and precedent.statut_traitement == S.ANNULE:
            # Le client revient sur sa décision : on le rappelle pour reconfirmer
            Article.objects.filter(pk=article.pk).update(etat_confirmation=EtatConfirmation.A_CONFIRMER,
                                                         date_confirmation=None)
