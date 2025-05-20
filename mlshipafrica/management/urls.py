from django.urls import path

from . import views # import views so we can use them in urls.

app_name = 'management'
urlpatterns = [
    path('vendeur_edit_profil/', views.vendeur_edit_profil, name='management_vendeur_edit_profil'),
    path('vendeur_edit_colis/', views.vendeur_edit_colis, name='management_vendeur_edit_colis'),
]