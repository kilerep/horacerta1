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
        self.assertIn("[OK] Configuração Django", content)
        self.assertIn("[OK] Banco de dados (default)", content)
        self.assertIn("[OK] Nenhuma migration pendente", content)
        self.assertIn("[OK] Modelos e migrations estão consistentes", content)
        self.assertIn("[OK] Arquivos estáticos críticos de origem", content)
        self.assertIn("Release pronta para a etapa de publicação.", content)

    @patch("accounts.management.commands.check_release_readiness.finders.find")
    def test_command_blocks_publication_when_a_critical_source_asset_is_missing(self, mocked_find):
        mocked_find.side_effect = lambda path: None if path == "css/public_landing_new.css" else f"/tmp/{path}"
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("check_release_readiness", stdout=output)

        content = output.getvalue()
        self.assertIn("[FALHA] Arquivos estáticos críticos de origem", content)
        self.assertIn("css/public_landing_new.css", content)
        self.assertIn("Release não está pronta para publicação.", content)

    @patch("accounts.management.commands.check_release_readiness.MigrationAutodetector.changes")
    def test_command_blocks_publication_when_models_have_no_migration(self, mocked_changes):
        mocked_changes.return_value = {"services": [object()]}
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("check_release_readiness", stdout=output)

        content = output.getvalue()
        self.assertIn("[FALHA] Existem alterações de modelo sem migration", content)
        self.assertIn("apps: services", content)

    @patch("accounts.management.commands.check_release_readiness.staticfiles_storage.exists")
    def test_command_can_require_collected_static_files(self, mocked_exists):
        mocked_exists.return_value = False
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "check_release_readiness",
                require_collected_static=True,
                stdout=output,
            )

        content = output.getvalue()
        self.assertIn("[FALHA] Arquivos estáticos coletados/manifesto", content)
        self.assertIn("ausente em STATIC_ROOT", content)
