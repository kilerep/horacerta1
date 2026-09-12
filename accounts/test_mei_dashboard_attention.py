from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import ActivityReportRequest, Contract, Punch


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

    def test_attention_panel_has_a_clear_empty_state_when_there_are_no_priority_items(self):
        self.contract_b.hourly_rate = Decimal("50.00")
        self.contract_b.save(update_fields=["hourly_rate"])
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tudo em ordem")
        self.assertContains(response, "Nenhuma pendência prioritária agora")
        self.assertContains(response, "Registrar horário")
