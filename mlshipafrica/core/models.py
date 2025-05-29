from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django_currentuser.middleware import (
    get_current_user, get_current_authenticated_user)
from tinymce.models import HTMLField

from mlshipafrica.utils import CodeGenerator
from phonenumber_field.modelfields import PhoneNumberField


# Create your models here.
class MyModelAbstract(models.Model):
    '''Champs communs aux modèles'''
    class Meta:
        abstract = True

    code = models.CharField(max_length=25, unique=True, editable=False)
    etat_validation = models.BooleanField('Etat validation', default=True)
    etat_suppression = models.BooleanField('Etat suppression', default=False)
    date_creation = models.DateTimeField('Date création', auto_now_add=True)
    date_modification = models.DateTimeField('Date modification', auto_now=True)
    date_validation = models.DateTimeField('Date validation', null=True, blank=True)
    date_suppression = models.DateTimeField('Date suppression', null=True, blank=True)
    creation_par = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name="creation_%(class)ss", related_query_name="creation_%(class)s", verbose_name = "Créé par")
    modification_par = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name="modification_%(class)ss", related_query_name="modification_%(class)s", verbose_name = "Modifié par")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_etat_validation = self.etat_validation
        self._init_etat_suppression = self.etat_suppression

    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''
        if not self.id:
            self.code = CodeGenerator(self.__class__, None, None)
            self.creation_par = get_current_user()
        else:
            self.modification_par = get_current_user()
        if self.etat_validation != self._init_etat_validation:
            if self.etat_validation == True:
                self.date_validation = timezone.now()
        if self.etat_suppression != self._init_etat_suppression:
            if self.etat_suppression == True:
                self.date_suppression = timezone.now()                             
        return super(MyModelAbstract, self).save(*args, **kwargs)  


class MyModeleManager(models.Manager):
    def get_queryset(self):
        # Personnalisez votre requête queryset ici
        qs = super().get_queryset()
        # print(hasattr(self.model, 'paroisse'))
        if hasattr(self.model, 'license') and get_current_user() and get_current_user().account_vendeur:
            qs = qs.filter(license=get_current_user().account_vendeur.license)
        return qs 
    

""" Permet l'utilisation en mode license """
class License(MyModelAbstract):

    #objects = MonModeleManager()

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'License'
        verbose_name_plural = 'Licenses'      
        db_table_comment = "Les enregistrements pour l'utilisation en mode license"


""" Permet de determiner les achats pour l'utilisation en mode license """
class AchatLicense(MyModelAbstract):

    debut = models.DateTimeField('date debut', null=True, blank=True)
    fin = models.DateTimeField('date fin', null=True, blank=True)
    cout = models.DecimalField('montant mise', max_digits=10, decimal_places=2, null=True, blank=True)
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_achats', related_query_name="license_achat", verbose_name = "license")

    def __str__(self):
        license_code = self.license.code if self.license and self.license.code else "???"
        debut_str = self.debut.strftime("%d-%m-%Y") if self.debut else "???"
        fin_str = self.fin.strftime("%d-%m-%Y") if self.fin else "???"
        return f"{license_code} valable de {debut_str} à {fin_str}"
    class Meta:
        verbose_name = 'Achat License'
        verbose_name_plural = 'Achats Licenses'      
        db_table_comment = "Les achats pour l'utilisation en mode license"


