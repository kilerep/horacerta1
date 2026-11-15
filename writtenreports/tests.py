"""Relatorios escritos (2026-11): documento formal que o prestador escreve, de horas ou de servico."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract, Punch
from writtenreports.models import WrittenReport

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_mei(email="escrito@example.com"):
    user = User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name="Ensimec", email=f"cli-{email}")
    employee = Employee.objects.create(user=user, company=company, full_name="Fagner Dos Santos", is_active=True)
    contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                       start_date=date(2026, 1, 1), is_active=True)
    return user, contract


def punch(contract, day, start, end):
    for t in (start, end):
        Punch.objects.create(contract=contract, timestamp=timezone.make_aware(datetime.combine(day, t)))


@override_settings(**BASE)
class WrittenReportTests(TestCase):
    def setUp(self):
        self.user, self.contract = make_mei()
        self.client.force_login(self.user)
        self.day = timezone.localdate() - timedelta(days=2)
        punch(self.contract, self.day, time(8, 0), time(12, 30))

    def _create_hours(self, **extra):
        data = {"kind": "HOURS", "title": "Relatório de atividades", "contract": self.contract.id,
                "date_from": (self.day - timedelta(days=1)).isoformat(), "date_to": timezone.localdate().isoformat(),
                "objective": "Manutenção das máquinas.", "activities": "Troca de rolamentos.",
                "observations": "", "conclusion": "Tudo funcionando."}
        data.update(extra)
        self.client.post(reverse("written_report_create"), data)
        return WrittenReport.objects.filter(owner=self.user).latest("created_at")

    def test_create_hours_draft_and_issue_freezes_data(self):
        report = self._create_hours()
        self.assertEqual(report.status, WrittenReport.Status.DRAFT)

        self.client.post(reverse("written_report_issue", args=[report.id]))
        report.refresh_from_db()

        self.assertEqual((report.status, report.number), (WrittenReport.Status.ISSUED, 1))
        self.assertEqual(report.snapshot["client"], "Ensimec")
        self.assertEqual(report.snapshot["total_hours"], "04:30")
        self.assertEqual(report.snapshot["total_value"], "R$ 225,00")
        # registro novo depois de emitido nao muda o relatorio travado
        punch(self.contract, self.day - timedelta(days=1), time(8, 0), time(9, 0))
        report.refresh_from_db()
        self.assertEqual(report.snapshot["total_hours"], "04:30")

    def test_issued_report_is_locked_but_can_be_deleted(self):
        report = self._create_hours()
        self.client.post(reverse("written_report_issue", args=[report.id]))

        response = self.client.get(reverse("written_report_edit", args=[report.id]))
        self.assertRedirects(response, reverse("written_report_detail", args=[report.id]))
        self.client.post(reverse("written_report_edit", args=[report.id]), {"title": "Mudado", "kind": "HOURS"})
        report.refresh_from_db()
        self.assertEqual(report.title, "Relatório de atividades")

        self.client.post(reverse("written_report_delete", args=[report.id]))
        self.assertFalse(WrittenReport.objects.filter(id=report.id).exists())

    def test_service_report_uses_service_data(self):
        job = ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=ServiceCategory.objects.get(slug="eletrica"),
            title="Troca do quadro elétrico", status=ServiceJob.Status.FINISHED,
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("50.00"),
        )
        self.client.post(reverse("written_report_create"), {
            "kind": "SERVICE", "title": "Relatório do serviço", "service_job": job.id,
            "activities": "Quadro trocado.", "objective": "", "observations": "", "conclusion": "",
        })
        report = WrittenReport.objects.get(owner=self.user)
        self.client.post(reverse("written_report_issue", args=[report.id]))
        report.refresh_from_db()

        self.assertEqual(report.snapshot["service"], "Troca do quadro elétrico")
        self.assertEqual(report.snapshot["client"], job.client_display_name)

    def test_cannot_issue_without_any_text(self):
        report = self._create_hours(objective="", activities="", conclusion="")
        response = self.client.post(reverse("written_report_issue", args=[report.id]), follow=True)
        report.refresh_from_db()

        self.assertEqual(report.status, WrittenReport.Status.DRAFT)
        self.assertContains(response, "Escreva pelo menos uma seção")

    def test_public_link_pdf_and_isolation(self):
        report = self._create_hours()
        self.client.post(reverse("written_report_issue", args=[report.id]))
        report.refresh_from_db()

        self.assertTrue(self.client.get(reverse("written_report_pdf", args=[report.id])).content.startswith(b"%PDF"))
        self.client.logout()
        html = self.client.get(reverse("written_report_public", args=[report.share_token])).content.decode()
        self.assertIn("Troca de rolamentos.", html)
        self.assertIn("Relatório nº 0001", html)
        self.assertNotIn("Observações", html)  # secao vazia nao aparece no documento
        other, _c = make_mei("outro-escrito@example.com")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("written_report_detail", args=[report.id])).status_code, 404)

    def test_reports_page_has_tab_to_written_reports(self):
        html = self.client.get(reverse("mei_reports")).content.decode()

        self.assertIn(reverse("written_report_list"), html)
        self.assertIn("Relatórios escritos", html)
