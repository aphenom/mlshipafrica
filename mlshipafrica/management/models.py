from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django_currentuser.middleware import (
    get_current_user, get_current_authenticated_user)
from tinymce.models import HTMLField

from core.models import Configuration, FormatArticle, License, Localite, PartenaireLogistique, Zone
from mlshipafrica.utils import CodeGenerator

from mlshipafrica.enums import STATUT_TRAITEMENT_COMMENTAIRES, STATUT_TRAITEMENT_ICONES, STATUT_VENDEUR_COULEURS, DureeActiviteChoice, FrequenceEnvoiChoice, NombreColisSemaineChoice, ProduitsChoice, StatutTraitement, STATUT_TRAITEMENT_COULEURS, StatutVendeur, TypePieceIdentiteChoice, TypeProfilStaffChoice, TypeVendeurChoice

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models import Q

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


""" Vendeur pour lequel on gere la livraison """
class ProfilStaff(MyModelAbstract):

    email = models.CharField("Email", max_length=100, null=True, blank=True)
    numero_contact = PhoneNumberField("Numéro", null=True, blank=True)
    observation = models.CharField("Observation", max_length=255, null=True, blank=True)
    role_profil = models.CharField("Type profil", max_length=25, choices=TypeProfilStaffChoice.choices, null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_profil_staff', verbose_name = "profil_staff")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_profils_staffs', related_query_name="license_profil_staff", verbose_name = "license")

    def __str__(self):
        return '{}'.format(self.user)

    class Meta:
        verbose_name = 'Profil Staff'
        verbose_name_plural = 'Profils Staff'      
        db_table_comment = "Les membre de l'équipe de gestion"

    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''                      
        if self.code and self.user.username != self.code:
            self.user.username = self.code
        self.user.save()
        return super(ProfilStaff, self).save(*args, **kwargs)        


