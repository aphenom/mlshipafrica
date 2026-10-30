from django.apps import AppConfig


class SmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sms'
    verbose_name = 'SMS'

    def ready(self):
        from sms import signals  # noqa: F401  (branche les déclencheurs sur l'historique des colis)
