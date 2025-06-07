# accounts/management/commands/seed.py
from datetime import datetime
from django.utils import timezone
from django.utils.timezone import make_aware

import json
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from allauth.account.models import EmailAddress

from core.models import AchatLicense, Configuration, FormatArticle, License, Localite, PartenaireLogistique, Zone
from management.models import ProfilStaff, Tarification, Vendeur
from django.db import transaction

from mlshipafrica.mlshipafrica.enums import TypeProfilStaffChoice

class Command(BaseCommand):
    help = 'Seed the database with initial data'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        # Ajouter des utilisateurs
        self.stdout.write("Création des données de Management...")
        
        date_format = '%Y-%m-%d %H:%M:%S'

        license = License.objects.filter().first()
        configuration = Configuration.objects.filter().first()

        users = [
            {"username": "demo1@example.com", "email": "demo1@example.com", "password": "demo123", "role": "VENDEUR"},
            {"username": "demo2@example.com", "email": "demo2@example.com", "password": "demo123", "role": "VENDEUR"},
            {"username": "agent@example.com", "email": "agent@example.com", "password": "demo123", "is_staff": True, "role": "AGENT"},
            {"username": "comptable@example.com", "email": "comptable@example.com", "password": "demo123", "is_staff": True, "role": "COMPTALE"},
            {"username": "administrateur@example.com", "email": "administrateur@example.com", "password": "demo123", "is_staff": True, "role": "ADMINISTRATEUR"},
            {"username": "admin@example.com", "email": "admin@example.com", "password": "12345", "is_staff": True, "is_superuser": True, "role": "SUPER"},
        ]

        email_adresses = [
            {"email": "demo1@example.com", "verified": 1, "primary":1},
            {"email": "demo2@example.com", "verified": 0, "primary":1},
            {"email": "agent@example.com", "verified": 1, "primary":1},
            {"email": "comptable@example.com", "verified": 1, "primary":1},
            {"email": "administrateur@example.com", "verified": 1, "primary":1},
            {"email": "admin@example.com", "verified": 1, "primary":1},
        ]

        vendeurs = [
            {"nom_store": "demo1", "email": "demo1@example.com"},
            {"nom_store": "demo2", "email": "demo2@example.com"},
        ]


        with transaction.atomic():

          """User"""
          for user_data in users:
              if not User.objects.filter(username=user_data['username']).exists():
                  user = User.objects.create_user(
                      username=user_data['username'],
                      email=user_data['email'],
                      password=user_data['password'],
                  )
                  if 'is_staff' in user_data:
                      user.is_staff = user_data['is_staff']
                  if 'is_superuser' in user_data:
                      user.is_superuser = user_data['is_superuser']

                  # Groupe
                  is_group_exist = Group.objects.filter(name=user_data['role']).exists()
                  if is_group_exist == False:
                    Group.objects.create(name=user_data['role'])
                  group = Group.objects.get(name=user_data['role'])
                  
                  user.groups.add(group)

                  user.save()
                  self.stdout.write(f"Utilisateur {user.username} créé.")
              else:
                  user = User.objects.filter(username=user_data['username']).first()
                  self.stdout.write(f"Utilisateur {user_data['username']} existe déjà.")

              for email_data in email_adresses:
                  if not EmailAddress.objects.filter(email=email_data['email']).exists() and email_data['email'] == user_data['email']:
                      email = EmailAddress.objects.create(
                          email=email_data['email'],
                          verified=email_data['verified'],
                          primary=email_data['primary'],
                          user=user,
                      )
                      email.save()
                      self.stdout.write(f"Email {email.email} créé.")
                  elif email_data['email'] == user_data['email']:
                      self.stdout.write(f"Email {email_data['email']} existe déjà.")

              if 'is_staff' in user_data:
                    if not ProfilStaff.objects.filter(user=user).exists():
                        profil_staff = ProfilStaff.objects.create(
                                  role_profil=TypeProfilStaffChoice.values[TypeProfilStaffChoice.names.index(user_data['role'])],
                                  user=user,
                                  license=license,
                              )
                        profil_staff.save()
                        self.stdout.write(f"Profil staff {profil_staff} créé.")
                    else:
                        self.stdout.write(f"Profil staff {user_data['email']} existe déjà.")

              if user_data['role'] == "VENDEUR":
                  for vendeur_data in vendeurs:
                    if not Vendeur.objects.filter(user=user).exists() and vendeur_data['email'] == user_data['email']:
                        vendeur = Vendeur.objects.create(
                                  nom_store=vendeur_data['nom_store'],
                                  user=user,
                                  license=license,
                              )
                        vendeur.save()
                        self.stdout.write(f"Vendeur {vendeur} créé.")
                    elif vendeur_data['email'] == user_data['email']:
                        self.stdout.write(f"vendeur {vendeur_data['nom_store']} existe déjà.")


          """Tarification"""
          tarifications = [
              {"format": "Petit", "localite_depart":"Abidjan", "localite_arrivee":"Abidjan", "partenaire_logistique":"Logistique SA", "montant_frais":1500, "cout_option_recuperation":300, "taux_option_encaissement":8},
              {"format": "Petit", "localite_depart":"Abidjan", "localite_arrivee":"Abidjan", "partenaire_logistique":"3000 Logistics", "montant_frais":2000, "cout_option_recuperation":300, "taux_option_encaissement":8},
              {"format": "Petit", "localite_depart":"Abidjan", "localite_arrivee":"Yamoussoukro", "partenaire_logistique":"Logistique SA", "montant_frais":2500, "cout_option_recuperation":300, "taux_option_encaissement":8},
              {"format": "Petit", "localite_depart":"Abidjan", "localite_arrivee":"Bouaké", "partenaire_logistique":"Logistique SA", "montant_frais":3000, "cout_option_recuperation":300, "taux_option_encaissement":8},
          ]
          for tarification_data in tarifications:
              tarification = Tarification()
              tarification.montant_frais = tarification_data["montant_frais"]
              tarification.cout_option_recuperation = tarification_data["cout_option_recuperation"]
              tarification.taux_option_encaissement = tarification_data["taux_option_encaissement"]
              tarification.partenaire_logistique = PartenaireLogistique.objects.filter(nom=tarification_data["partenaire_logistique"]).first()
              tarification.format_article = FormatArticle.objects.filter(nom=tarification_data["format"]).first()
              tarification.localite_depart = Localite.objects.filter(nom=tarification_data["localite_depart"]).first()
              if tarification.localite_depart:
                tarification.zone_depart = tarification.localite_depart.zone
              tarification.localite_arrivee = Localite.objects.filter(nom=tarification_data["localite_arrivee"]).first()
              if tarification.localite_arrivee:
                tarification.zone_arrivee = tarification.localite_arrivee.zone
              tarification.config = configuration
              tarification.license = configuration.license if configuration else license
              tarification.save()
              self.stdout.write(f"Tarification {tarification} créé.")


          self.stdout.write(self.style.SUCCESS("Creating Management done with success."))

