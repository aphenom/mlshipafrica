"""
Applique la grille officielle ML COD Intérieur : zones 2 à 6, 275 localités, délais,
tarifs ML (Petit / Moyen) et coût partenaire interne.

    python manage.py appliquer_grille_ml_cod --dry-run      # montre ce qui va changer, n'écrit rien
    python manage.py appliquer_grille_ml_cod                # applique (dans une transaction)
    python manage.py appliquer_grille_ml_cod --license LIC26ABCD10
    python manage.py appliquer_grille_ml_cod --couts /home/mlcod/prive/couts_partenaire.json

Le fichier de coûts partenaire reste HORS du dépôt Git (donnée interne). Sans --couts, les coûts
déjà saisis ne sont pas modifiés.

Ce que fait la commande, pour chaque license :
  1. Zones : crée ou met à jour « Zone 2 » à « Zone 6 » (numéro + délais). Les anciennes zones
     d'arrivée sans numéro (ancienne numérotation 1 à 5) sont renommées « Ancienne … » et désactivées.
     Rien n'est supprimé : les colis déjà créés gardent leurs références.
  2. Localités : chaque localité de la liste officielle est rattachée à sa zone (recherche sans
     accents ni tirets ; créée si absente). Les localités d'arrivée absentes de la liste officielle
     ne sont plus proposées (is_arrivee = False) ; les localités de départ (Abidjan) ne sont pas touchées.
  3. Tarifs : un tarif général par zone et par format (Petit, Moyen), avec le prix ML et le coût
     partenaire. Les anciens tarifs généraux des anciennes zones sont désactivés. Les tarifs
     spécifiques à un vendeur ne sont jamais modifiés : ils sont listés pour être revus à la main.

La commande est rejouable : la relancer ne crée pas de doublon.
"""
import json
import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Configuration, FormatArticle, License, Localite, Zone
from management.grille_ml_cod import DELAIS, LOCALITES, TARIFS_ML
from management.models import Tarification

# Orthographes rencontrées dans l'ancienne base → nom officiel (clés déjà normalisées)
ALIAS = {
    'zouanhouien': 'zouanhounien',
    'odienne': 'odienne',
    'ferkessedougou': 'ferkessedougou',
}


def normaliser(nom):
    """« N’Djem » → « ndjem », « Grand Lahou » → « grandlahou » : comparaison sans accents ni ponctuation."""
    texte = unicodedata.normalize('NFKD', str(nom or ''))
    texte = ''.join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = re.sub(r'[^a-z0-9]', '', texte)
    return ALIAS.get(texte, texte)


