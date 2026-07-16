from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceJob


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceGuidedLayoutTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="layout-servicos@example.test",
            email="layout-servicos@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="layout-cliente@example.test",
            email="layout-cliente@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(owner=owner, name="Cliente Layout")
        employee = Employee.objects.create(
            user=self.professional,
            company=self.company,
            full_name="Prestador Layout",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=self.company,
            hourly_rate=Decimal("100.00"),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(
            name="Consultoria",
            slug="consultoria-layout",
            is_active=True,
        )
        self.client.force_login(self.professional)

    def test_guided_layout_assets_exist(self):
        self.assertIsNotNone(finders.find("css/services_guided_flow.css"))
        self.assertIsNotNone(finders.find("css/services_theme_polish.css"))

    def test_services_and_guide_load_theme_aware_guided_layout(self):
        services_response = self.client.get(reverse("service_job_list"))
        guide_response = self.client.get(reverse("service_start_guide"))

        self.assertEqual(services_response.status_code, 200)
        self.assertEqual(guide_response.status_code, 200)
        self.assertContains(services_response, "css/services_guided_flow.css")
        self.assertContains(guide_response, "css/services_guided_flow.css")
        self.assertContains(services_response, "css/services_theme_polish.css")
        self.assertContains(guide_response, "css/services_theme_polish.css")
        self.assertContains(services_response, "Entenda as etapas e os documentos")
        self.assertContains(guide_response, "Qual é a sua situação agora?")

    def test_guide_explains_deliverables_and_offers_category_shortcuts(self):
        response = self.client.get(reverse("service_start_guide"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O que você terá ao final")
        self.assertContains(response, "Pedido organizado")
        self.assertContains(response, "Entrega profissional")
        self.assertContains(response, "Encontre pelo tipo de trabalho")
        self.assertContains(response, reverse("service_job_create_from_template", args=["visita-tecnica-diagnostico"]))
        self.assertContains(response, reverse("service_job_create_from_template", args=["instalacao-tecnica"]))
        self.assertContains(response, reverse("service_job_create_from_template", args=["limpeza-recorrente"]))
        self.assertContains(response, reverse("service_job_create_from_template", args=["servico-automotivo"]))
        self.assertContains(response, "O modelo é um ponto de partida")

    def test_accountability_document_loads_professional_layout_and_share_action(self):
        job = ServiceJob.objects.create(
            professional=self.professional,
            contract=self.contract,
            client=self.company,
            category=self.category,
            title="Serviço para prestação de contas",
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("100.00"),
            status=ServiceJob.Status.REPORT_SENT,
        )

        response = self.client.get(reverse("service_accountability", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/services_guided_flow.css")
        self.assertContains(response, "accountability-page")
        self.assertContains(response, "Prestação de contas do serviço")
        self.assertContains(response, "Enviar pelo WhatsApp")
        self.assertContains(response, "https://wa.me/")
