"""2026-11-17: folgas e feriados aparecem no Historico e no fechamento de horas (opcao a)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, DayOff, Punch

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


@override_settings(**BASE)
class DayOffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="folga@example.com", email="folga@example.com",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Ensimec", email="cli-folga@example.com")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Fagner", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2025, 1, 1), is_active=True)
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.day = self.today.replace(day=1)

    def test_mark_and_unmark_day_off(self):
        self.client.post(reverse("mei_day_off"), {"date": self.day.isoformat(), "kind": "FERIADO", "note": "Feriado local"})
        off = DayOff.objects.get(owner=self.user)
        self.assertEqual((off.date, off.kind, off.note), (self.day, "FERIADO", "Feriado local"))

        self.client.post(reverse("mei_day_off"), {"date": self.day.isoformat(), "action": "remove"})
        self.assertFalse(DayOff.objects.exists())

    def test_history_shows_day_off_instead_of_empty(self):
        DayOff.objects.create(owner=self.user, date=self.day, kind=DayOff.Kind.FOLGA)

        html = self.client.get(reverse("mei_history")).content.decode()

        self.assertIn("Folgas e feriados", html)
        self.assertIn('status-dayoff', html)
        self.assertIn(f"{self.day:%d/%m} (Folga)", html)

    def test_report_payload_and_pdf_carry_day_off(self):
        from accounts.views._shared import _build_service_report_payload

        DayOff.objects.create(owner=self.user, date=self.day, kind=DayOff.Kind.FERIADO, note="Natal")
        payload = _build_service_report_payload(self.contract, self.day, self.day + timedelta(days=1))

        self.assertEqual(payload["days"][0]["day_off"], "Feriado · Natal")
        self.assertEqual(payload["days"][1]["day_off"], "")

    def test_other_user_day_off_is_not_shown(self):
        other = User.objects.create_user(username="outra-folga@example.com", email="outra-folga@example.com",
                                         password="Teste@12345", role=User.Role.FUNCIONARIO)
        DayOff.objects.create(owner=other, date=self.day, kind=DayOff.Kind.FOLGA)

        self.assertNotIn(f"{self.day:%d/%m} (Folga)", self.client.get(reverse("mei_history")).content.decode())

    def test_bad_date_does_not_crash(self):
        response = self.client.post(reverse("mei_day_off"), {"date": "ontem"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(DayOff.objects.exists())
