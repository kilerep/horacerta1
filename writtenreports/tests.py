"""Relatorios escritos: documento formal de servico que o prestador escreve (2026-11-15).

So relatorio de servico, com cliente e servico digitados livremente; o de horas fica no Fechamento de horas.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from writtenreports.models import WrittenReport

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_user(email="escrito@example.com"):
    return User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)


@override_settings(**BASE)
class WrittenServiceReportTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def _create(self, **extra):
        today = timezone.localdate()
        data = {"title": "Relatório de manutenção", "client_name": "Ensimec", "service_name": "Troca de rolamentos da prensa 3",
                "date_from": (today - timedelta(days=2)).isoformat(), "date_to": today.isoformat(),
                "objective": "Manutenção da linha 2.", "activities": "Troca de rolamentos.",
                "observations": "", "conclusion": "Tudo funcionando."}
        data.update(extra)
        self.client.post(reverse("written_report_create"), data)
        return WrittenReport.objects.filter(owner=self.user).latest("created_at")

    def test_form_has_free_text_client_and_service_and_no_hours_option(self):
        html = self.client.get(reverse("written_report_create")).content.decode()

        self.assertIn('name="client_name"', html)
        self.assertIn('name="service_name"', html)
        self.assertNotIn('name="contract"', html)
        self.assertNotIn('name="service_job"', html)
        self.assertNotIn("Relatório de horas", html)

    def test_create_and_issue_keeps_what_was_typed(self):
        report = self._create()
        self.assertEqual((report.status, report.kind), (WrittenReport.Status.DRAFT, WrittenReport.Kind.SERVICE))

        self.client.post(reverse("written_report_issue", args=[report.id]))
        report.refresh_from_db()

        self.assertEqual((report.status, report.number), (WrittenReport.Status.ISSUED, 1))
        self.assertEqual(report.snapshot["client"], "Ensimec")
        self.assertEqual(report.snapshot["service"], "Troca de rolamentos da prensa 3")
        self.assertIn(" a ", report.snapshot["period"])

    def test_client_and_service_are_required(self):
        response = self.client.post(reverse("written_report_create"), {
            "title": "Sem dados", "client_name": "", "service_name": "", "activities": "x"})

        self.assertContains(response, "Informe o cliente")
        self.assertContains(response, "Informe o serviço")
        self.assertFalse(WrittenReport.objects.exists())

    def test_issued_report_is_locked_but_can_be_deleted(self):
        report = self._create()
        self.client.post(reverse("written_report_issue", args=[report.id]))

        response = self.client.get(reverse("written_report_edit", args=[report.id]))
        self.assertRedirects(response, reverse("written_report_detail", args=[report.id]))
        self.client.post(reverse("written_report_edit", args=[report.id]), {"title": "Mudado"})
        report.refresh_from_db()
        self.assertEqual(report.title, "Relatório de manutenção")

        self.client.post(reverse("written_report_delete", args=[report.id]))
        self.assertFalse(WrittenReport.objects.filter(id=report.id).exists())

    def test_cannot_issue_without_any_text(self):
        report = self._create(objective="", activities="", conclusion="")
        response = self.client.post(reverse("written_report_issue", args=[report.id]), follow=True)
        report.refresh_from_db()

        self.assertEqual(report.status, WrittenReport.Status.DRAFT)
        self.assertContains(response, "Escreva pelo menos uma seção")

    def test_public_link_pdf_and_isolation(self):
        report = self._create()
        self.client.post(reverse("written_report_issue", args=[report.id]))
        report.refresh_from_db()

        self.assertTrue(self.client.get(reverse("written_report_pdf", args=[report.id])).content.startswith(b"%PDF"))
        self.client.logout()
        html = self.client.get(reverse("written_report_public", args=[report.share_token])).content.decode()
        self.assertIn("Troca de rolamentos.", html)
        self.assertIn("Troca de rolamentos da prensa 3", html)
        self.assertIn("Relatório nº 0001", html)
        self.assertNotIn("Observações", html)  # secao vazia nao aparece no documento
        self.client.force_login(make_user("outro-escrito@example.com"))
        self.assertEqual(self.client.get(reverse("written_report_detail", args=[report.id])).status_code, 404)

    def test_old_hours_report_still_opens(self):
        old = WrittenReport.objects.create(
            owner=self.user, kind=WrittenReport.Kind.HOURS, title="Antigo", status=WrittenReport.Status.ISSUED,
            number=9, activities="Texto", date_from=date(2026, 11, 1), date_to=date(2026, 11, 10),
            snapshot={"client": "Ensimec", "period": "01/11/2026 a 10/11/2026", "rows": [], "total_hours": "00:00",
                      "sender": "Fagner", "issued": "15/11/2026 às 10:00"},
        )

        self.assertEqual(self.client.get(reverse("written_report_detail", args=[old.id])).status_code, 200)
        self.assertTrue(self.client.get(reverse("written_report_pdf", args=[old.id])).content.startswith(b"%PDF"))

    def test_reports_page_has_tab_to_written_reports(self):
        from companies.models import Company, Employee
        from timeclock.models import Contract

        company = Company.objects.create(owner=self.user, name="Ensimec", email="cli-escrito@example.com")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Fagner", is_active=True)
        Contract.objects.create(company=company, employee=employee, start_date=date(2026, 1, 1), is_active=True)
        html = self.client.get(reverse("mei_reports")).content.decode()

        self.assertIn(reverse("written_report_list"), html)
        self.assertIn("Relatórios de serviço", html)
