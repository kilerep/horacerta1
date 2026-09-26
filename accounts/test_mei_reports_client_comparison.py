from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, Punch


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiReportsClientComparisonTests(TestCase):
    """Bloco 4 do roadmap: "Comparativo simples por cliente e periodo"."""

    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="comparativo-mei@example.com",
            email="comparativo-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.owner_a = User.objects.create_user(
            username="comparativo-cliente-a@example.com",
            email="comparativo-cliente-a@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.owner_b = User.objects.create_user(
            username="comparativo-cliente-b@example.com",
            email="comparativo-cliente-b@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company_a = Company.objects.create(
            owner=self.owner_a,
            name="Cliente Alfa",
            email="comparativo-a@example.com",
        )
        self.company_b = Company.objects.create(
            owner=self.owner_b,
            name="Cliente Beta",
            email="comparativo-b@example.com",
        )
        self.employee_a = Employee.objects.create(
            user=self.mei_user,
            company=self.company_a,
            full_name="Prestador do comparativo",
            is_active=True,
        )
        self.employee_b = Employee.objects.create(
            user=self.mei_user,
            company=self.company_b,
            full_name="Prestador do comparativo",
            is_active=True,
        )
        self.contract_a = Contract.objects.create(
            employee=self.employee_a,
            company=self.company_a,
            hourly_rate=Decimal("100.00"),
            start_date=timezone.localdate() - timedelta(days=60),
            is_active=True,
        )
        self.contract_b = Contract.objects.create(
            employee=self.employee_b,
            company=self.company_b,
            hourly_rate=Decimal("50.00"),
            start_date=timezone.localdate() - timedelta(days=60),
            is_active=True,
        )

    def _punch_hours(self, contract, day, start_hour, hours):
        start = timezone.make_aware(datetime.combine(day, time(hour=start_hour)))
        Punch.objects.create(contract=contract, timestamp=start)
        Punch.objects.create(contract=contract, timestamp=start + timedelta(hours=hours))

    def test_comparison_shows_totals_per_client_for_current_month_by_default(self):
        today = timezone.localdate()
        self._punch_hours(self.contract_a, today, 8, 4)
        self._punch_hours(self.contract_b, today, 8, 2)
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comparativo por cliente")
        self.assertContains(response, "Cliente Alfa")
        self.assertContains(response, "Cliente Beta")
        self.assertContains(response, "04:00")
        self.assertContains(response, "R$ 400,00")
        self.assertContains(response, "02:00")
        self.assertContains(response, "R$ 100,00")
        # Cliente Alfa trabalhou mais horas no periodo: deve aparecer com a
        # barra cheia (maior total do comparativo).
        self.assertContains(response, "--comparison-width: 100%")

    def test_comparison_respects_explicit_date_filter(self):
        today = timezone.localdate()
        outside_period = today - timedelta(days=45)
        self._punch_hours(self.contract_a, outside_period, 8, 3)
        self.client.force_login(self.mei_user)

        response = self.client.get(
            reverse("mei_reports"),
            {"date_from": today.replace(day=1).isoformat(), "date_to": today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comparativo por cliente")
        # Fora do periodo filtrado, o total do cliente Alfa deve ser zero.
        self.assertContains(response, "00:00")

    def test_comparison_is_hidden_with_a_single_client(self):
        Contract.objects.filter(id=self.contract_b.id).delete()
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Comparativo por cliente")

    def test_comparison_never_leaks_another_providers_clients(self):
        other_mei_user = User.objects.create_user(
            username="outro-prestador@example.com",
            email="outro-prestador@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        other_owner = User.objects.create_user(
            username="outro-cliente@example.com",
            email="outro-cliente@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        other_company = Company.objects.create(
            owner=other_owner,
            name="Cliente de outro prestador",
            email="outro-cliente-empresa@example.com",
        )
        other_employee = Employee.objects.create(
            user=other_mei_user,
            company=other_company,
            full_name="Outro prestador",
            is_active=True,
        )
        Contract.objects.create(
            employee=other_employee,
            company=other_company,
            hourly_rate=Decimal("70.00"),
            start_date=timezone.localdate() - timedelta(days=30),
            is_active=True,
        )
        today = timezone.localdate()
        self._punch_hours(self.contract_a, today, 8, 1)
        self._punch_hours(self.contract_b, today, 8, 1)
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cliente de outro prestador")
