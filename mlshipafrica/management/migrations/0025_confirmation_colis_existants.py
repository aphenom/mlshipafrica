"""Colis déjà en route ou terminés avant la mise en service de la confirmation : marqués « confirmés »
(sinon ils apparaîtraient à tort dans la file des agents). Les colis encore chez le vendeur ou au hub
restent « à confirmer » et entrent dans la file."""
from django.db import migrations

AVANT_EXPEDITION = ('brouillon', 'en_attente_ramassage', 'en_attente_depot', 'ramasse', 'depot', 'annule')


def marquer(apps, schema_editor):
    Article = apps.get_model('management', 'Article')
    Article.objects.exclude(statut_traitement__in=AVANT_EXPEDITION).update(etat_confirmation='confirme')
    Article.objects.filter(statut_traitement='annule').update(etat_confirmation='annule')
    # Agent COD du vendeur reporté sur ses colis en attente
    Vendeur = apps.get_model('management', 'Vendeur')
    for vendeur in Vendeur.objects.filter(agent_cod__isnull=False):
        Article.objects.filter(vendeur=vendeur, agent_cod__isnull=True).update(agent_cod=vendeur.agent_cod)


class Migration(migrations.Migration):
    dependencies = [('management', '0024_confirmation_acompte')]
    operations = [migrations.RunPython(marquer, migrations.RunPython.noop)]
