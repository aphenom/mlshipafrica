"""
Retours (vendeurs sans stockage) et substitution.

  En retour vers Abidjan → frais de retour = 50 % des frais ML (cumulés si le colis revient plusieurs fois)
  Revenu à Abidjan (J0)  → SMS au vendeur : 3 jours pour substituer, sinon venir récupérer
  J5                     → rappel
  J7 et J8               → alertes
  J10                    → avis : garde payante à partir de J11, abandon à J30
  J11 à J30              → garde : 500 F par colis et par jour, plafonnée à 10 000 F
  J30                    → le manager prononce l'abandon (statut « Abandonné »)

Vendeurs en stockage : pas de garde ni de rappels ; le manager remet le colis en stock (ou le met de côté
s'il est abîmé). Les frais de retour s'appliquent quand même.

La tâche `retours_quotidien` (chaque matin) est rejouable : elle recalcule la garde à partir de la date
de retour, sans jamais la compter deux fois.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from core.models import Configuration
from management.models import Article, HistoriqueArticle
from mlshipafrica.enums import EtatConfirmation, StatutTraitement as S


def configuration_de(article):
    return (article.config or Configuration.objects.filter(license=article.license, etat_suppression=False)
            .order_by('-pk').first())


def _parametre(config, nom, defaut):
    valeur = getattr(config, nom, None) if config else None
    return Decimal(str(valeur)) if valeur is not None else Decimal(str(defaut))


def jours_a_abidjan(article, maintenant=None):
    if not article.date_revenu_abidjan:
        return None
    maintenant = maintenant or timezone.now()
    return (timezone.localtime(maintenant).date() - timezone.localtime(article.date_revenu_abidjan).date()).days


def garde_due(article, jours, config):
    """Garde cumulée à J+jours (0 pour un vendeur en stockage)."""
    if jours is None or (article.vendeur_id and article.vendeur.option_stockage):
        return Decimal('0')
    premier = int(_parametre(config, 'garde_premier_jour', 11))
    if jours < premier:
        return Decimal('0')
    par_jour = _parametre(config, 'garde_par_jour', 500)
    plafond = _parametre(config, 'garde_plafond', 10000)
    return min((jours - premier + 1) * par_jour, plafond)


def _sms_vendeur(article, cle, variables, suffixe):
    from sms.service import mettre_en_file
    vendeur = article.vendeur
    if vendeur is None:
        return None
    return mettre_en_file(cle, vendeur.numero_sms or vendeur.numero_contact, dict(variables, colis=article.code),
                          cle_dedoublonnage='%s:%s:g%d:%s' % (cle, article.code, article.generation, suffixe),
                          article=article, vendeur=vendeur)


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='retours_selon_mouvement')
def retours_selon_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw') or not created or instance.etat_suppression or not instance.etat_validation:
        return
    article = instance.article
    statut = instance.statut_traitement
    if statut == S.EN_RETOUR:
        config = configuration_de(article)
        taux = _parametre(config, 'taux_frais_retour', 50)
        frais = (Decimal(str(article.montant_frais or 0)) * taux / 100).quantize(Decimal('1'))
        Article.objects.filter(pk=article.pk).update(frais_retour=(article.frais_retour or 0) + frais)
    elif statut == S.REVENU_ABIDJAN:
        Article.objects.filter(pk=article.pk).update(date_revenu_abidjan=instance.date_creation or timezone.now(),
                                                     frais_garde=0)
        article.refresh_from_db()
        if not (article.vendeur_id and article.vendeur.option_stockage):
            transaction.on_commit(lambda: _sms_vendeur(article, 'retour', {}, 'j0'))
    elif statut == S.ABANDONNE:
        transaction.on_commit(lambda: _sms_vendeur(article, 'ret_abandon_def', {}, 'abandon'))


def traiter_retours(maintenant=None):
    """Tâche quotidienne : rappels J5, J7, J8, J10 et garde dès J11. Renvoie un bilan."""
    maintenant = maintenant or timezone.now()
    bilan = {'colis': 0, 'sms': 0, 'garde_maj': 0, 'a_abandonner': []}
    colis = (Article.objects.filter(statut_traitement=S.REVENU_ABIDJAN, date_revenu_abidjan__isnull=False,
                                    etat_suppression=False).select_related('vendeur', 'config'))
    for article in colis:
        bilan['colis'] += 1
        config = configuration_de(article)
        jours = jours_a_abidjan(article, maintenant)
        garde = garde_due(article, jours, config)
        if garde != article.frais_garde:
            Article.objects.filter(pk=article.pk).update(frais_garde=garde)
            bilan['garde_maj'] += 1
        if jours >= 30:
            bilan['a_abandonner'].append(article.code)
        if article.vendeur_id and article.vendeur.option_stockage:
            continue
        premier = int(_parametre(config, 'garde_premier_jour', 11))
        par_jour = _parametre(config, 'garde_par_jour', 500)
        debut_garde = timezone.localtime(article.date_revenu_abidjan).date() + timedelta(days=premier)
        abandon = timezone.localtime(article.date_revenu_abidjan).date() + timedelta(days=30)
        variables = {'garde': '%d F' % par_jour, 'debut': debut_garde.strftime('%d/%m'), 'date': abandon.strftime('%d/%m')}
        message = None
        if jours == 5:
            message = _sms_vendeur(article, 'rappel_subst', dict(variables, date=debut_garde.strftime('%d/%m')), 'j5')
        elif jours in (7, 8):
            message = _sms_vendeur(article, 'ret_alerte', dict(variables, n='1re' if jours == 7 else '2e',
                                                               date=debut_garde.strftime('%d/%m')), 'j%d' % jours)
        elif jours == 10:
            message = _sms_vendeur(article, 'ret_abandon', variables, 'j10')
        if message:
            bilan['sms'] += 1
    return bilan


@transaction.atomic
def substituer(article, user, nouveau_client):
    """
    Le vendeur donne un nouveau client pour un colis revenu à Abidjan. Le colis repart en préparation,
    les frais sont recalculés pour la nouvelle destination, et il faut le reconfirmer.
    nouveau_client : nom, prenom, numero_principal, numero_secondaire, adresse, localite (Localite), valeur (montant à encaisser)
    """
    article = Article.objects.select_for_update().get(pk=article.pk)
    if article.statut_traitement != S.REVENU_ABIDJAN:
        raise ValidationError("Seul un colis revenu à Abidjan peut être substitué.")
    if not nouveau_client.get('numero_principal') or not nouveau_client.get('localite'):
        raise ValidationError("Indiquez au moins le numéro et la localité du nouveau client.")
    article.nom_destinataire = nouveau_client.get('nom') or ''
    article.prenom_destinataire = nouveau_client.get('prenom') or ''
    article.numero_principal_destinataire = nouveau_client['numero_principal']
    article.numero_secondaire_destinataire = nouveau_client.get('numero_secondaire') or None
    article.adresse_destinataire = nouveau_client.get('adresse') or ''
    article.localite_arrivee = nouveau_client['localite']
    if nouveau_client.get('valeur') is not None:
        article.valeur = nouveau_client['valeur']
        article.valeur_totale = Decimal(str(nouveau_client['valeur'])) * (article.quantite or 1)
    article.generation += 1
    article.etat_confirmation = EtatConfirmation.A_CONFIRMER
    article.date_confirmation = None
    article.date_revenu_abidjan = None
    article.frais_garde = article.frais_garde  # la garde déjà due reste due
    # Nouveaux frais pour la nouvelle destination (Article.save recalcule quand le tarif est vide)
    article.tarification = None
    article.statut_traitement = S.SUBSTITUE
    article.save()
    if article.tarification_id is None:
        raise ValidationError("Aucun tarif pour cette destination.")
    dernier = article.get_last_historique()
    if dernier is None or dernier.statut_traitement != S.SUBSTITUE:
        HistoriqueArticle.objects.create(article=article, statut_traitement=S.SUBSTITUE, date=timezone.now(),
                                         commentaire='Nouveau client : %s' % article.localite_arrivee,
                                         license=article.license, dernier_historique_article=dernier)
    return article
