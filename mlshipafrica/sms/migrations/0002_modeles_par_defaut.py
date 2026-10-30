"""Textes par défaut des SMS (plan validé par la direction le 29/10/2026). Modifiables ensuite dans l'administration.

Textes sans accents : un seul caractère accentué ou une apostrophe typographique fait passer le SMS en
Unicode et double son prix.
"""
from django.db import migrations

MODELES = [
    ('cl_recu', 'Client : colis reçu chez nous (ramassé ou déposé)', 'client', 5, True,
     "{boutique} : commande confirmee. A payer a la livraison : {montant}. Livraison prevue a {ville} vers le {date}. Info : {tel}"),
    ('cl_arrive', 'Client : colis arrivé dans sa ville', 'client', 5, True,
     "{boutique} : votre colis est arrive a {ville}. Preparez {montant}, nous vous appelons pour la remise. Info : {tel}"),
    ('cl_echec', 'Client : 1er échec de livraison (une seule fois par colis)', 'client', 5, True,
     "{boutique} : nous n'avons pas pu vous remettre votre colis ({montant}). Appelez le {tel} pour fixer une nouvelle livraison."),
    ('cl_annule', 'Client : commande annulée avant expédition', 'client', 5, True,
     "{boutique} : votre commande {ref} est annulee. Si c'est une erreur, appelez le {tel}."),
    ('v_annule_av', 'Vendeur : commande annulée avant expédition', 'vendeur', 5, True,
     "MLCOD : commande {ref} annulee avant expedition. Le colis reste disponible : relancez-la ou recuperez-le depuis votre espace."),
    ('recap', 'Vendeur : résumé du jour à 19 h (activé dans les paramètres SMS)', 'vendeur', 9, True,
     "MLCOD {jour} : {recus} colis recus, {expedies} expedies, {livres} livres, {echecs} echecs, {annules} annules avant expedition. Detail dans votre espace."),
]


def creer(apps, schema_editor):
    SmsModele = apps.get_model('sms', 'SmsModele')
    SmsParametres = apps.get_model('sms', 'SmsParametres')
    for cle, libelle, destinataire, priorite, actif, texte in MODELES:
        SmsModele.objects.get_or_create(cle=cle, defaults={
            'libelle': libelle, 'destinataire': destinataire, 'priorite': priorite, 'actif': actif, 'texte': texte})
    SmsParametres.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('sms', '0001_initial')]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
