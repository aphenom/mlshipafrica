"""
Import de commandes par le vendeur, au format de la plateforme (modèle Excel / CSV téléchargeable).

  1. Le vendeur télécharge le modèle, le remplit (une ligne par commande) et l'envoie.
  2. La plateforme vérifie chaque ligne (ville desservie, téléphone, produit, prix, stock) et affiche un aperçu.
  3. Il confirme : les commandes valides sont créées et envoyées (en attente de dépôt ou de ramassage), comme une
     commande saisie à la main ; les lignes en erreur sont listées pour être corrigées.
"""
import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render

from management.models import Article, ProduitStock, Vendeur
from mlshipafrica.enums import SourceCommande, StatutTraitement as S

MAX_LIGNES = 500
COLONNES = [
    ('nom', "Nom du client *", ('nom', 'nomclient', 'client', 'nomduclient')),
    ('prenom', "Prénom", ('prenom', 'prenoms')),
    ('telephone', "Téléphone *", ('telephone', 'tel', 'numero', 'contact', 'telephone1')),
    ('telephone2', "Téléphone 2", ('telephone2', 'tel2', 'autrenumero', 'numero2')),
    ('ville', "Ville *", ('ville', 'localite', 'destination', 'commune')),
    ('adresse', "Adresse / quartier", ('adresse', 'quartier', 'adressequartier', 'lieu')),
    ('produit', "Produit *", ('produit', 'designation', 'article', 'nomduproduit')),
    ('quantite', "Quantité", ('quantite', 'qte', 'qty')),
    ('prix', "Prix unitaire (F) *", ('prixunitaire', 'prix', 'prixunitairef', 'pu')),
    ('format', "Format (Petit, Moyen, Grand)", ('format', 'formatpetitmoyengrand', 'taille')),
    ('encaisser', "Encaisser (oui/non)", ('encaisser', 'encaisseroui', 'encaissernon', 'encaisserouinon', 'cod')),
    ('ramassage', "Ramassage chez moi (oui/non)", ('ramassage', 'ramassagechezmoi', 'ramassagechezmoiouinon')),
    ('reference', "Ma référence", ('mareference', 'reference', 'ref', 'numerocommande')),
    ('ref_stock', "Référence stock", ('referencestock', 'refstock')),
]


def _norm(texte):
    texte = unicodedata.normalize('NFKD', str(texte or ''))
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in texte if not unicodedata.combining(c)).lower())


def _oui(valeur, defaut):
    v = _norm(valeur)
    if not v:
        return defaut
    return v in ('oui', 'o', 'yes', 'y', '1', 'vrai', 'true', 'x')


def lire_fichier(nom, contenu):
    from management.fichier_prestataire import lire_csv, lire_xlsx
    onglets = lire_xlsx(contenu) if nom.lower().endswith('.xlsx') else lire_csv(contenu)
    if not onglets:
        raise ValueError("Fichier vide.")
    lignes = onglets[0]['lignes']
    for i, ligne in enumerate(lignes[:10]):
        roles = {}
        for j, cellule in enumerate(ligne):
            n = _norm(cellule)
            for cle, _, alias in COLONNES:
                if n in alias and cle not in roles:
                    roles[cle] = j
        if {'nom', 'telephone', 'ville', 'produit'} <= set(roles) and ('prix' in roles):
            donnees = []
            for k, l in enumerate(lignes[i + 1:], start=i + 2):
                d = {cle: (l[j] if j < len(l) else None) for cle, j in roles.items()}
                if not any(str(v or '').strip() for v in d.values()):
                    continue
                d['ligne'] = k
                donnees.append(d)
            return donnees
    raise ValueError("En-têtes non reconnus : utilisez le modèle (Nom du client, Téléphone, Ville, Produit, Prix unitaire…).")


def _texte(v, n):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()[:n]


