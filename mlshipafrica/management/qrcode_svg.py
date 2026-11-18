"""
QR code en SVG, généré par le serveur, sans bibliothèque ni CDN : les étiquettes, factures et feuilles de route
s'impriment avec leur QR code même hors ligne.

Encodage octet (UTF-8), correction M (15 %), versions 1 à 10 (jusqu'à 213 octets : largement assez pour un code
colis ou un numéro de bordereau). Algorithme standard ISO/IEC 18004 (même logique que la bibliothèque de référence
« QR Code generator » de Nayuki).
"""
from functools import lru_cache

ECC_PAR_BLOC = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]   # niveau M, versions 1 à 10
NB_BLOCS = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
FORMAT_M = 0


def _modules_bruts(v):
    r = (16 * v + 128) * v + 64
    if v >= 2:
        n = v // 7 + 2
        r -= (25 * n - 10) * n - 55
        if v >= 7:
            r -= 36
    return r


def _octets_donnees(v):
    return _modules_bruts(v) // 8 - ECC_PAR_BLOC[v] * NB_BLOCS[v]


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


@lru_cache(maxsize=None)
def _diviseur(degre):
    r = [0] * (degre - 1) + [1]
    racine = 1
    for _ in range(degre):
        for j in range(degre):
            r[j] = _gf_mul(r[j], racine)
            if j + 1 < degre:
                r[j] ^= r[j + 1]
        racine = _gf_mul(racine, 0x02)
    return tuple(r)


def _reste(donnees, diviseur):
    r = [0] * len(diviseur)
    for b in donnees:
        f = b ^ r.pop(0)
        r.append(0)
        for i, c in enumerate(diviseur):
            r[i] ^= _gf_mul(c, f)
    return r


def _positions_alignement(v, taille):
    if v == 1:
        return []
    n = v // 7 + 2
    pas = (v * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    res = [6]
    pos = taille - 7
    for _ in range(n - 1):
        res.insert(1, pos)
        pos -= pas
    return res


def matrice(texte):
    """Texte → matrice carrée de booléens (True = module noir)."""
    data = texte.encode('utf-8')
    for v in range(1, 11):
        bits_compteur = 8 if v <= 9 else 16
        if 4 + bits_compteur + 8 * len(data) <= _octets_donnees(v) * 8:
            break
    else:
        raise ValueError("Texte trop long pour le QR code")
    # --- flux de bits
    bits = []
    def ajouter(val, n):
        bits.extend((val >> i) & 1 for i in reversed(range(n)))
    ajouter(0b0100, 4)
    ajouter(len(data), bits_compteur)
    for b in data:
        ajouter(b, 8)
    capacite = _octets_donnees(v) * 8
    ajouter(0, min(4, capacite - len(bits)))
    ajouter(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < capacite:
        ajouter(pad, 8)
        pad ^= 0xEC ^ 0x11
    octets = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    # --- blocs + correction d'erreurs, entrelacés
    nb, ecc = NB_BLOCS[v], ECC_PAR_BLOC[v]
    bruts = _modules_bruts(v) // 8
    courts = nb - bruts % nb
    long_court = bruts // nb
    div = _diviseur(ecc)
    blocs, k = [], 0
    for i in range(nb):
        n = long_court - ecc + (0 if i < courts else 1)
        dat = octets[k:k + n]
        k += n
        bloc = dat + _reste(dat, div)
        if i < courts:
            bloc.insert(long_court - ecc, None)
        blocs.append(bloc)
    final = []
    for i in range(len(blocs[0])):
        for j, bloc in enumerate(blocs):
            if i != long_court - ecc or j >= courts:
                final.append(bloc[i])
    # --- motifs fixes
    taille = v * 4 + 17
    m = [[False] * taille for _ in range(taille)]
    fixe = [[False] * taille for _ in range(taille)]

    def poser(x, y, noir):
        m[y][x] = noir
        fixe[y][x] = True

    for i in range(taille):
        poser(6, i, i % 2 == 0)
        poser(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (taille - 4, 3), (3, taille - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < taille and 0 <= y < taille:
                    poser(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _positions_alignement(v, taille)
    for i, ax in enumerate(al):
        for j, ay in enumerate(al):
            if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    poser(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def format_bits(masque):
        d = FORMAT_M << 3 | masque
        r = d
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        return (d << 10 | r) ^ 0x5412

    def dessiner_format(masque):
        b = format_bits(masque)
        bit = lambda i: (b >> i) & 1 == 1
        for i in range(6):
            poser(8, i, bit(i))
        poser(8, 7, bit(6))
        poser(8, 8, bit(7))
        poser(7, 8, bit(8))
        for i in range(9, 15):
            poser(14 - i, 8, bit(i))
        for i in range(8):
            poser(taille - 1 - i, 8, bit(i))
        for i in range(8, 15):
            poser(8, taille - 15 + i, bit(i))
        poser(8, taille - 8, True)

    dessiner_format(0)                       # réserve les zones de format
    if v >= 7:
        r = v
        for _ in range(12):
            r = (r << 1) ^ ((r >> 11) * 0x1F25)
        b = v << 12 | r
        for i in range(18):
            noir = (b >> i) & 1 == 1
            a, c = taille - 11 + i % 3, i // 3
            poser(a, c, noir)
            poser(c, a, noir)
    # --- données en zigzag
    i = 0
    droite = taille - 1
    while droite >= 1:
        if droite == 6:
            droite = 5
        for vert in range(taille):
            for j in range(2):
                x = droite - j
                y = taille - 1 - vert if ((droite + 1) & 2) == 0 else vert
                if not fixe[y][x] and i < len(final) * 8:
                    m[y][x] = (final[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        droite -= 2
    # --- masque : le moins pénalisant
    conditions = [
        lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    ]
    base = [row[:] for row in m]
    meilleur, score_min = None, None
    for k, cond in enumerate(conditions):
        for y in range(taille):
            for x in range(taille):
                m[y][x] = base[y][x] ^ (not fixe[y][x] and cond(x, y))
        dessiner_format(k)
        s = _penalite(m)
        if score_min is None or s < score_min:
            meilleur, score_min = [row[:] for row in m], s
    return meilleur


def _penalite(m):
    n = len(m)
    p = 0
    for lignes in (m, [list(c) for c in zip(*m)]):
        for row in lignes:
            run, prec = 0, None
            for c in row:
                if c == prec:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prec = 1, c
            if run >= 5:
                p += run - 2
            s = ''.join('1' if c else '0' for c in row)
            p += 40 * (s.count('1011101') if ('00001011101' in s or '10111010000' in s) else 0)
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                p += 3
    noirs = sum(sum(r) for r in m)
    p += abs(noirs * 20 - n * n * 10) // (n * n) * 10
    return p


@lru_cache(maxsize=2048)
def svg(texte, bord=2):
    """SVG carré, mis à l'échelle par le CSS (largeur/hauteur 100 %)."""
    mat = matrice(str(texte))
    n = len(mat) + 2 * bord
    chemins = ''.join('M%d %dh1v1h-1z' % (x + bord, y + bord) for y, row in enumerate(mat) for x, c in enumerate(row) if c)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" shape-rendering="crispEdges" '
            'role="img" aria-label="QR code %s"><rect width="100%%" height="100%%" fill="#fff"/>'
            '<path d="%s" fill="#000"/></svg>') % (n, n, str(texte).replace('"', ''), chemins)
