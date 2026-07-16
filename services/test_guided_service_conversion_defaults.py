from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceRequest


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class GuidedServiceConversionDefaultsTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="prestador-conversao@example.test",
            email="prestador-conversao@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="empresa-conversao@example.test",
            email="empresa-conversao@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(owner=owner, name="Empresa Conversão")
        employee = Employee.objects.create(
            user=self.professional,
            company=self.company,
            full_name="Prestador Conversão",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=self.company,
            hourly_rate=Decimal("100.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.event_category = ServiceCategory.objects.create(
            name="Eventos e sonorização",
            slug="eventos-sonorizacao",
            is_active=True,
        )
        self.travel_category = ServiceCategory.objects.create(
            name="Administrativo e escritório",
            slug="administrativo-escritorio",
            is_active=True,
        )
        self.client.force_login(self.professional)

    def _base_payload(self, category, title, description):
        return {
            "client_mode": "registered",
            "contract": str(self.contract.id),
            "category": str(category.id),
            "title": title,
            "description": description,
            "urgency": ServiceRequest.Urgency.NORMAL,
            "source": ServiceRequest.Source.WHATSAPP,
        }

    def test_event_request_conversion_adds_zero_value_equipment_suggestions(self):
        payload = self._base_payload(
            self.event_category,
            "Evento corporativo",
            "Tipo de evento: palestra\nEquipamentos ou serviços solicitados: sonorização",
        )
        payload["submit_action"] = "convert"

        response = self.client.post(
            reverse("service_request_create_from_scenario", args=["evento"]),
            payload,
        )

        self.assertEqual(response.status_code, 302)
        job = ServiceRequest.objects.get(title="Evento corporativo").converted_service
        self.assertSetEqual(
            set(job.item_expenses.values_list("name", flat=True)),
            {"Caixa de som ativa", "Microfone", "Kit de cabos"},
        )
        for item in job.item_expenses.all():
            self.assertEqual(item.unit_value, Decimal("0.00"))
            self.assertEqual(item.usage_status, ServiceItemExpense.UsageStatus.PLANNED)
        self.assertIn("energia adequada", job.notes)

    def test_saved_travel_request_keeps_presets_when_converted_later(self):
        payload = self._base_payload(
            self.travel_category,
            "Viagem para atendimento na filial",
            "Objetivo da viagem: suporte local\nDestino: filial\nPolítica de reembolso: conforme empresa",
        )
        payload.update(
            {
                "preferred_date": timezone.localdate().isoformat(),
                "preferred_time": "08:00",
                "address_street": "Rua da Filial",
                "address_number": "10",
                "address_city": "Blumenau",
                "address_state": "SC",
                "submit_action": "save",
            }
        )

        create_response = self.client.post(
            reverse("service_request_create_from_scenario", args=["viagem"]),
            payload,
        )
        self.assertEqual(create_response.status_code, 302)
        service_request = ServiceRequest.objects.get(title="Viagem para atendimento na filial")
        self.assertIsNone(service_request.converted_service_id)

        convert_response = self.client.post(reverse("service_request_convert", args=[service_request.id]))

        self.assertEqual(convert_response.status_code, 302)
        service_request.refresh_from_db()
        job = service_request.converted_service
        self.assertEqual(job.service_street, "Rua da Filial")
        self.assertEqual(job.service_number, "10")
        self.assertEqual(job.service_city, "Blumenau")
        self.assertEqual(job.item_expenses.count(), 5)
        self.assertSetEqual(
            set(job.item_expenses.values_list("name", flat=True)),
            {"Pedágio", "Combustível", "Estacionamento", "Alimentação em viagem", "Hospedagem ou passagem"},
        )
