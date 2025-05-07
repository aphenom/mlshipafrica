from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django_currentuser.middleware import (
    get_current_user, get_current_authenticated_user)
from tinymce.models import HTMLField

from core.models import License, PartenaireLogistique, Zone
from mlshipafrica.utils import CodeGenerator

from mlshipafrica.enums import StatutTraitement, STATUT_TRAITEMENT_COULEURS

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
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
        self._init_date_validation = self.date_validation
        self._init_date_suppression = self.date_suppression

    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''
        if not self.id:
            self.code = CodeGenerator(self, None, None)
            self.creation_par = get_current_user()
        else:
            self.modification_par = get_current_user()
        if self.date_validation != self._init_date_validation:
            if self.etat_validation == True:
                self.date_validation = timezone.now()
        if self.date_suppression != self._init_date_suppression:
            if self.etat_suppression == True:
                self.date_suppression = timezone.now()                             
        return super(MyModelAbstract, self).save(*args, **kwargs)  


""" Vendeur pour lequel on gere la livraison """
class Vendeur(MyModelAbstract):

    nom = models.CharField("Nom", max_length=100, null=True, blank=True)
    adresse = models.CharField("Adresse", max_length=255, null=True, blank=True)
    logo = models.ImageField(upload_to='uploaded_media/management/vendeur_logos', null=True, blank=True)
    nom_contact = models.CharField("Nom contact", max_length=100, null=True, blank=True)
    prenom_contact = models.CharField("Prénom(s) contact", max_length=255, null=True, blank=True)
    fonction_contact = models.CharField("Fonction contact", max_length=255, null=True, blank=True)
    numero_contact = PhoneNumberField("Numéro contact", null=True, blank=True)
    email_contact = models.CharField("Email contact", max_length=100, null=True, blank=True)
    numero_sms = PhoneNumberField("Numéro notification sms", null=True, blank=True)
    email_notification = models.CharField("Email notification", max_length=100, null=True, blank=True)
    etat_approbation = models.BooleanField('Etat approbation', default=False)
    approbation_par = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name='approbation_vendeurs', related_query_name="approbation_vendeur", verbose_name = "approuvé par")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_vendeur', verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_vendeurs', related_query_name="license_vendeur", verbose_name = "license")
    

    def __str__(self):
        return '{}'.format(self.nom)

    class Meta:
        verbose_name = 'Vendeur'
        verbose_name_plural = 'Vendeurs'      
        db_table_comment = "Les Vendeurs pour lesquels il faut gérer la livraison"

    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''                      
        if self.code and self.user.username != self.code:
            self.user.username = self.code
        if self.nom and self.user.last_name != self.nom:
            self.user.last_name = self.nom
        self.user.save()
        return super(Vendeur, self).save(*args, **kwargs)        


@receiver(post_save, sender=User)
def save_user_username(sender, instance, **kwargs):
    if not instance.username:
        instance.username = instance.email
        instance.save()


""" Parametrage des tarifs selon les critères souhaités """
class Tarification(MyModelAbstract):

    montant_frais = models.DecimalField('Montant frais', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    cout_option_recuperation = models.DecimalField('cout fixe option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option de récupération au cas où il serait uniforme pour chaque colis")
    taux_option_recuperation = models.DecimalField('taux option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option de récupération")
    cout_option_encaissement = models.DecimalField('cout fixe option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    taux_option_encaissement = models.DecimalField('taux option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option d'encaissement")

    partenaire_logistique = models.ForeignKey(PartenaireLogistique, models.SET_NULL, null=True, blank=True, related_name='partenaire_logistiquetarifications', related_query_name="partenaire_logistiquetarification", verbose_name = "partenaire logistique")
    zone_depart = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_departtarifications', related_query_name="zone_departtarification", verbose_name = "zone départ")
    zone_arrivee = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_arriveetarifications', related_query_name="zone_arriveetarification", verbose_name = "zone arrivée")
    localite_depart = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='localite_departtarifications', related_query_name="localite_departtarification", verbose_name = "localité départ")
    localite_arrivee = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='localite_arriveetarifications', related_query_name="localite_arriveetarification", verbose_name = "localité arrivée")
    format_article = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='format_articletarifications', related_query_name="format_articletarification", verbose_name = "format article")
    vendeur = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='vendeur_tarifications', related_query_name="vendeur_tarification", verbose_name = "vendeur")
    config = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='config_tarifications', related_query_name="config_tarification", verbose_name = "Configuration")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_tarifications', related_query_name="license_tarification", verbose_name = "license")
    

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Tarification'
        verbose_name_plural = 'Tarifications'      
        db_table_comment = "Les tarifs définis selon les critères souhaités"


