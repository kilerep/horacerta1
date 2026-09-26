from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"], SECURE_SSL_REDIRECT=False)
class PwaOfflinePageTests(SimpleTestCase):
    """O offline.html antigo redirecionava para "/" quando navigator.onLine era
    true. Com Wi-Fi sem internet ou servidor fora do ar isso vira um loop
    (offline -> "/" -> service worker falha -> offline ...), que e o sintoma
    "modo aviao, o app nao funciona". Trava a correcao.
    """

    def test_ping_is_public_empty_and_never_cached(self):
        response = self.client.get(reverse("pwa_ping"))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.content, b"")

    def test_ping_only_accepts_get(self):
        self.assertEqual(self.client.post(reverse("pwa_ping")).status_code, 405)

    def test_offline_page_does_not_redirect_based_on_navigator_online(self):
        response = self.client.get(reverse("offline"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("if (navigator.onLine)", body)
        self.assertNotIn("Você está online, redirecionando", body)

    def test_offline_page_probes_the_server_before_leaving(self):
        response = self.client.get(reverse("offline"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'var PING_URL = "/ping/";')
        self.assertContains(response, "Nada é salvo enquanto você estiver sem conexão")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"], SECURE_SSL_REDIRECT=False)
class ServiceWorkerPrivacyTests(SimpleTestCase):
    """O SW v1-v3 guardava HTML autenticado em cache, sem limpar no logout.
    Trava as regras que impedem a volta desse vazamento."""

    def _sw(self):
        return self.client.get(reverse("pwa_service_worker")).content.decode()

    def test_service_worker_is_v4_and_never_caches_private_pages(self):
        body = self._sw()

        self.assertIn('const SW_VERSION = "hc-sw-v4";', body)
        # allowlist explicita de paginas publicas; "/" fica de fora (redireciona logado)
        self.assertIn('new Set(["/help/", "/terms/", "/privacy/"])', body)
        self.assertNotIn("ESSENTIAL_ASSETS", body)
        self.assertNotIn("DYNAMIC_CACHE", body)
        self.assertNotIn("/me/", body)

    def test_service_worker_purges_legacy_caches_on_activate(self):
        body = self._sw()

        self.assertIn("caches.delete(name)", body)
        self.assertIn("keep.has(name)", body)

    def test_service_worker_only_caches_hashed_static_assets(self):
        self.assertIn("HASHED_STATIC", self._sw())

    def test_service_worker_never_queues_or_caches_writes(self):
        body = self._sw()

        self.assertIn("saveFailedResponse", body)
        self.assertNotIn("sync", body.lower().replace("async", ""))


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"], SECURE_SSL_REDIRECT=False)
class PrivateResponseHeadersTests(TestCase):
    def setUp(self):
        from accounts.models import User

        self.user = User.objects.create_user(
            username="mei_headers", email="mei_headers@example.com", password="Senha-Forte-123", role=User.Role.FUNCIONARIO
        )

    def test_authenticated_html_is_no_store_and_varies_on_cookie(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("mei_contract"), follow=True)

        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])

    def test_public_pages_stay_cacheable_for_the_service_worker(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("help"))

        self.assertNotIn("no-store", response.get("Cache-Control", ""))

    def test_logout_asks_browser_to_clear_http_cache_only(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response["Clear-Site-Data"], '"cache"')


class ConnectionGuardWiringTests(SimpleTestCase):
    def test_guard_is_loaded_before_form_feedback_can_lock_buttons(self):
        from pathlib import Path

        from django.conf import settings

        for template in ("templates/base.html", "templates/accounts/base.html", "templates/public/base_public.html"):
            html = (Path(settings.BASE_DIR) / template).read_text(encoding="utf-8")
            self.assertIn("js/connection_guard.js", html, template)
