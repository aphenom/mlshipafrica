"""
Administration des SMS (réservée aux super-utilisateurs, c'est-à-dire la direction).

  Paramètres SMS  : activer l'envoi, numéro service client, heures calmes, résumé du soir, solde
  Modèles de SMS  : texte de chaque SMS, activé ou non
  SMS             : file et historique (lecture seule), recherche par numéro, code colis ou ticket
"""
from django.contrib import admin

from sms.models import SmsMessage, SmsModele, SmsParametres
from sms.texte import preparer


class ReserveDirection(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SmsParametres)
class SmsParametresAdmin(ReserveDirection):
    list_display = ('__str__', 'actif', 'tel_service', 'resume_soir_actif', 'solde_sms', 'pause_jusqua', 'derniere_erreur')
    readonly_fields = ('solde_sms', 'date_solde', 'derniere_erreur')
    fields = ('actif', 'tel_service', ('heure_debut_silence', 'heure_fin_silence'), 'resume_soir_actif',
              'pause_jusqua', 'derniere_erreur', ('solde_sms', 'date_solde'))


@admin.register(SmsModele)
class SmsModeleAdmin(ReserveDirection):
    list_display = ('libelle', 'destinataire', 'actif', 'cout_estime', 'date_modification')
    list_filter = ('destinataire', 'actif')
    readonly_fields = ('cle', 'destinataire', 'cout_estime')
    fields = ('cle', 'libelle', 'destinataire', 'texte', 'cout_estime', 'actif', 'priorite')

    @admin.display(description='Coût estimé')
    def cout_estime(self, obj):
        _, unicode, segments = preparer(obj.texte)
        return '%d SMS par envoi%s (avant remplissage des variables)' % (segments, ', Unicode' if unicode else '')


@admin.register(SmsMessage)
class SmsMessageAdmin(ReserveDirection):
    list_display = ('date_creation', 'modele_cle', 'destinataire', 'statut', 'segments', 'tentatives', 'article', 'erreur')
    list_filter = ('statut', 'modele_cle')
    search_fields = ('destinataire', 'ticket', 'article__code', 'vendeur__nom_store')
    date_hierarchy = 'date_creation'
    list_select_related = ('article',)
    readonly_fields = [f.name for f in SmsMessage._meta.fields]
    actions = ['remettre_en_file']

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description='Remettre en file (SMS en échec seulement)')
    def remettre_en_file(self, request, queryset):
        n = queryset.filter(statut=SmsMessage.ECHEC).exclude(erreur__startswith='Numéro refusé').update(
            statut=SmsMessage.EN_FILE, tentatives=0, erreur='', verrou='')
        self.message_user(request, '%d SMS remis en file.' % n)
