from django.test import SimpleTestCase
from django.urls import reverse


class PublicHelpPageTests(SimpleTestCase):
    def test_help_page_explains_current_mei_first_flow(self):
        response = self.client.get(reverse("help"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MEIs e prestadores")
        self.assertContains(response, "Cadastre o primeiro cliente")
        self.assertContains(response, "Pedidos e serviços")
        self.assertContains(response, "O cliente precisa de conta?")
        self.assertContains(response, "O HoraCerta usa GPS?")
        self.assertContains(response, "Meu Perfil → Segurança da conta")

    def test_help_page_does_not_keep_outdated_company_first_message(self):
        response = self.client.get(reverse("help"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Empresa cadastra o MEI")
        self.assertNotContains(response, "Empresa acompanha em tempo real")

    def test_help_page_has_searchable_faq_with_expanded_topics(self):
        """Assistente leve (Bloco novo, sem custo de IA): busca por palavra-chave
        sobre uma base de perguntas mais ampla, em vez de só 4 duvidas fixas.
        """
        response = self.client.get(reverse("help"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="help-search"')
        self.assertContains(response, 'id="categoria-relatorios"')
        self.assertContains(response, 'id="categoria-clientes-contratos"')
        self.assertContains(response, "Instalar como app")
        self.assertContains(response, "Central de Notificações")
        self.assertContains(response, "Nenhuma dúvida encontrada")

    def test_help_page_faq_items_carry_searchable_text(self):
        response = self.client.get(reverse("help"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="faq-item"')
        self.assertContains(response, "data-search=")
