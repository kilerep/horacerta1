from django.test import SimpleTestCase
from django.urls import reverse


class PublicHelpPageTests(SimpleTestCase):
    def test_help_page_explains_current_mei_first_flow(self):
        response = self.client.get(reverse("help"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MEIs e prestadores")
        self.assertContains(response, "Cadastre o primeiro cliente")
        self.assertContains(response, "Pedidos e serviços")
        self.assertContains(response, "O cliente precisa de conta?")
        self.assertContains(response, "O HoraCerta usa GPS?")
        self.assertContains(response, "Meu Perfil → Segurança da conta")

    def test_help_page_does_not_keep_outdated_company_first_message(self):
        response = self.client.get(reverse("help"))

        self.assertNotContains(response, "Empresa cadastra o MEI")
        self.assertNotContains(response, "Empresa acompanha em tempo real")
