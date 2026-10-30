"""
SMS ML COD Intérieur (fournisseur HSMS).

- SmsParametres : réglages modifiables par la direction (activation, numéro service client, heures calmes,
  résumé du soir). Les identifiants HSMS ne sont PAS ici : ils restent dans les variables d'environnement.
- SmsModele : texte de chaque SMS, modifiable dans l'administration Django.
- SmsMessage : la file d'envoi. Chaque SMS y est écrit d'abord, puis envoyé par la tâche planifiée
  `sms_envoyer` (chaque minute). Rien n'est envoyé pendant la requête web : une panne HSMS ne
  ralentit ni ne bloque jamais l'équipe.
"""
from django.db import models
from django.utils import timezone


class SmsParametres(models.Model):
    """Ligne unique (pk = 1) : utiliser SmsParametres.charger()."""

    actif = models.BooleanField(
        "Envoi des SMS activé", default=False,
        help_text="Tant que c'est décoché, les SMS sont préparés dans la file mais ne partent pas.")
    tel_service = models.CharField(
        "Numéro service client (variable {tel})", max_length=30, default="27 22 35 16 19")
    heure_debut_silence = models.PositiveSmallIntegerField(
        "Début des heures calmes (heure d'Abidjan)", default=21,
        help_text="Aucun SMS client ou vendeur entre cette heure et la fin des heures calmes.")
    heure_fin_silence = models.PositiveSmallIntegerField("Fin des heures calmes", default=7)
    resume_soir_actif = models.BooleanField(
        "Résumé du soir aux vendeurs (19 h)", default=False,
        help_text="Un SMS par vendeur ayant eu de l'activité dans la journée.")
    pause_jusqua = models.DateTimeField(
        "File en pause jusqu'à", null=True, blank=True,
        help_text="Rempli automatiquement si le solde est épuisé ou si HSMS refuse la connexion.")
    derniere_erreur = models.CharField("Dernière erreur HSMS", max_length=255, blank=True, default='')
    solde_sms = models.IntegerField("Solde SMS (dernier relevé)", null=True, blank=True)
    date_solde = models.DateTimeField("Date du relevé de solde", null=True, blank=True)
    # Jeton HSMS réutilisable (évite une connexion à chaque minute). Jamais affiché dans l'administration.
    jeton_api = models.CharField(max_length=255, blank=True, default='', editable=False)

    class Meta:
        verbose_name = 'Paramètres SMS'
        verbose_name_plural = 'Paramètres SMS'

    def __str__(self):
        return 'Paramètres SMS'

    @classmethod
    def charger(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class SmsModele(models.Model):
    """Texte d'un SMS. Variables entre accolades : {boutique}, {montant}, {ville}, {date}, {tel}, {ref}…"""

    DESTINATAIRE_CLIENT = 'client'
    DESTINATAIRE_VENDEUR = 'vendeur'
    DESTINATAIRES = ((DESTINATAIRE_CLIENT, 'Client final'), (DESTINATAIRE_VENDEUR, 'Vendeur'))

    cle = models.CharField("Clé", max_length=40, unique=True)
    libelle = models.CharField("Quand part ce SMS", max_length=150)
    destinataire = models.CharField(max_length=10, choices=DESTINATAIRES)
    texte = models.TextField(
        "Texte", help_text="Sans accents de préférence : un seul caractère spécial double le prix du SMS.")
    actif = models.BooleanField("Actif", default=True)
    priorite = models.PositiveSmallIntegerField(
        "Priorité", default=5, help_text="1 = part même pendant les heures calmes (codes) · 5 = normal · 9 = peut attendre.")
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Modèle de SMS'
        verbose_name_plural = 'Modèles de SMS'
        ordering = ['destinataire', 'cle']

    def __str__(self):
        return self.libelle


class SmsMessage(models.Model):
    EN_FILE = 'en_file'
    ENVOI = 'envoi'
    ENVOYE = 'envoye'
    DELIVRE = 'delivre'
    REJETE = 'rejete'
    NON_DELIVRE = 'non_delivre'
    ECHEC = 'echec'
    ANNULE = 'annule'
    STATUTS = (
        (EN_FILE, 'En file'), (ENVOI, "En cours d'envoi"), (ENVOYE, 'Envoyé à HSMS'),
        (DELIVRE, 'Délivré'), (REJETE, 'Rejeté'), (NON_DELIVRE, 'Non délivré'),
        (ECHEC, 'Échec (abandonné)'), (ANNULE, 'Annulé'),
    )
    STATUTS_FINAUX = (DELIVRE, REJETE, NON_DELIVRE, ECHEC, ANNULE)

    modele_cle = models.CharField("Modèle", max_length=40, db_index=True)
    destinataire = models.CharField("Numéro (225XXXXXXXXXX)", max_length=20)
    texte = models.TextField()
    unicode = models.BooleanField(default=False)
    segments = models.PositiveSmallIntegerField(default=1)
    priorite = models.PositiveSmallIntegerField(default=5)
    # Une même clé = un seul SMS, quoi qu'il arrive (double clic, double enregistrement, relance du cron)
    cle_dedoublonnage = models.CharField(max_length=150, unique=True)

    statut = models.CharField(max_length=12, choices=STATUTS, default=EN_FILE, db_index=True)
    envoyer_apres = models.DateTimeField(default=timezone.now, db_index=True)
    tentatives = models.PositiveSmallIntegerField(default=0)
    verrou = models.CharField(max_length=36, blank=True, default='', db_index=True)
    date_verrou = models.DateTimeField(null=True, blank=True)

    ticket = models.CharField("Ticket HSMS", max_length=64, blank=True, default='', db_index=True)
    code_accuse = models.SmallIntegerField("Code accusé HSMS", null=True, blank=True)
    erreur = models.CharField(max_length=255, blank=True, default='')
    reponse_fournisseur = models.TextField(blank=True, default='')

    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    date_accuse = models.DateTimeField(null=True, blank=True)

    article = models.ForeignKey('management.Article', models.SET_NULL, null=True, blank=True, related_name='sms_messages')
    historique = models.ForeignKey('management.HistoriqueArticle', models.SET_NULL, null=True, blank=True, related_name='sms_messages')
    vendeur = models.ForeignKey('management.Vendeur', models.SET_NULL, null=True, blank=True, related_name='sms_messages')

    class Meta:
        verbose_name = 'SMS'
        verbose_name_plural = 'SMS (file et historique)'
        ordering = ['-date_creation']
        indexes = [models.Index(fields=['statut', 'envoyer_apres', 'priorite'], name='sms_file_idx')]

    def __str__(self):
        return '%s → %s (%s)' % (self.modele_cle, self.destinataire, self.get_statut_display())
