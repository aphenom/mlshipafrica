""" Pages d'erreur personnalisées (utilisées quand DEBUG = False) """
from django.http import HttpResponse
from django.template import loader
from django.utils import timezone

from .logging_utils import new_ref


def _context(request, code):
    return {
        'code': code,
        'ref': getattr(request, 'error_ref', None) or new_ref(),
        'path': request.path,
        'date': timezone.localtime().strftime('%d/%m/%Y %H:%M:%S'),
    }


def _render(request, template_name, code):
    # Rendu sans RequestContext : pas de context processors ni d'accès BDD,
    # pour que la page s'affiche même si la cause de l'erreur est la BDD
    try:
        template = loader.get_template(template_name)
        return HttpResponse(template.render(_context(request, code)), status=code)
    except Exception:
        return HttpResponse(
            '<h1>Erreur {}</h1><p>Référence : {}</p>'.format(code, _context(request, code)['ref']),
            status=code,
        )


def bad_request(request, exception=None):
    return _render(request, 'errors/400.html', 400)


def permission_denied(request, exception=None):
    return _render(request, 'errors/403.html', 403)


def page_not_found(request, exception=None):
    return _render(request, 'errors/404.html', 404)


def server_error(request):
    return _render(request, 'errors/500.html', 500)


def csrf_failure(request, reason=''):
    return _render(request, 'errors/403.html', 403)
