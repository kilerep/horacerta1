from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob, ServiceWorkLog


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceRepeatTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="recorrente@example.test",
            email="recorrente@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="cliente-recorrente@example.test",
            email="cliente-recorrente@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(owner=owner, name="Cliente Recorrente", whatsapp="47999990000")
        employee = Employee.objects.create(
            user=self.professional,
            company=company,
            full_name="Prestador Recorrente",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=company,
            hourly_rate=Decimal("85.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.get(slug="manutencao")
        self.source = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Manutenção preventiva",
            description="Revisar componentes e realizar testes.",
            service_street="Rua da Manutenção",
            service_number="55",
            service_city="Blumenau",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time=time(9, 0),
            planned_end_time=time(11, 0),
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("85.00"),
            notes="Levar ferramentas de teste.",
            status=ServiceJob.Status.REPORT_SENT,
        )
        ServiceItemExpense.objects.create(
            service_job=self.source,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Kit de limpeza",
            unit=ServiceItemUnit.UNIT,
            quantity=Decimal("1.00"),
            unit_value=Decimal("30.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
            receipt_note="Usado no atendimento anterior.",
        )
        ServiceWorkLog.objects.create(
            service_job=self.source,
            work_date=timezone.localdate(),
            start_time=time(9, 0),
            end_time=time(10, 30),
            description="Atendimento anterior.",
        )
        self.client.force_login(self.professional)

    def test_service_detail_offers_next_visit(self):
        response = self.client.get(reverse("service_job_detail", args=[self.source.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criar próxima visita")
        self.assertContains(response, reverse("service_job_repeat", args=[self.source.id]))

    def test_repeat_page_prefills_previous_service(self):
        response = self.client.get(reverse("service_job_repeat", args=[self.source.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Serviço recorrente ou nova visita")
        self.assertContains(response, "Manutenção preventiva")
        self.assertContains(response, "Cliente Recorrente")
        self.assertContains(response, "sem copiar horas trabalhadas")

    def test_repeat_creates_independent_planned_visit_and_resets_execution(self):
        next_date = timezone.localdate() + timedelta(days=30)

        response = self.client.post(
            reverse("service_job_repeat", args=[self.source.id]),
            {
                "title": "Manutenção preventiva mensal",
                "next_date": next_date.isoformat(),
                "planned_start_time": "10:00",
                "planned_end_time": "12:00",
                "copy_items": "on",
                "copy_notes": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        repeated = ServiceJob.objects.exclude(id=self.source.id).get(title="Manutenção preventiva mensal")
        self.assertEqual(response.url, reverse("service_job_detail", args=[repeated.id]))
        self.assertEqual(repeated.professional, self.professional)
        self.assertEqual(repeated.contract, self.contract)
        self.assertEqual(repeated.client, self.contract.company)
        self.assertEqual(repeated.category, self.category)
        self.assertEqual(repeated.start_date, next_date)
        self.assertEqual(repeated.planned_start_time, time(10, 0))
        self.assertEqual(repeated.planned_end_time, time(12, 0))
        self.assertEqual(repeated.status, ServiceJob.Status.PLANNED)
        self.assertEqual(repeated.notes, self.source.notes)
        self.assertNotEqual(repeated.public_token, self.source.public_token)
        self.assertIsNone(repeated.preview_generated_at)
        self.assertIsNone(repeated.preview_sent_at)
        self.assertIsNone(repeated.public_report_first_viewed_at)
        self.assertFalse(repeated.work_logs.exists())

        copied_item = repeated.item_expenses.get(name="Kit de limpeza")
        self.assertEqual(copied_item.usage_status, ServiceItemExpense.UsageStatus.PLANNED)
        self.assertEqual(copied_item.quantity, Decimal("1.00"))
        self.assertEqual(copied_item.unit_value, Decimal("30.00"))
        self.assertEqual(copied_item.receipt_note, "")

    def test_repeat_can_skip_items_and_notes(self):
        next_date = timezone.localdate() + timedelta(days=60)

        response = self.client.post(
            reverse("service_job_repeat", args=[self.source.id]),
            {
                "title": "Visita sem materiais",
                "next_date": next_date.isoformat(),
                "planned_start_time": "09:00",
                "planned_end_time": "11:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        repeated = ServiceJob.objects.get(title="Visita sem materiais")
        self.assertEqual(repeated.notes, "")
        self.assertFalse(repeated.item_expenses.exists())

    def test_other_professional_cannot_repeat_service(self):
        other = User.objects.create_user(
            username="outro-recorrente@example.test",
            email="outro-recorrente@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other)

        response = self.client.get(reverse("service_job_repeat", args=[self.source.id]))

        self.assertEqual(response.status_code, 404)
