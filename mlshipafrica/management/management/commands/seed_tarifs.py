from django.core.management.base import BaseCommand
from core.models import Zone, Localite, FormatArticle, Configuration, License
from management.models import Tarification

class Command(BaseCommand):
    help = "Seed zones, localites, formats and tarifs"

    def handle(self, *args, **kwargs):
        license = License.objects.first()  # à adapter selon ta logique
        config = Configuration.objects.first()  # à adapter aussi

        # === Zones et localités ===
        zone_data = {
            "Zone 1": ["Aboisso", "Agboville", "Azaguié", "Bonoua", "Dabou", "Grand-Bassam", "Jacqueville", "Sikensi"],
            "Zone 2": ["Bouaké", "Abengourou", "Daloa", "Gagnoa", "Korhogo", "Man", "San-Pedro", "Yamoussoukro"],
            "Zone 3": [
                "Divo", "Tiassalé", "N'Douci", "Adzopé", "Agnibilékrou", "Agou", "Akoupé", "Bangolo", "Biankouman", 
                "Bondoukou", "Bonon", "Bouaflé", "Bouna", "Danané", "Djebonoua", "Domaine SOGB", "Fresco", 
                "Grand Lahou", "Hermankono", "Irobo", "Koun Fao", "Lakota", "Logoualé", "Mahapleu", 
                "Sassandra", "Séguéla", "Tanda", "Tiebissou", "Tieningboué", "Touba", "Toupah", "Vavoua", 
                "Sangouiné", "Aniassué"
            ],
            "Zone 4": [
                "Adiaké", "Andé", "Arrah", "Bazra-Nattis", "Beoumi", "Bongouanou", "Boundiali", "Daoukro", 
                "Diégonefla", "Dimbokro", "Djekanou", "Doropo", "Duékoué", "Ferkessedougou", "Gabiadji", "Gouméré", 
                "Grand-Béréby", "Guézon", "Guiberoua", "Issia", "Katiola", "Kotobi", "Kouto", "Maféré", "Mankono", 
                "Méagui", "Niakara", "Odiénné", "Ouangolodougou", "Oumé", "Oupoyo", "Sakassou", "Sinématiali", 
                "Sinfra", "Soubré", "Tafiré", "Tingréla", "Toulépleu", "Toumodi", "Yabayo", "Zouan-Houien", 
                "Zuénoula", "Tabou", "Guiglo", "Blolequin"
            ],
            "Zone 5": [
                "Transua", "Dianra", "Alépé", "Assuéfry", "Bettie", "Bocanda", "Buyo", "Dabakala", 
                "Grand-Zattry", "Guitry", "Kani", "M'Bahiakro", "M'batto", "Ouellé", "Ouragahio", "Saioua", 
                "Sandégué", "Sirasso", "Yakassé Attobrou", "Zoukougbeu"
            ],
        }

        zone_instances = {}
        for zone_nom, localites in zone_data.items():
            zone = Zone.objects.create(nom=zone_nom, is_depart=False, is_arrivee=True, license=license)
            self.stdout.write(self.style.SUCCESS(f"Zone '{zone.nom}' créée."))
            zone_instances[zone_nom] = zone

            for ville in localites:
                localite = Localite.objects.create(
                    nom=ville,
                    is_depart=False,
                    is_arrivee=True,
                    zone=zone,
                    license=license
                )
                self.stdout.write(f"  Localité '{ville}' créée dans la {zone.nom}.")

        # Abidjan
        abidjan_zone = Zone.objects.create(nom="Zone A", is_depart=True, is_arrivee=True, license=license)
        abidjan = Localite.objects.create(
            nom="Abidjan",
            is_depart=True,
            is_arrivee=True,
            zone=abidjan_zone,
            license=license
        )
        self.stdout.write(self.style.SUCCESS("Zone A et localité Abidjan créées."))

        # === Formats d'article ===
        formats = [
            ("Petit", "taille maximale : 30 x 20 x 20 – poids maximal : 3 kg"),
            ("Moyen", "taille maximale : 60 x 40 x 40 – poids maximal : 10 kg"),
            ("Grand", "taille maximale : 100 x 50 x 50 – poids maximal : 50 kg"),
        ]
        format_instances = {}
        for nom, desc in formats:
            fmt = FormatArticle.objects.create(nom=nom, caracteristique=desc, license=license)
            format_instances[nom] = fmt
            self.stdout.write(self.style.SUCCESS(f"Format '{nom}' créé."))

        # === Tarification ===
        tarifs = {
            "Zone 1": {"Petit": 3234, "Moyen": 4851, "Grand": 4800},
            "Zone 2": {"Petit": 3381, "Moyen": 4998, "Grand": 20250},
            "Zone 3": {"Petit": 3381, "Moyen": 5032, "Grand": 20250},
            "Zone 4": {"Petit": 3385, "Moyen": 3400, "Grand": 22500},
            "Zone 5": {"Petit": 4800, "Moyen": 6975, "Grand": 27540},
        }

        for zone_nom, formats_data in tarifs.items():
            for format_nom, montant in formats_data.items():
                Tarification.objects.create(
                    localite_depart=abidjan,
                    localite_arrivee=None,
                    zone_depart=abidjan.zone,
                    zone_arrivee=zone_instances[zone_nom],
                    format_article=format_instances[format_nom],
                    montant_frais=montant,
                    config=config,
                    license=license,
                )
                self.stdout.write(f"Tarif Abidjan → {zone_nom} [{format_nom}] = {montant} FCFA")

        self.stdout.write(self.style.SUCCESS("Seed terminé avec succès."))
