""" Référence d'erreur par requête + enrichissement des logs """
import contextvars
import logging
import uuid


# Référence de la requête en cours, lue par le filtre de logs
current_ref = contextvars.ContextVar('current_ref', default='-')


def new_ref():
    return uuid.uuid4().hex[:8].upper()


class ErrorRefMiddleware:
    ''' Attribue une référence unique à chaque requête (request.error_ref).
        Elle est affichée sur la page d'erreur et écrite dans les logs. '''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.error_ref = new_ref()
        token = current_ref.set(request.error_ref)
        try:
            return self.get_response(request)
        finally:
            current_ref.reset(token)


class RequestContextFilter(logging.Filter):
    ''' Ajoute ref, utilisateur, IP, méthode et URL à chaque ligne de log '''

    def filter(self, record):
        record.ref = current_ref.get()
        request = getattr(record, 'request', None)
        record.user = '-'
        record.ip = '-'
        record.method = '-'
        record.path = '-'
        if request is not None and hasattr(request, 'META'):
            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False):
                record.user = '{} (id={})'.format(user.get_username(), user.pk)
            forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            record.ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '-')
            record.method = request.method
            record.path = request.get_full_path()
        return True