def verifier(vendeur, donnees):
    """Chaque ligne → dict prêt à créer, ou erreurs. Rien n'est écrit."""
    from core.models import FormatArticle, Localite
    villes = {_norm(l.nom): l for l in Localite.objects.filter(license=vendeur.license, is_arrivee=True, etat_validation=True,
                                                                  etat_suppression=False)}
    formats = {_norm(f.nom): f for f in FormatArticle.objects.filter(license=vendeur.license, etat_suppression=False)}
    format_defaut = formats.get('petit') or next(iter(formats.values()), None)
    stock = {p.reference.lower(): p for p in ProduitStock.objects.filter(vendeur=vendeur, actif=True)} if vendeur.option_stockage else {}
    deja = set(Article.objects.filter(vendeur=vendeur, source=SourceCommande.DIRECTE, reference_externe__isnull=False,
                                      etat_suppression=False).values_list('reference_externe', flat=True))
    vues = set()
    lignes = []
    for d in donnees[:MAX_LIGNES]:
        erreurs = []
        nom, tel = _texte(d.get('nom'), 100), re.sub(r'[^\d+]', '', _texte(d.get('telephone'), 30))
        if not nom:
            erreurs.append("nom manquant")
        if len(re.sub(r'\D', '', tel)) < 8:
            erreurs.append("téléphone invalide")
        ville = villes.get(_norm(d.get('ville')))
        if ville is None:
            erreurs.append("ville non desservie : %s" % (_texte(d.get('ville'), 40) or 'vide'))
        produit = _texte(d.get('produit'), 100)
        if not produit:
            erreurs.append("produit manquant")
        try:
            quantite = int(float(str(d.get('quantite') or 1).replace(',', '.')))
            if quantite < 1:
                raise ValueError
        except ValueError:
            erreurs.append("quantité invalide")
            quantite = 1
        try:
            prix = Decimal(str(d.get('prix') or '').replace(' ', '').replace(' ', '').replace(',', '.'))
            if prix < 0:
                raise InvalidOperation
        except InvalidOperation:
            erreurs.append("prix invalide")
            prix = Decimal('0')
        fmt = formats.get(_norm(d.get('format'))) if _texte(d.get('format'), 30) else format_defaut
        if fmt is None:
            erreurs.append("format inconnu : %s" % _texte(d.get('format'), 30))
        produit_stock = None
        ref_stock = _texte(d.get('ref_stock'), 60)
        if ref_stock:
            produit_stock = stock.get(ref_stock.lower())
            if produit_stock is None:
                erreurs.append("référence stock inconnue : %s" % ref_stock)
            elif produit_stock.quantite_disponible < quantite:
                erreurs.append("stock insuffisant (%d disponible)" % produit_stock.quantite_disponible)
        reference = _texte(d.get('reference'), 80)
        if reference and reference in deja:
            erreurs.append("référence %s déjà utilisée (commande déjà créée)" % reference)
        elif reference and reference in vues:
            erreurs.append("référence %s en double dans le fichier" % reference)
        if reference:
            vues.add(reference)
        lignes.append({
            'ligne': d['ligne'], 'erreurs': erreurs, 'nom': nom, 'prenom': _texte(d.get('prenom'), 255), 'telephone': tel,
            'telephone2': re.sub(r'[^\d+]', '', _texte(d.get('telephone2'), 30)), 'ville': ville.nom if ville else _texte(d.get('ville'), 40),
            'ville_id': ville.pk if ville else None, 'adresse': _texte(d.get('adresse'), 255), 'produit': produit,
            'quantite': quantite, 'prix': str(prix), 'total': str(prix * quantite), 'format_id': fmt.pk if fmt else None,
            'format': fmt.nom if fmt else '', 'encaisser': _oui(d.get('encaisser'), True),
            'ramassage': _oui(d.get('ramassage'), False), 'reference': _texte(d.get('reference'), 80),
            'produit_stock_id': produit_stock.pk if produit_stock else None,
        })
    return lignes


