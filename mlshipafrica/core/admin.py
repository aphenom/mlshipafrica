from django.contrib import admin

from core.models import JournalAudit


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    """Lecture seule, réservé à la direction (super-utilisateurs)."""
    list_display = ('date', 'utilisateur', 'role', 'action', 'modele', 'objet_code', 'apres')
    list_filter = ('action', 'modele', 'role')
    search_fields = ('objet_code', 'objet_id', 'utilisateur__email')
    date_hierarchy = 'date'
    list_select_related = ('utilisateur',)
    readonly_fields = [f.name for f in JournalAudit._meta.fields]

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
