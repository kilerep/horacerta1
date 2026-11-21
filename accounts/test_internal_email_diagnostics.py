from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

PWD = "Uma-Senha-Forte-482"
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


@override_settings(**BASE)
class InternalEmailDiagnosticsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin@example.com", email="admin@example.com", password=PWD, is_superuser=True, is_staff=True
        )
        self.mei = User.objects.create_user(
            username="mei@example.com", email="mei@example.com", password=PWD, role=User.Role.FUNCIONARIO
        )

    def test_anonymous_and_regular_users_cannot_open_it(self):
        self.assertEqual(self.client.get(reverse("internal_email")).status_code, 302)
        self.client.force_login(self.mei)
        self.assertEqual(self.client.get(reverse("internal_email")).status_code, 403)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_mode_is_flagged_as_the_problem(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("internal_email"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "modo CONSOLE")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="contato@horacerta.com.br",
        EMAIL_HOST_PASSWORD="segredo-super-secreto",
    )
    def test_page_never_shows_the_smtp_password(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("internal_email"))

        self.assertNotContains(response, "segredo-super-secreto")
        self.assertContains(response, "Senha definida: sim")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_sends_a_test_email_and_reports_success(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("internal_email"), {"to_email": "destino@example.com"})

        self.assertContains(response, "Enviado para destino@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["destino@example.com"]])

    def test_shows_the_real_error_when_sending_fails(self):
        self.client.force_login(self.admin)

        with mock.patch("django.core.mail.send_mail", side_effect=OSError("Connection refused")):
            response = self.client.post(reverse("internal_email"), {"to_email": "destino@example.com"})

        self.assertContains(response, "Falhou ao enviar")
        self.assertContains(response, "OSError: Connection refused")


@override_settings(**BASE)
class PasswordResetResilienceTests(TestCase):
    def test_smtp_failure_does_not_break_reset_or_reveal_the_account(self):
        User.objects.create_user(username="quem@example.com", email="quem@example.com", password=PWD)

        with mock.patch("django.contrib.auth.forms.PasswordResetForm.send_mail", side_effect=OSError("smtp down")):
            existing = self.client.post(reverse("password_reset"), {"email": "quem@example.com"})
            unknown = self.client.post(reverse("password_reset"), {"email": "ninguem@example.com"})

        self.assertEqual(existing.status_code, 302)
        self.assertEqual(existing["Location"], unknown["Location"])
