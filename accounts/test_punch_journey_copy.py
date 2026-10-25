"""O botao principal e o texto da jornada falam a lingua do prestador:
"Registrar entrada" / "Registrar saida", sem termos tecnicos (par/impar)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract, Punch


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class PunchJourneyCopyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="jornada@example.com", email="jornada@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO, first_name="Jo",
        )
        company = Company.objects.create(owner=self.user, name="Cliente ABC")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Jo", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.client.force_login(self.user)

    def _punch(self):
        Punch.objects.create(contract=self.contract, timestamp=timezone.now())

    def _page(self):
        return self.client.get(reverse("employee_dashboard"), {"contract": str(self.contract.id)})

    def test_no_punches_offers_entrada(self):
        response = self._page()

        self.assertContains(response, "Registrar entrada")
        self.assertContains(response, "Toque em “Registrar entrada”")
        self.assertNotContains(response, "Registrar saída · Cliente ABC")

    def test_one_open_punch_offers_saida_and_says_since_when(self):
        self._punch()

        response = self._page()

        self.assertContains(response, "Registrar saída · Cliente ABC")
        if timezone.localtime().hour >= 20:
            self.assertContains(response, "ainda não registrou a saída")
        else:
            self.assertContains(response, "Trabalhando desde")
            self.assertContains(response, "Quando terminar, toque em “Registrar saída”")

    def test_two_punches_close_the_period_and_offer_entrada_again(self):
        self._punch()
        self._punch()

        response = self._page()

        self.assertContains(response, "Registrar entrada · Cliente ABC")
        self.assertContains(response, "Saída registrada às")

    def test_no_technical_wording_on_the_punch_screen(self):
        self._punch()

        html = self._page().content.decode().lower()

        for word in ("timestamp", "ímpar", "impar", "número de registros"):
            self.assertNotIn(word, html)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class WorkPeriodEventTests(TestCase):
    def test_second_punch_of_the_day_emits_work_period_completed(self):
        from accounts.models import ProductEvent

        user = User.objects.create_user(
            username="periodo@example.com", email="periodo@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=user, name="Cliente P")
        employee = Employee.objects.create(user=user, company=company, full_name="P", is_active=True)
        contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.client.force_login(user)
        url = reverse("employee_dashboard")

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"action": "punch", "contract": str(contract.id)})
        first = ProductEvent.objects.filter(user=user, event="work_period_completed").count()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"action": "punch", "contract": str(contract.id)})
        second = ProductEvent.objects.filter(user=user, event="work_period_completed").count()

        self.assertEqual((first, second), (0, 1))
        self.assertEqual(ProductEvent.objects.filter(user=user, event="punch_recorded").count(), 2)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class FirstReportCtaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rel@example.com", email="rel@example.com", password="x-Senha-123456", role=User.Role.FUNCIONARIO
        )
        company = Company.objects.create(owner=self.user, name="Cliente R")
        employee = Employee.objects.create(user=self.user, company=company, full_name="R", is_active=True)
        self.company, self.employee = company, employee
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.client.force_login(self.user)

    def _page(self):
        return self.client.get(reverse("employee_dashboard"), {"contract": str(self.contract.id)})

    def test_cta_appears_only_after_a_completed_period_and_before_any_report(self):
        Punch.objects.create(contract=self.contract, timestamp=timezone.now())
        self.assertNotContains(self._page(), "Gerar meu primeiro relatório")

        Punch.objects.create(contract=self.contract, timestamp=timezone.now())
        self.assertContains(self._page(), "Gerar meu primeiro relatório")

    def test_cta_disappears_once_a_report_exists(self):
        from timeclock.models import ServiceReport

        Punch.objects.create(contract=self.contract, timestamp=timezone.now())
        Punch.objects.create(contract=self.contract, timestamp=timezone.now())
        ServiceReport.objects.create(
            company=self.company, employee=self.employee, contract=self.contract,
            report_date=date(2026, 6, 4), date_from=date(2026, 6, 1), date_to=date(2026, 6, 4), title="r",
        )

        self.assertNotContains(self._page(), "Gerar meu primeiro relatório")
