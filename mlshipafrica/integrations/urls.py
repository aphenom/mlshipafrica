from django.urls import path

from integrations import views

app_name = 'integrations'

urlpatterns = [
    path('woura/webhook/', views.webhook_woura, name='woura_webhook'),
    path('api/v1/colis/', views.api_colis, name='api_colis'),
    path('api/v1/colis/<str:code>/', views.api_colis_detail, name='api_colis_detail'),
    path('api/v1/tarifs/', views.api_tarifs, name='api_tarifs'),
    path('mes-integrations/', views.vendeur_integrations, name='vendeur_integrations'),
]