""" Les articles répresentant les colis à livrer """
class Article(MyModelAbstract):

    code_tracking = models.CharField('Code tracking', max_length=25, null=True, blank=True, db_comment="Code unique auprès du prestatire du colis permettant de le suivre")
    
    valeur = models.DecimalField('Valeur', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    montant_frais = models.DecimalField('Montant frais', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    is_option_recuperation = models.BooleanField('état option recuperation du colis', default=False, db_comment="Possibilité ou non de récuperer le colis directement chez le vendeur")
    is_option_encaissement = models.BooleanField('état option encaissement du client', default=False, db_comment="Possibilité ou non d'encaisser le paiement du colis directement chez le client")
    cout_option_recuperation = models.DecimalField('cout fixe option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option de récupération au cas où il serait uniforme pour chaque colis (= self+%valeur)")
    taux_option_recuperation = models.DecimalField('taux option recuperation colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option de récupération (= %valeur)")
    cout_option_encaissement = models.DecimalField('cout fixe option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis (= self+%valeur)")
    taux_option_encaissement = models.DecimalField('taux option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option d'encaissement (= %valeur)")
    montant_total_frais = models.DecimalField('Montant total frais', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout total des frais associé au colis (=montant_frais+cout_option_recuperation+cout_option_encaissement)")

    nom_destinataire = models.CharField("Nom destinataire", max_length=100, null=True, blank=True)
    nom_destinataire = models.CharField("Prénom(s) destinataire", max_length=255, null=True, blank=True)
    numero_principal_destinataire = PhoneNumberField("Numéro principal destinataire", null=True, blank=True)
    numero_secondaire_destinataire = PhoneNumberField("Numéro secondaire destinataire", null=True, blank=True)

    statut_traitement = models.CharField(max_length=25, choices=StatutTraitement.choices,default=StatutTraitement.BROUILLON, null=True, blank=True)
    etat_encaissement = models.BooleanField('état encaissement client', default=False)
    etat_reglement = models.BooleanField('état reglement vendeur', default=False)
    etat_reversement = models.BooleanField('état reversement encaissement', default=False)

    tarification = models.ForeignKey(Tarification, models.SET_NULL, null=True, blank=True, related_name='tarification_articles', related_query_name="tarification_article", verbose_name = "partenaire logistique")
    partenaire_logistique = models.ForeignKey(PartenaireLogistique, models.SET_NULL, null=True, blank=True, related_name='partenaire_logistiquearticles', related_query_name="partenaire_logistiquearticle", verbose_name = "partenaire logistique")
    zone_depart = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_departarticles', related_query_name="zone_departarticle", verbose_name = "zone départ")
    zone_arrivee = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_arriveearticles', related_query_name="zone_arriveearticle", verbose_name = "zone arrivée")
    localite_depart = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='localite_departarticles', related_query_name="localite_departarticle", verbose_name = "localité départ")
    localite_arrivee = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='localite_arriveearticles', related_query_name="localite_arriveearticle", verbose_name = "localité arrivée")
    format_article = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='format_articlearticles', related_query_name="format_articlearticle", verbose_name = "format article")
    vendeur = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='vendeur_articles', related_query_name="vendeur_article", verbose_name = "vendeur")
    config = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='config_articles', related_query_name="config_article", verbose_name = "Configuration")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_articles', related_query_name="license_article", verbose_name = "license")
    
    #last_histo_article
    #last_reglement_article

    def __str__(self):
        return '{}'.format(self.code)
    
    def get_statut_traitement_couleur(self):
        return STATUT_TRAITEMENT_COULEURS.get(self.statut_traitement, 'black')  # couleur par défaut si non trouvée
 
    class Meta:
        verbose_name = 'Article'
        verbose_name_plural = 'Articles'      
        db_table_comment = "Les articles répresentant les colis à livrer"


""" Historisations des mouvements des articles répresentant les colis pendant le traitement"""
class HistoriqueArticle(MyModelAbstract):

    statut_traitement = models.CharField(max_length=25, choices=StatutTraitement.choices,default=StatutTraitement.BROUILLON, null=True, blank=True)
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    dernier_historique_article = models.OneToOneField('self', models.SET_NULL, related_name="prochain_historique", verbose_name="dernier historique article", null=True, blank=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_historiquearticles', related_query_name="article_historiquearticle", verbose_name = "article")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_historiquearticles', related_query_name="license_historiquearticle", verbose_name = "license")

    def get_statut_traitement_couleur(self):
        return STATUT_TRAITEMENT_COULEURS.get(self.statut_traitement, 'black')  # couleur par défaut si non trouvée
    
    def __str__(self):
        return '{} {}'.format(self.article, self.statut_traitement)

    class Meta:
        verbose_name = 'Historique Article'
        verbose_name_plural = 'Historiques Articles'      
        db_table_comment = "Historisations des mouvements des articles répresentant les colis pendant le traitement"


""" Les reglements des frais de livraison du vendeur """
class ReglementArticle(MyModelAbstract):

    montant_reglement = models.DecimalField('Montant réglé', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant réglé par le vendeur")
    montant_restant = models.DecimalField('Montant restant', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant restant après ce règlement")
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    dernier_reglement_article = models.OneToOneField('self', models.SET_NULL, related_name="prochain_reglement", verbose_name="dernier reglement article", null=True, blank=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_reglementarticles', related_query_name="article_reglementarticle", verbose_name = "article")
    vendeur = models.ForeignKey(Vendeur, on_delete=models.CASCADE, related_name='vendeur_reglementarticles', related_query_name="vendeur_reglementarticle", verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_reglementarticles', related_query_name="license_reglementarticle", verbose_name = "license")

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Reglement Article'
        verbose_name_plural = 'Reglement Articles'      
        db_table_comment = "Les reglements des frais de livraison du vendeur"


""" Les encaissements des paiements des clients pour le vendeur """
class Encaissement(MyModelAbstract):

    montant = models.DecimalField('Montant', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant récupérer avec le client")
    etat_reversement = models.BooleanField('état reversement', default=False, db_comment="Etat du reversement du montant encaissé au vendeur")
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_encaissements', related_query_name="article_encaissement", verbose_name = "article")
    vendeur = models.ForeignKey(Vendeur, on_delete=models.CASCADE, related_name='vendeur_encaissements', related_query_name="vendeur_encaissement", verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_encaissements', related_query_name="license_encaissement", verbose_name = "license")

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Encaissement'
        verbose_name_plural = 'Encaissements'      
        db_table_comment = "Les encaissements des paiements des clients pour le vendeur"


""" Les reversments aux vendeurs des encaissements des paiements de leurs clients """
class Reversement(MyModelAbstract):

    montant_reversement = models.DecimalField('Montant reversé', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant reversé au vendeur")
    montant_restant = models.DecimalField('Montant restant', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant restant après reversement au vendeur")
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    dernier_reversement = models.OneToOneField('self', models.SET_NULL, related_name="prochain_reversement", verbose_name="dernier reversement", null=True, blank=True)
    encaissement = models.ForeignKey(Encaissement, on_delete=models.CASCADE, related_name='encaissement_reversements', related_query_name="encaissement_reversement", verbose_name = "article")
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_reversements', related_query_name="article_reversement", verbose_name = "article")
    vendeur = models.ForeignKey(Vendeur, on_delete=models.CASCADE, related_name='vendeur_reversements', related_query_name="vendeur_reversement", verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_reversements', related_query_name="license_reversement", verbose_name = "license")

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Reversement'
        verbose_name_plural = 'Reversements'      
        db_table_comment = "Les reversments aux vendeurs des encaissements des paiements de leurs clients"