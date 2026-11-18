"""
Cloche de notifications et messages sur les commandes.

Qui est prévenu de quoi (chacun ne voit que ce qui le concerne) :
  - commande créée par un vendeur          → son agent COD (sinon les managers)
  - colis reçu chez nous (déposé, ramassé)  → le vendeur, son agent COD
  - en transit, livré, échec, revenu        → le vendeur ; échec et retour aussi au manager et à l'agent
  - message sur une commande               → vendeur → son agent et les managers ; équipe → le vendeur
  - facture de paiement émise, versée      → le vendeur ; vague de paiements → le CEO (informé)
  - contestation d'une facture             → comptable(s) et CEO
  - envoi de stock annoncé                 → managers ; stock validé → le vendeur
  - stockage demandé                       → le commercial du vendeur et le CEO
  - nouveau numéro de paiement à valider    → comptable(s)
Les textes ne contiennent jamais l'argent de la société pour l'équipe terrain, ni le nom du prestataire.
"""
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from management.models import Article, HistoriqueArticle, MessageColis, Notification, ProfilStaff, Releve, Vendeur
from mlshipafrica.droits import a_le_droit
from mlshipafrica.enums import StatutTraitement as S, TypeProfilStaffChoice as R


def _equipe(license, *roles):
    return list(User.objects.filter(account_profil_staff__license=license, account_profil_staff__role_profil__in=roles,
                                    is_active=True))


def _url_colis(article, pour_vendeur):
    nom = 'management:management_vendeur_detail_colis' if pour_vendeur else 'management:management_admin_detail_colis'
    return reverse(nom, args=[article.code])


def notifier(destinataires, type_, titre, texte='', url='', cle=''):
    """Crée une notification par destinataire (sans doublon si `cle` est donnée). Après validation de la transaction."""
    vus = {u.pk: u for u in destinataires if u is not None}

    def creer():
        for user in vus.values():
            k = '%s:%s' % (cle, user.pk) if cle else ''
            if k and Notification.objects.filter(cle=k).exists():
                continue
            Notification.objects.create(destinataire=user, type=type_, titre=titre[:150], texte=texte[:300], url=url[:300], cle=k)
    transaction.on_commit(creer)


def _agent_ou_managers(article):
    if article.agent_cod_id and article.agent_cod.user_id:
        return [article.agent_cod.user]
    return _equipe(article.license, R.MANAGER)


STATUTS_VENDEUR = {
    S.DEPOT: "Colis reçu chez ML COD", S.RAMASSE: "Colis ramassé", S.EN_TRANSIT: "Colis en route",
    S.LIVRE: "Colis livré", S.ECHEC_LIVRAISON: "Échec de livraison : votre consigne est attendue",
    S.REVENU_ABIDJAN: "Colis revenu à Abidjan", S.ANNULE: "Commande annulée avant expédition",
}


@receiver(post_save, sender=HistoriqueArticle, dispatch_uid='notifications_selon_mouvement')
def selon_mouvement(sender, instance, created, **kwargs):
    if kwargs.get('raw') or not created or instance.etat_suppression:
        return
    article, statut = instance.article, instance.statut_traitement
    vendeur_user = article.vendeur.user if article.vendeur_id and article.vendeur.user_id else None
    client = ('%s %s' % (article.nom_destinataire or '', article.prenom_destinataire or '')).strip()
    ville = article.localite_arrivee.nom if article.localite_arrivee_id else ''
    if statut in (S.EN_ATTENTE_DEPOT, S.EN_ATTENTE_RAMASSAGE) and (instance.dernier_historique_article_id is None):
        notifier(_agent_ou_managers(article), 'commande', "Nouvelle commande %s à confirmer" % article.code,
                 "%s · %s · %s" % (article.vendeur.nom_store if article.vendeur_id else '', client, ville),
                 _url_colis(article, False), 'cree:%s' % article.pk)
    if statut in STATUTS_VENDEUR and vendeur_user is not None:
        notifier([vendeur_user], 'statut', "%s · %s" % (STATUTS_VENDEUR[statut], article.code), "%s · %s" % (client, ville),
                 _url_colis(article, True), 'statut:%s:%s' % (instance.pk, statut))
    if statut in (S.DEPOT, S.RAMASSE):
        notifier(_agent_ou_managers(article), 'depot', "Colis %s reçu au bureau" % article.code, client,
                 _url_colis(article, False), 'depot:%s' % instance.pk)
    if statut in (S.ECHEC_LIVRAISON, S.EN_RETOUR, S.REVENU_ABIDJAN):
        notifier(_agent_ou_managers(article) + _equipe(article.license, R.MANAGER), 'echec',
                 "%s · %s" % (dict(S.choices)[statut], article.code), "%s · %s" % (client, ville),
                 _url_colis(article, False), 'echec:%s' % instance.pk)


# --------------------------------------------------------------------------------------------- messages

