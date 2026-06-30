from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from companies.models import Company, Employee


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class PasswordChangeFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="seguranca-mei@example.com",
            email="seguranca-mei@example.com",
            password="SenhaAtual@123",
            role=User.Role.FUNCIONARIO,
        )
        self.owner = User.objects.create_user(
            username="empresa-seguranca@example.com",
            email="empresa-seguranca@example.com",
            password="SenhaEmpresa@123",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(
            owner=self.owner,
            name="Empresa de Segurança",
            email="empresa-seguranca@example.com",
        )
        Employee.objects.create(
            user=self.user,
            company=company,
            full_name="Prestador de Segurança",
        )

    def test_password_change_requires_authenticated_user(self):
        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_authenticated_user_can_change_password_and_keep_current_session(self):
        self.client.force_login(self.user)

        form_response = self.client.get(reverse("password_change"))
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, "Alterar senha")
        self.assertContains(form_response, "Senha atual")
        self.assertContains(form_response, "Nova senha")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "SenhaAtual@123",
                "new_password1": "NovaSenha@456",
                "new_password2": "NovaSenha@456",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Senha atualizada")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NovaSenha@456"))
        self.assertFalse(self.user.check_password("SenhaAtual@123"))

        current_session_response = self.client.get(reverse("password_change"))
        self.assertEqual(current_session_response.status_code, 200)

    def test_wrong_current_password_does_not_change_credentials(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "SenhaErrada@123",
                "new_password1": "NovaSenha@456",
                "new_password2": "NovaSenha@456",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("old_password", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SenhaAtual@123"))

    def test_mei_profile_exposes_password_change_action(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("mei_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Segurança da conta")
        self.assertContains(response, "Alterar senha")
        self.assertContains(response, reverse("password_change"))

    def test_company_settings_exposes_password_change_action(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("company_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Segurança da conta")
        self.assertContains(response, "Alterar senha")
        self.assertContains(response, reverse("password_change"))

    def test_company_sees_company_return_actions_after_password_change(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "SenhaEmpresa@123",
                "new_password1": "NovaSenhaEmpresa@456",
                "new_password2": "NovaSenhaEmpresa@456",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voltar às configurações")
        self.assertContains(response, reverse("company_settings"))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("NovaSenhaEmpresa@456"))
