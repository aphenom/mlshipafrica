"""
Liste les comptes de l'équipe et leur rôle, et permet de changer un rôle avant la mise en ligne.

    python manage.py roles_equipe
    python manage.py roles_equipe --attribuer agent1@mlcod.ci agent

Rôles : super (CEO), comptable, manager, agent (agent COD), commercial, administrateur (technique).
Avant ce lot, « administrateur » faisait presque tout : vérifier chaque compte et lui donner son vrai rôle.
"""
from django.core.management.base import BaseCommand, CommandError

from management.models import ProfilStaff
from mlshipafrica.droits import DROITS
from mlshipafrica.enums import TypeProfilStaffChoice


class Command(BaseCommand):
    help = "Liste les rôles de l'équipe ; --attribuer EMAIL ROLE pour en changer un."

    def add_arguments(self, parser):
        parser.add_argument('--attribuer', nargs=2, metavar=('EMAIL', 'ROLE'))

    def handle(self, *args, **options):
        if options.get('attribuer'):
            email, role = options['attribuer']
            if role not in TypeProfilStaffChoice.values:
                raise CommandError('Rôle inconnu. Choix : %s' % ', '.join(TypeProfilStaffChoice.values))
            profil = ProfilStaff.objects.filter(user__email__iexact=email).first() or ProfilStaff.objects.filter(email__iexact=email).first()
            if profil is None:
                raise CommandError('Aucun compte équipe avec cet email.')
            profil.role_profil = role
            profil.save()
            self.stdout.write(self.style.SUCCESS('%s est maintenant : %s' % (email, profil.get_role_profil_display())))
            return
        for profil in ProfilStaff.objects.select_related('user').order_by('role_profil', 'user__email'):
            droits = sorted(nom for nom, roles in DROITS.items() if profil.role_profil in roles)
            etat = '' if profil.etat_validation and not profil.etat_suppression else ' (inactif)'
            self.stdout.write('%-35s %-26s%s  droits : %s' % (profil.user.email or profil.email, profil.get_role_profil_display(), etat,
                                                              ', '.join(droits) or 'aucun'))
