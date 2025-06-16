from django.urls import path

from . import views # import views so we can use them in urls.

app_name = 'core'
urlpatterns = [
    path('_liste/', views._liste, name='core_liste'),
    path('_new/', views._new, name='core_new'),
    path('_edit/<str:code>/', views._edit, name='core_edit'),
    # path('admin_detail_colis/<str:code>/', views.admin_detail_colis, name='management_admin_detail_colis'),
    # path('admin_liste_paiements/', views.admin_liste_paiements, name='management_admin_liste_paiements'),
    # path('admin_liste_reversements/', views.admin_liste_reversements, name='management_admin_liste_reversements'),
]