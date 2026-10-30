"""
Client de l'API HSMS (https://www.hsms.ci/doc-api/), sans dépendance externe (urllib).

Authentification à deux niveaux :
  1. jeton Bearer obtenu par POST /api/token/ (email + mot de passe du compte HSMS), réutilisable :
     on le garde en base (SmsParametres.jeton_api) et on le renouvelle sur 401 ;
  2. clientid + clientsecret de l'application HSMS, dans le corps de chaque appel.

Les identifiants viennent des variables d'environnement (fichier .env), jamais de la base ni du navigateur :
  HSMS_EMAIL, HSMS_PASSWORD, HSMS_CLIENT_ID, HSMS_CLIENT_SECRET, HSMS_BASE_URL (facultatif).

À vérifier en recette : la documentation HSMS ne montre pas la réponse exacte de l'envoi.
`extraire_tickets` lit les formes les plus probables et la réponse brute est toujours gardée
(SmsMessage.reponse_fournisseur) pour corriger sans perte.
"""
import json
import socket
import urllib.error
import urllib.request

from decouple import config

URL_PAR_DEFAUT = 'https://www.hsms.ci/api'


class ErreurHsms(Exception):
    """genre : auth, numero_invalide, solde_insuffisant, application_inactive, requete, serveur, reseau, delai, limite"""

    REESSAYABLES = ('serveur', 'reseau', 'delai', 'limite')
    BLOQUANTES = ('solde_insuffisant', 'application_inactive', 'auth')

    def __init__(self, message, genre, statut_http=None, corps=None):
        super().__init__(message)
        self.genre = genre
        self.statut_http = statut_http
        self.corps = corps

    @property
    def reessayable(self):
        return self.genre in self.REESSAYABLES

    @property
    def met_en_pause(self):
        """Problème de compte (pas du message) : on suspend toute la file."""
        return self.genre in self.BLOQUANTES


def classer(statut_http, corps):
    corps = corps if isinstance(corps, dict) else {}
    texte = (str(corps.get('message') or corps.get('detail') or '') + json.dumps(corps.get('errors') or {})).lower()
    if statut_http in (401, 403):
        return 'auth'
    if statut_http == 429:
        return 'limite'
    if statut_http >= 500:
        return 'serveur'
    if any(m in texte for m in ('solde', 'insuffisant', 'balance', 'credit')):
        return 'solde_insuffisant'
    if any(m in texte for m in ('inactive', 'désactiv', 'desactiv')):
        return 'application_inactive'
    if any(m in texte for m in ('numero', 'numéro', 'telephone', 'téléphone', 'phone')):
        return 'numero_invalide'
    return 'requete'


def extraire_tickets(corps):
    if not isinstance(corps, (dict, list)):
        return []
    if isinstance(corps, list):
        return [str(t.get('ticket') or t.get('id')) for t in corps if isinstance(t, dict) and (t.get('ticket') or t.get('id'))]
    for source in (corps, corps.get('data'), corps.get('result')):
        if isinstance(source, list):
            return extraire_tickets(source)
        if not isinstance(source, dict):
            continue
        if isinstance(source.get('ticket'), (str, int)):
            return [str(source['ticket'])]
        for cle in ('tickets', 'messages'):
            if isinstance(source.get(cle), list):
                return [str(t.get('ticket') or t.get('id')) if isinstance(t, dict) else str(t) for t in source[cle]]
    return []


