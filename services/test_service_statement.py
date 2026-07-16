from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob, ServiceWorkLog


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceStatementTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-contas@example.test",
            email="prestador-contas@example.test",
            password="Teste@12345",
            first_name="Gabriel",
            role=User.Role.FUNCIONARIO,
        )
        self.category = ServiceCategory.objects.create(
            name="Atendimento externo",
            slug="atendimento-externo-test",
            is_active=True,
        )
        self.job = ServiceJob.objects.create(
            professional=self.professional,
            category=self.category,
            manual_client_name="Empresa Contratante",
            manual_client_whatsapp="47999990000",
            title="Viagem técnica para filial",
            description="Atendimento técnico realizado na filial.",
            service_city="Joinville",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time=time(8, 0),
            planned_end_time=time(18, 0),
            billing_mode=ServiceJob.BillingMode.FIXED,
            fixed_labor_value=Decimal("500.00"),
            status=ServiceJob.Status.FINISHED,
        )
        ServiceWorkLog.objects.create(
            service_job=self.job,
            work_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(10, 0),
            description="Reunião e atendimento técnico.",
        )
        ServiceItemExpense.objects.create(
            service_job=self.job,
            type=ServiceItemExpense.ItemType.FUEL,
            name="Combustível",
            unit=ServiceItemUnit.SERVICE,
            quantity=Decimal("1.00"),
            unit_value=Decimal("100.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
            receipt_note="Cupom fiscal 001",
        )
        ServiceItemExpense.objects.create(
            service_job=self.job,
            type=ServiceItemExpense.ItemType.TOLL,
            name="Pedágio",
            unit=ServiceItemUnit.SERVICE,
            quantity=Decimal("1.00"),
            unit_value=Decimal("30.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        ServiceItemExpense.objects.create(
            service_job=self.job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Cabo técnico",
            unit=ServiceItemUnit.UNIT,
            quantity=Decimal("1.00"),
            unit_value=Decimal("50.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        ServiceItemExpense.objects.create(
            service_job=self.job,
            type=ServiceItemExpense.ItemType.FOOD,
            name="Alimentação não utilizada",
            unit=ServiceItemUnit.SERVICE,
            quantity=Decimal("1.00"),
            unit_value=Decimal("40.00"),
            usage_status=ServiceItemExpense.UsageStatus.NOT_USED,
        )

    def test_provider_statement_groups_hours_expenses_and_items(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_statement", args=[self.job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prestação de contas")
        self.assertContains(response, "02:00")
        self.assertContains(response, "Combustível")
        self.assertContains(response, "Pedágio")
        self.assertContains(response, "Cabo técnico")
        self.assertContains(response, "Cupom fiscal 001")
        self.assertContains(response, "R$ 130,00")
        self.assertContains(response, "R$ 50,00")
        self.assertContains(response, "R$ 680,00")
        self.assertContains(response, "Alimentação não utilizada")
        self.assertContains(response, reverse("public_service_statement", args=[self.job.public_token]))

    def test_public_statement_can_be_shared_without_login(self):
        response = self.client.get(reverse("public_service_statement", args=[self.job.public_token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresa Contratante")
        self.assertContains(response, "Viagem técnica para filial")
        self.assertContains(response, "Imprimir ou salvar em PDF")
        self.assertNotContains(response, "Copiar link")

    def test_other_provider_cannot_open_private_statement(self):
        other = User.objects.create_user(
            username="outro-contas@example.test",
            email="outro-contas@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other)

        response = self.client.get(reverse("service_statement", args=[self.job.id]))

        self.assertEqual(response.status_code, 404)

    def test_service_card_links_to_statement(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_job_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prestação de contas")
        self.assertContains(response, reverse("service_statement", args=[self.job.id]))
