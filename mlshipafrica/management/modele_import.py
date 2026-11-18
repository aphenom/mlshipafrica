"""
Modèle Excel (.xlsx) d'import de commandes, propre à chaque vendeur.

Écrit à la main (XML + zip, sans dépendance) pour rester relu par lire_xlsx :
  - onglet « Commandes » (le seul lu à l'import) : en-têtes exacts, colonnes téléphone en texte (le 0 du début est
    gardé), listes déroulantes Ville / Format / oui-non / Référence stock ;
  - onglet « Listes » : villes desservies, formats, références de stock du vendeur (avec la quantité disponible) ;
  - onglet « Mode d'emploi » : règles et une ligne d'exemple (hors de l'onglet lu, pour ne jamais être importée).
"""
import io
import zipfile
from xml.sax.saxutils import escape

LIGNES_MAX = 500


def _lettre(i):
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cellule(ref, valeur, style=0):
    st = ' s="%d"' % style if style else ''
    if valeur is None or valeur == '':
        return '<c r="%s"%s/>' % (ref, st) if style else ''
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, st, valeur)
    return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, st, escape(str(valeur)))


def _feuille(lignes, largeurs=(), styles_ligne=None, figer=False, validations='', colonnes_texte=()):
    cols = ''.join('<col min="%d" max="%d" width="%s" customWidth="1"%s/>' % (
        i + 1, i + 1, w, ' style="3"' if i in colonnes_texte else '') for i, w in enumerate(largeurs))
    vue = ('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews>') if figer else '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    corps = []
    for i, ligne in enumerate(lignes):
        style = (styles_ligne or {}).get(i, 0)
        cells = ''.join(_cellule('%s%d' % (_lettre(j), i + 1), v, style or (3 if j in colonnes_texte and i else 0))
                        for j, v in enumerate(ligne))
        corps.append('<row r="%d">%s</row>' % (i + 1, cells))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '%s%s<sheetData>%s</sheetData>%s</worksheet>') % (
        vue, '<cols>%s</cols>' % cols if cols else '', ''.join(corps), validations)


def _liste(col, formule, titre, message):
    plage = '%s2:%s%d' % (col, col, LIGNES_MAX + 1)
    return ('<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" errorStyle="warning" '
            'promptTitle="%s" prompt="%s" errorTitle="Valeur inconnue" error="Choisissez dans la liste : sinon la ligne sera refusée." '
            'sqref="%s"><formula1>%s</formula1></dataValidation>') % (escape(titre, {'"': '&quot;'}), escape(message, {'"': '&quot;'}),
                                                                       plage, escape(formule))


def modele_xlsx(colonnes, villes, formats, stocks):
    """colonnes = COLONNES de import_commandes ; villes/formats = noms ; stocks = [(référence, désignation, disponible)]."""
    cles = [c for c, _, _ in colonnes]
    pos = {c: _lettre(i) for i, c in enumerate(cles)}
    texte = [cles.index(c) for c in ('telephone', 'telephone2', 'reference', 'ref_stock') if c in cles]

    n_v, n_f, n_s = max(len(villes), 1), max(len(formats), 1), max(len(stocks), 1)
    validations = [
        _liste(pos['ville'], 'Listes!$A$2:$A$%d' % (n_v + 1), 'Ville', 'Choisissez une ville desservie.'),
        _liste(pos['format'], 'Listes!$B$2:$B$%d' % (n_f + 1), 'Format', 'Vide = Petit.'),
        _liste(pos['encaisser'], '"oui,non"', 'Encaisser', 'oui = le livreur encaisse le client. Vide = oui.'),
        _liste(pos['ramassage'], '"oui,non"', 'Ramassage', 'oui = nous passons chez vous. Vide = non (dépôt au bureau).'),
    ]
    if stocks:
        validations.append(_liste(pos['ref_stock'], 'Listes!$C$2:$C$%d' % (n_s + 1), 'Référence stock',
                                  'Seulement si le produit part de votre stock chez nous.'))
    validations = '<dataValidations count="%d">%s</dataValidations>' % (len(validations), ''.join(validations))
    largeurs = {'nom': 22, 'prenom': 16, 'telephone': 15, 'telephone2': 15, 'ville': 18, 'adresse': 24, 'produit': 26,
                'quantite': 10, 'prix': 18, 'format': 14, 'encaisser': 13, 'ramassage': 16, 'reference': 16, 'ref_stock': 16}
    commandes = _feuille([[l for _, l, _ in colonnes]], [largeurs.get(c, 14) for c in cles], {0: 1}, True, validations, texte)

    n = max(len(villes), len(formats), len(stocks))
    listes = [['Villes desservies', 'Formats', 'Mes références stock', 'Produit', 'Disponible']]
    for i in range(n):
        s = stocks[i] if i < len(stocks) else ('', '', '')
        listes.append([villes[i] if i < len(villes) else '', formats[i] if i < len(formats) else '', s[0], s[1],
                       s[2] if s[0] else ''])
    listes = _feuille(listes, (24, 14, 20, 30, 12), {0: 1}, True)

    exemple = dict(nom='Kouassi', prenom='Aya', telephone='0707070707', ville=villes[0] if villes else 'Bouaké',
                   adresse='Quartier Commerce', produit='Crème visage', quantite=2, prix=7500,
                   format=formats[0] if formats else 'Petit', encaisser='oui', ramassage='non', reference='CMD-001')
    aide = [
        ["Comment remplir le modèle ML COD Intérieur"],
        [''],
        ["1. Remplissez l'onglet « Commandes » : une ligne par commande, à partir de la ligne 2. Ne changez pas les en-têtes."],
        ["2. Les colonnes avec * sont obligatoires. Ville, Format, Encaisser, Ramassage : choisissez dans la liste déroulante."],
        ["3. Téléphone : tapez le numéro complet avec le 0 (ex. 0707070707). La colonne est en texte, le 0 est gardé."],
        ["4. Prix unitaire : le prix d'une pièce en F, sans espace ni « F ». Le total = prix × quantité."],
        ["5. Encaisser vide = oui (le livreur encaisse le client). Ramassage vide = non (vous déposez au bureau)."],
        ["6. Ma référence : votre numéro de commande. Une même référence ne peut servir qu'une fois."],
        ["7. Référence stock : seulement si le produit part de votre stock chez nous (voir l'onglet « Listes »)."],
        ["8. Enregistrez en .xlsx (ou .csv) puis envoyez le fichier : chaque ligne est vérifiée avant création."],
        [''],
        ["Exemple de ligne (à ne pas recopier dans « Commandes ») :"],
        [l for _, l, _ in colonnes],
        [exemple.get(c, '') for c in cles],
    ]
    aide = _feuille(aide, [largeurs.get(c, 14) for c in cles], {0: 1, 11: 1, 12: 2})

    feuilles = [('Commandes', commandes), ('Listes', listes), ("Mode d'emploi", aide)]
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/>'
              '<name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3A5F"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-'
                             'officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(len(feuilles)))
                   + '</Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(nom, {'"': '&quot;'}), i + 1, i + 1)
                             for i, (nom, _) in enumerate(feuilles)) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                             'worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(feuilles)))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                     'Target="styles.xml"/></Relationships>' % (len(feuilles) + 1))
        z.writestr('xl/styles.xml', styles)
        for i, (_, xml) in enumerate(feuilles):
            z.writestr('xl/worksheets/sheet%d.xml' % (i + 1), xml)
    return sortie.getvalue()
