"""
Texte des SMS : alphabet GSM 03.38, nettoyage des caractères qui forcent l'Unicode, segments facturés.

Un SMS GSM-7 fait 160 caractères (153 par segment s'il est découpé). En Unicode : 70 (67 par segment).
Un seul caractère hors alphabet (’, ê, ç, ô, emoji…) fait passer tout le message en Unicode et peut
doubler ou tripler le coût : on remplace ces caractères avant d'envoyer.
"""
import re

GSM7_BASIQUE = (
    '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?'
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
)
GSM7_EXTENSION = '^{}\\[~]|€\f'  # valides, mais comptent double

REMPLACEMENTS = {
    '’': "'", '‘': "'", '‚': "'", '´': "'", '`': "'",
    '“': '"', '”': '"', '„': '"', '«': '"', '»': '"',
    '–': '-', '—': '-', '‐': '-', '‑': '-', '−': '-',
    '…': '...', ' ': ' ', ' ': ' ', ' ': ' ', '​': '',
    'ê': 'e', 'ë': 'e', 'ē': 'e', 'Ê': 'E', 'Ë': 'E', 'È': 'E',
    'â': 'a', 'á': 'a', 'ã': 'a', 'Â': 'A', 'À': 'A', 'Á': 'A',
    'î': 'i', 'ï': 'i', 'í': 'i', 'Î': 'I', 'Ï': 'I',
    'ô': 'o', 'ó': 'o', 'õ': 'o', 'Ô': 'O', 'Ò': 'O', 'Ó': 'O',
    'û': 'u', 'ú': 'u', 'Û': 'U', 'Ù': 'U', 'Ú': 'U',
    'ç': 'c', 'œ': 'oe', 'Œ': 'OE', 'ÿ': 'y',
}


def est_gsm7(texte):
    return all(c in GSM7_BASIQUE or c in GSM7_EXTENSION for c in str(texte))


def nettoyer(texte):
    sortie = ''.join(REMPLACEMENTS.get(c, c) for c in str(texte))
    return re.sub(r'[ \t]{2,}', ' ', sortie).strip()


def segments(texte):
    """(encodage, unités, segments facturés)"""
    texte = str(texte)
    if est_gsm7(texte):
        unites = sum(2 if c in GSM7_EXTENSION else 1 for c in texte)
        return 'gsm7', unites, 1 if unites <= 160 else -(-unites // 153)
    unites = sum(2 if ord(c) > 0xFFFF else 1 for c in texte)
    return 'unicode', unites, 1 if unites <= 70 else -(-unites // 67)


def preparer(texte):
    """Texte nettoyé + indication Unicode + nombre de segments."""
    propre = nettoyer(texte)
    encodage, _, nb = segments(propre)
    return propre, encodage == 'unicode', nb


def remplir(modele, variables):
    """« {colis} » → valeur. Une variable inconnue reste visible pour être repérée en recette."""
    return re.sub(r'\{(\w+)\}', lambda m: str(variables[m.group(1)]) if variables.get(m.group(1)) is not None else m.group(0),
                  str(modele or ''))


def montant_f(valeur):
    """12500 → « 12 500 F »"""
    return '{:,}'.format(int(round(float(valeur or 0)))).replace(',', ' ') + ' F'
