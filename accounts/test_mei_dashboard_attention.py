from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.views.mei import UNVIEWED_REPORT_REMINDER_DAYS
from companies.models import Company, Employee
from timeclock.models import ActivityReportRequest, Contract, Punch, ServiceReport


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiDashboardAttentionTests(TestCase):
    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="resumo-mei@example.com",
            email="resumo-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.owner_a = User.objects.create_user(
            username="cliente-resumo-a@example.com",
            email="cliente-resumo-a@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.owner_b = User.objects.create_user(
            username="cliente-resumo-b@example.com",
            email="cliente-resumo-b@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company_a = Company.objects.create(
            owner=self.owner_a,
            name="Cliente com pendências",
            email="cliente-a@example.com",
        )
        self.company_b = Company.objects.create(
            owner=self.owner_b,
            name="Cliente sem valor/hora",
            email="cliente-b@example.com",
        )
        self.employee_a = Employee.objects.create(
            user=self.mei_user,
            company=self.company_a,
            full_name="Prestador do resumo",
            is_active=True,
        )
        self.employee_b = Employee.objects.create(
            user=self.mei_user,
            company=self.company_b,
            full_name="Prestador do resumo",
            is_active=True,
        )
        self.contract_a = Contract.objects.create(
            employee=self.employee_a,
            company=self.company_a,
            hourly_rate=Decimal("80.00"),
            start_date=timezone.localdate() - timedelta(days=7),
            is_active=True,
        )
        self.contract_b = Contract.objects.create(
            employee=self.employee_b,
            company=self.company_b,
            hourly_rate=Decimal("0.00"),
            start_date=timezone.localdate() - timedelta(days=7),
            is_active=True,
        )

    def test_attention_panel_provides_direct_actions_for_relevant_pending_items(self):
        today = timezone.localdate()
        Punch.objects.create(
            contract=self.contract_a,
            timestamp=timezone.make_aware(datetime.combine(today, time(hour=10))),
        )
        report_request = ActivityReportRequest.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            requested_by=self.owner_a,
            subject="Enviar resumo do período",
            date_from=today - timedelta(days=7),
            date_to=today,
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ação de hoje")
        self.assertContains(response, "Registro incompleto")
        self.assertContains(response, "Ver dia")
        self.assertContains(response, "Valor por hora pendente")
        self.assertContains(response, "Definir valor/hora")
        self.assertContains(response, "Relatório solicitado")
        self.assertContains(response, "Abrir solicitação")
        self.assertContains(response, reverse("mei_client_edit", args=[self.contract_b.id]))
        self.assertContains(response, reverse("mei_service_report_request_detail", args=[report_request.id]))
        self.assertContains(response, f"contract={self.contract_a.id}")
        self.assertContains(response, f"date_from={today.isoformat()}")
        self.assertContains(response, f"date_to={today.isoformat()}")

    def test_attention_panel_shows_pending_payment_after_client_views_report(self):
        today = timezone.localdate()
        viewed_report = ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=today,
            date_from=today - timedelta(days=7),
            date_to=today,
            title="Relatório de horas - semana",
            status=ServiceReport.Status.VIEWED,
            payment_status=ServiceReport.PaymentStatus.PENDING,
            conference_first_viewed_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recebimento pendente")
        self.assertContains(response, "Cliente com pendências")
        self.assertContains(response, reverse("mei_service_report_detail", args=[viewed_report.id]))

    def test_attention_panel_hides_reports_not_yet_viewed_or_already_paid(self):
        today = timezone.localdate()
        ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=today,
            title="Relatório enviado, ainda não visto",
            status=ServiceReport.Status.SENT,
            payment_status=ServiceReport.PaymentStatus.PENDING,
        )
        ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=today,
            title="Relatório já pago",
            status=ServiceReport.Status.PAID,
            payment_status=ServiceReport.PaymentStatus.PAID,
            conference_first_viewed_at=timezone.now() - timedelta(days=2),
            paid_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Recebimento pendente")

    def test_attention_panel_reminds_about_unviewed_report_after_grace_period(self):
        stale_report = ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=timezone.localdate(),
            title="Relatório enviado e esquecido",
            status=ServiceReport.Status.SENT,
            conference_token="11111111-1111-1111-1111-111111111111",
            conference_link_created_at=timezone.now() - timedelta(days=UNVIEWED_REPORT_REMINDER_DAYS + 1),
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relatório não visualizado")
        self.assertContains(response, "Cliente com pendências")
        self.assertContains(response, reverse("mei_service_report_whatsapp", args=[stale_report.id]))

    def test_attention_panel_does_not_nudge_within_grace_period_or_once_viewed(self):
        ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=timezone.localdate(),
            title="Relatório enviado agora há pouco",
            status=ServiceReport.Status.SENT,
            conference_token="22222222-2222-2222-2222-222222222222",
            conference_link_created_at=timezone.now(),
        )
        ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=timezone.localdate(),
            title="Relatório antigo, mas já visualizado",
            status=ServiceReport.Status.VIEWED,
            conference_token="33333333-3333-3333-3333-333333333333",
            conference_link_created_at=timezone.now() - timedelta(days=UNVIEWED_REPORT_REMINDER_DAYS + 5),
            conference_first_viewed_at=timezone.now() - timedelta(days=UNVIEWED_REPORT_REMINDER_DAYS + 4),
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Relatório não visualizado")

    def test_attention_panel_never_shows_pending_payment_reports_from_another_professional(self):
        other_mei_user = User.objects.create_user(
            username="outro-resumo-mei@example.com",
            email="outro-resumo-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        other_owner = User.objects.create_user(
            username="cliente-resumo-c@example.com",
            email="cliente-resumo-c@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        other_company = Company.objects.create(
            owner=other_owner,
            name="Cliente de outro prestador",
            email="cliente-c@example.com",
        )
        other_employee = Employee.objects.create(
            user=other_mei_user,
            company=other_company,
            full_name="Outro prestador",
            is_active=True,
        )
        other_contract = Contract.objects.create(
            employee=other_employee,
            company=other_company,
            hourly_rate=Decimal("80.00"),
            start_date=timezone.localdate() - timedelta(days=7),
            is_active=True,
        )
        ServiceReport.objects.create(
            company=other_company,
            employee=other_employee,
            contract=other_contract,
            report_date=timezone.localdate(),
            title="Relatório de outro prestador",
            status=ServiceReport.Status.VIEWED,
            payment_status=ServiceReport.PaymentStatus.PENDING,
            conference_first_viewed_at=timezone.now() - timedelta(days=1),
        )
        ServiceReport.objects.create(
            company=other_company,
            employee=other_employee,
            contract=other_contract,
            report_date=timezone.localdate(),
            title="Relatório esquecido de outro prestador",
            status=ServiceReport.Status.SENT,
            conference_token="44444444-4444-4444-4444-444444444444",
            conference_link_created_at=timezone.now() - timedelta(days=UNVIEWED_REPORT_REMINDER_DAYS + 1),
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cliente de outro prestador")

    def test_attention_panel_has_a_clear_empty_state_when_there_are_no_priority_items(self):
        self.contract_b.hourly_rate = Decimal("50.00")
        self.contract_b.save(update_fields=["hourly_rate"])
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tudo em ordem")
        self.assertContains(response, "Nenhuma pendência prioritária agora")
        self.assertContains(response, "Registrar horário")