def poster_message(user, texte, article=None, releve=None, interne=False, contester=False):
    texte = (texte or '').strip()[:2000]
    if not texte:
        raise ValueError("Écrivez un message.")
    de_vendeur = not user.is_staff
    m = MessageColis.objects.create(article=article, releve=releve, auteur=user, de_vendeur=de_vendeur,
                                    interne=interne and not de_vendeur, contestation=contester and de_vendeur, texte=texte)
    objet = article or releve
    license = objet.license if article else releve.vendeur.license
    vendeur = article.vendeur if article else releve.vendeur
    nom = vendeur.nom_store if vendeur else ''
    if article:
        if de_vendeur:
            notifier(_agent_ou_managers(article) + _equipe(license, R.MANAGER), 'message', "Message de %s sur %s" % (nom, article.code),
                     texte[:200], _url_colis(article, False) + '#messages')
        elif not m.interne and vendeur and vendeur.user_id:
            notifier([vendeur.user], 'message', "Réponse de ML COD sur %s" % article.code, texte[:200], _url_colis(article, True) + '#messages')
    else:
        if de_vendeur:
            if contester:
                Releve.objects.filter(pk=releve.pk).update(contestation_ouverte=True)
            notifier(_equipe(license, R.COMPTABLE, R.SUPER), 'contestation' if contester else 'message',
                     ("Contestation de %s sur la facture %s" if contester else "Question de %s sur la facture %s") % (nom, releve.code),
                     texte[:200], reverse('management:management_admin_releves') + '?etape=factures&releve=' + releve.code)
        elif not m.interne and vendeur and vendeur.user_id:
            notifier([vendeur.user], 'message', "Réponse sur votre facture %s" % releve.code, texte[:200],
                     reverse('management:management_vendeur_releves') + '?facture=' + releve.code)
    return m


def messages_visibles(user, article=None, releve=None):
    qs = MessageColis.objects.filter(article=article) if article else MessageColis.objects.filter(releve=releve)
    if not user.is_staff:
        qs = qs.filter(interne=False)
    return qs.select_related('auteur')


@login_required
def poster(request):
    """Formulaire de message (détail colis équipe ou vendeur, facture de paiement)."""
    if request.method != 'POST':
        raise Http404
    user = request.user
    article = releve = None
    retour = request.POST.get('retour') or '/'
    if request.POST.get('article'):
        if user.is_staff:
            if not a_le_droit(user, 'colis_voir'):
                raise PermissionDenied
            article = Article.objects.filter(license=user.account_profil_staff.license, code=request.POST['article']).first()
        else:
            article = Article.objects.filter(vendeur__user=user, code=request.POST['article']).first()
    elif request.POST.get('releve'):
        if user.is_staff:
            if not a_le_droit(user, 'releves'):
                raise PermissionDenied
            releve = Releve.objects.filter(vendeur__license=user.account_profil_staff.license, code=request.POST['releve']).first()
            if releve is not None and request.POST.get('resolu'):
                Releve.objects.filter(pk=releve.pk).update(contestation_ouverte=False)
        else:
            releve = Releve.objects.filter(vendeur__user=user, code=request.POST['releve']).first()
    if article is None and releve is None:
        raise Http404
    try:
        poster_message(user, request.POST.get('texte'), article=article, releve=releve,
                       interne=bool(request.POST.get('interne')), contester=bool(request.POST.get('contester')))
        django_messages.success(request, "Message envoyé.")
    except ValueError as e:
        django_messages.error(request, str(e))
    if not retour.startswith('/') or retour.startswith('//'):
        retour = '/'
    return redirect(retour)


# --------------------------------------------------------------------------------------------- cloche

def non_lues(user):
    if not getattr(user, 'is_authenticated', False):
        return 0
    return Notification.objects.filter(destinataire=user, lue=False).count()


@login_required
def mes_notifications(request):
    notifs = Notification.objects.filter(destinataire=request.user)
    if request.method == 'POST':
        notifs.filter(lue=False).update(lue=True)
        return redirect('management:management_notifications')
    ouvrir = request.GET.get('ouvrir')
    if ouvrir:
        n = notifs.filter(pk=ouvrir).first()
        if n is not None:
            Notification.objects.filter(pk=n.pk).update(lue=True)
            if n.url.startswith('/') and not n.url.startswith('//'):
                return redirect(n.url)
    if request.GET.get('format') == 'json':
        return JsonResponse({'non_lues': notifs.filter(lue=False).count(), 'notifications': [
            {'id': n.pk, 'titre': n.titre, 'texte': n.texte, 'lue': n.lue, 'date': timezone.localtime(n.date).strftime('%d/%m %H:%M')}
            for n in notifs[:10]]})
    return render(request, 'management/notifications.html', {'notifs': notifs[:200]})


# --------------------------------------------------------------------------------------------- autres évènements

