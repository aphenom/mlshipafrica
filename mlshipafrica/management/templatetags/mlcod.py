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


def texte_qr_commande(a):
    """Les informations de la commande lues par n'importe quel lecteur de QR code (la 1re ligne reste le code)."""
    montant = '{:,.0f} F'.format(a.valeur_totale or 0).replace(',', ' ') if a.is_option_encaissement else 'rien (payé)'
    lignes = [a.code, 'ML COD Intérieur',
              'Client : %s' % ('%s %s' % (a.nom_destinataire or '', a.prenom_destinataire or '')).strip()[:40],
              'Tél : %s' % (a.numero_principal_destinataire or ''),
              'Ville : %s' % (a.localite_arrivee.nom if a.localite_arrivee_id else ''),
              'Produit : %s x%s' % (((a.produit_stock.designation if a.produit_stock_id else a.designation) or '')[:30], a.quantite or 1),
              'À encaisser : %s' % montant]
    return '\n'.join(lignes)


@register.filter
def qr_commande(article):
    """{{ article|qr_commande }} : QR code avec les informations de la commande."""
    from django.utils.safestring import mark_safe
    from management.qrcode_svg import svg
    try:
        return mark_safe(svg(texte_qr_commande(article)))
    except ValueError:
        return qr(article.code)
