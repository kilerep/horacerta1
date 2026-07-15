from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class InterfaceTextIntegrityTests(SimpleTestCase):
    MOJIBAKE_MARKERS = ("Ã", "Â", "�")

    def test_all_html_templates_are_valid_utf8_without_mojibake(self):
        templates_root = Path(settings.BASE_DIR) / "templates"
        template_paths = sorted(templates_root.rglob("*.html"))

        self.assertTrue(template_paths, "Nenhum template HTML foi encontrado para validação.")

        failures = []
        for path in template_paths:
            text = path.read_text(encoding="utf-8")
            found = [marker for marker in self.MOJIBAKE_MARKERS if marker in text]
            if found:
                failures.append(f"{path.relative_to(settings.BASE_DIR)}: {', '.join(found)}")

        self.assertEqual(
            failures,
            [],
            "Templates com possíveis caracteres corrompidos:\n" + "\n".join(failures),
        )

    def test_public_landing_does_not_publish_unverified_promises(self):
        landing = (Path(settings.BASE_DIR) / "templates" / "public" / "landing.html").read_text(
            encoding="utf-8"
        )
        unsupported_claims = (
            "100% conforme LGPD",
            "criptografia de ponta a ponta",
            "NFS-e integrada",
            "150 avaliações",
            "funciona completamente offline",
        )

        for claim in unsupported_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, landing)
