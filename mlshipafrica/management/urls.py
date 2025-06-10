from django.urls import path

from . import views # import views so we can use them in urls.

app_name = 'management'
urlpatterns = [
    path('vendeur_edit_profil/', views.vendeur_edit_profil, name='management_vendeur_edit_profil'),
    path('vendeur_profil/', views.vendeur_profil, name='management_vendeur_profil'),
    path('vendeur_edit_colis/', views.vendeur_edit_colis, name='management_vendeur_edit_colis'),
    path('vendeur_liste_colis/', views.vendeur_liste_colis, name='management_vendeur_liste_colis'),
    path('vendeur_liste_colis_reversement/', views.vendeur_liste_colis_reversement, name='management_vendeur_liste_colis_reversement'),
    path('vendeur_facture_colis/<str:code>/', views.vendeur_facture_colis, name='management_vendeur_facture_colis'),
    path('vendeur_detail_colis/<str:code>/', views.vendeur_detail_colis, name='management_vendeur_detail_colis'),
    path('admin_liste_vendeurs/', views.admin_liste_vendeurs, name='management_admin_liste_vendeurs'),
    path('admin_vendeur_edit_profil/<str:code>/', views.admin_vendeur_edit_profil, name='management_admin_vendeur_edit_profil'),
    path('admin_vendeur_profil/<str:code>/', views.admin_vendeur_profil, name='management_admin_vendeur_profil'),
    path('admin_liste_colis/', views.admin_liste_colis, name='management_admin_liste_colis'),
    path('admin_detail_colis/<str:code>/', views.admin_detail_colis, name='management_admin_detail_colis'),
    path('admin_liste_paiements/', views.admin_liste_paiements, name='management_admin_liste_paiements'),
    path('admin_liste_reversements/', views.admin_liste_reversements, name='management_admin_liste_reversements'),
]