from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiProfileProviderLinksTests(TestCase):
    def setUp(self):
        self.provider = User.objects.create_user(
            username="prestador-perfil@example.test",
            email="prestador-perfil@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        company_owner = User.objects.create_user(
            username="cliente-perfil@example.test",
            email="cliente-perfil@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(
            owner=company_owner,
            name="Cliente do perfil",
        )
        employee = Employee.objects.create(
            user=self.provider,
            company=company,
            full_name="Prestador do perfil",
            is_active=True,
        )
        Contract.objects.create(
            employee=employee,
            company=company,
            hourly_rate=Decimal("85.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.client.force_login(self.provider)

    def test_profile_links_to_provider_company_invites(self):
        response = self.client.get(reverse("mei_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresas contratantes")
        self.assertContains(response, "Abrir vínculos e convites")
        self.assertContains(response, reverse("provider_link_invites"))
        self.assertContains(response, "facilitar a operação")