""" Vendeur pour lequel on gere la livraison """
class Vendeur(MyModelAbstract):

    nom_entreprise = models.CharField("Nom entreprise", max_length=100, null=True, blank=True)
    immatriculation = models.CharField("RCCM / Numéro d'immatriculation", max_length=100, null=True, blank=True)
    nom_gerant = models.CharField("Nom gérant", max_length=255, null=True, blank=True)
    nom_store = models.CharField("Nom boutique / store", max_length=100)
    email = models.CharField("Email", max_length=100, null=True, blank=True)
    adresse = models.CharField("Adresse", max_length=255, null=True, blank=True)
    logo = models.ImageField("Logo", upload_to='uploaded_media/management/logos_vendeur/', null=True, blank=True)
    nom_contact = models.CharField("Nom", max_length=100, null=True, blank=True)
    prenom_contact = models.CharField("Prénom(s)", max_length=255, null=True, blank=True)
    fonction_contact = models.CharField("Fonction", max_length=255, null=True, blank=True)
    numero_contact = PhoneNumberField("Numéro", null=True, blank=True)
    email_contact = models.CharField("Email", max_length=100, null=True, blank=True)
    numero_sms = PhoneNumberField("Numéro notification sms", null=True, blank=True)
    email_notification = models.CharField("Email notification", max_length=100, null=True, blank=True)
    etat_approbation = models.BooleanField('Etat approbation', default=False)
    date_approbation = models.DateTimeField('Date validation', null=True, blank=True)
    approbation_par = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name='approbation_vendeurs', related_query_name="approbation_vendeur", verbose_name = "approuvé par")
    etat_importation = models.BooleanField('Etat importation', default=False)
    date_approbation = models.DateTimeField('Date importation', null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_vendeur', verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_vendeurs', related_query_name="license_vendeur", verbose_name = "license")

    type_vendeur = models.CharField("Type vendeur", max_length=25, choices=TypeVendeurChoice.choices, null=True, blank=True)

    # Upload documents
    type_piece_identite = models.CharField("Type pièce d’identité", max_length=25, choices=TypePieceIdentiteChoice.choices, null=True, blank=True)
    piece_identite = models.FileField("Pièce d’identité", upload_to='uploaded_media/management/documents_vendeur/', null=True, blank=True)
    permis = models.FileField("Permis de conduire", upload_to='uploaded_media/management/documents_vendeur/', null=True, blank=True)
    passeport = models.FileField("Passeport", upload_to='uploaded_media/management/documents_vendeur/', null=True, blank=True)
    dfe = models.FileField("Déclaration Fiscale d’Exercice (DFE)", upload_to='uploaded_media/management/documents_vendeur/', null=True, blank=True)
    rccm = models.FileField("RCCM", upload_to='uploaded_media/management/documents_vendeur/', null=True, blank=True)

    # Activité commerciale
    duree_activite = models.CharField("Ancienneté", max_length=20, choices=DureeActiviteChoice.choices, null=True, blank=True)

    plateformes = models.JSONField("Plateformes utilisées", blank=True, null=True)
    # plateformes_facebook = models.BooleanField("Facebook / Instagram", default=False)
    # plateformes_whatsapp = models.BooleanField("WhatsApp", default=False)
    # plateformes_ecommerce = models.BooleanField("Shopify / YouCan / Storeino", default=False)
    plateformes_autre = models.CharField("Autres plateformes utilisées", max_length=100, null=True, blank=True)

    type_produits_vendus = models.CharField("Type de produits vendus", max_length=255, null=True, blank=True)

    # Produits à expédier
    produits = models.JSONField("Produits à expédier", blank=True, null=True)
    # produits_cosmetiques = models.BooleanField("Cosmétiques", default=False)
    # produits_mode = models.BooleanField("Mode / Accessoires", default=False)
    # produits_sante = models.BooleanField("Santé / Bien-être", default=False)
    # produits_high_tech = models.BooleanField("High-tech", default=False)
    # produits_maison = models.BooleanField("Maison / Cuisine", default=False)
    produits_autre = models.CharField("Autre type de produit", max_length=100, null=True, blank=True)

    # Nature colis
    nature_colis = models.JSONField("Nature des colis", blank=True, null=True)
    # nature_petit = models.BooleanField("Petit (moins de 2kg)", default=False)
    # nature_moyen = models.BooleanField("Moyen (entre 3 - 5kg)", default=False)
    # nature_gros = models.BooleanField("Gros (plus de 10kg)", default=False)
    # nature_large = models.BooleanField("Large (plus de 50kg)", default=False)

    # Fréquence et volume
    frequence_envoi = models.CharField("Fréquence d’envoi", max_length=20, choices=FrequenceEnvoiChoice.choices, null=True, blank=True)
    nombre_colis_semaine = models.CharField("Nombre moyen de colis livré par semaine", max_length=20, choices=NombreColisSemaineChoice.choices, null=True, blank=True)

    # Paiement à la livraison (COD)
    cod_actif = models.BooleanField("Souhaitez-vous activer le paiement à la livraison ?", default=False)
    collecte_par_mlship = models.BooleanField("ML SHIP collecte et reverse l’argent ?", default=False)

    def __str__(self):
        return '{}'.format(self.nom_store)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_etat_approbation = self.etat_approbation

    class Meta:
        verbose_name = 'Vendeur'
        verbose_name_plural = 'Vendeurs'      
        db_table_comment = "Les Vendeurs pour lesquels il faut gérer la livraison"
        ordering = ['-date_creation']

    def get_statut_vendeur(self):
        if self.etat_suppression is False:
            if self.etat_approbation is True:
                if self.etat_validation is True:
                    return StatutVendeur.ACTIF
                else:
                    return StatutVendeur.INACTIF
            else:
                return StatutVendeur.ATTENTE_APPROBATION
        else:
            return StatutVendeur.SUPPRIME

    def get_statut_vendeur_couleur(self):
        return STATUT_VENDEUR_COULEURS.get(self.get_statut_vendeur(), 'warning')  # couleur par défaut si non trouvée


    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''                      
        if self.code and self.user.username != self.code:
            self.user.username = self.code
        if self.nom_store and self.user.last_name != self.nom_store:
            self.user.last_name = self.nom_store
        self.user.save()
        if self.etat_approbation != self._init_etat_approbation:
            if self.etat_approbation == True:
                self.date_approbation = timezone.now() 
                self.approbation_par = get_current_user()
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
    localite_depart = models.ForeignKey(Localite, models.SET_NULL, null=True, blank=True, related_name='localite_departtarifications', related_query_name="localite_departtarification", verbose_name = "localité départ")
    localite_arrivee = models.ForeignKey(Localite, models.SET_NULL, null=True, blank=True, related_name='localite_arriveetarifications', related_query_name="localite_arriveetarification", verbose_name = "localité arrivée")
    format_article = models.ForeignKey(FormatArticle, models.SET_NULL, null=True, blank=True, related_name='format_articletarifications', related_query_name="format_articletarification", verbose_name = "format article")
    vendeur = models.ForeignKey(Vendeur, models.SET_NULL, null=True, blank=True, related_name='vendeur_tarifications', related_query_name="vendeur_tarification", verbose_name = "vendeur")
    config = models.ForeignKey(Configuration, models.SET_NULL, null=True, blank=True, related_name='config_tarifications', related_query_name="config_tarification", verbose_name = "Configuration")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_tarifications', related_query_name="license_tarification", verbose_name = "license")

    """ prendre les valeurs globales des configs lorsque la config est definie et pas sur le tarif""" 
    
    def get_final_cout_option_recuperation(self):
        cout = self.cout_option_recuperation if self.cout_option_recuperation else self.config.cout_option_recuperation
        return cout

    def get_final_cout_option_encaissement(self):
        cout = self.cout_option_encaissement if self.cout_option_encaissement else self.config.cout_option_encaissement
        return cout

    def get_final_taux_option_recuperation(self):
        taux = self.taux_option_recuperation if self.taux_option_recuperation else self.config.taux_option_recuperation
        return taux

    def get_final_taux_option_encaissement(self):
        taux = self.taux_option_encaissement if self.taux_option_encaissement else self.config.taux_option_encaissement
        return taux
    
    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Tarification'
        verbose_name_plural = 'Tarifications'      
        db_table_comment = "Les tarifs définis selon les critères souhaités"
        ordering = ['-date_creation']


