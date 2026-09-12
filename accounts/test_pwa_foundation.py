import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class PwaFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pwa-user@example.com",
            email="pwa-user@example.com",
            password="Senha@12345",
            role=User.Role.FUNCIONARIO,
        )

    def test_public_foundation_routes_respond(self):
        urls = [
            reverse("landing"),
            reverse("login"),
            reverse("password_reset"),
            reverse("pwa_manifest"),
            reverse("pwa_service_worker"),
            reverse("offline"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_manifest_uses_current_application_routes(self):
        response = self.client.get(reverse("pwa_manifest"))
        manifest = json.loads(response.content)
        shortcut_urls = [item["url"] for item in manifest["shortcuts"]]

        self.assertEqual(manifest["start_url"], reverse("landing"))
        self.assertIn(reverse("employee_dashboard"), shortcut_urls)
        self.assertIn(reverse("mei_contract"), shortcut_urls)
        self.assertIn(reverse("service_job_list"), shortcut_urls)
        self.assertNotIn("/timeclock/me/", shortcut_urls)
        self.assertNotIn("/app/clientes/", shortcut_urls)
        self.assertNotIn("/services/", shortcut_urls)

    def test_service_worker_is_served_from_root_scope(self):
        response = self.client.get(reverse("pwa_service_worker"))
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, 'const SW_VERSION = "hc-sw-v3";')
        self.assertContains(response, 'const OFFLINE_PAGE = "/offline/";')

    def test_pwa_status_requires_login_and_reports_only_available_capabilities(self):
        anonymous_response = self.client.get(reverse("pwa_status"))
        self.assertEqual(anonymous_response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(reverse("pwa_status"))
        payload = response.json()
        self.assertTrue(payload["pwa_available"])
        self.assertFalse(payload["push_notifications_available"])
        self.assertEqual(payload["service_worker_url"], reverse("pwa_service_worker"))

    def test_push_subscription_endpoint_does_not_claim_to_be_enabled(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("register_push"),
            data=json.dumps({"endpoint": "https://example.invalid/push"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 501)
        self.assertFalse(response.json()["enabled"])
