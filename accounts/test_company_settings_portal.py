from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class CompanySettingsPortalTests(TestCase):
    def setUp(self):
        self.company_user = User.objects.create_user(
            username="empresa-config@example.test",
            email="empresa-config@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.client.force_login(self.company_user)

    def test_company_settings_links_to_hiring_organization_portal(self):
        response = self.client.get(reverse("company_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal da empresa contratante")
        self.assertContains(response, reverse("organization_entry"))
        self.assertContains(response, "prestadores de serviço")

    def test_company_settings_does_not_offer_legacy_location_tracking_configuration(self):
        response = self.client.get(reverse("company_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Confiabilidade do registro")
        self.assertNotContains(response, "company_attendance_reliability")
