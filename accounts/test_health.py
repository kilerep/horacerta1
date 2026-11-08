from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import health
from accounts.models import User

PWD = "Uma-Senha-Forte-482"
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


class HealthChecksTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_email_is_a_failure(self):
        self.assertEqual(health.check_email()["status"], health.FAIL)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST_USER="a@b.com",
        EMAIL_HOST_PASSWORD="x", DEFAULT_FROM_EMAIL="HoraCerta <a@b.com>",
    )
    def test_real_smtp_config_passes(self):
        self.assertEqual(health.check_email()["status"], health.OK)

    def test_public_url_must_be_https_domain_not_ip(self):
        with override_settings(APP_BASE_URL="http://18.119.139.101"):
            self.assertEqual(health.check_public_url()["status"], health.FAIL)
        with override_settings(APP_BASE_URL="https://18.119.139.101"):
            self.assertEqual(health.check_public_url()["status"], health.FAIL)
        with override_settings(APP_BASE_URL="https://horacertagestao.com.br"):
            self.assertEqual(health.check_public_url()["status"], health.OK)

    def test_debug_and_weak_secret_are_failures(self):
        with override_settings(DEBUG=True):
            self.assertEqual(health.check_debug()["status"], health.FAIL)
        with override_settings(SECRET_KEY="django-insecure-abc"):
            self.assertEqual(health.check_secret_key()["status"], health.FAIL)

    def test_pending_migration_is_reported(self):
        fake = mock.Mock(app_label="accounts")
        fake.name = "9999_fake"
        with mock.patch("accounts.health.MigrationExecutor") as executor:
            executor.return_value.migration_plan.return_value = [(fake, False)]
            result = health.check_pending_migrations()

        self.assertEqual(result["status"], health.FAIL)
        self.assertIn("accounts.9999_fake", result["detail"])

    def test_database_check_passes_in_tests(self):
        self.assertEqual(health.check_database()["status"], health.OK)

    def test_command_exits_nonzero_on_failure(self):
        out = StringIO()
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            with self.assertRaises(SystemExit) as ctx:
                call_command("check_health", stdout=out)

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("E-mail em modo CONSOLE", out.getvalue())


@override_settings(**BASE)
class InternalHealthPageTests(TestCase):
    def test_only_superuser_can_open_it_and_no_secret_is_shown(self):
        admin = User.objects.create_user(username="a@example.com", email="a@example.com", password=PWD, is_superuser=True)
        mei = User.objects.create_user(username="m@example.com", email="m@example.com", password=PWD)

        self.assertEqual(self.client.get(reverse("internal_health")).status_code, 302)
        self.client.force_login(mei)
        self.assertEqual(self.client.get(reverse("internal_health")).status_code, 403)
        self.client.force_login(admin)
        with override_settings(EMAIL_HOST_PASSWORD="segredo-super-secreto"):
            response = self.client.get(reverse("internal_health"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saúde do sistema")
        self.assertNotContains(response, "segredo-super-secreto")
