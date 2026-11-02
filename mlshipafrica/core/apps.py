from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from core.audit import brancher
        brancher()  # journal d'audit sur les objets sensibles (core/audit.py)
