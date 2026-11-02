"""
Journal d'audit automatique : chaque création ou modification des objets sensibles écrit une ligne
avec l'auteur, son rôle, l'ancienne et la nouvelle valeur des champs modifiés.

Les objets suivis sont listés dans SUIVIS. Les mises à jour en masse (queryset.update) ne passent pas
par ici : elles sont réservées aux tâches techniques (file SMS).
"""
import datetime
import decimal
import logging

from django.apps import apps
from django.db.models.signals import post_save, pre_save
from django_currentuser.middleware import get_current_user

logger = logging.getLogger(__name__)

IGNORES = {'date_modification', 'modification_par', 'date_creation', 'creation_par', 'jeton_api'}

# (application, modèle) → champs suivis (None = tous les champs simples)
SUIVIS = {
    ('core', 'Zone'): None,
    ('core', 'Localite'): None,
    ('core', 'FormatArticle'): None,
    ('core', 'PartenaireLogistique'): None,
    ('core', 'Configuration'): None,
    ('management', 'Tarification'): None,
    ('management', 'ProfilStaff'): None,
    ('management', 'Vendeur'): ('etat_approbation', 'etat_validation', 'etat_suppression', 'commercial', 'agent_cod',
                                'collecte_par_mlship', 'cod_actif', 'numero_sms', 'nom_store', 'license', 'option_stockage'),
    ('management', 'Article'): ('statut_traitement', 'montant_frais', 'montant_total_frais', 'montant_a_reverser',
                                'valeur', 'valeur_totale', 'format_article', 'localite_arrivee', 'tarification',
                                'is_option_encaissement', 'is_option_recuperation', 'etat_reglement',
                                'etat_encaissement', 'etat_reversement', 'etat_suppression', 'etat_validation',
                                'etat_confirmation', 'agent_cod'),
    ('management', 'HistoriqueArticle'): ('statut_traitement', 'article', 'etat_suppression', 'commentaire'),
    ('management', 'ReglementArticle'): None,
    ('management', 'Encaissement'): None,
    ('management', 'Reversement'): None,
    ('management', 'Acompte'): None,
    ('management', 'EntreeStock'): ('statut', 'date_reception', 'recu_par'),
    ('management', 'MouvementStock'): None,
    ('sms', 'SmsParametres'): ('actif', 'tel_service', 'heure_debut_silence', 'heure_fin_silence', 'resume_soir_actif'),
    ('sms', 'SmsModele'): ('texte', 'actif', 'priorite'),
}


def _valeur(v):
    if isinstance(v, (decimal.Decimal,)):
        return str(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if v is None or isinstance(v, (bool, int, float, str, list, dict)):
        return v
    return str(v)


def instantane(instance, champs):
    donnees = {}
    for f in instance._meta.concrete_fields:
        if f.name in IGNORES or (champs is not None and f.name not in champs):
            continue
        donnees[f.name] = _valeur(getattr(instance, f.attname))
    return donnees


def _avant(sender, instance, **kwargs):
    if kwargs.get('raw') or instance.pk is None:
        instance._audit_avant = None
        return
    champs = SUIVIS[(sender._meta.app_label, sender.__name__)]
    ancien = sender._base_manager.filter(pk=instance.pk).first()
    instance._audit_avant = instantane(ancien, champs) if ancien is not None else None


def _apres(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    try:
        champs = SUIVIS[(sender._meta.app_label, sender.__name__)]
        apres = instantane(instance, champs)
        avant = getattr(instance, '_audit_avant', None)
        if created or avant is None:
            action, diff_avant, diff_apres = 'creation', None, apres
        else:
            changes = [k for k in apres if apres.get(k) != avant.get(k)]
            if not changes:
                return
            action = 'suppression' if 'etat_suppression' in changes and apres.get('etat_suppression') else 'modification'
            diff_avant = {k: avant.get(k) for k in changes}
            diff_apres = {k: apres.get(k) for k in changes}
        user = get_current_user()
        user = user if getattr(user, 'is_authenticated', False) else None
        profil = getattr(user, 'account_profil_staff', None) if user else None
        role = profil.role_profil if profil else ('vendeur' if user is not None and hasattr(user, 'account_vendeur') else ('systeme' if user is None else ''))
        JournalAudit = apps.get_model('core', 'JournalAudit')
        JournalAudit.objects.create(
            utilisateur=user, role=role or '', action=action, modele=sender.__name__, objet_id=str(instance.pk),
            objet_code=str(getattr(instance, 'code', '') or '')[:40], avant=diff_avant, apres=diff_apres)
    except Exception:  # le journal ne doit jamais empêcher le travail
        logger.exception("Journal d'audit non écrit pour %s %s", sender.__name__, instance.pk)


def brancher():
    for (app, nom) in SUIVIS:
        try:
            modele = apps.get_model(app, nom)
        except LookupError:
            continue
        pre_save.connect(_avant, sender=modele, dispatch_uid='audit_avant_%s_%s' % (app, nom))
        post_save.connect(_apres, sender=modele, dispatch_uid='audit_apres_%s_%s' % (app, nom))
