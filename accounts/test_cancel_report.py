"""O prestador cancela um relatorio (ex.: cliente contestou) para corrigir os dias.

Cancelar libera o bloqueio dos dias, desativa o link publico e mantem o
relatorio no historico. Relatorio pago nao cancela; cancelado nao reabre link."""

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract, ServiceReport
from timeclock.services import report_locks_day

Status = ServiceReport.Status


def make_mei(email):
    user = User.objects.create_user(username=email, email=email, password="x-Senha-123456", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name=f"Cliente {email}")
    employee = Employee.objects.create(user=user, company=company, full_name=email, is_active=True)
    contract = Contract.objects.create(
        company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
    )
    return user, company, employee, contract


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class CancelReportTests(TestCase):
    def setUp(self):
        self.user, self.company, self.employee, self.contract = make_mei("cancela@example.com")
        self.report = ServiceReport.objects.create(
            company=self.company, employee=self.employee, contract=self.contract, report_date=date(2026, 6, 4),
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 4), title="Relatorio",
        )
        self.report.ensure_conference_link()
        self.report.save()
        self.url = reverse("mei_service_report_detail", args=[self.report.id])
        self.client.force_login(self.user)

    def _reload(self):
        self.report.refresh_from_db()
        return self.report

    def test_cancel_frees_the_days_revokes_the_link_and_keeps_the_report(self):
        self.assertTrue(report_locks_day(date(2026, 6, 2), contract=self.contract))
        token = self.report.conference_token

        response = self.client.post(
            self.url, {"action": "cancel_report", "cancel_reason": "cliente contestou o dia 3", "confirm_cancel": "on"}
        )

        self.assertEqual(response.status_code, 302)
        report = self._reload()
        self.assertEqual(report.status, Status.CANCELED)
        self.assertIsNotNone(report.canceled_at)
        self.assertEqual(report.cancel_reason, "cliente contestou o dia 3")
        self.assertIsNotNone(report.conference_revoked_at)
        self.assertFalse(report_locks_day(date(2026, 6, 2), contract=self.contract))
        self.assertEqual(self.client_class().get(reverse("public_service_report_conference", args=[token])).status_code, 410)

    def test_cancel_needs_the_confirmation_checkbox(self):
        self.client.post(self.url, {"action": "cancel_report"})

        self.assertNotEqual(self._reload().status, Status.CANCELED)
        self.assertTrue(report_locks_day(date(2026, 6, 2), contract=self.contract))

    def test_paid_report_cannot_be_canceled(self):
        self.report.payment_status = ServiceReport.PaymentStatus.PAID
        self.report.save()

        self.client.post(self.url, {"action": "cancel_report", "confirm_cancel": "on"})

        self.assertNotEqual(self._reload().status, Status.CANCELED)
        self.assertNotContains(self.client.get(self.url), "cancel-report-panel")

    def test_canceled_report_cannot_get_a_new_link_or_be_marked_received(self):
        self.client.post(self.url, {"action": "cancel_report", "confirm_cancel": "on"})

        self.client.post(self.url, {"action": "generate_conference_link"})
        self.client.post(
            reverse("mei_contract"),
            {"action": "set_payment_status", "report_id": str(self.report.id), "payment_status": "paid"},
        )

        report = self._reload()
        self.assertIsNotNone(report.conference_revoked_at)
        self.assertNotEqual(report.payment_status, ServiceReport.PaymentStatus.PAID)

    def test_client_cannot_respond_to_a_canceled_report(self):
        token = self.report.conference_token
        self.client.post(self.url, {"action": "cancel_report", "confirm_cancel": "on"})

        response = self.client_class().post(
            reverse("public_service_report_respond", args=[token]), {"action": "confirm"}
        )

        self.assertEqual(response.status_code, 410)

    def test_detail_page_shows_the_cancel_panel_then_the_canceled_notice(self):
        self.assertContains(self.client.get(self.url), "Cancelar relatório para corrigir")

        self.client.post(self.url, {"action": "cancel_report", "cancel_reason": "corrigir", "confirm_cancel": "on"})
        page = self.client.get(self.url)

        self.assertContains(page, "Relatório cancelado")
        self.assertContains(page, "Motivo: corrigir")
        self.assertNotContains(page, "Cancelar relatório para corrigir")
        self.assertNotContains(page, "Gerar link de conferencia")

    def test_canceled_report_does_not_count_as_first_report_in_onboarding(self):
        self.client.post(self.url, {"action": "cancel_report", "confirm_cancel": "on"})

        response = self.client.get(reverse("mei_panel"))

        steps = response.context["onboarding_steps"]
        self.assertFalse(steps[3]["done"])

    def test_another_mei_cannot_cancel_it(self):
        other, *_ = make_mei("outro@example.com")
        self.client.force_login(other)

        response = self.client.post(self.url, {"action": "cancel_report", "confirm_cancel": "on"})

        self.assertIn(response.status_code, (403, 404))
        self.assertNotEqual(self._reload().status, Status.CANCELED)
