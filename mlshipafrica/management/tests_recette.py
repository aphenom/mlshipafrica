"""Mode RECETTE : bandeau, aucun envoi, commandes protégées."""
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import override_settings

from management import tests_pages


class Recette(tests_pages.RecettePages):
    test_toutes_les_pages = None

    @override_settings(RECETTE=True)
    def test_bandeau_et_envois_coupes(self):
        self.client.force_login(self.vendeur.user)
        self.assertIn('VERSION DE TEST', self.client.get('/').content.decode())
        from sms.service import envoyer_file
        from integrations.service import envoyer_file as envoyer_integrations
        self.assertEqual(envoyer_file()['envoyes'], 0)
        self.assertEqual(envoyer_integrations(), {'envoyes': 0, 'erreurs': 0})

    def test_pas_de_bandeau_en_production(self):
        self.client.force_login(self.vendeur.user)
        self.assertNotIn('VERSION DE TEST', self.client.get('/').content.decode())

    def test_preparation_refusee_hors_recette(self):
        with self.assertRaises(CommandError):
            call_command('recette_preparer', '--mot-de-passe', 'x', stdout=StringIO())
