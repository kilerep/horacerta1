from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract

from .models import ServiceCategory, ServiceJob
from .service_accountability import DOCUMENT_CACHE_CONTROL


User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class AccountabilityPrivacyTests(TestCase):
    def setUp(self):
        self.provider = User.objects.create_user(
            username="prestador-privado@example.test",
            email="prestador-privado@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client_owner = User.objects.create_user(
            username="cliente-privado@example.test",
            email="cliente-privado@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            owner=self.client_owner,
            name="Cliente Prestação de Contas",
            email="financeiro-cliente@example.test",
        )
        self.employee = Employee.objects.create(
            user=self.provider,
            company=self.company,
            full_name="Prestador de Teste",
            phone="",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate=Decimal("120.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(
            name="Atendimento externo",
            slug="atendimento-externo-privacidade",
            is_active=True,
        )
        self.job = ServiceJob.objects.create(
            professional=self.provider,
            contract=self.contract,
            category=self.category,
            title="Atendimento externo reservado",
            description="Atendimento realizado conforme combinado.",
            status=ServiceJob.Status.REPORT_SENT,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("120.00"),
        )

    def assert_private_document_headers(self, response):
        self.assertEqual(response["Cache-Control"], DOCUMENT_CACHE_CONTROL)
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["Expires"], "0")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_public_accountability_is_not_cacheable_or_indexable(self):
        response = self.client.get(
            reverse("public_service_accountability", args=[self.job.public_token])
        )

        self.assertEqual(response.status_code, 200)
        self.assert_private_document_headers(response)
        self.assertContains(response, 'content="noindex,nofollow,noarchive"')
        self.assertContains(response, "Não divulgado")
        self.assertNotContains(response, self.provider.email)

        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.public_report_first_viewed_at)

    def test_public_pdf_uses_the_same_privacy_headers_and_records_view(self):
        self.job.public_report_first_viewed_at = None
        self.job.save(update_fields=["public_report_first_viewed_at", "updated_at"])

        response = self.client.get(
            reverse("public_service_accountability_pdf", args=[self.job.public_token])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assert_private_document_headers(response)
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.public_report_first_viewed_at)

    def test_public_accountability_is_blocked_before_final_report(self):
        self.job.status = ServiceJob.Status.FINISHED
        self.job.save(update_fields=["status", "finished_at", "updated_at"])

        response = self.client.get(
            reverse("public_service_accountability", args=[self.job.public_token])
        )

        self.assertEqual(response.status_code, 404)

    def test_other_provider_cannot_open_internal_accountability(self):
        other_provider = User.objects.create_user(
            username="outro-prestador@example.test",
            email="outro-prestador@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other_provider)

        response = self.client.get(reverse("service_accountability", args=[self.job.id]))

        self.assertEqual(response.status_code, 404)

    def test_internal_share_action_contains_context_not_only_the_url(self):
        self.client.force_login(self.provider)

        response = self.client.get(reverse("service_accountability", args=[self.job.id]))

        self.assertEqual(response.status_code, 200)
        self.assert_private_document_headers(response)
        self.assertContains(response, "Enviar pelo WhatsApp")
        self.assertContains(response, "presta%C3%A7%C3%A3o%20de%20contas")
        self.assertContains(response, "Atendimento%20externo%20reservado")