def releves_emis(releves, par):
    for r in releves:
        if r.vendeur.user_id:
            notifier([r.vendeur.user], 'paiement', "Facture de paiement %s émise" % r.code,
                     "Votre paiement est en préparation : voir le détail colis par colis.",
                     reverse('management:management_facture_paiement', args=[r.code]), 'emis:%s' % r.pk)
            if r.total_stockage:
                notifier([r.vendeur.user], 'stock', "Frais de stockage déduits : %s F" % '{:,.0f}'.format(r.total_stockage).replace(',', '\u202f'),
                         "Déduits de votre facture de paiement %s." % r.code,
                         reverse('management:management_vendeur_stock'), 'stockage-deduit:%s' % r.pk)
    if releves:
        license = releves[0].vendeur.license
        total = sum((r.net for r in releves if r.net > 0), 0)
        notifier([u for u in _equipe(license, R.SUPER) if u != par], 'paiement',
                 "%d facture(s) de paiement générée(s)" % len(releves),
                 "Net total %s F, par %s" % ('{:,.0f}'.format(total).replace(',', ' '), par.get_full_name() or par.email if par else 'la plateforme'),
                 reverse('management:management_admin_releves') + '?etape=factures')


def releve_verse(releve):
    if releve.vendeur.user_id:
        notifier([releve.vendeur.user], 'paiement', "Paiement envoyé · facture %s" % releve.code,
                 "Référence %s" % releve.reference_versement,
                 reverse('management:management_facture_paiement', args=[releve.code]), 'verse:%s' % releve.pk)


def stock_annonce(entree):
    notifier(_equipe(entree.vendeur.license, R.MANAGER), 'stock', "Envoi de stock %s annoncé" % entree.code,
             entree.vendeur.nom_store or '', reverse('management:management_admin_stock'), 'stock:%s' % entree.pk)


def stock_valide(entree):
    if entree.vendeur.user_id:
        notifier([entree.vendeur.user], 'stock', "Envoi %s reçu et compté" % entree.code, "Voir les quantités reçues.",
                 reverse('management:management_vendeur_stock'), 'stockok:%s' % entree.pk)


def stockage_demande(vendeur):
    dest = _equipe(vendeur.license, R.SUPER)
    if vendeur.commercial_id and vendeur.commercial.user_id:
        dest.append(vendeur.commercial.user)
    notifier(dest, 'vendeur', "%s demande le stockage" % (vendeur.nom_store or vendeur.code), "À activer dans sa fiche vendeur.",
             reverse('management:management_admin_vendeur_edit_profil', args=[vendeur.code]), 'stockage:%s' % vendeur.pk)


def numero_a_valider(vendeur):
    notifier(_equipe(vendeur.license, R.COMPTABLE), 'paiement', "Nouveau numéro de paiement à valider",
             vendeur.nom_store or vendeur.code, reverse('management:management_admin_moyens_versement'))


def _f(montant):
    return '{:,.0f}'.format(montant).replace(',', '\u202f') + ' F'


def stockage_a_valider_rappel(license, debut, lignes):
    from management.stock import nom_mois
    total = sum(l['montant'] for l in lignes)
    notifier(_equipe(license, R.COMPTABLE, R.SUPER), 'paiement', "Stockage de %s à valider" % nom_mois(debut),
             "%d vendeur%s · %s à charger sur les paiements en cours." % (len(lignes), 's' if len(lignes) > 1 else '', _f(total)),
             reverse('management:management_admin_releves') + '?etape=stockage', 'rappel-stockage:%s' % debut.strftime('%Y-%m'))


def stockage_charge(lignes, debut, par):
    from management.stock import nom_mois
    for l in lignes:
        v = l['vendeur']
        if v.user_id:
            notifier([v.user], 'stock', "Stockage de %s : %s" % (nom_mois(debut), _f(l['montant'])),
                     "%d pièce%s chez nous × %s, déduit de votre prochain paiement." % (l['pieces'], 's' if l['pieces'] > 1 else '', _f(l['tarif'])),
                     reverse('management:management_vendeur_stock'), 'stockage-mois:%s:%s' % (v.pk, debut.strftime('%Y-%m')))
    if lignes:
        license = lignes[0]['vendeur'].license
        notifier([u for u in _equipe(license, R.SUPER) if u != par], 'paiement', "Stockage de %s chargé" % nom_mois(debut),
                 "%d vendeur%s · %s, par %s." % (len(lignes), 's' if len(lignes) > 1 else '', _f(sum(l['montant'] for l in lignes)),
                                                 par.get_full_name() or par.email),
                 reverse('management:management_admin_releves') + '?etape=stockage', 'stockage-charge:%s:%s' % (license.pk, debut.strftime('%Y-%m')))


def stockage_en_retard_rappel(license, debut, lignes, jour):
    """Tous les jours tant qu'un mois passé n'est pas chargé : la comptable et le CEO."""
    from management.stock import nom_mois
    total = sum(l['montant'] for l in lignes)
    notifier(_equipe(license, R.COMPTABLE, R.SUPER), 'paiement', "En retard : stockage de %s non chargé" % nom_mois(debut),
             "%d vendeur%s · %s à charger. Rien n'est perdu tant que vous le chargez." % (len(lignes), 's' if len(lignes) > 1 else '', _f(total)),
             reverse('management:management_admin_releves') + '?etape=stockage',
             'retard-stockage:%s:%s' % (debut.strftime('%Y-%m'), jour.isoformat()))
