"""
Lecture du fichier hebdomadaire du prestataire : Excel (.xlsx, export Google Sheets compris) ou CSV.

Le fichier est lu tel que le prestataire l'envoie : une ligne d'en-tête (« Numéro de commande », « Montant »,
« Statut », « date de retrait », « Agent »…) n'importe où dans les premières lignes, une commande par ligne, et
des commentaires de suivi posés sur les cellules (« 07… le bon numéro », « client indisponible »…).

Aucune dépendance : un .xlsx est un zip de fichiers XML, lu ici avec la bibliothèque standard.

Attention aux colonnes : « Montant » est ce que le client paie à la livraison (à encaisser), PAS ce que le
prestataire nous facture. Le coût facturé n'est lu que dans une colonne explicitement nommée coût / frais /
facturé ; sans cette colonne, aucun coût n'est modifié.
"""
import csv
import io
import posixpath
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
TYPE_COMMENTAIRES = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'

# Nom du prestataire : jamais affiché ni enregistré (clients, vendeurs et équipe ne doivent pas le voir).
# Le nom n'est pas dans le code (dépôt public) : il est lu dans le .env, NOMS_A_MASQUER=nom1,nom2.


def _masque():
    from django.conf import settings
    noms = [n.strip() for n in getattr(settings, 'NOMS_A_MASQUER', []) if n and n.strip()]
    if not noms:
        return None
    motif = '|'.join(r'\s*'.join(re.escape(c) for c in nom) for nom in noms)
    return re.compile(r'\b(?:%s)\b\s*(?:[-/:._]\s*)?' % motif, re.IGNORECASE)


def masquer(texte):
    texte = str(texte or '')
    masque = _masque()
    if masque is not None:
        texte = re.sub(r'[(\[]\s*[)\]]', '', masque.sub('', texte))
    return re.sub(r'\s{2,}', ' ', texte).strip(' :-/')


def norm(texte):
    texte = unicodedata.normalize('NFD', str(texte or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', texte).strip()


# ----------------------------------------------------------------------------------------------- colonnes

COLONNES = {
    'numero': ('numero de commande', 'n commande', 'no commande', 'numero commande', 'id commande', 'commande', 'numero',
               'reference', 'ref', 'tracking', 'code tracking', 'code', 'code colis', 'id'),
    'cout': ('cout', 'cout facture', 'cout prestataire', 'frais', 'frais prestataire', 'frais de livraison', 'facture',
             'montant facture', 'tarif', 'prix livraison'),
    'montant': ('montant', 'montant a encaisser', 'a encaisser', 'reste a payer', 'total a payer', 'prix', 'amount', 'valeur'),
    'agent': ('agent', 'livreur', 'agent cod'),
    'statut': ('statut', 'status', 'etat'),
    'date_retrait': ('date de retrait', 'date de retait', 'date retrait', 'date de livraison', 'date livraison', 'date'),
    'type_livraison': ('type de livraison', 'type'),
    'infos': ('adresse de livraison detaillee', 'adresse', 'infos', 'informations', 'observation', 'observations', 'commentaire', 'details'),
    'produit': ('produit', 'article', 'designation', 'produits'),
    'ville': ('ville', 'destination', 'localite'),
}


def _role(entete):
    n = norm(entete)
    if not n:
        return None
    if n.startswith('agent') or n.startswith('livreur'):
        return 'agent'
    for role, noms in COLONNES.items():
        if n in noms:
            return role
    for role, noms in COLONNES.items():  # « Montant  » , « Statut colis », « Numéro de commande ML »
        if any(n.startswith(nom + ' ') for nom in noms if len(nom) > 3):
            return role
    return None


def _entetes(ligne):
    roles = {}
    for i, valeur in enumerate(ligne):
        role = _role(valeur)
        if role and role not in roles:
            roles[role] = i
    return roles if 'numero' in roles else None


# ----------------------------------------------------------------------------------------------- valeurs

def montant(valeur):
    if valeur in (None, ''):
        return None
    if isinstance(valeur, (int, float, Decimal)):
        return Decimal(str(valeur)).quantize(Decimal('1'))
    texte = re.sub(r'[^\d,.\-]', '', str(valeur)).replace(',', '.')
    if texte.count('.') > 1 or re.fullmatch(r'\d{1,3}\.\d{3}', texte):
        texte = texte.replace('.', '')  # 16.500 → 16500
    try:
        return Decimal(texte).quantize(Decimal('1')) if texte not in ('', '-', '.') else None
    except InvalidOperation:
        return None


def numero(valeur):
    if valeur is None:
        return ''
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    texte = str(valeur).strip()
    return texte[:-2] if re.fullmatch(r'\d+\.0', texte) else texte


def date_retrait(valeur):
    if valeur in (None, ''):
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, (int, float)) or re.fullmatch(r'\d{5}(\.\d+)?', str(valeur).strip()):
        return date(1899, 12, 30) + timedelta(days=int(float(valeur)))  # numéro de série Excel
    m = re.search(r'(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})', str(valeur))
    if m:
        j, mois, a = (int(x) for x in m.groups())
        a = a + 2000 if a < 100 else a
        try:
            return date(a, mois, j)
        except ValueError:
            return None
    return None


def commentaires(texte):
    """Texte d'un commentaire Excel → liste de messages (le premier, puis les réponses)."""
    texte = str(texte or '').replace('\r', '')
    if 'Comment:' in texte or 'Reply:' in texte:
        morceaux = re.split(r'^(?:Comment|Reply):\s*$', texte, flags=re.M)[1:]
    else:
        morceaux = [re.sub(r'^[^\n:]{1,60}:\n', '', texte)]  # note simple « Auteur:\ntexte »
    return [masquer(re.sub(r'\s+', ' ', m)) for m in morceaux if m.strip()]


# ----------------------------------------------------------------------------------------------- xlsx

def _col(ref):
    n = 0
    for c in re.match(r'[A-Z]+', ref).group():
        n = n * 26 + ord(c) - 64
    return n - 1


def _cible(base, cible):
    return cible.lstrip('/') if cible.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(base), cible))


