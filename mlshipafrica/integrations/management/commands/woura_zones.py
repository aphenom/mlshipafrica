"""Affiche ou envoie à Woura la liste des localités desservies (PUT /zones) : python manage.py woura_zones [--envoyer]"""
import json
import urllib.request

from decouple import config
from django.core.management.base import BaseCommand, CommandError

from core.models import License
from integrations.service import zones_pour_woura


class Command(BaseCommand):
    help = "Zones pour Woura : localités, pays CI, frais du format Petit."

    def add_arguments(self, parser):
        parser.add_argument('--envoyer', action='store_true')

    def handle(self, *args, **options):
        license = License.objects.filter(etat_suppression=False).first()
        corps = zones_pour_woura(license)
        if not options['envoyer']:
            self.stdout.write(json.dumps(corps, ensure_ascii=False, indent=1)[:3000])
            self.stdout.write('%d localités. Ajoutez --envoyer pour les transmettre à Woura.' % len(corps['zones']))
            return
        cle, base = config('WOURA_API_KEY', default=''), config('WOURA_BASE_URL', default='').rstrip('/')
        if not cle or not base:
            raise CommandError('WOURA_API_KEY et WOURA_BASE_URL sont nécessaires dans le .env')
        requete = urllib.request.Request(base + '/zones', data=json.dumps(corps).encode(), method='PUT',
                                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cle})
        with urllib.request.urlopen(requete, timeout=30) as r:
            self.stdout.write('Woura : %s %s' % (r.status, r.read(500).decode('utf-8', 'replace')))
