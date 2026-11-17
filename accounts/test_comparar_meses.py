"""2026-11-17: Meu resumo compara as horas do mes com o mesmo periodo do mes passado, por cliente."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, Punch

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def punch_pair(contract, day, hours):
    start = timezone.make_aware(datetime.combine(day, time(8, 0)))
    Punch.objects.create(contract=contract, timestamp=start)
    Punch.objects.create(contract=contract, timestamp=start + timedelta(hours=hours))


@override_settings(**BASE)
class CompareMonthsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compara@example.com", email="compara@example.com",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Ensimec", email="cli-compara@example.com")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Fagner", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2025, 1, 1), is_active=True)
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.prev_first = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)

    def _panel(self):
        return self.client.get(reverse("mei_panel")).content.decode()

    def test_more_hours_than_same_period_last_month(self):
        punch_pair(self.contract, self.today.replace(day=1), 5)
        punch_pair(self.contract, self.prev_first, 2)

        html = self._panel()

        self.assertIn("+03:00", html)
        self.assertIn("que no mesmo período do mês passado", html)

    def test_fewer_hours_shows_minus(self):
        punch_pair(self.contract, self.today.replace(day=1), 1)
        punch_pair(self.contract, self.prev_first, 4)

        self.assertIn("-03:00", self._panel())

    def test_hours_after_same_day_last_month_do_not_count(self):
        punch_pair(self.contract, self.today.replace(day=1), 2)
        prev_last = self.today.replace(day=1) - timedelta(days=1)
        if prev_last.day > self.today.day:  # dia do mes passado depois do "hoje": fica fora da comparacao
            punch_pair(self.contract, prev_last, 6)

        # as 6h do fim do mes passado ficam fora: nao ha horas no mesmo periodo para comparar
        self.assertIn("Sem horas no mesmo período do mês passado", self._panel())

    def test_no_history_says_so(self):
        self.assertIn("Sem horas no mesmo período do mês passado", self._panel())