def _texte(noeud):
    return ''.join(t.text or '' for t in noeud.iter('{%s}t' % NS['m']))


def lire_xlsx(contenu):
    """→ liste d'onglets : {'nom', 'lignes': [[valeurs]], 'commentaires': {(ligne, col): [messages]}}"""
    try:
        z = zipfile.ZipFile(io.BytesIO(contenu))
        classeur = ET.fromstring(z.read('xl/workbook.xml'))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError("Fichier Excel illisible.")
    noms = set(z.namelist())
    partages = []
    if 'xl/sharedStrings.xml' in noms:
        partages = [_texte(si) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS)]
    liens = {r.get('Id'): _cible('xl/workbook.xml', r.get('Target'))
             for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')).findall('rel:Relationship', NS)}
    onglets = []
    for feuille in classeur.find('m:sheets', NS).findall('m:sheet', NS):
        chemin = liens.get(feuille.get('{%s}id' % NS['r']))
        if not chemin or chemin not in noms:
            continue
        lignes = {}
        for c in ET.fromstring(z.read(chemin)).iter('{%s}c' % NS['m']):
            ref, t = c.get('r'), c.get('t')
            v = c.find('m:v', NS)
            if t == 's' and v is not None:
                valeur = partages[int(v.text)]
            elif t == 'inlineStr':
                valeur = _texte(c)
            elif v is None or v.text is None:
                continue
            elif t in ('str', 'e'):
                valeur = v.text
            elif t == 'b':
                valeur = v.text == '1'
            else:
                try:
                    valeur = float(v.text)
                except ValueError:
                    valeur = v.text
            ligne = int(re.search(r'\d+', ref).group()) - 1
            lignes.setdefault(ligne, {})[_col(ref)] = valeur
        notes = {}
        rels = posixpath.join(posixpath.dirname(chemin), '_rels', posixpath.basename(chemin) + '.rels')
        if rels in noms:
            for r in ET.fromstring(z.read(rels)).findall('rel:Relationship', NS):
                if r.get('Type') == TYPE_COMMENTAIRES and _cible(chemin, r.get('Target')) in noms:
                    for com in ET.fromstring(z.read(_cible(chemin, r.get('Target')))).iter('{%s}comment' % NS['m']):
                        ref = com.get('ref')
                        cle = (int(re.search(r'\d+', ref).group()) - 1, _col(ref))
                        notes[cle] = commentaires(_texte(com.find('m:text', NS)))
        largeur = max([max(l) + 1 for l in lignes.values()] or [0])
        tableau = [[lignes.get(i, {}).get(j) for j in range(largeur)] for i in range(max(lignes) + 1 if lignes else 0)]
        onglets.append({'nom': feuille.get('name'), 'lignes': tableau, 'commentaires': notes})
    return onglets


def lire_csv(contenu):
    texte = contenu.decode('utf-8-sig', errors='replace') if isinstance(contenu, bytes) else contenu
    if not texte.strip():
        return []
    try:
        dialecte = csv.Sniffer().sniff(texte[:4000], delimiters=';,\t')
    except csv.Error:
        dialecte = csv.excel
    return [{'nom': 'CSV', 'lignes': list(csv.reader(io.StringIO(texte), dialect=dialecte)), 'commentaires': {}}]


# ----------------------------------------------------------------------------------------------- commandes

def commandes(onglet):
    """Lignes de commande d'un onglet : dictionnaires prêts à rapprocher. None si l'onglet n'a pas d'en-tête reconnu."""
    lignes = onglet['lignes']
    for i, ligne in enumerate(lignes[:15]):
        roles = _entetes(ligne)
        if roles:
            break
    else:
        return None

    def cell(ligne, role):
        j = roles.get(role)
        return ligne[j] if j is not None and j < len(ligne) else None

    sortie = []
    for k, ligne in enumerate(lignes[i + 1:], start=i + 1):
        num = numero(cell(ligne, 'numero'))
        if not num or norm(num) in ('total', 'totaux'):
            continue
        notes = []
        for (l, _c), messages in sorted(onglet['commentaires'].items()):
            if l == k:
                notes.extend(messages)
        sortie.append({
            'rang': k + 1, 'numero': num[:100],
            'montant': montant(cell(ligne, 'montant')), 'cout': montant(cell(ligne, 'cout')) if 'cout' in roles else None,
            'agent': masquer(cell(ligne, 'agent'))[:100], 'statut': str(cell(ligne, 'statut') or '').strip()[:60],
            'date_retrait': date_retrait(cell(ligne, 'date_retrait')),
            'type_livraison': masquer(cell(ligne, 'type_livraison'))[:255], 'infos': masquer(cell(ligne, 'infos')),
            'produit': masquer(cell(ligne, 'produit'))[:255], 'ville': masquer(cell(ligne, 'ville'))[:100],
            'commentaires': notes,
        })
    return sortie


def lire(nom_fichier, contenu, onglet=''):
    """→ (nom de l'onglet lu, commandes). Par défaut : le dernier onglet qui contient des commandes."""
    xlsx = contenu[:2] == b'PK'
    onglets = lire_xlsx(contenu) if xlsx else lire_csv(contenu)
    if onglet:
        choisis = [o for o in onglets if norm(o['nom']) == norm(onglet)]
        if not choisis:
            raise ValueError("Onglet « %s » introuvable. Onglets du fichier : %s." % (onglet, ', '.join(o['nom'] for o in onglets)))
        onglets = choisis
    for o in reversed(onglets):
        lignes = commandes(o)
        if lignes:
            return o['nom'], lignes
    raise ValueError("Aucune commande trouvée : il faut une colonne « Numéro de commande » (ou référence, code, tracking).")


# ----------------------------------------------------------------------------------------------- statuts

def famille_prestataire(statut):
    n = norm(statut)
    if not n:
        return ''
    if 'retour' in n or 'retourne' in n:
        return 'retour'
    if 'annul' in n:
        return 'annule'
    if n.startswith('livre') or n in ('retire', 'remis', 'paye'):
        return 'livre'
    if 'echec' in n or 'injoignable' in n or 'refus' in n:
        return 'echec'
    if 'arriv' in n:
        return 'arrive'
    if 'transit' in n or 'expedi' in n or 'route' in n:
        return 'transit'
    if 'cours' in n or 'livraison' in n:
        return 'livraison'
    return 'autre'
