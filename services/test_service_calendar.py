from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceJob


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False, TIME_ZONE="America/Sao_Paulo")
class ServiceCalendarTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="agenda@example.test",
            email="agenda@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="cliente-agenda@example.test",
            email="cliente-agenda@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(owner=owner, name="Cliente Agenda", whatsapp="47999990000")
        employee = Employee.objects.create(
            user=self.professional,
            company=company,
            full_name="Prestador Agenda",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=company,
            hourly_rate=Decimal("100.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Instalação de quadro",
            description="Instalar e testar o novo quadro elétrico.",
            service_street="Rua Técnica",
            service_number="120",
            service_city="Blumenau",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time=time(8, 30),
            planned_end_time=time(11, 0),
            status=ServiceJob.Status.PLANNED,
        )
        self.client.force_login(self.professional)

    def test_service_detail_offers_calendar_download(self):
        response = self.client.get(reverse("service_job_detail", args=[self.job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adicionar ao calendário")
        self.assertContains(response, reverse("service_job_calendar_ics", args=[self.job.id]))

    def test_calendar_download_contains_service_data(self):
        response = self.client.get(reverse("service_job_calendar_ics", args=[self.job.id]))
        body = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("SUMMARY:Instalação de quadro", body)
        self.assertIn("DTSTART;TZID=America/Sao_Paulo:", body)
        self.assertIn("LOCATION:Rua Técnica\\, 120\\, Blumenau\\, SC", body)
        self.assertIn("Cliente: Cliente Agenda", body)
        self.assertIn("END:VCALENDAR", body)

    def test_calendar_requires_planned_date(self):
        job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Serviço sem data",
            status=ServiceJob.Status.DRAFT,
        )

        response = self.client.get(reverse("service_job_calendar_ics", args=[job.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_job_detail", args=[job.id]))

    def test_other_professional_cannot_download_calendar(self):
        other = User.objects.create_user(
            username="outro-agenda@example.test",
            email="outro-agenda@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other)

        response = self.client.get(reverse("service_job_calendar_ics", args=[self.job.id]))

        self.assertEqual(response.status_code, 404)
