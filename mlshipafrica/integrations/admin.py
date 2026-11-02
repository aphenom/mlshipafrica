from django.contrib import admin

from integrations.models import EvenementIntegration


@admin.register(EvenementIntegration)
class EvenementIntegrationAdmin(admin.ModelAdmin):
    """Journal des appels (lecture seule, direction)."""
    list_display = ('date', 'sens', 'canal', 'type', 'statut', 'tentatives', 'vendeur', 'article', 'reponse')
    list_filter = ('sens', 'canal', 'statut', 'type')
    search_fields = ('identifiant', 'article__code', 'vendeur__nom_store')
    readonly_fields = [f.name for f in EvenementIntegration._meta.fields]

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
