from django.urls import path

from sms import views

app_name = 'sms'

urlpatterns = [
    path('hsms/accuses/<str:secret>/', views.accuses_hsms, name='sms_accuses_hsms'),
]
