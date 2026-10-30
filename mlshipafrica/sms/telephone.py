"""
Numéros de Côte d'Ivoire au format attendu par HSMS : 225 + 10 chiffres, sans « + » ni espace.
« 07 08 09 10 11 » → « 2250708091011 ».

Depuis 2021 : 10 chiffres ; mobiles 01 (Moov), 05 (MTN), 07 (Orange) ; fixes 21, 25, 27 (pas de SMS).
"""
import re

PREFIXES_MOBILES = ('01', '05', '07')


def normaliser_ci(numero):
    """Renvoie (msisdn, None) ou (None, raison)."""
    if numero is None or str(numero).strip() == '':
        return None, 'numéro manquant'
    # PhoneNumber (django-phonenumber-field) ou texte
    brut = getattr(numero, 'as_e164', None) or str(numero)
    chiffres = re.sub(r'[^\d+]', '', brut)
    if chiffres.startswith('+'):
        chiffres = chiffres[1:]
    if chiffres.startswith('00'):
        chiffres = chiffres[2:]
    if chiffres.startswith('225') and len(chiffres) == 13:
        chiffres = chiffres[3:]
    if len(chiffres) != 10:
        return None, 'le numéro doit avoir 10 chiffres'
    if chiffres[:2] not in PREFIXES_MOBILES:
        return None, 'pas un numéro mobile (01, 05 ou 07)'
    return '225' + chiffres, None
