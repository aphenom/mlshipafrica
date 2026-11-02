"""
Points d'entrée des intégrations.

  POST /integrations/woura/webhook/          webhook Woura (signé), réponse immédiate
  API vendeur (Authorization: Bearer <clé>) :
  GET  /integrations/api/v1/tarifs/          grille ML COD Intérieur (localités, zones, délais, prix)
  GET  /integrations/api/v1/colis/           ses colis (50 derniers, ?statut=…)
  POST /integrations/api/v1/colis/           créer une commande (JSON : reference, nom, telephone, ville, adresse,
                                             montant, designation, taille)
  GET  /integrations/api/v1/colis/<code>/    un colis

Aucune donnée interne dans les réponses : ni coût, ni marge, ni nom de prestataire, ni acompte.
"""
import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from integrations.models import EvenementIntegration as E, IntegrationVendeur
from integrations.service import creer_commande, recevoir_woura


@csrf_exempt
@require_POST
def webhook_woura(request):
    code, message = recevoir_woura(request.body, request.headers.get('Woura-Signature', ''))
    return JsonResponse({'message': message}, status=code)


def _vendeur_api(request):
    entete = request.headers.get('Authorization', '')
    cle = entete[7:].strip() if entete.startswith('Bearer ') else ''
    if not cle:
        return None, None
    integration = (IntegrationVendeur.objects.filter(api_actif=True, cle_live=cle).select_related('vendeur').first()
                   or IntegrationVendeur.objects.filter(api_actif=True, cle_test=cle).select_related('vendeur').first())
    if integration is None or integration.vendeur.etat_suppression or not integration.vendeur.etat_approbation:
        return None, None
    return integration.vendeur, cle.startswith('mlc_test')


def _colis_json(a):
    return {'code': a.code, 'reference': a.reference_externe, 'statut': a.statut_traitement,
            'libelle_statut': a.get_statut_traitement_display(), 'ville': str(a.localite_arrivee or ''),
            'montant_a_encaisser': int(a.valeur_totale or 0) if a.is_option_encaissement else 0,
            'frais_livraison': int(a.montant_total_frais or 0), 'date_creation': a.date_creation.isoformat()}


def _journal(vendeur, type_, contenu, reponse):
    import uuid
    E.objects.create(sens=E.ENTRANT, canal=E.API, type=type_, identifiant='api:in:%s' % uuid.uuid4().hex, vendeur=vendeur,
                     contenu=contenu, reponse=json.dumps(reponse, ensure_ascii=False)[:2000], statut=E.TRAITE)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_colis(request):
    vendeur, test = _vendeur_api(request)
    if vendeur is None:
        return JsonResponse({'erreur': 'clé API invalide'}, status=401)
    from management.models import Article
    if request.method == 'GET':
        qs = Article.objects.filter(vendeur=vendeur, etat_suppression=False).select_related('localite_arrivee').order_by('-date_creation')
        if request.GET.get('statut'):
            qs = qs.filter(statut_traitement=request.GET['statut'])
        return JsonResponse({'colis': [_colis_json(a) for a in qs[:50]]})
    try:
        donnees = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        return JsonResponse({'erreur': 'JSON invalide'}, status=400)
    reference = str(donnees.get('reference') or '').strip()
    try:
        article, cree = creer_commande(vendeur, donnees, 'api', ('test:' if test else '') + reference, test=test)
    except ValidationError as erreur:
        reponse = {'erreur': ' '.join(erreur.messages)}
        _journal(vendeur, 'colis.creer', donnees, reponse)
        return JsonResponse(reponse, status=422)
    reponse = dict(_colis_json(article), test=test)
    _journal(vendeur, 'colis.creer', donnees, reponse)
    return JsonResponse(reponse, status=201 if cree else 200)


@require_http_methods(['GET'])
def api_colis_detail(request, code):
    vendeur, _ = _vendeur_api(request)
    if vendeur is None:
        return JsonResponse({'erreur': 'clé API invalide'}, status=401)
    from management.models import Article
    article = Article.objects.filter(vendeur=vendeur, code=code, etat_suppression=False).select_related('localite_arrivee').first()
    if article is None:
        return JsonResponse({'erreur': 'colis introuvable'}, status=404)
    return JsonResponse(_colis_json(article))


@require_http_methods(['GET'])
def api_tarifs(request):
    vendeur, _ = _vendeur_api(request)
    if vendeur is None:
        return JsonResponse({'erreur': 'clé API invalide'}, status=401)
    from core.models import Localite
    from management.models import Tarification
    tarifs = {}
    for t in Tarification.objects.filter(license=vendeur.license, vendeur__isnull=True, etat_validation=True,
                                         etat_suppression=False).select_related('format_article'):
        tarifs.setdefault(t.zone_arrivee_id, {})[t.format_article.nom if t.format_article_id else 'tous'] = int(t.montant_frais or 0)
    localites = Localite.objects.filter(license=vendeur.license, is_arrivee=True, etat_validation=True, etat_suppression=False,
                                        zone__numero__isnull=False).select_related('zone')
    return JsonResponse({'localites': [{'ville': l.nom, 'zone': l.zone.nom, 'delai': l.zone.get_delai_display(),
                                        'prix': tarifs.get(l.zone_id, {})} for l in localites]})


# ----------------------------------------------------------------------------------------- espace vendeur

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render


@login_required
def vendeur_integrations(request):
    """Le vendeur active Woura, ses clés d'API (test et production) et son webhook ; il voit le journal de ses appels."""
    from management.models import Vendeur
    from mlshipafrica.enums import StatutTraitement
    from integrations.models import cle_live, cle_test, secret_webhook
    try:
        vendeur = Vendeur.objects.get(user=request.user, etat_approbation=True)
    except Vendeur.DoesNotExist:
        raise Http404
    integration, _ = IntegrationVendeur.objects.get_or_create(vendeur=vendeur)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'woura':
            integration.woura_actif = bool(request.POST.get('woura_actif'))
            integration.woura_boutique_id = (request.POST.get('woura_boutique_id') or '').strip()[:80]
            if integration.woura_actif and not integration.woura_boutique_id:
                django_messages.error(request, "Indiquez l'identifiant de votre boutique Woura.")
                return redirect('integrations:vendeur_integrations')
        elif action == 'api':
            integration.api_actif = bool(request.POST.get('api_actif'))
            url = (request.POST.get('webhook_url') or '').strip()
            if url and not url.startswith('https://'):
                django_messages.error(request, "L'URL du webhook doit commencer par https://")
                return redirect('integrations:vendeur_integrations')
            integration.webhook_url = url
            integration.webhook_evenements = [s for s in request.POST.getlist('evenements') if s in StatutTraitement.values]
        elif action == 'regenerer':
            integration.cle_test, integration.cle_live, integration.webhook_secret = cle_test(), cle_live(), secret_webhook()
        integration.save()
        django_messages.success(request, "Intégrations enregistrées.")
        return redirect('integrations:vendeur_integrations')
    journal = E.objects.filter(vendeur=vendeur).order_by('-date')[:30]
    statuts = [(v, l) for v, l in StatutTraitement.choices if v not in ('brouillon',)]
    return render(request, 'integrations/vendeur_integrations.html', locals())
