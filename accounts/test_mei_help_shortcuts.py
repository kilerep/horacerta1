from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiReportsHelpShortcutTests(TestCase):
    """Atalho contextual (assistente leve) que leva direto para a secao de
    duvidas sobre relatorios em vez de deixar o prestador procurar sozinho.
    """

    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="ajuda-mei@example.com",
            email="ajuda-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.owner = User.objects.create_user(
            username="ajuda-cliente@example.com",
            email="ajuda-cliente@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            owner=self.owner,
            name="Cliente do teste de ajuda",
            email="ajuda-empresa@example.com",
        )
        self.employee = Employee.objects.create(
            user=self.mei_user,
            company=self.company,
            full_name="Prestador do teste de ajuda",
            is_active=True,
        )
        Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate=Decimal("50.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )

    def test_reports_page_links_to_relevant_help_section(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_reports"))

        self.assertEqual(response.status_code, 200)
        expected_href = f"{reverse('help')}#categoria-relatorios"
        self.assertContains(response, expected_href)
