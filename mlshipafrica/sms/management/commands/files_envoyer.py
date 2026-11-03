"""
Une seule tâche planifiée pour les deux files : SMS (HSMS) et événements sortants (Woura, webhooks vendeurs).

Un seul démarrage de Django toutes les 2 minutes au lieu de deux chaque minute. Les deux files sont lues par
des requêtes indexées : quand il n'y a rien à envoyer, la tâche se termine en quelques millisecondes après le
démarrage. CRONTAB_LOCK_JOBS empêche deux passages de se chevaucher.
"""
from django.core.management.base import BaseCommand

from integrations.service import envoyer_file as envoyer_evenements
from sms.service import envoyer_file as envoyer_sms


class Command(BaseCommand):
    help = "Envoie les SMS et les événements d'intégration en file (toutes les 2 minutes)."

    def handle(self, *args, **options):
        sms = envoyer_sms(limite=300)
        if sms['envoyes'] or sms['reportes'] or sms['echecs'] or sms['pause']:
            self.stdout.write('SMS : %(envoyes)d envoyés, %(reportes)d reportés, %(echecs)d en échec, pause=%(pause)s' % sms)
        ev = envoyer_evenements(limite=300)
        if ev['envoyes'] or ev['erreurs']:
            self.stdout.write('Intégrations : %(envoyes)d envoyés, %(erreurs)d en erreur' % ev)
