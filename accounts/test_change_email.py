from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

PWD = "Uma-Senha-Forte-482"


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ChangeEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="antigo@example.com", email="antigo@example.com", password=PWD, role=User.Role.FUNCIONARIO
        )
        self.other = User.objects.create_user(
            username="outro@example.com", email="outro@example.com", password=PWD, role=User.Role.FUNCIONARIO
        )
        self.client.force_login(self.user)

    def test_requires_login(self):
        response = self.client_class().get(reverse("change_email"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_changes_email_and_username_and_keeps_session(self):
        response = self.client.post(reverse("change_email"), {"new_email": "Novo@Example.com", "current_password": PWD})

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual((self.user.email, self.user.username), ("novo@example.com", "novo@example.com"))
        self.assertEqual(self.client.get(reverse("mei_panel")).status_code, 200)

    def test_new_email_can_be_used_to_log_in(self):
        self.client.post(reverse("change_email"), {"new_email": "novo@example.com", "current_password": PWD})
        anonymous = self.client_class()

        response = anonymous.post(reverse("login"), {"username": "novo@example.com", "password": PWD})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(anonymous.session["_auth_user_id"]), self.user.pk)

    def test_wrong_password_does_not_change_anything(self):
        response = self.client.post(
            reverse("change_email"), {"new_email": "novo@example.com", "current_password": "errada"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Senha atual incorreta")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "antigo@example.com")

    def test_email_used_by_another_account_is_rejected(self):
        response = self.client.post(
            reverse("change_email"), {"new_email": "OUTRO@example.com", "current_password": PWD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível usar este e-mail")
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.email, "antigo@example.com")
        self.assertEqual(self.other.email, "outro@example.com")

    def test_menu_links_to_email_change_even_for_mei_without_clients(self):
        response = self.client.get(reverse("mei_panel"))

        self.assertContains(response, reverse("change_email"))