@transaction.atomic
def creer(vendeur, lignes, user):
    from core.models import Configuration, Localite
    from management.stock import reserver_pour_commande
    conf = Configuration.objects.filter(license=vendeur.license, etat_suppression=False).order_by('-pk').first()
    depart = Localite.objects.filter(license=vendeur.license, is_depart=True, etat_suppression=False).first()
    creees, refus = [], []
    for l in lignes:
        if l['erreurs']:
            continue
        try:
            with transaction.atomic():
                a = Article(vendeur=vendeur, license=vendeur.license, config=conf, localite_depart=depart,
                            localite_arrivee_id=l['ville_id'], format_article_id=l['format_id'], valeur=Decimal(l['prix']),
                            quantite=l['quantite'], valeur_totale=Decimal(l['total']), designation=l['produit'],
                            nom_destinataire=l['nom'], prenom_destinataire=l['prenom'] or None,
                            numero_principal_destinataire=l['telephone'], numero_secondaire_destinataire=l['telephone2'] or None,
                            adresse_destinataire=l['adresse'] or None, reference_externe=l['reference'] or None,
                            is_option_encaissement=l['encaisser'] and vendeur.collecte_par_mlship is not False,
                            is_option_recuperation=l['ramassage'], produit_stock_id=l['produit_stock_id'],
                            produits=['autre'], etat_validation=False)
                a.save()                                            # brouillon : tarif et frais calculés
                reserver_pour_commande(a, user)
                a.statut_traitement = S.EN_ATTENTE_RAMASSAGE if a.is_option_recuperation else S.EN_ATTENTE_DEPOT
                a.save()
            creees.append(a)
        except ValidationError as e:
            refus.append("ligne %d : %s" % (l['ligne'], ' '.join(e.messages)))
        except IntegrityError:
            refus.append("ligne %d : référence %s déjà utilisée" % (l['ligne'], l['reference']))
    return creees, refus


def _vendeur(request):
    vendeur = Vendeur.objects.filter(user=request.user).first()
    if vendeur is None or request.user.is_staff or not vendeur.etat_approbation:
        raise Http404
    return vendeur


@login_required
def vendeur_import_colis(request):
    vendeur = _vendeur(request)
    if request.GET.get('modele'):
        reponse = HttpResponse(content_type='text/csv; charset=utf-8')
        reponse['Content-Disposition'] = 'attachment; filename="modele-commandes-ml-cod.csv"'
        reponse.write('﻿')
        w = csv.writer(reponse, delimiter=';')
        w.writerow([libelle for _, libelle, _ in COLONNES])
        w.writerow(['Kouassi', 'Aya', '0707070707', '', 'Bouaké', 'Quartier Commerce', 'Crème visage', 2, 7500, 'Petit', 'oui',
                    'non', 'CMD-001', ''])
        return reponse
    lignes = request.session.get('import_colis')
    if request.method == 'POST':
        if request.POST.get('confirmer') and lignes:
            creees, refus = creer(vendeur, lignes, request.user)
            request.session.pop('import_colis', None)
            if creees:
                pl = 's' if len(creees) > 1 else ''
                messages.success(request, "%d commande%s créée%s et envoyée%s." % (len(creees), pl, pl, pl))
            for r in refus[:20]:
                messages.error(request, r)
            return redirect('management:management_vendeur_liste_colis')
        if request.POST.get('annuler'):
            request.session.pop('import_colis', None)
            return redirect('management:management_vendeur_import_colis')
        fichier = request.FILES.get('fichier')
        if not fichier:
            messages.error(request, "Choisissez un fichier.")
            return redirect('management:management_vendeur_import_colis')
        try:
            donnees = lire_fichier(fichier.name, fichier.read())
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('management:management_vendeur_import_colis')
        if len(donnees) > MAX_LIGNES:
            messages.error(request, "Plus de %d lignes : découpez le fichier." % MAX_LIGNES)
            return redirect('management:management_vendeur_import_colis')
        request.session['import_colis'] = verifier(vendeur, donnees)
        return redirect('management:management_vendeur_import_colis')
    valides = [l for l in lignes or [] if not l['erreurs']]
    return render(request, 'management/vendeur_import_colis.html', {
        'vendeur': vendeur, 'lignes': lignes, 'valides': valides, 'erreurs': [l for l in lignes or [] if l['erreurs']],
        'colonnes': COLONNES, 'total': sum(Decimal(l['total']) for l in valides if l['encaisser'])})
