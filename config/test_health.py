from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SECURE_SSL_REDIRECT=False)
class HealthcheckTests(TestCase):
    def test_healthcheck_returns_minimal_operational_status(self):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "application": "ok",
                "database": "ok",
            },
        )
        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))

    @patch("config.health.connection.cursor", side_effect=Exception("database unavailable"))
    def test_healthcheck_returns_503_without_exposing_exception(self, _cursor):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "unavailable",
                "application": "ok",
                "database": "unavailable",
            },
        )
        self.assertNotContains(response, "database unavailable", status_code=503)
