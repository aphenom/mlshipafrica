"""SMS du calendrier des retours (vendeurs sans stockage) et de la réception de stock."""
from django.db import migrations

MODELES = [
    ('retour', 'Vendeur : colis revenu à Abidjan (J0)', 'vendeur', 5,
     "MLCOD : votre colis {colis} est revenu a Abidjan. Vous avez 3 jours pour le substituer, sinon venez le recuperer."),
    ('rappel_subst', 'Vendeur : rappel J5, colis à récupérer', 'vendeur', 5,
     "MLCOD : rappel, votre colis {colis} vous attend au bureau ML COD Interieur. Merci de le recuperer avant le {date}."),
    ('ret_alerte', 'Vendeur : alertes J7 et J8', 'vendeur', 5,
     "MLCOD : {n} alerte, colis {colis} a recuperer. A partir du {date} : garde de {garde} par jour."),
    ('ret_abandon', "Vendeur : J10, garde payante et date d'abandon", 'vendeur', 5,
     "MLCOD : colis {colis} non recupere. Garde de {garde} par jour a partir du {debut}. Le {date} il sera declare abandonne."),
    ('ret_abandon_def', 'Vendeur : J30, abandon définitif', 'vendeur', 5,
     "MLCOD : colis {colis} declare abandonne apres 30 jours sans recuperation."),
    ('v_stock', "Vendeur : stock reçu à l'entrepôt (un SMS par bordereau)", 'vendeur', 5,
     "MLCOD : stock recu, {nb} pieces ({refs} references). Bordereau {id}. Detail et ecarts dans votre espace."),
]


def creer(apps, schema_editor):
    SmsModele = apps.get_model('sms', 'SmsModele')
    for cle, libelle, destinataire, priorite, texte in MODELES:
        SmsModele.objects.get_or_create(cle=cle, defaults={
            'libelle': libelle, 'destinataire': destinataire, 'priorite': priorite, 'actif': True, 'texte': texte})


class Migration(migrations.Migration):
    dependencies = [('sms', '0002_modeles_par_defaut')]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
