# accounts/management/commands/seed.py
from datetime import datetime
from django.utils import timezone
from django.utils.timezone import make_aware

import json
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount 
from allauth.account.models import EmailAddress

from core.models import AchatLicense, Configuration, FormatArticle, License, Localite, PartenaireLogistique, Zone

class Command(BaseCommand):
    help = 'Seed the database with initial data'

    def handle(self, *args, **kwargs):
        # Ajouter des utilisateurs
        self.stdout.write("Création des données de Core...")
        
        
        """License"""
        license = License()
        license.save()
        self.stdout.write(f"License {license} créée.")


        """AchatLicense"""
        achat_license = AchatLicense()
        achat_license.debut=timezone.now()
        achat_license.license=license
        achat_license.save()
        self.stdout.write(f"AchatLicense {achat_license} créé.")


        """Configuration"""
        configuration = Configuration()
        configuration.app_nom="ML Ship Africa"
        configuration.adresse="Abidjan"
        configuration.contact="0701020304"
        configuration.email="contact@mlshipafrica.com"
        configuration.enable_option_encaissement=True
        configuration.enable_option_recuperation=True
        configuration.cout_option_recuperation=300
        configuration.monnaie="FCFA"
        configuration.license=license
        configuration.save()
        self.stdout.write(f"Configuration {configuration} créée.")

        """PartenaireLogistique"""
        partenaireLogistiques = [
            {"nom": "Logistique SA", "email": "contact@logistiquesa.com", "contact":"0101020304", "adresse":"Abidjan Yopougon"},
            {"nom": "3000 Logistics", "email": "contact@3000logistics.com", "contact":"0101020304", "adresse":"Abidjan Cocody"},
        ]
        for partenaireLogistique in partenaireLogistiques:
            partenaire_logistique = PartenaireLogistique()
            partenaire_logistique.adresse = partenaireLogistique["adresse"]
            partenaire_logistique.contact = partenaireLogistique["contact"]
            partenaire_logistique.email = partenaireLogistique["email"]
            partenaire_logistique.nom = partenaireLogistique["nom"]
            partenaire_logistique.license = license
            partenaire_logistique.save()
            self.stdout.write(f"PartenaireLogistique {partenaire_logistique} créé.")


        """Zone"""
        zones = [
            {"nom": "Zone A", "is_depart": True, "is_arrivee":True},
            {"nom": "Zone B", "is_depart": False, "is_arrivee":True},
            {"nom": "Zone C", "is_depart": False, "is_arrivee":True},
        ]
        for zone_data in zones:
            zone = Zone()
            zone.nom = zone_data["nom"]
            zone.is_depart = zone_data["is_depart"]
            zone.is_arrivee = zone_data["is_arrivee"]
            zone.license = license
            zone.save()
            self.stdout.write(f"Zone {zone} créée.")


        """Localité"""
        localites = [
            {"nom": "Abidjan", "is_depart": True, "is_arrivee":True, "zone":"Zone A"},
            {"nom": "Yamoussoukro", "is_depart": False, "is_arrivee":True, "zone":"Zone B"},
            {"nom": "Bassam", "is_depart": False, "is_arrivee":True, "zone":"Zone A"},
            {"nom": "Bouaflé", "is_depart": False, "is_arrivee":True, "zone":"Zone B"},
            {"nom": "Bouaké", "is_depart": False, "is_arrivee":True, "zone":"Zone C"},
            {"nom": "Korhogo", "is_depart": False, "is_arrivee":True, "zone":"Zone C"},
        ]
        for localite_data in localites:
            localite = Localite()
            localite.nom = localite_data["nom"]
            localite.is_depart = localite_data["is_depart"]
            localite.is_arrivee = localite_data["is_arrivee"]
            localite_zone = Zone.objects.filter(nom=localite_data["zone"]).first()
            localite.zone = localite_zone
            localite.license = license
            localite.save()
            self.stdout.write(f"Localite {localite} créée.")


        """FormatArticle"""
        formatArticles = [
            {"nom": "Petit", "caracteristique":"taille maximale : 30 x 20 x 20 – poids maximal : 3 kg"},
            {"nom": "Moyen", "caracteristique":"taille maximale : 60 x 40 x 40 – poids maximal : 10 kg"},
            {"nom": "Grand", "caracteristique":"taille maximale : 100 x 50 x 50 – poids maximal : 50 kg"},
            {"nom": "Large", "caracteristique":"taille maximale :  150 x 140 x 120 – poids maximal : 150 kg"},
        ]
        for formatArticle in formatArticles:
            format_article = FormatArticle()
            format_article.nom = formatArticle["nom"]
            format_article.caracteristique = localite_data["caracteristique"]
            format_article.license = license
            format_article.save()
            self.stdout.write(f"FormatArticle {format_article} créé.")


        self.stdout.write(self.style.SUCCESS("Creating Core done with success."))