""" Permet une config personnalisée en fonction de la license """
class Configuration(MyModelAbstract):

    ''' Stock la configuration générale de la plateforme '''
    enable_option_recuperation = models.BooleanField('état option recuperation colis', default=True, db_comment="Possibilité ou non de récuperer le colis directement chez le vendeur")
    enable_option_encaissement = models.BooleanField('état option encaissement client', default=True, db_comment="Possibilité ou non d'encaisser le paiement du colis directement chez le client")
    cout_option_recuperation = models.DecimalField('cout fixe option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option de récupération au cas où il serait uniforme pour chaque colis")
    taux_option_recuperation = models.DecimalField('taux option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option de récupération")
    cout_option_encaissement = models.DecimalField('cout fixe option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    taux_option_encaissement = models.DecimalField('taux option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option d'encaissement")
    url_api_sms = models.CharField("SMS Base URL", max_length=100, null=True, blank=True)
    key_api_sms = models.CharField("SMS API KEY", max_length=100, null=True, blank=True)
    id_api_sms = models.CharField("SMS API ID", max_length=100, null=True, blank=True)
    json_api_sms  = models.TextField('JSON API SMS', null=True, blank=True)
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_configurations', related_query_name="license_configuration", verbose_name = "license")
    
    app_nom = models.CharField('nom plateforme', max_length=50)
    slogan = models.CharField("slogan", max_length=100, null=True, blank=True)
    # gameplay_url = models.CharField("Gameplay URL", max_length=100, null=True, blank=True)
    # gameplay_backend_url = models.CharField("Gameplay Backend URL", max_length=100, null=True, blank=True)
    email = models.EmailField("email", max_length=100, null=True, blank=True)
    monnaie = models.CharField("monnaie", max_length=15, null=True, blank=True)
    contact = models.CharField("contact", max_length=100, null=True, blank=True)
    adresse = models.CharField("adresse", max_length=100, null=True, blank=True)
    # sms_api_url = models.CharField("SMS Base URL", max_length=100, null=True, blank=True)
    # sms_api_id = models.CharField("SMS API ID", max_length=100, null=True, blank=True)
    # sms_api_key = models.CharField("SMS API KEY", max_length=100, null=True, blank=True)
    # notification_api_url = models.CharField("Notification Base URL", max_length=100, null=True, blank=True)
    # notification_api_id = models.CharField("Notification API ID", max_length=100, null=True, blank=True)
    # notification_api_key = models.CharField("Notification API KEY", max_length=100, null=True, blank=True)
    # sms_api_url = models.CharField("SMS Base URL", max_length=100, null=True, blank=True)
    # sms_api_id = models.CharField("SMS API ID", max_length=100, null=True, blank=True)
    # sms_api_key = models.CharField("SMS API KEY", max_length=100, null=True, blank=True)
    # email_api_url = models.CharField("Email Base URL", max_length=100, null=True, blank=True)
    # email_api_id = models.CharField("Email API ID", max_length=100, null=True, blank=True)
    # email_api_key = models.CharField("Email API KEY", max_length=100, null=True, blank=True)
    # transaction_api_url = models.CharField("Paiement Base URL", max_length=100, null=True, blank=True)
    # transaction_api_id = models.CharField("Paiement API ID", max_length=100, null=True, blank=True)
    # transaction_api_key = models.CharField("Paiement API KEY", max_length=100, null=True, blank=True)
    # transaction_api_password = models.CharField("Paiement API PASSWORD", max_length=100, null=True, blank=True)
    logo = models.ImageField(upload_to='uploaded_media/config/logos')
    logo_symbol = models.ImageField(upload_to='uploaded_media/config/logo_symbols')
    favicon = models.ImageField(upload_to='uploaded_media/config/favicons')
    # minimum_retrait = models.DecimalField('montant minimum de retrait', max_digits=10, decimal_places=2, null=True, blank=True)
    # minimum_depot = models.DecimalField('montant minimum de dépôt', max_digits=10, decimal_places=2, null=True, blank=True)
    # note_information = HTMLField("note d'information", null=True, blank=True)

    def __str__(self):
        return '{} {}'.format(self.license, self.code)

    class Meta:
        verbose_name = 'Configuration'
        verbose_name_plural = 'Configurations'      
        db_table_comment = "Les configurations générales de la plateforme"


""" Les partenaires logistique pour les livraisons """
class PartenaireLogistique(MyModelAbstract):

    nom = models.CharField('nom', max_length=100)
    email = models.EmailField("email", max_length=100, null=True, blank=True)
    contact = PhoneNumberField("contact", max_length=100, null=True, blank=True)
    adresse = models.CharField("adresse", max_length=100, null=True, blank=True)
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_partenairelogistiques', related_query_name="license_partenairelogistique", verbose_name = "license")

    def __str__(self):
        return '{} - {}'.format(self.code, self.nom)

    class Meta:
        verbose_name = 'Partenaire Logistique'
        verbose_name_plural = 'Partenaires Logistique'
        db_table_comment = "Les partenaires logistique pour les livraisons"


""" Détermine les zones à couvrir pour activité de livraison """
class Zone(MyModelAbstract):

    is_depart = models.BooleanField('est depart', default=True, db_comment="Possibilité ou non de faire partir un colis de cette zone")
    is_arrivee = models.BooleanField('est arrivee', default=True, db_comment="Possibilité ou non d'envoyer un colis vers cette zone")
    nom = models.CharField('nom', max_length=100)
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_zones', related_query_name="license_zone", verbose_name = "license")
    
    objects = MyModeleManager()

    def __str__(self):
        # return '{} - {}'.format(self.code, self.nom)
        return '{}'.format(self.nom)

    class Meta:
        verbose_name = 'Zone'
        verbose_name_plural = 'Zones'      
        db_table_comment = "Les zones à couvrir pour l'activité de livraison"


""" Détermine les localités à couvrir pour activité de livraison """
class Localite(MyModelAbstract):

    is_depart = models.BooleanField('est depart', default=True, db_comment="Possibilité ou non de faire partir un colis de cette localité")
    is_arrivee = models.BooleanField('est arrivee', default=True, db_comment="Possibilité ou non d'envoyer un colis vers cette localité")
    nom = models.CharField('nom', max_length=100)
    zone = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_localites', related_query_name="zone_localite", verbose_name = "zone")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_localites', related_query_name="license_localite", verbose_name = "license")
    
    objects = MyModeleManager()

    def __str__(self):
        # return '{} - {}'.format(self.code, self.nom)
        return '{}'.format(self.nom)

    class Meta:
        verbose_name = 'Localité'
        verbose_name_plural = 'Localités'      
        db_table_comment = "Les localités à couvrir pour l'activité de livraison"
        ordering = ['nom']


""" Détermine les formats des colis pour l'activité """
class FormatArticle(MyModelAbstract):

    nom = models.CharField('nom', max_length=100)
    caracteristique = models.CharField('caracteristique', max_length=255)
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_formatarticles', related_query_name="license_formatarticle", verbose_name = "license")
    
    objects = MyModeleManager()

    def __str__(self):
        # return '{} - {}'.format(self.code, self.nom)
        return '{} | {}'.format(self.nom, self.caracteristique) if self.caracteristique else '{}'.format(self.nom)

    class Meta:
        verbose_name = 'Format Article'
        verbose_name_plural = 'Formats Article'      
        db_table_comment = "Les formats des colis à traiter"

      