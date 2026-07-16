from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ServiceCategory, ServiceItemExpense, ServiceJob


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceGuidesTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-guiado@example.test",
            email="prestador-guiado@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.category = ServiceCategory.objects.create(
            name="Administrativo e escritório",
            slug="administrativo-escritorio",
            is_active=True,
        )

    def test_start_page_explains_main_service_scenarios(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_start"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recebi um pedido pelo WhatsApp")
        self.assertContains(response, "Vou realizar um evento")
        self.assertContains(response, "Vou fazer uma viagem a trabalho")
        self.assertContains(response, "Pedido")
        self.assertContains(response, "Combinado")
        self.assertContains(response, "Preparação")
        self.assertContains(response, "Execução")
        self.assertContains(response, "Entrega")
        self.assertContains(response, reverse("service_trip_create"))

    def test_services_page_promotes_guided_start_event_and_trip(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_job_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Começar com orientação")
        self.assertContains(response, "Evento e sonorização")
        self.assertContains(response, "Viagem a trabalho")
        self.assertContains(response, reverse("service_start"))

    def test_trip_form_starts_with_professional_text(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_trip_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nova viagem a trabalho")
        self.assertContains(response, "Viagem a trabalho e atendimento externo")
        self.assertContains(response, "prestação de contas clara")
        self.assertContains(response, "reembolsadas")

    def test_creating_trip_adds_expense_suggestions_without_price(self):
        self.client.force_login(self.professional)

        response = self.client.post(
            reverse("service_trip_create"),
            {
                "client_mode": "casual",
                "manual_client_name": "Empresa Viagem",
                "manual_client_whatsapp": "47999990000",
                "manual_client_email": "viagem@example.test",
                "service_zip_code": "89000000",
                "service_street": "Rua da Viagem",
                "service_number": "100",
                "service_complement": "",
                "service_district": "Centro",
                "service_city": "Blumenau",
                "service_state": "SC",
                "service_reference": "Recepção",
                "category": str(self.category.id),
                "title": "Viagem técnica para filial",
                "description": "Atendimento técnico e acompanhamento da equipe local.",
                "start_date": timezone.localdate().isoformat(),
                "planned_start_time": "08:00",
                "planned_end_time": "18:00",
                "billing_mode": ServiceJob.BillingMode.HOURLY,
                "hourly_rate_snapshot": "150.00",
                "fixed_labor_value": "",
                "notes": "Enviar comprovantes para conferência.",
                "submit_action": "create",
            },
        )

        self.assertEqual(response.status_code, 302)
        job = ServiceJob.objects.get(professional=self.professional, title="Viagem técnica para filial")
        self.assertEqual(job.hourly_rate_snapshot, Decimal("150.00"))
        self.assertEqual(job.item_expenses.count(), 6)
        self.assertTrue(job.item_expenses.filter(name="Combustível", type=ServiceItemExpense.ItemType.FUEL).exists())
        self.assertTrue(job.item_expenses.filter(name="Pedágio", type=ServiceItemExpense.ItemType.TOLL).exists())
        self.assertTrue(job.item_expenses.filter(name="Hospedagem", type=ServiceItemExpense.ItemType.EXPENSE).exists())
        self.assertFalse(job.item_expenses.exclude(unit_value=Decimal("0.00")).exists())
        self.assertFalse(job.item_expenses.exclude(usage_status=ServiceItemExpense.UsageStatus.PLANNED).exists())

    def test_company_account_cannot_use_provider_guided_start(self):
        company_user = User.objects.create_user(
            username="empresa-guia@example.test",
            email="empresa-guia@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.client.force_login(company_user)

        response = self.client.get(reverse("service_start"))

        self.assertEqual(response.status_code, 302)
