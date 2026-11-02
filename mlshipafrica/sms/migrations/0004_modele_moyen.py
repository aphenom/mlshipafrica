from django.db import migrations


def creer(apps, schema_editor):
    apps.get_model('sms', 'SmsModele').objects.get_or_create(cle='moyen', defaults={
        'libelle': 'Vendeur : coordonnées de versement modifiées (sécurité)', 'destinataire': 'vendeur', 'priorite': 1,
        'actif': True,
        'texte': "MLCOD : un nouveau moyen de paiement ({moyen}) a ete ajoute a votre compte. Si ce n'est pas vous, appelez-nous."})


class Migration(migrations.Migration):
    dependencies = [('sms', '0003_modeles_retours')]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
