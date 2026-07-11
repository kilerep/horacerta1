from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ServiceCategory, ServiceItemExpense, ServiceJob
from .service_templates import SERVICE_TEMPLATES


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceTemplateLibraryTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="modelos@example.test",
            email="modelos@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.category, _ = ServiceCategory.objects.get_or_create(
            slug="manutencao",
            defaults={
                "name": "Manutenção",
                "description": "Serviços de manutenção.",
                "is_active": True,
            },
        )
        if not self.category.is_active:
            self.category.is_active = True
            self.category.save(update_fields=["is_active"])
        self.client.force_login(self.professional)

    def test_library_lists_professional_templates_and_is_linked_from_services(self):
        services_response = self.client.get(reverse("service_job_list"))
        library_response = self.client.get(reverse("service_template_library"))

        self.assertEqual(services_response.status_code, 200)
        self.assertContains(services_response, "Modelos profissionais")
        self.assertContains(services_response, reverse("service_template_library"))
        self.assertEqual(library_response.status_code, 200)
        self.assertContains(library_response, f"{len(SERVICE_TEMPLATES)} pontos de partida")
        self.assertContains(library_response, "Visita técnica e diagnóstico")
        self.assertContains(library_response, "Evento e sonorização")
        self.assertContains(library_response, "Aula, treinamento ou consultoria")
        self.assertContains(library_response, "Os valores nunca são preenchidos automaticamente")

    def test_template_prefills_scope_and_category(self):
        response = self.client.get(
            reverse("service_job_create_from_template", args=["manutencao-preventiva"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Novo serviço — Manutenção preventiva")
        self.assertContains(response, "Manutenção preventiva programada")
        self.assertContains(response, "Executar manutenção preventiva")
        self.assertContains(response, "O cliente deve disponibilizar acesso")
        self.assertEqual(str(response.context["form"].initial["category"].id), str(self.category.id))

    def test_template_creates_independent_service_with_zero_price_suggestions(self):
        response = self.client.post(
            reverse("service_job_create_from_template", args=["manutencao-preventiva"]),
            {
                "client_mode": "casual",
                "manual_client_name": "Cliente do modelo",
                "manual_client_whatsapp": "47999990000",
                "manual_client_email": "cliente-modelo@example.test",
                "category": str(self.category.id),
                "title": "Manutenção preventiva mensal",
                "description": "Executar manutenção preventiva e registrar anomalias.",
                "billing_mode": ServiceJob.BillingMode.UNDEFINED,
                "notes": "Revisar o escopo com o cliente.",
                "submit_action": "draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        job = ServiceJob.objects.get(title="Manutenção preventiva mensal")
        self.assertEqual(response.url, reverse("service_job_detail", args=[job.id]))
        self.assertEqual(job.professional, self.professional)
        self.assertEqual(job.manual_client_name, "Cliente do modelo")
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)
        self.assertEqual(job.item_expenses.count(), 2)
        self.assertSetEqual(
            set(job.item_expenses.values_list("name", flat=True)),
            {"Material de limpeza técnica", "Consumíveis de manutenção"},
        )
        for item in job.item_expenses.all():
            self.assertEqual(item.unit_value, Decimal("0.00"))
            self.assertEqual(item.usage_status, ServiceItemExpense.UsageStatus.PLANNED)
            self.assertIn("Revise quantidade, valor e necessidade", item.description)

    def test_invalid_template_returns_404(self):
        response = self.client.get(
            reverse("service_job_create_from_template", args=["modelo-inexistente"])
        )

        self.assertEqual(response.status_code, 404)
