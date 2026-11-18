"""
Prépare une version de test (recette) à partir d'une copie de la base de production. Refuse de tourner hors recette.

    python manage.py recette_preparer --mot-de-passe Test2026!
Donne le même mot de passe à tous les comptes (équipe et vendeurs) pour tester chaque rôle, met en pause l'envoi
des SMS, vide les files d'envoi (SMS, Woura, webhooks) et liste un compte par rôle.
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Version de test : mot de passe commun, envois coupés, liste des comptes par rôle."

    def add_arguments(self, parser):
        parser.add_argument('--mot-de-passe', required=True)

    def handle(self, *args, **o):
        nom_base = settings.DATABASES['default'].get('NAME', '')
        if not getattr(settings, 'RECETTE', False) or 'recette' not in str(nom_base).lower():
            raise CommandError("Refusé : cette commande ne tourne que sur une recette (RECETTE=True, base « …recette… »).")
        from integrations.models import EvenementIntegration
        from management.models import ProfilStaff, Vendeur
        from sms.models import SmsMessage, SmsParametres
        SmsParametres.objects.filter(pk=1).update(actif=False)
        SmsMessage.objects.filter(statut=SmsMessage.EN_FILE).update(statut=SmsMessage.ANNULE)
        EvenementIntegration.objects.filter(statut=EvenementIntegration.EN_FILE).update(statut=EvenementIntegration.ECHEC)
        n = 0
        for u in User.objects.filter(is_active=True).iterator():
            u.set_password(o['mot_de_passe'])
            u.save(update_fields=['password'])
            n += 1
        self.stdout.write("%d compte(s) : mot de passe commun appliqué. Envois coupés." % n)
        for p in ProfilStaff.objects.select_related('user').order_by('role_profil'):
            if p.user_id:
                self.stdout.write('  %-28s %s' % (p.get_role_profil_display(), p.user.email or p.user.username))
        for v in Vendeur.objects.filter(etat_approbation=True).select_related('user').order_by('-pk')[:5]:
            if v.user_id:
                self.stdout.write('  %-28s %s (%s)' % ('Vendeur', v.user.email or v.user.username, v.nom_store))
