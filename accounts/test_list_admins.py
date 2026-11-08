from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User


class ListAdminsCommandTests(TestCase):
    def test_lists_superusers_without_any_password_data(self):
        User.objects.create_user(username="chefe@example.com", email="chefe@example.com", password="Segredo-Forte-9", is_superuser=True)
        User.objects.create_user(username="mei@example.com", email="mei@example.com", password="Segredo-Forte-9")
        out = StringIO()

        call_command("list_admins", stdout=out)

        text = out.getvalue()
        self.assertIn("chefe@example.com", text)
        self.assertNotIn("mei@example.com", text)
        self.assertNotIn("Segredo-Forte-9", text)
        self.assertIn("/interno/email/", text)

    def test_warns_when_there_is_no_admin(self):
        out = StringIO()

        call_command("list_admins", stdout=out)

        self.assertIn("Nenhum administrador", out.getvalue())
