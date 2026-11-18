"""Filtres des écrans ML COD Plateforme : {% load mlcod %}"""
from decimal import Decimal, InvalidOperation

from django import template

from mlshipafrica.enums import STATUT_TRAITEMENT_CLASSES

register = template.Library()


@register.filter
def fcfa(valeur):
    """12500 → « 12 500 F » (espace fine insécable, signe moins typographique), comme dans la maquette."""
    try:
        n = int(Decimal(str(valeur if valeur not in (None, '') else 0)).quantize(Decimal('1')))
    except (InvalidOperation, ValueError):
        return valeur
    chiffres = '{:,}'.format(abs(n)).replace(',', ' ')
    return ('− ' if n < 0 else '') + chiffres + ' F'


@register.filter
def st_classe(statut):
    """Classe du badge d'un statut (st-livre, st-echec…)."""
    return STATUT_TRAITEMENT_CLASSES.get(str(statut), 'b-mute')


@register.filter
def couleur_taux(taux):
    """Vert à partir de 80 %, orange de 75 à 79 %, rouge en dessous, gris sans donnée."""
    if taux is None:
        return 'var(--line)'
    return 'var(--ok)' if taux >= 80 else 'var(--warn)' if taux >= 75 else 'var(--bad)'


@register.filter
def get_item(dico, cle):
    """{{ comptes|get_item:statut }} : valeur d'un dictionnaire par sa clé."""
    return dico.get(cle) if hasattr(dico, 'get') else None


@register.filter
def qr(valeur):
    """QR code SVG généré par le serveur (aucun CDN) : {{ article.code|qr }}."""
    from django.utils.safestring import mark_safe
    from management.qrcode_svg import svg
    if not valeur:
        return ''
    try:
        return mark_safe(svg(str(valeur)))
    except ValueError:
        return ''
