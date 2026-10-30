"""Envoie un SMS de test, immédiatement, pour vérifier la configuration HSMS : manage.py sms_test 0707070707"""
from django.core.management.base import BaseCommand, CommandError

from sms.hsms import ErreurHsms
from sms.models import SmsParametres
from sms.service import client_par_defaut
from sms.telephone import normaliser_ci
from sms.texte import preparer


class Command(BaseCommand):
    help = "Envoie un SMS de test (ne passe pas par la file) et affiche la réponse brute de HSMS."

    def add_arguments(self, parser):
        parser.add_argument('numero')
        parser.add_argument('--message', default='MLCOD : test de configuration SMS. Merci de ne pas repondre.')

    def handle(self, *args, **options):
        msisdn, raison = normaliser_ci(options['numero'])
        if raison:
            raise CommandError('Numéro refusé : %s' % raison)
        client = client_par_defaut(SmsParametres.charger())
        if not client.configure:
            raise CommandError('Variables HSMS_EMAIL, HSMS_PASSWORD, HSMS_CLIENT_ID, HSMS_CLIENT_SECRET absentes du .env')
        texte, unicode, segments = preparer(options['message'])
        try:
            tickets, reponse = client.envoyer(msisdn, texte, unicode)
            solde, _ = client.solde()
        except ErreurHsms as erreur:
            raise CommandError('%s (type : %s, réponse : %s)' % (erreur, erreur.genre, erreur.corps))
        self.stdout.write(self.style.SUCCESS('Envoyé à %s · %d SMS · tickets %s' % (msisdn, segments, tickets or '?')))
        self.stdout.write('Réponse HSMS : %s' % reponse)
        self.stdout.write('Solde restant : %s' % solde)
