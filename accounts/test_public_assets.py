from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class PublicAssetTests(SimpleTestCase):
    def test_critical_public_assets_exist(self):
        critical_assets = (
            "css/design_tokens.css",
            "css/ui_system.css",
            "css/public_landing_new.css",
            "js/theme_engine.js",
            "js/pwa-register.js",
            "pwa/icon-512.png",
            "pwa/apple-touch-icon-180.png",
            "pwa/favicon-32.png",
        )

        missing = [path for path in critical_assets if not finders.find(path)]

        self.assertEqual(
            missing,
            [],
            f"Assets públicos ausentes: {', '.join(missing)}",
        )
