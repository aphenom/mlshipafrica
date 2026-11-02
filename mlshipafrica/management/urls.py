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
    path('vendeur_substituer_colis/<str:code>/', views.vendeur_substituer_colis, name='management_vendeur_substituer_colis'),
    path('admin_liste_vendeurs/', views.admin_liste_vendeurs, name='management_admin_liste_vendeurs'),
    path('admin_vendeur_edit_profil/<str:code>/', views.admin_vendeur_edit_profil, name='management_admin_vendeur_edit_profil'),
    path('admin_vendeur_profil/<str:code>/', views.admin_vendeur_profil, name='management_admin_vendeur_profil'),
    path('admin_liste_colis/', views.admin_liste_colis, name='management_admin_liste_colis'),
    path('admin_liste_colis_vendeurs/', views.admin_liste_colis_vendeurs, name='management_admin_liste_colis_vendeurs'),
    path('admin_detail_colis/<str:code>/', views.admin_detail_colis, name='management_admin_detail_colis'),
    path('admin_liste_paiements/', views.admin_liste_paiements, name='management_admin_liste_paiements'),
    path('admin_liste_paiements_vendeurs/', views.admin_liste_paiements_vendeurs, name='management_admin_liste_paiements_vendeurs'),
    path('admin_liste_reversements/', views.admin_liste_reversements, name='management_admin_liste_reversements'),
    path('admin_liste_reversements_vendeurs/', views.admin_liste_reversements_vendeurs, name='management_admin_liste_reversements_vendeurs'),
    path('admin_mouvements_colis/', views.admin_mouvements_colis, name='management_admin_mouvements_colis'),
    path('admin_activites_paiements/', views.admin_activites_paiements, name='management_admin_activites_paiements'),
    path('admin_activites_reversements/', views.admin_activites_reversements, name='management_admin_activites_reversements'),
    path('admin_import_vendeur/', views.admin_import_vendeur, name='management_admin_import_vendeur'),
    path('admin_confirmations/', views.admin_confirmations, name='management_admin_confirmations'),
    path('admin_acomptes/', views.admin_acomptes, name='management_admin_acomptes'),
    path('admin_stock/', views.admin_stock, name='management_admin_stock'),
    path('admin_releves/', views.admin_releves, name='management_admin_releves'),
    path('admin_benefice/', views.admin_benefice, name='management_admin_benefice'),
    path('admin_commissions/', views.admin_commissions, name='management_admin_commissions'),
    path('vendeur_releves/', views.vendeur_releves, name='management_vendeur_releves'),
    path('vendeur_stock/', views.vendeur_stock, name='management_vendeur_stock'),
]