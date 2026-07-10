from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class EventProposalTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="som-eventos@example.test",
            email="som-eventos@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.owner = User.objects.create_user(
            username="cliente-evento@example.test",
            email="cliente-evento@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            owner=self.owner,
            name="Cliente Evento",
            whatsapp="47999990000",
            email="cliente-evento@example.test",
        )
        self.employee = Employee.objects.create(
            user=self.professional,
            company=self.company,
            full_name="Operador de som",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate=Decimal("0.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(
            name="Eventos e sonorização",
            slug="eventos-sonorizacao-teste",
            is_active=True,
        )
        self.job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Som para aniversário",
            description="Operação de som, montagem e desmontagem.",
            service_street="Rua do Evento",
            service_number="100",
            service_city="Blumenau",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time="18:00",
            planned_end_time="23:00",
            billing_mode=ServiceJob.BillingMode.FIXED,
            fixed_labor_value=Decimal("1450.00"),
            notes="Sinal e saldo serão combinados com o cliente antes do evento.",
            status=ServiceJob.Status.PLANNED,
        )
        ServiceItemExpense.objects.create(
            service_job=self.job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Caixa ativa",
            unit=ServiceItemUnit.UNIT,
            quantity=Decimal("2.00"),
            unit_value=Decimal("450.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )

    def test_event_proposal_review_generates_public_sheet_and_hides_item_prices(self):
        self.client.force_login(self.professional)

        review_response = self.client.get(reverse("service_event_proposal_detail", args=[self.job.id]))

        self.assertEqual(review_response.status_code, 200)
        self.assertContains(review_response, "Revisar proposta de evento")
        self.assertContains(review_response, "Proposta pronta para envio")
        self.assertContains(review_response, "R$ 1.450,00")
        self.assertContains(review_response, "Caixa ativa")
        self.assertNotContains(review_response, "R$ 450,00")

        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.preview_generated_at)
        self.assertIsNone(self.job.preview_sent_at)
        self.assertEqual(self.job.status, ServiceJob.Status.PLANNED)

        public_response = self.client.get(reverse("public_service_event_proposal", args=[self.job.public_token]))
        self.assertEqual(public_response.status_code, 200)
        self.assertContains(public_response, "Proposta de evento")
        self.assertContains(public_response, "R$ 1.450,00")
        self.assertContains(public_response, "Caixa ativa")
        self.assertContains(public_response, "Valor fechado")
        self.assertNotContains(public_response, "R$ 450,00")

    def test_event_proposal_whatsapp_marks_the_proposal_as_sent(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_event_proposal_whatsapp", args=[self.job.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("wa.me", response.url)
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.preview_generated_at)
        self.assertIsNotNone(self.job.preview_sent_at)
        self.assertEqual(self.job.status, ServiceJob.Status.SENT)

    def test_other_professional_cannot_open_the_event_proposal(self):
        other = User.objects.create_user(
            username="outro@example.test",
            email="outro@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other)

        response = self.client.get(reverse("service_event_proposal_detail", args=[self.job.id]))

        self.assertEqual(response.status_code, 404)