class ClientHsms:
    def __init__(self, email=None, mot_de_passe=None, client_id=None, client_secret=None, url=None,
                 jeton=None, sur_nouveau_jeton=None, delai_secondes=15, transport=None):
        self.email = email if email is not None else config('HSMS_EMAIL', default='')
        self.mot_de_passe = mot_de_passe if mot_de_passe is not None else config('HSMS_PASSWORD', default='')
        self.client_id = client_id if client_id is not None else config('HSMS_CLIENT_ID', default='')
        self.client_secret = client_secret if client_secret is not None else config('HSMS_CLIENT_SECRET', default='')
        self.url = (url or config('HSMS_BASE_URL', default=URL_PAR_DEFAUT)).rstrip('/')
        self.jeton = jeton or None
        self.sur_nouveau_jeton = sur_nouveau_jeton
        self.delai = delai_secondes
        self._transport = transport or self._transport_urllib

    @property
    def configure(self):
        return all((self.email, self.mot_de_passe, self.client_id, self.client_secret))

    # -- bas niveau ---------------------------------------------------------

    def _transport_urllib(self, url, corps, entetes):
        requete = urllib.request.Request(url, data=json.dumps(corps).encode('utf-8'), method='POST', headers=entetes)
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as reponse:
                return reponse.status, reponse.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        except (socket.timeout, TimeoutError) as e:
            raise ErreurHsms('HSMS ne répond pas (%s)' % e, 'delai')
        except urllib.error.URLError as e:
            genre = 'delai' if isinstance(getattr(e, 'reason', None), socket.timeout) else 'reseau'
            raise ErreurHsms('HSMS injoignable (%s)' % e, genre)

    def _brut(self, chemin, corps, entetes=None):
        tout = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        tout.update(entetes or {})
        statut, texte = self._transport(self.url + chemin, corps, tout)
        try:
            donnees = json.loads(texte) if texte else None
        except ValueError:
            donnees = {'brut': texte[:500]}
        return statut, donnees

    def obtenir_jeton(self, forcer=False):
        if self.jeton and not forcer:
            return self.jeton
        statut, corps = self._brut('/token/', {'email': self.email, 'password': self.mot_de_passe})
        jeton = None
        if isinstance(corps, dict):
            jeton = corps.get('token')
            if not jeton and isinstance(corps.get('data'), dict):
                jeton = corps['data'].get('token')
        if statut >= 300 or not jeton:
            raise ErreurHsms('HSMS : connexion refusée (email ou mot de passe)', 'auth', statut, corps)
        self.jeton = jeton
        if self.sur_nouveau_jeton:
            self.sur_nouveau_jeton(jeton)
        return jeton

    def _appel(self, chemin, donnees):
        if not self.configure:
            raise ErreurHsms('HSMS non configuré (variables HSMS_* manquantes)', 'auth')
        corps = {'clientid': self.client_id, 'clientsecret': self.client_secret}
        corps.update(donnees)
        for essai in range(2):
            jeton = self.obtenir_jeton(forcer=essai > 0)
            statut, reponse = self._brut(chemin, corps, {'Authorization': 'Bearer ' + jeton})
            if statut == 401 and essai == 0:
                continue
            ok = statut < 300 and not (isinstance(reponse, dict) and reponse.get('success') is False)
            if ok:
                return reponse if reponse is not None else {}
            message = reponse.get('message') if isinstance(reponse, dict) else None
            raise ErreurHsms('HSMS : %s' % (message or 'erreur %s' % statut), classer(statut, reponse), statut, reponse)
        raise ErreurHsms('HSMS : jeton refusé après renouvellement', 'auth', 401)

    # -- API ------------------------------------------------------------------

    def envoyer(self, telephone, message, unicode=False):
        """Renvoie (tickets, réponse brute)."""
        donnees = {'telephone': telephone, 'message': message}
        if unicode:
            donnees['unicode'] = True
        reponse = self._appel('/envoi-sms', donnees)
        return extraire_tickets(reponse), reponse

    def accuses(self, tickets):
        """Statuts de livraison de tickets précis (50 au plus par appel)."""
        return self._appel('/envoi-sms/notifications', {'tickets': list(tickets)[:50], 'max': 50})

    def solde(self):
        reponse = self._appel('/check-sms', {})
        source = reponse.get('data') if isinstance(reponse, dict) and isinstance(reponse.get('data'), dict) else reponse
        source = source if isinstance(source, dict) else {}
        for cle in ('SMS disponibles', 'sms_disponibles', 'sms'):
            if source.get(cle) is not None:
                try:
                    return int(float(source[cle])), reponse
                except (TypeError, ValueError):
                    break
        return None, reponse
