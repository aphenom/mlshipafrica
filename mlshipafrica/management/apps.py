from django.apps import AppConfig


class ManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'management'

    def ready(self):
        from management import confirmation, finance, retours, stock  # noqa: F401  (acompte, argent, retours et stock selon les mouvements)
