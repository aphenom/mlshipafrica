from django.apps import AppConfig


class ManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'management'

    def ready(self):
        from management import confirmation, finance, notifications, retours, stock  # noqa: F401  (acompte, argent, cloche, retours et stock selon les mouvements)