""" Les articles répresentant les colis à livrer """
class Article(MyModelAbstract):

    code_tracking = models.CharField('Code tracking', max_length=25, null=True, blank=True, db_comment="Code unique auprès du prestatire du colis permettant de le suivre")
    
    valeur = models.DecimalField('Valeur unitaire', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    designation = models.CharField("Désignation", max_length=100, null=True, blank=True)
    quantite = models.PositiveSmallIntegerField(default=1, null=True, blank=True, verbose_name = "Quantité")
    valeur_totale = models.DecimalField('Valeur totale', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout global selon la quantité")
    produits = models.JSONField("Type de produits", blank=True, null=True)
    produits_autre = models.CharField("Autre type de produit", max_length=100, null=True, blank=True)
    
    
    montant_frais = models.DecimalField('Montant frais', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis")
    is_option_recuperation = models.BooleanField('état option récupération du colis', default=False, db_comment="Possibilité ou non de récupérer le colis directement chez le vendeur")
    is_option_encaissement = models.BooleanField('état option encaissement du client', default=False, db_comment="Possibilité ou non d'encaisser le paiement du colis directement chez le client")
    cout_option_recuperation = models.DecimalField('cout fixe option récupération colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option de récupération au cas où il serait uniforme pour chaque colis (= self+%valeur)")
    taux_option_recuperation = models.DecimalField('taux option récupération colis', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option de récupération (= %valeur)")
    cout_option_encaissement = models.DecimalField('cout fixe option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout fixe de l'option d'encaissement au cas où il serait uniforme pour chaque colis (= self+%valeur)")
    taux_option_encaissement = models.DecimalField('taux option encaissement client', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Taux appliqué sur chaque colis pour l'option d'encaissement (= %valeur)")
    montant_total_frais = models.DecimalField('Montant total frais', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout total des frais associé au colis (=montant_frais+cout_option_recuperation+cout_option_encaissement)")
    montant_a_reverser = models.DecimalField('Montant à reverser lors de collecte de fond', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Cout total retranché des frais associé au colis lors des collecte de fond (=valeur_totale-(montant_frais+cout_option_recuperation+cout_option_encaissement))")

    nom_destinataire = models.CharField("Nom", max_length=100, null=True, blank=True)
    prenom_destinataire = models.CharField("Prénom(s)", max_length=255, null=True, blank=True)
    numero_principal_destinataire = PhoneNumberField("Numéro principal", null=True, blank=True)
    numero_secondaire_destinataire = PhoneNumberField("Numéro secondaire", null=True, blank=True)
    adresse_destinataire = models.CharField("Adresse", max_length=255, null=True, blank=True)
    
    etat_importation = models.BooleanField('Etat importation', default=False)
    date_approbation = models.DateTimeField('Date importation', null=True, blank=True)

    statut_traitement = models.CharField(max_length=25, choices=StatutTraitement.choices,default=StatutTraitement.BROUILLON, null=True, blank=True)
    etat_encaissement = models.BooleanField('état encaissement client', default=False)
    etat_reglement = models.BooleanField('état reglement vendeur', default=False)
    etat_reversement = models.BooleanField('état reversement encaissement', default=False)

    tarification = models.ForeignKey(Tarification, models.SET_NULL, null=True, blank=True, related_name='tarification_articles', related_query_name="tarification_article", verbose_name = "partenaire logistique")
    partenaire_logistique = models.ForeignKey(PartenaireLogistique, models.SET_NULL, null=True, blank=True, related_name='partenaire_logistique_articles', related_query_name="partenaire_logistique_article", verbose_name = "partenaire logistique")
    zone_depart = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_depart_articles', related_query_name="zone_depart_article", verbose_name = "zone départ")
    zone_arrivee = models.ForeignKey(Zone, models.SET_NULL, null=True, blank=True, related_name='zone_arrivee_articles', related_query_name="zone_arrivee_article", verbose_name = "zone arrivée")
    localite_depart = models.ForeignKey(Localite, models.SET_NULL, null=True, blank=True, related_name='localite_depart_articles', related_query_name="localite_depart_article", verbose_name = "localité départ")
    localite_arrivee = models.ForeignKey(Localite, models.SET_NULL, null=True, blank=True, related_name='localite_arrivee_articles', related_query_name="localite_arrivee_article", verbose_name = "localité destination")
    format_article = models.ForeignKey(FormatArticle, models.SET_NULL, null=True, blank=True, related_name='format_article_articles', related_query_name="format_article_article", verbose_name = "format article")
    vendeur = models.ForeignKey(Vendeur, models.SET_NULL, null=True, blank=True, related_name='vendeur_articles', related_query_name="vendeur_article", verbose_name = "vendeur")
    config = models.ForeignKey(Configuration, models.SET_NULL, null=True, blank=True, related_name='config_articles', related_query_name="config_article", verbose_name = "Configuration")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_articles', related_query_name="license_article", verbose_name = "license")
    
    #last_histo_article
    #last_reglement_article

    def __str__(self):
        return '{}'.format(self.code)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_statut_traitement = self.statut_traitement

    def get_statut_traitement_couleur(self):
        return STATUT_TRAITEMENT_COULEURS.get(self.statut_traitement, 'black')  # couleur par défaut si non trouvée
 
    def get_statut_traitement_commentaire(self):
        return STATUT_TRAITEMENT_COMMENTAIRES.get(self.statut_traitement, '')  # commentaire par défaut si non trouvée
 
    def get_statut_traitement_icone(self):
        return STATUT_TRAITEMENT_ICONES.get(self.statut_traitement, '')  # icon par défaut si non trouvée
 
    def get_produits_display(self):
        if not self.produits:
            return ""
        
        produits = [
            f'{ProduitsChoice(choix).label}'
            for choix in self.produits
            if choix != ProduitsChoice.AUTRE and choix in ProduitsChoice.values
        ]
        if self.produits_autre:
            produits.append(
                self.produits_autre
            )
            
        return ", ".join(produits)
    
    def get_last_historique(self):
        return self.article_historiquearticles.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation").first()

    def get_last_reglement(self):
        return self.article_reglementarticles.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation").first()

    def get_last_encaissement(self):
        return self.article_encaissements.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation").first()

    def get_last_reversement(self):
        return self.article_reversements.filter(etat_validation=True, etat_suppression=False).order_by("-date_creation").first()
  

    class Meta:
        verbose_name = 'Article'
        verbose_name_plural = 'Articles'      
        db_table_comment = "Les articles répresentant les colis à livrer"
        ordering = ['-date_creation']

    def save(self, *args, **kwargs):
        if not self.id or not self.tarification:
            query = Q(localite_depart=self.localite_depart) | Q(localite_depart=None)
            query &= Q(localite_arrivee=self.localite_arrivee) | Q(localite_arrivee=None)
            query &= Q(zone_depart=self.localite_depart.zone) | Q(zone_depart=None)
            query &= Q(zone_arrivee=self.localite_arrivee.zone) | Q(zone_arrivee=None)
            query &= Q(format_article=self.format_article) | Q(format_article=None)
            query &= Q(vendeur=self.vendeur) | Q(vendeur=None)
            query &= Q(etat_validation=True)
            query &= Q(etat_suppression=False)
            query &= Q(license=self.license)

            # print(self.tarification)

            # Exécutez la requête pour récupérer les paramètres de tarification
            tarification = Tarification.objects.filter(query).order_by("-vendeur", "-format_article", "-localite_arrivee", "-localite_arrivee", "-zone_depart", "-zone_arrivee").first()
            tarification_taux_option_recuperation = tarification.get_final_taux_option_recuperation() or 0
            tarification_taux_option_encaissement = tarification.get_final_taux_option_encaissement() or 0
            tarification_cout_option_recuperation = tarification.get_final_cout_option_recuperation()
            tarification_cout_option_encaissement = tarification.get_final_cout_option_encaissement()
            
            self.valeur_totale = self.valeur_totale if self.valeur_totale and self.valeur_totale > 0 else self.valeur*self.quantite
           
            if self.statut_traitement != StatutTraitement.BROUILLON:
                self.tarification = tarification
           
            self.montant_frais = tarification.montant_frais
            self.taux_option_recuperation = tarification_taux_option_recuperation if self.is_option_recuperation is True else None
            self.taux_option_encaissement = tarification_taux_option_encaissement if self.is_option_encaissement is True else None
            
            if self.is_option_recuperation is True:
                self.cout_option_recuperation = tarification_cout_option_recuperation if tarification_cout_option_recuperation else round((self.valeur_totale*tarification_taux_option_recuperation)/100,0)
            else:
                self.cout_option_recuperation = None

            if self.is_option_encaissement is True:
                self.cout_option_encaissement = tarification_cout_option_encaissement if tarification_cout_option_encaissement else round((self.valeur_totale*tarification_taux_option_encaissement)/100,0)
            else:
                self.cout_option_encaissement = None

            self.montant_total_frais = self.montant_frais + (self.cout_option_recuperation if self.cout_option_recuperation else 0) + (self.cout_option_encaissement if self.cout_option_encaissement else 0)
            
            if self.is_option_encaissement is True:
                self.montant_a_reverser = self.valeur_totale - self.montant_total_frais
        
        if self.statut_traitement != self._init_statut_traitement and get_current_user().is_staff is False: #, StatutTraitement.EN_ATTENTE_DEPOT, StatutTraitement.EN_ATTENTE_RAMASSAGE):
            histo_article = HistoriqueArticle()
            histo_article.article = self
            histo_article.date = timezone.now()
            histo_article.statut_traitement = self.statut_traitement
            histo_article.license = self.license
            histo_article.dernier_historique_article = self.get_last_historique()
            histo_article.save()

        return super().save(*args, **kwargs)
    

""" Historisations des mouvements des articles répresentant les colis pendant le traitement"""
class HistoriqueArticle(MyModelAbstract):

    statut_traitement = models.CharField(max_length=25, choices=StatutTraitement.choices,default=StatutTraitement.BROUILLON, null=True, blank=True)
    date = models.DateTimeField('Date historique', null=True, blank=True)
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    dernier_historique_article = models.ForeignKey('self', on_delete=models.CASCADE, related_name="prochain_historiques", related_query_name="prochain_historique", verbose_name="dernier historique article", null=True, blank=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_historiquearticles', related_query_name="article_historiquearticle", verbose_name = "article")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_historiquearticles', related_query_name="license_historiquearticle", verbose_name = "license")

    def get_statut_traitement_couleur(self):
        return STATUT_TRAITEMENT_COULEURS.get(self.statut_traitement, 'black')  # couleur par défaut si non trouvée
    
    def get_statut_traitement_commentaire(self):
        return STATUT_TRAITEMENT_COMMENTAIRES.get(self.statut_traitement, '') # if self.commentaire is None or self.commentaire == '' else self.commentaire  # commentaire par défaut si non trouvée
 
    def get_statut_traitement_icone(self):
        return STATUT_TRAITEMENT_ICONES.get(self.statut_traitement, '')  # icon par défaut si non trouvée
     
    def __str__(self):
        return '{} {}'.format(self.article, self.statut_traitement)

    class Meta:
        verbose_name = 'Historique Article'
        verbose_name_plural = 'Historiques Articles'      
        db_table_comment = "Historisations des mouvements des articles répresentant les colis pendant le traitement"


""" Les reglements des frais de livraison du vendeur """
class ReglementArticle(MyModelAbstract):

    montant_reglement = models.DecimalField('Montant réglé', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant réglé par le vendeur")
    montant_reduction = models.DecimalField('Montant réduction', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant réduction appliqué à ce règlement")
    montant_restant = models.DecimalField('Montant restant', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant restant après ce règlement")
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    date = models.DateTimeField('Date reglement', null=True, blank=True)
    reference = models.CharField('Référence reglement', max_length=255, null=True, blank=True)
    dernier_reglement_article = models.ForeignKey('self', on_delete=models.CASCADE, related_name="prochain_reglement", related_query_name="prochain_reglements", verbose_name="dernier reglement article", null=True, blank=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_reglementarticles', related_query_name="article_reglementarticle", verbose_name = "article")
    vendeur = models.ForeignKey(Vendeur, on_delete=models.CASCADE, related_name='vendeur_reglementarticles', related_query_name="vendeur_reglementarticle", verbose_name = "vendeur")
    license = models.ForeignKey(License, models.SET_NULL, null=True, blank=True, related_name='license_reglementarticles', related_query_name="license_reglementarticle", verbose_name = "license")

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Reglement Article'
        verbose_name_plural = 'Reglement Articles'      
        db_table_comment = "Les reglements des frais de livraison du vendeur"

    def save(self, *args, **kwargs):
        if not self.id:
            montant_initial = self.article.get_last_reglement().montant_restant if self.article.get_last_reglement() and self.article.get_last_reglement().montant_restant else self.article.montant_total_frais
            self.montant_restant = int(montant_initial) - int(self.montant_reduction) - int(self.montant_reglement)
            self.vendeur = self.article.vendeur
            self.license = self.article.license
            self.dernier_reglement_article = self.article.get_last_reglement()
            if self.montant_restant == 0:
                self.article.etat_reglement = True
                self.article.save()
        return super().save(*args, **kwargs)

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

    def save(self, *args, **kwargs):
        if not self.id:
            self.montant = self.article.valeur_totale
            self.vendeur = self.article.vendeur
            self.license = self.article.license
        return super().save(*args, **kwargs)

""" Les reversments aux vendeurs des encaissements des paiements de leurs clients """
class Reversement(MyModelAbstract):

    montant_reversement = models.DecimalField('Montant reversé', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant reversé au vendeur")
    montant_restant = models.DecimalField('Montant restant', max_digits=10, decimal_places=2, null=True, blank=True, db_comment="Montant restant après reversement au vendeur")
    commentaire  = models.TextField('Commentaire', null=True, blank=True)
    date = models.DateTimeField('Date reversement', null=True, blank=True)
    reference = models.CharField('Référence reversement', max_length=255, null=True, blank=True)
    dernier_reversement = models.ForeignKey('self', on_delete=models.CASCADE, related_name="prochain_reversement", related_query_name="prochain_reversements", verbose_name="dernier reversement", null=True, blank=True)
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

    def save(self, *args, **kwargs):
        if not self.id and self.article.statut_traitement == StatutTraitement.LIVRE_PAYE:
            montant_initial = self.article.get_last_reversement().montant_restant if self.article.get_last_reversement() and self.article.get_last_reversement().montant_restant else self.encaissement.montant
            self.montant_restant = int(montant_initial) - int(self.montant_reversement)
            self.vendeur = self.article.vendeur
            self.license = self.article.license
            self.dernier_reglement_article = self.article.get_last_reglement()
            if self.montant_restant == 0:
                 # historique
                histo_article = HistoriqueArticle()
                histo_article.article = self.article
                histo_article.date = timezone.now() if self.date < self.article.get_last_historique().date.strftime("%Y-%m-%d %H:%M") else self.date
                histo_article.statut_traitement = StatutTraitement.REVERSE
                histo_article.license = self.license
                histo_article.dernier_historique_article = self.article.get_last_historique()
                histo_article.save()
                #article
                self.article.statut_traitement = StatutTraitement.REVERSE
                self.article.etat_reversement = True
                self.article.save()
        return super().save(*args, **kwargs)        