"""Primeira semana de um cliente novo (analise 2026-11-15, itens 3, 6 e 7)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


@override_settings(**BASE)
class NewAccountDeadEndsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="novo-semana@example.com", email="novo-semana@example.com",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(self.user)

    def test_reports_without_clients_explains_instead_of_bouncing(self):
        response = self.client.get(reverse("mei_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Você ainda não tem clientes.")
        self.assertContains(response, reverse("mei_client_create"))

    def test_panel_without_clients_is_not_all_good(self):
        html = self.client.get(reverse("mei_panel")).content.decode()

        self.assertIn("Cadastre seu primeiro cliente", html)
        self.assertNotIn("Tudo em ordem", html)

    def test_help_covers_production_romaneio_and_written_reports(self):
        html = self.client.get(reverse("help")).content.decode()

        self.assertIn("Produção e romaneio", html)
        self.assertIn("relatório escrito", html)


@override_settings(**BASE)
class LeftoversAndContactTests(TestCase):
    def test_company_evaluation_page_redirects_to_signup(self):
        response = self.client.get("/avaliacao/")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], reverse("signup_mei"))

    def test_terms_no_longer_mention_company_self_signup(self):
        html = self.client.get(reverse("terms")).content.decode()

        self.assertNotIn("autocadastro de empresa", html)

    @override_settings(SUPPORT_EMAIL="suporte@horacertagestao.com.br", SUPPORT_WHATSAPP="11988887777",
                       COMPANY_LEGAL_NAME="HoraCerta Tecnologia", COMPANY_CNPJ="12.345.678/0001-90")
    def test_support_contact_comes_from_settings(self):
        terms = self.client.get(reverse("terms")).content.decode()
        user = User.objects.create_user(username="suporte@example.com", email="suporte@example.com",
                                        password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(user)
        panel = self.client.get(reverse("mei_panel")).content.decode()

        self.assertIn("mailto:suporte@horacertagestao.com.br", terms)
        self.assertIn("CNPJ 12.345.678/0001-90", terms)
        self.assertIn("https://wa.me/5511988887777", panel)
        self.assertIn("Falar com o suporte", panel)

    def test_no_support_button_without_whatsapp(self):
        user = User.objects.create_user(username="semzap@example.com", email="semzap@example.com",
                                        password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(user)

        self.assertNotIn("Falar com o suporte", self.client.get(reverse("mei_panel")).content.decode())