class Command(BaseCommand):
    help = "Applique la grille ML COD Intérieur (zones 2 à 6, 275 localités, délais, tarifs, coût partenaire)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Affiche les changements sans rien écrire.")
        parser.add_argument('--license', dest='license_code', help="Code de la license à traiter (par défaut : toutes).")
        parser.add_argument('--couts', dest='fichier_couts',
                            help="Fichier JSON des coûts partenaire, gardé hors du dépôt Git (facultatif).")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.couts = {}
        if options.get('fichier_couts'):
            try:
                with open(options['fichier_couts'], encoding='utf-8') as f:
                    self.couts = {int(z): {k: int(v) for k, v in formats.items()} for z, formats in json.load(f).items()}
            except (OSError, ValueError, AttributeError) as e:
                raise CommandError("Fichier de coûts illisible : %s" % e)
        licenses = License.objects.filter(etat_suppression=False)
        if options.get('license_code'):
            licenses = licenses.filter(code=options['license_code'])
            if not licenses.exists():
                raise CommandError("License introuvable : %s" % options['license_code'])
        if not licenses.exists():
            raise CommandError("Aucune license en base : lancez d'abord seed_cores.")

        for license in licenses:
            self.stdout.write(self.style.MIGRATE_HEADING("License %s" % license.code))
            try:
                with transaction.atomic():
                    rapport = self.appliquer(license)
                    self.afficher(rapport)
                    if dry_run:
                        raise _AnnulerDryRun()
            except _AnnulerDryRun:
                self.stdout.write(self.style.WARNING("  --dry-run : rien n'a été enregistré."))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Grille ML COD Intérieur appliquée."))

    # ------------------------------------------------------------------ #

    def appliquer(self, license):
        r = {'zones_creees': [], 'zones_maj': [], 'zones_desactivees': [], 'localites_creees': [],
             'localites_deplacees': [], 'localites_retirees': [], 'tarifs_crees': [], 'tarifs_maj': [],
             'tarifs_desactives': [], 'tarifs_vendeurs_a_revoir': [], 'formats_crees': [], 'couts_manquants': []}

        config = Configuration.objects.filter(license=license, etat_suppression=False).order_by('-pk').first()
        depart = (Localite.objects.filter(license=license, is_depart=True, etat_suppression=False)
                  .select_related('zone').order_by('pk').first())

        # 1. Zones officielles
        zones = {}
        for numero, (mini, maxi) in DELAIS.items():
            nom = 'Zone %d' % numero
            zone = Zone.objects.filter(license=license, numero=numero, etat_suppression=False).first()
            if zone is None:
                zone = Zone(license=license, numero=numero, nom=nom, is_depart=False, is_arrivee=True)
                r['zones_creees'].append(nom)
            else:
                if (zone.nom, zone.delai_min_jours, zone.delai_max_jours, zone.is_arrivee, zone.etat_validation) != (nom, mini, maxi, True, True):
                    r['zones_maj'].append(nom)
            zone.nom, zone.delai_min_jours, zone.delai_max_jours = nom, mini, maxi
            zone.is_arrivee, zone.etat_validation = True, True
            zones[numero] = zone
        # Les anciennes zones d'arrivée (sans numéro) libèrent leur nom avant l'enregistrement des nouvelles
        anciennes = (Zone.objects.filter(license=license, numero__isnull=True, etat_suppression=False)
                     .exclude(pk=getattr(getattr(depart, 'zone', None), 'pk', None)))
        for ancienne in anciennes:
            if not ancienne.is_arrivee and ancienne.is_depart:
                continue
            ancien_nom = ancienne.nom
            if not ancienne.nom.startswith('Ancienne '):
                ancienne.nom = ('Ancienne ' + ancienne.nom)[:100]
            ancienne.etat_validation = False
            ancienne.is_arrivee = False
            ancienne.save()
            r['zones_desactivees'].append(ancien_nom)
        for zone in zones.values():
            zone.save()

        # 2. Localités
        existantes = {}
        for loc in Localite.objects.filter(license=license, etat_suppression=False).select_related('zone'):
            existantes.setdefault(normaliser(loc.nom), loc)
        officielles = set()
        for numero, noms in LOCALITES.items():
            zone = zones[numero]
            for nom in noms:
                cle = normaliser(nom)
                officielles.add(cle)
                loc = existantes.get(cle)
                if loc is None:
                    loc = Localite(license=license, nom=nom, zone=zone, is_depart=False, is_arrivee=True)
                    loc.save()
                    existantes[cle] = loc
                    r['localites_creees'].append('%s (Zone %d)' % (nom, numero))
                    continue
                if loc.zone_id != zone.pk:
                    r['localites_deplacees'].append('%s : %s → Zone %d' % (loc.nom, loc.zone.nom if loc.zone_id else 'sans zone', numero))
                changement = loc.zone_id != zone.pk or not loc.is_arrivee or not loc.etat_validation or loc.nom != nom
                loc.zone, loc.is_arrivee, loc.etat_validation, loc.nom = zone, True, True, nom
                if changement:
                    loc.save()
        for cle, loc in existantes.items():
            if cle in officielles or loc.is_depart or not loc.is_arrivee:
                continue
            loc.is_arrivee = False
            loc.save()
            r['localites_retirees'].append(loc.nom)

        # 3. Formats
        formats = {}
        for nom in ('Petit', 'Moyen', 'Grand'):
            fmt = FormatArticle.objects.filter(license=license, nom__iexact=nom, etat_suppression=False).first()
            if fmt is None and nom != 'Grand':
                fmt = FormatArticle(license=license, nom=nom)
                fmt.save()
                r['formats_crees'].append(nom)
            formats[nom] = fmt

        # 4. Tarifs généraux (vendeur = None, localité d'arrivée = None)
        generaux = Tarification.objects.filter(license=license, vendeur__isnull=True, localite_arrivee__isnull=True,
                                               etat_suppression=False)
        gardes = set()
        for numero, prix in TARIFS_ML.items():
            zone = zones[numero]
            for nom_format, montant in prix.items():
                fmt = formats[nom_format]
                tarif = generaux.filter(zone_arrivee=zone, format_article=fmt).order_by('-etat_validation', '-pk').first()
                # Coût partenaire : celui du fichier --couts, sinon on garde celui déjà saisi
                cout = self.couts.get(numero, {}).get(nom_format)
                if tarif is None:
                    tarif = Tarification(license=license, zone_arrivee=zone, format_article=fmt, config=config,
                                         localite_depart=depart, zone_depart=getattr(depart, 'zone', None))
                    r['tarifs_crees'].append('Zone %d %s : %s F' % (numero, nom_format, montant))
                elif (tarif.montant_frais, tarif.etat_validation) != (montant, True) or (cout is not None and tarif.cout_partenaire != cout):
                    r['tarifs_maj'].append('Zone %d %s : %s → %s F' % (numero, nom_format, _f(tarif.montant_frais), montant))
                tarif.montant_frais = montant
                if cout is not None:
                    tarif.cout_partenaire = cout
                elif tarif.cout_partenaire is None:
                    r['couts_manquants'].append('Zone %d %s' % (numero, nom_format))
                tarif.etat_validation = True
                if tarif.config_id is None:
                    tarif.config = config
                tarif.save()
                gardes.add(tarif.pk)
        # Tarifs généraux des anciennes zones d'arrivée : désactivés (jamais supprimés).
        # On ne touche ni aux tarifs « toutes zones » ni à ceux de la zone de départ (Abidjan).
        zone_depart_id = getattr(depart, 'zone_id', None)
        perimes = (generaux.filter(etat_validation=True, zone_arrivee__isnull=False, zone_arrivee__numero__isnull=True)
                   .exclude(pk__in=gardes).select_related('zone_arrivee', 'format_article'))
        if zone_depart_id:
            perimes = perimes.exclude(zone_arrivee_id=zone_depart_id)
        for tarif in perimes:
            tarif.etat_validation = False
            tarif.save()
            r['tarifs_desactives'].append('%s · %s · %s F' % (tarif.zone_arrivee or 'toutes zones', tarif.format_article or 'tous formats', _f(tarif.montant_frais)))
        # Tarifs propres à un vendeur : à revoir à la main
        for tarif in Tarification.objects.filter(license=license, vendeur__isnull=False, etat_validation=True,
                                                 etat_suppression=False).select_related('vendeur', 'zone_arrivee', 'format_article'):
            r['tarifs_vendeurs_a_revoir'].append('%s · %s · %s · %s F' % (tarif.vendeur, tarif.zone_arrivee or 'toutes zones',
                                                                          tarif.format_article or 'tous formats', _f(tarif.montant_frais)))
        return r

    def afficher(self, r):
        titres = [
            ('zones_creees', 'Zones créées'), ('zones_maj', 'Zones mises à jour'),
            ('zones_desactivees', 'Anciennes zones désactivées'), ('formats_crees', 'Formats créés'),
            ('localites_creees', 'Localités créées'), ('localites_deplacees', 'Localités changées de zone'),
            ('localites_retirees', "Localités retirées de la liste d'arrivée"),
            ('tarifs_crees', 'Tarifs créés'), ('tarifs_maj', 'Tarifs mis à jour'),
            ('tarifs_desactives', 'Anciens tarifs désactivés'),
            ('tarifs_vendeurs_a_revoir', 'Tarifs propres à un vendeur, À REVOIR À LA MAIN'),
            ('couts_manquants', 'Tarifs sans coût partenaire (à saisir par le CEO ou via --couts)'),
        ]
        for cle, titre in titres:
            lignes = r[cle]
            self.stdout.write('  %s : %d' % (titre, len(lignes)))
            for ligne in lignes[:400]:
                self.stdout.write('    - %s' % ligne)


class _AnnulerDryRun(Exception):
    pass


def _f(valeur):
    return '—' if valeur is None else '%d' % valeur
