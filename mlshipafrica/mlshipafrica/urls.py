"""
URL configuration for ludo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from .views import index #annuler, annuler_participation, api_get_partie_privee_via_by_code, cgu, check_participation_et_partie, connect_with_state, creer_partie_privee, facebook_login_with_state, faq, index, index_partie, login_demo, mysignup, participer_partie, privacy, register_device, api_update_room_info
#from .cron import cron_transfert_cinetpay
from django.conf.urls.static import static
from django.conf import settings


urlpatterns = [

    path('', index, name='index'),
    # path('annuler/', annuler, name='annuler'),
    
    # Allauth URLs pour l'authentification
    path('accounts/', include('allauth.urls')),

    path('tinymce/', include('tinymce.urls')),

    path('management/', include('management.urls')),
   
    path('core/', include('core.urls')),

    # path('player/', include('player.urls')),

    # path('cron/cron_transfert_cinetpay/', cron_transfert_cinetpay, name='cron_transfert_cinetpay'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
