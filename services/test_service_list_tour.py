from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class ServiceListTourTests(TestCase):
    """Tour guiado (baloes) da tela de Servicos, pedido do usuario para
    resolver a confusao real entre "pedido" e "servico" no fluxo. Reaproveita
    o mesmo endpoint de dispensar tour ja usado no Meu Resumo.
    """

    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="tour-services@example.com",
            email="tour-services@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )

    def test_tour_is_offered_by_default_and_explains_pedido_vs_servico(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("service_job_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "service_job_list")
        self.assertContains(response, "if (true) {")
        self.assertContains(response, "Um pedido aceito vira um serviço")

    def test_dismissing_the_services_tour_stops_auto_start_without_affecting_mei_panel_tour(self):
        self.client.force_login(self.mei_user)

        dismiss_response = self.client.post(reverse("mei_dismiss_tour"), {"tour": "service_job_list"})
        self.assertEqual(dismiss_response.status_code, 200)

        self.mei_user.refresh_from_db()
        self.assertIn("service_job_list", self.mei_user.dismissed_tours)
        self.assertFalse(self.mei_user.has_dismissed_tour("mei_panel"))

        services_response = self.client.get(reverse("service_job_list"))
        self.assertContains(services_response, "if (false) {")

        panel_response = self.client.get(reverse("mei_panel"))
        self.assertContains(panel_response, "if (true) {")

    def test_quick_actions_visually_separate_frequent_from_configuration_actions(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("service_job_list"))

        self.assertContains(response, 'class="quick-card primary"', count=2)
        self.assertContains(response, 'class="quick-card muted"', count=2)
