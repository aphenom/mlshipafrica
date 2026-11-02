from django.apps import AppConfig


class ManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'management'

    def ready(self):
        from management import confirmation, retours  # noqa: F401  (acompte et retours selon les mouvements)
