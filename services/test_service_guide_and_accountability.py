from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceJob, ServiceWorkLog


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceGuideAndAccountabilityTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-guia@example.test",
            email="prestador-guia@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="cliente-guia@example.test",
            email="cliente-guia@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            owner=owner,
            name="Empresa da viagem",
            whatsapp="47999990000",
            email="empresa-viagem@example.test",
        )
        employee = Employee.objects.create(
            user=self.professional,
            company=self.company,
            full_name="Prestador da viagem",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=self.company,
            hourly_rate=Decimal("100.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(
            name="Administrativo e escritório",
            slug="administrativo-escritorio",
            description="Atendimento externo e apoio administrativo.",
            is_active=True,
        )
        self.client.force_login(self.professional)

    def test_services_page_prioritizes_guided_start_paths(self):
        response = self.client.get(reverse("service_job_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Central de serviços")
        self.assertContains(response, "Começar um atendimento")
        self.assertContains(response, "Pedido vindo do WhatsApp")
        self.assertContains(response, "Evento ou sonorização")
        self.assertContains(response, "Viagem ou atendimento externo")
        self.assertContains(response, "Entenda as etapas e os documentos")
        self.assertContains(response, "Pedido de serviço")
        self.assertContains(response, "Folha ou proposta")
        self.assertContains(response, "prestação de contas")
        self.assertContains(response, reverse("service_start_guide"))
        self.assertContains(response, reverse("service_travel_create"))

    def test_start_guide_explains_flow_from_request_to_report(self):
        response = self.client.get(reverse("service_start_guide"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registrar o pedido")
        self.assertContains(response, "Enviar a folha")
        self.assertContains(response, "Executar e registrar")
        self.assertContains(response, "Entregar o relatório")
        self.assertContains(response, "Vou fazer um evento ou sonorização")
        self.assertContains(response, "Vou viajar ou trabalhar fora da empresa")
        self.assertContains(response, "mostra a próxima ação")
        self.assertContains(response, reverse("service_job_create_from_template", args=["evento-sonorizacao"]))

    def test_travel_flow_creates_zero_value_expense_presets(self):
        response = self.client.post(
            reverse("service_travel_create"),
            {
                "client_mode": "registered",
                "contract": str(self.contract.id),
                "category": str(self.category.id),
                "title": "Viagem para atendimento na filial",
                "description": "Atendimento presencial e levantamento de atividades.",
                "billing_mode": ServiceJob.BillingMode.HOURLY,
                "notes": "Registrar comprovantes e períodos trabalhados.",
                "submit_action": "draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        job = ServiceJob.objects.get(title="Viagem para atendimento na filial")
        self.assertEqual(response.url, reverse("service_job_detail", args=[job.id]))
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)
        self.assertEqual(job.contract, self.contract)
        self.assertEqual(job.item_expenses.count(), 5)
        self.assertSetEqual(
            set(job.item_expenses.values_list("name", flat=True)),
            {
                "Pedágio",
                "Combustível",
                "Estacionamento",
                "Alimentação em viagem",
                "Hospedagem ou passagem",
            },
        )
        for item in job.item_expenses.all():
            self.assertEqual(item.unit_value, Decimal("0.00"))
            self.assertEqual(item.usage_status, ServiceItemExpense.UsageStatus.PLANNED)

    def _create_completed_job(self):
        job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            client=self.company,
            category=self.category,
            title="Atendimento externo concluído",
            description="Atividades realizadas durante viagem de trabalho.",
            start_date=timezone.localdate(),
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("100.00"),
            status=ServiceJob.Status.REPORT_SENT,
            notes="Comprovantes conferidos com o responsável da empresa.",
        )
        ServiceWorkLog.objects.create(
            service_job=job,
            work_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(12, 0),
            description="Atendimento e levantamento na filial.",
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.FUEL,
            name="Combustível",
            quantity=Decimal("1.00"),
            unit_value=Decimal("120.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
            receipt_note="Cupom 123",
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Material de apoio",
            quantity=Decimal("2.00"),
            unit_value=Decimal("15.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        return job

    def test_accountability_separates_hours_expenses_and_materials(self):
        job = self._create_completed_job()

        response = self.client.get(reverse("service_accountability", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prestação de contas do serviço")
        self.assertContains(response, "Atendimento e levantamento na filial")
        self.assertContains(response, "Combustível")
        self.assertContains(response, "Cupom 123")
        self.assertContains(response, "Material de apoio")
        self.assertContains(response, "04:00")
        self.assertContains(response, "R$ 120,00")
        self.assertContains(response, "R$ 30,00")
        self.assertContains(response, "R$ 550,00")
        self.assertContains(response, reverse("service_accountability_pdf", args=[job.id]))
        self.assertContains(response, reverse("public_service_accountability", args=[job.public_token]))

    def test_public_accountability_requires_final_report(self):
        job = self._create_completed_job()
        public_url = reverse("public_service_accountability", args=[job.public_token])

        response = self.client.get(public_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresa da viagem")

        job.status = ServiceJob.Status.FINISHED
        job.save(update_fields=["status", "finished_at", "updated_at"])
        blocked = self.client.get(public_url)
        self.assertEqual(blocked.status_code, 404)

    def test_accountability_pdf_is_downloadable(self):
        job = self._create_completed_job()

        response = self.client.get(reverse("service_accountability_pdf", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("horacerta_prestacao_contas_", response["Content-Disposition"])

    def test_other_professional_cannot_open_internal_accountability(self):
        job = self._create_completed_job()
        other = User.objects.create_user(
            username="outro-prestador-guia@example.test",
            email="outro-prestador-guia@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other)

        response = self.client.get(reverse("service_accountability", args=[job.id]))

        self.assertEqual(response.status_code, 404)
