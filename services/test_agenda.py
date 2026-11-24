"""2026-11-17: agenda da semana dos servicos e lembrete do dia (sininho e Meu resumo)."""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract, InternalNotification

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


@override_settings(**BASE)
class AgendaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="agenda@example.com", email="agenda@example.com",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Ensimec", email="cli-agenda@example.com")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Fagner", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2025, 1, 1), is_active=True)
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def _job(self, title, day, status=ServiceJob.Status.PLANNED, start=time(9, 0), user=None, contract=None):
        return ServiceJob.objects.create(
            professional=user or self.user, contract=contract or self.contract, category=self.category, title=title,
            status=status, start_date=day, planned_start_time=start,
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("50.00"),
        )

    def test_week_lists_jobs_by_day_and_skips_archived(self):
        self._job("Troca de chuveiro", self.today)
        self._job("Arquivado", self.today, status=ServiceJob.Status.ARCHIVED)

        html = self.client.get(reverse("service_agenda")).content.decode()

        self.assertIn("Agenda da semana", html)
        self.assertIn("Troca de chuveiro", html)
        self.assertIn("09:00", html)
        self.assertNotIn("Arquivado", html)
        self.assertIn("Hoje", html)

    def test_navigate_to_next_week(self):
        next_week = self.today + timedelta(days=7)
        self._job("Semana que vem", next_week)

        html = self.client.get(reverse("service_agenda"), {"semana": next_week.isoformat()}).content.decode()

        self.assertIn("Semana que vem", html)
        self.assertIn("Esta semana", html)

    def test_today_reminder_once_in_bell_and_on_panel(self):
        self._job("Quadro elétrico", self.today)

        panel = self.client.get(reverse("mei_panel")).content.decode()
        self.client.get(reverse("service_agenda"))

        self.assertIn("Hoje você tem 1 serviço", panel)
        self.assertEqual(InternalNotification.objects.filter(
            recipient_user=self.user, notification_type=InternalNotification.NotificationType.SERVICE_REMINDER).count(), 1)

    def test_no_reminder_without_jobs_today_and_other_users_isolated(self):
        other = User.objects.create_user(username="outro-agenda@example.com", email="outro-agenda@example.com",
                                         password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=other, name="Outra", email="cli-outra-agenda@example.com")
        employee = Employee.objects.create(user=other, company=company, full_name="Outro", is_active=True)
        contract = Contract.objects.create(company=company, employee=employee, start_date=date(2025, 1, 1), is_active=True)
        self._job("Do outro", self.today, user=other, contract=contract)

        self.client.get(reverse("mei_panel"))
        html = self.client.get(reverse("service_agenda")).content.decode()

        self.assertNotIn("Do outro", html)
        self.assertFalse(InternalNotification.objects.filter(recipient_user=self.user).exists())

    def test_services_nav_has_agenda(self):
        html = self.client.get(reverse("service_job_list")).content.decode()

        self.assertIn(reverse("service_agenda"), html)
