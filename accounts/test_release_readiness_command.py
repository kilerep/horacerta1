from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class ReleaseReadinessCommandTests(TestCase):
    def test_command_passes_when_application_database_migrations_and_assets_are_ready(self):
        output = StringIO()

        call_command("check_release_readiness", stdout=output)

        content = output.getvalue()
        self.assertIn("[OK] Configuracao Django", content)
        self.assertIn("[OK] Banco de dados (default)", content)
        self.assertIn("[OK] Nenhuma migration pendente", content)
        self.assertIn("[OK] Arquivos estaticos criticos", content)
        self.assertIn("Release pronta para a etapa de publicacao.", content)

    @patch("accounts.management.commands.check_release_readiness.finders.find")
    def test_command_blocks_publication_when_a_critical_asset_is_missing(self, mocked_find):
        mocked_find.side_effect = lambda path: None if path == "css/public_landing_new.css" else f"/tmp/{path}"
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("check_release_readiness", stdout=output)

        content = output.getvalue()
        self.assertIn("[FALHA] Arquivos estaticos criticos", content)
        self.assertIn("css/public_landing_new.css", content)
        self.assertIn("Release nao esta pronta para publicacao.", content)
