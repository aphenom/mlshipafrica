"""
Intégrations : Woura (place de marché) et API vendeur (sites des vendeurs : WooCommerce, Shopify, Google Sheets…).

Les secrets de la plateforme (clé Woura, secret du webhook Woura) restent dans le .env.
Chaque vendeur a ses propres clés d'API (test et production) et, s'il le souhaite, une URL de webhook.
Tous les appels entrants et sortants sont journalisés (EvenementIntegration) et dédoublonnés.
"""
import secrets

from django.db import models
from django.utils import timezone


def nouvelle_cle(prefixe):
    return '%s_%s' % (prefixe, secrets.token_urlsafe(24))


def cle_test():
    return nouvelle_cle('mlc_test')


def cle_live():
    return nouvelle_cle('mlc_live')


def secret_webhook():
    return nouvelle_cle('whsec')


class IntegrationVendeur(models.Model):
    vendeur = models.OneToOneField('management.Vendeur', on_delete=models.CASCADE, related_name='integration')
    # Woura
    woura_actif = models.BooleanField("Woura activé", default=False)
    woura_boutique_id = models.CharField("Identifiant de la boutique Woura", max_length=80, blank=True, default='', db_index=True)
    # API vendeur
    api_actif = models.BooleanField("API activée", default=False)
    cle_test = models.CharField(max_length=60, unique=True, default=cle_test)
    cle_live = models.CharField(max_length=60, unique=True, default=cle_live)
    webhook_url = models.URLField("URL de webhook (https)", blank=True, default='')
    webhook_secret = models.CharField(max_length=60, default=secret_webhook)
    webhook_evenements = models.JSONField("Événements envoyés", default=list, blank=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Intégration vendeur'

    def __str__(self):
        return 'Intégrations %s' % self.vendeur


class EvenementIntegration(models.Model):
    ENTRANT, SORTANT = 'entrant', 'sortant'
    WOURA, API = 'woura', 'api'
    EN_FILE, ENVOYE, TRAITE, ERREUR, ECHEC = 'en_file', 'envoye', 'traite', 'erreur', 'echec'
    STATUTS = ((EN_FILE, 'En file'), (ENVOYE, 'Envoyé'), (TRAITE, 'Traité'), (ERREUR, 'Erreur (nouvel essai)'), (ECHEC, 'Échec'))

    sens = models.CharField(max_length=8, choices=((ENTRANT, 'Entrant'), (SORTANT, 'Sortant')))
    canal = models.CharField(max_length=6, choices=((WOURA, 'Woura'), (API, 'API vendeur')))
    type = models.CharField(max_length=60)
    identifiant = models.CharField("Identifiant (dédoublonnage)", max_length=120, unique=True)
    vendeur = models.ForeignKey('management.Vendeur', models.SET_NULL, null=True, blank=True, related_name='evenements_integration')
    article = models.ForeignKey('management.Article', models.SET_NULL, null=True, blank=True, related_name='evenements_integration')
    contenu = models.JSONField(default=dict)
    reponse = models.TextField(blank=True, default='')
    statut = models.CharField(max_length=8, choices=STATUTS, default=EN_FILE, db_index=True)
    tentatives = models.PositiveSmallIntegerField(default=0)
    envoyer_apres = models.DateTimeField(default=timezone.now, db_index=True)
    date = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Événement d'intégration"
        verbose_name_plural = "Journal des intégrations"
        ordering = ['-date']
