"""
Webhook des accusés de réception HSMS.

URL à déclarer chez HSMS (mode « DLR Push ») :
    https://app.mlcodinterieur.com/sms/hsms/accuses/<HSMS_WEBHOOK_SECRET>/

Le secret dans l'URL empêche un tiers d'envoyer de faux accusés. Corps attendu (JSON) :
    {"ticket": "...", "status": 3, "status_label": "Délivré", "recipient": "225..."}
Une liste d'accusés est aussi acceptée.
"""
import hmac
import json
import logging

from decouple import config
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.views.decorators.http import require_POST

from sms.service import appliquer_accuse, lire_accuses

logger = logging.getLogger('sms')


@csrf_exempt
@require_POST
def accuses_hsms(request, secret):
    attendu = config('HSMS_WEBHOOK_SECRET', default='')
    if not attendu or not hmac.compare_digest(str(secret), attendu):
        return HttpResponseForbidden('secret invalide')
    try:
        corps = json.loads(request.body.decode('utf-8') or 'null')
    except ValueError:
        corps = request.POST.dict() or None
    if corps is None:
        return HttpResponse(status=400)
    traites = 0
    for ticket, code in lire_accuses(corps):
        traites += appliquer_accuse(ticket, code)
    return JsonResponse({'ok': True, 'traites': traites})



# ----------------------------------------------------------------------------- réglages du CEO
from django.contrib import messages as flash  # noqa: E402
from django.contrib.auth.decorators import login_required  # noqa: E402
from django.shortcuts import redirect, render  # noqa: E402

from mlshipafrica.droits import droit_requis  # noqa: E402


@login_required
@droit_requis('messages_auto')
def messages_auto(request):
    """Le CEO règle chaque message : SMS et/ou e-mail (vendeur), textes, informations insérées, actif ou non."""
    from sms.messages_auto import EXEMPLE, INFOS, envoyer_email
    from sms.models import SmsModele, SmsParametres
    from sms.service import mettre_en_file
    from sms.texte import preparer, remplir
    parametres = SmsParametres.charger()
    if request.method == 'POST':
        if request.POST.get('global'):
            parametres.actif = bool(request.POST.get('sms_global'))
            parametres.tel_service = (request.POST.get('tel_service') or parametres.tel_service).strip()[:30]
            parametres.save()
            flash.success(request, "Réglages généraux enregistrés.")
            return redirect('sms:messages_auto')
        modele = SmsModele.objects.filter(cle=request.POST.get('cle')).first()
        if modele is None:
            return redirect('sms:messages_auto')
        if request.POST.get('test'):
            exemple = dict(EXEMPLE)
            numero = (request.POST.get('numero_test') or '').strip()
            if numero:
                m = mettre_en_file(modele.cle, numero, exemple, 'test:%s:%s' % (modele.cle, timezone.now().timestamp()))
                flash.success(request, "SMS de test mis en file pour %s." % numero if m else "SMS désactivé : activez-le pour tester.")
            if modele.destinataire == SmsModele.DESTINATAIRE_VENDEUR and request.user.email and modele.email_texte:
                class _V:  # destinataire de test : le CEO lui-même
                    email, user_id, pk = request.user.email, None, None
                actif = modele.email_actif
                modele.email_actif = True
                envoyer_email(modele, _V(), exemple, 'test:%s:%s' % (modele.cle, timezone.now().timestamp()))
                modele.email_actif = actif
                flash.success(request, "E-mail de test envoyé à %s." % request.user.email)
            return redirect('%s#m-%s' % (request.path, modele.cle))
        modele.actif = bool(request.POST.get('actif'))
        modele.texte = (request.POST.get('texte') or modele.texte).strip()[:612]
        if modele.destinataire == SmsModele.DESTINATAIRE_VENDEUR:
            modele.email_actif = bool(request.POST.get('email_actif'))
            modele.email_objet = (request.POST.get('email_objet') or '').strip()[:200]
            modele.email_texte = (request.POST.get('email_texte') or '').strip()[:5000]
        modele.save()
        flash.success(request, "« %s » enregistré." % modele.libelle)
        return redirect('%s#m-%s' % (request.path, modele.cle))
    rubriques = []
    for cle, libelle in SmsModele._meta.get_field('categorie').choices:
        liste = list(SmsModele.objects.filter(categorie=cle))
        for m in liste:
            texte, unicode, nb = preparer(remplir(m.texte, EXEMPLE))
            m.apercu, m.unicode, m.nb_sms = texte, unicode, nb
            m.apercu_objet = remplir(m.email_objet, EXEMPLE)
            m.apercu_email = remplir(m.email_texte, EXEMPLE)
        if liste:
            rubriques.append({'cle': cle, 'libelle': libelle, 'modeles': liste, 'infos': INFOS.get(cle, [])})
    import json
    return render(request, 'sms/messages_auto.html', {'rubriques': rubriques, 'parametres': parametres,
                                                      'exemple_json': json.dumps(EXEMPLE, ensure_ascii=False)})
