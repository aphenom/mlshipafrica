from core.models import Configuration
from mlshipafrica.enums import StatutTraitement, StatutVendeur, TypeProfilStaffChoice, TypeVendeurChoice
from django.urls import resolve
from django.db.models import Q
from django.templatetags.static import static
from django.conf import settings
from django.contrib.auth.models import User

def context(request):

    statut_traitement = StatutTraitement
    statut_vendeur = StatutVendeur
    type_profil_staff = TypeProfilStaffChoice
    license = None
    configuration = None
    vendeur = None
    profil_staff = None
    user = request.user
    notification_messages = None

    try:  
        my_current_url = resolve(request.path_info).url_name 
    except:
        my_current_url = None

    # if config.parallax and hasattr(config.parallax, 'url'):
    #     costum_parallax = config.parallax.url
    # else:
    #     costum_parallax = static('images/login/login.jpg') 
        
    if user.is_authenticated:
        if hasattr(user, 'account_vendeur'):
            vendeur = user.account_vendeur
            license = vendeur.license
        if hasattr(user, 'account_profil_staff'):
            profil_staff = user.account_profil_staff
            license = profil_staff.license
        configuration = Configuration.objects.filter(license=license, etat_validation=True, etat_suppression=False).order_by("-pk").first()  
        # try:
        #     company = Company.objects.get(user=request.user)
        #     notification_messages = Message.objects.filter(company=company, submessage__isnull=True, is_readed=False, is_active=True).order_by("-created_at")
        # except Company.DoesNotExist:
        #     notification_messages = None
        # try:
        #     member = Member.objects.get(user=request.user)
        #     notification_messages = Message.objects.filter(member=member, submessage__isnull=True, is_readed=False, is_active=True).order_by("-created_at")
        # except Member.DoesNotExist:
        #     if notification_messages == None:
        #         notification_messages = None
        # test_message = User.objects.filter(pk=request.user.pk, groups__name='message').exists()        
        # if request.user.is_staff == True and (test_message or request.user.is_superuser):
        #     notification_messages = Message.objects.filter(Q(submessage__isnull=True, is_active=True, is_from_user=True, is_noreply=False)).order_by("-created_at")         
    else:
        notification_messages = None
    return {
            'configuration' : configuration, 
            'statut_vendeur' : statut_vendeur, 
            'statut_traitement': statut_traitement, 
            'type_profil_staff': type_profil_staff, 
            'my_current_url': my_current_url, 
            'notification_messages': notification_messages
            }      