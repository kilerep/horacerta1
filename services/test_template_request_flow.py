from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceJob, ServiceRequest


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class TemplateRequestFlowTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-modelo-pedido@example.test",
            email="prestador-modelo-pedido@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="cliente-modelo-pedido@example.test",
            email="cliente-modelo-pedido@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(owner=owner, name="Cliente Limpeza")
        employee = Employee.objects.create(
            user=self.professional,
            company=self.company,
            full_name="Prestador de Limpeza",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=self.company,
            hourly_rate=Decimal("80.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(
            name="Limpeza e conservação",
            slug="limpeza-conservacao",
            is_active=True,
        )
        self.client.force_login(self.professional)

    def _payload(self, submit_action):
        return {
            "client_mode": "registered",
            "contract": str(self.contract.id),
            "category": str(self.category.id),
            "title": "Limpeza mensal do escritório",
            "description": "Necessidade informada pelo cliente: limpeza mensal.\n\nPontos de conferência:\n- áreas e prioridades",
            "preferred_date": timezone.localdate().isoformat(),
            "preferred_time": "08:00",
            "address_street": "Rua do Escritório",
            "address_number": "100",
            "address_city": "Blumenau",
            "address_state": "SC",
            "urgency": ServiceRequest.Urgency.NORMAL,
            "source": ServiceRequest.Source.WHATSAPP,
            "submit_action": submit_action,
        }

    def test_library_separates_negotiation_from_confirmed_service(self):
        response = self.client.get(reverse("service_template_library"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ainda estou negociando")
        self.assertContains(response, "Serviço já combinado")
        self.assertContains(
            response,
            reverse("service_request_create_from_template", args=["limpeza-recorrente"]),
        )
        self.assertContains(
            response,
            reverse("service_job_create_from_template", args=["limpeza-recorrente"]),
        )

    def test_template_request_form_prepares_scope_and_category(self):
        response = self.client.get(
            reverse("service_request_create_from_template", args=["limpeza-recorrente"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pedido — Limpeza recorrente")
        self.assertContains(response, "Escopo sugerido para confirmar")
        self.assertContains(response, "Conferir áreas e prioridades")
        self.assertContains(response, str(self.category.id))
        self.assertContains(response, "Quantidades e valores continuam sob sua revisão")

    def test_template_request_saved_for_later_keeps_zero_price_suggestions(self):
        response = self.client.post(
            reverse("service_request_create_from_template", args=["limpeza-recorrente"]),
            self._payload("save"),
        )

        self.assertEqual(response.status_code, 302)
        service_request = ServiceRequest.objects.get(title="Limpeza mensal do escritório")
        self.assertIsNone(service_request.converted_service_id)
        self.assertSetEqual(
            set(service_request.quick_items.values_list("name", flat=True)),
            {"Produtos de limpeza", "Sacos para resíduos"},
        )
        for item in service_request.quick_items.all():
            self.assertIsNone(item.estimated_unit_value)

    def test_template_request_can_open_service_with_items_and_billing_mode(self):
        response = self.client.post(
            reverse("service_request_create_from_template", args=["limpeza-recorrente"]),
            self._payload("convert"),
        )

        self.assertEqual(response.status_code, 302)
        service_request = ServiceRequest.objects.get(title="Limpeza mensal do escritório")
        job = service_request.converted_service
        self.assertEqual(response.url, reverse("service_job_detail", args=[job.id]))
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.FIXED)
        self.assertIn("materiais delicados", job.notes)
        self.assertEqual(job.service_street, "Rua do Escritório")
        self.assertSetEqual(
            set(job.item_expenses.values_list("name", flat=True)),
            {"Produtos de limpeza", "Sacos para resíduos"},
        )
        for item in job.item_expenses.all():
            self.assertEqual(item.unit_value, Decimal("0.00"))
