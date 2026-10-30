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
