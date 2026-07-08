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
class ServiceJobHealthPanelTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-health@example.test",
            email="prestador-health@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="cliente-health@example.test",
            email="cliente-health@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(owner=owner, name="Cliente Health", whatsapp="47999990000")
        employee = Employee.objects.create(
            user=self.professional,
            company=company,
            full_name="Prestador Health",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=company,
            hourly_rate=Decimal("90.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(name="Manutenção", slug="manutencao-health", is_active=True)

    def test_service_detail_shows_readiness_warnings_for_incomplete_service(self):
        job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Serviço sem local",
            status=ServiceJob.Status.PLANNED,
        )
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_job_detail", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checklist do serviço")
        self.assertContains(response, "Linha do tempo do serviço")
        self.assertContains(response, "1. Rascunho")
        self.assertContains(response, "2. Planejado")
        self.assertContains(response, "3. Em execução")
        self.assertContains(response, "4. Finalizado")
        self.assertContains(response, "5. Relatório enviado")
        self.assertContains(response, "Serve para qualquer tipo de prestação")
        self.assertContains(response, "Adicione endereço, cidade ou referência")
        self.assertContains(response, "Registre períodos para comprovar execução")

    def test_service_detail_shows_health_panel_for_complete_service(self):
        job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            category=self.category,
            title="Serviço completo",
            description="Troca e conferência técnica.",
            service_street="Rua Técnica",
            service_number="10",
            service_city="Blumenau",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time="09:00",
            planned_end_time="11:00",
            status=ServiceJob.Status.IN_PROGRESS,
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Material técnico",
            unit=ServiceItemUnit.UNIT,
            quantity=Decimal("1.00"),
            unit_value=Decimal("25.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        ServiceWorkLog.objects.create(
            service_job=job,
            work_date=timezone.localdate(),
            start_time="09:00",
            end_time="10:00",
            description="Execução inicial.",
        )
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_job_detail", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checklist do serviço")
        self.assertContains(response, "Endereço/local informado")
        self.assertContains(response, "Descrição do combinado registrada")
        self.assertContains(response, "Períodos de trabalho registrados")
