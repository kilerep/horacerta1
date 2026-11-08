from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiProductTourTests(TestCase):
    """Tour guiado (baloes) do Meu Resumo: aparece na primeira visita, some
    depois de dispensado, e o estado fica no usuario (nao em localStorage) -
    pedido do usuario para funcionar mesmo trocando de aparelho.
    """

    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="tour-mei@example.com",
            email="tour-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )

    def test_tour_is_offered_by_default_to_a_user_who_never_dismissed_it(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mei_panel")
        self.assertContains(response, "if (true) {")

    def test_dismissing_the_tour_persists_on_the_user_and_stops_auto_start(self):
        self.client.force_login(self.mei_user)

        dismiss_response = self.client.post(reverse("mei_dismiss_tour"), {"tour": "mei_panel"})
        self.assertEqual(dismiss_response.status_code, 200)

        self.mei_user.refresh_from_db()
        self.assertIn("mei_panel", self.mei_user.dismissed_tours)

        panel_response = self.client.get(reverse("mei_panel"))
        self.assertContains(panel_response, "if (false) {")

    def test_dismiss_endpoint_rejects_unknown_tour_keys(self):
        self.client.force_login(self.mei_user)

        response = self.client.post(reverse("mei_dismiss_tour"), {"tour": "algo-inventado"})

        self.assertEqual(response.status_code, 400)
        self.mei_user.refresh_from_db()
        self.assertEqual(self.mei_user.dismissed_tours, [])

    def test_dismiss_endpoint_requires_login_and_post(self):
        response = self.client.post(reverse("mei_dismiss_tour"), {"tour": "mei_panel"})
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.mei_user)
        get_response = self.client.get(reverse("mei_dismiss_tour"))
        self.assertEqual(get_response.status_code, 405)

    def test_dismissing_the_tour_never_affects_another_user(self):
        other_user = User.objects.create_user(
            username="outro-tour-mei@example.com",
            email="outro-tour-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(self.mei_user)
        self.client.post(reverse("mei_dismiss_tour"), {"tour": "mei_panel"})

        other_user.refresh_from_db()
        self.assertEqual(other_user.dismissed_tours, [])
