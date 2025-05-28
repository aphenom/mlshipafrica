from django.urls import path

from . import views # import views so we can use them in urls.

app_name = 'management'
urlpatterns = [
    path('vendeur_edit_profil/', views.vendeur_edit_profil, name='management_vendeur_edit_profil'),
    path('vendeur_edit_colis/', views.vendeur_edit_colis, name='management_vendeur_edit_colis'),
    path('vendeur_facture_colis/<str:code>/', views.vendeur_facture_colis, name='management_vendeur_facture_colis'),
    path('vendeur_detail_colis/<str:code>/', views.vendeur_detail_colis, name='management_vendeur_detail_colis'),
]