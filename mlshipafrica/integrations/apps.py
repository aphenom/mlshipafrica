from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations'
    verbose_name = 'Intégrations (Woura, API vendeur)'

    def ready(self):
        from integrations import signals  # noqa: F401  (événements sortants selon les mouvements des colis)
