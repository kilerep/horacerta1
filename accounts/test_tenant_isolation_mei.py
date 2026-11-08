"""Isolamento entre prestadores (MEIs): o MEI B nunca alcanca objetos do MEI A.

O produto isola por consulta (Company.owner / Employee.user / professional), nao
por banco. Um unico filtro esquecido vira vazamento entre clientes reais, entao
estas rotas por-objeto sao testadas de forma sistematica: qualquer acesso do
MEI B a um ID do MEI A deve ser negado (403/404) e nada pode mudar no banco.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceJob, ServiceRequest
from timeclock.models import Contract, ServiceReport

User = get_user_model()
DENIED = (403, 404)


def make_mei(email):
    user = User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name=f"Cliente de {email}")
    employee = Employee.objects.create(user=user, company=company, full_name=email, is_active=True)
    contract = Contract.objects.create(
        company=company,
        employee=employee,
        hourly_rate=Decimal("50.00"),
        start_date=date(2026, 1, 1),
        is_active=True,
    )
    return user, company, employee, contract


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class MeiTenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_a, cls.company_a, cls.employee_a, cls.contract_a = make_mei("mei-a@example.com")
        cls.user_b, cls.company_b, cls.employee_b, cls.contract_b = make_mei("mei-b@example.com")
        category = ServiceCategory.objects.get(slug="eletrica")
        cls.report_a = ServiceReport.objects.create(
            company=cls.company_a,
            employee=cls.employee_a,
            contract=cls.contract_a,
            report_date=date(2026, 6, 4),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 4),
            title="Relatorio do A",
        )
        cls.report_a.ensure_conference_link()
        cls.report_a.save()
        cls.job_a = ServiceJob.objects.create(
            professional=cls.user_a,
            contract=cls.contract_a,
            category=category,
            title="Servico do A",
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=cls.contract_a.hourly_rate,
        )
        cls.request_a = ServiceRequest.objects.create(
            professional=cls.user_a,
            contract=cls.contract_a,
            client=cls.company_a,
            client_name=cls.company_a.name,
            category=category,
            title="Pedido do A",
            description="Descricao privada do A.",
        )
        cls.catalog_a = ServiceItemCatalog.objects.create(
            professional=cls.user_a,
            category=category,
            item_type=ServiceItemExpense.ItemType.PART,
            name="Item privado do A",
            unit="UNIT",
            estimated_unit_value=Decimal("10.00"),
        )

    def setUp(self):
        self.client.force_login(self.user_b)

    def assert_denied(self, response, what):
        self.assertIn(response.status_code, DENIED, f"{what}: MEI B nao deveria acessar objeto do MEI A")

    def test_mei_b_cannot_read_mei_a_objects(self):
        routes = {
            "editar cliente": reverse("mei_client_edit", args=[self.contract_a.id]),
            "preparar relatorio do cliente": reverse("mei_service_report_prepare", args=[self.contract_a.id]),
            "detalhe do relatorio": reverse("mei_service_report_detail", args=[self.report_a.id]),
            "relatorio pdf": reverse("mei_service_report_pdf", args=[self.report_a.id]),
            "relatorio whatsapp": reverse("mei_service_report_whatsapp", args=[self.report_a.id]),
            "detalhe do servico": reverse("service_job_detail", args=[self.job_a.id]),
            "editar servico": reverse("service_job_update", args=[self.job_a.id]),
            "servico pdf": reverse("service_job_report_pdf", args=[self.job_a.id]),
            "servico ics": reverse("service_job_calendar_ics", args=[self.job_a.id]),
            "detalhe do pedido": reverse("service_request_detail", args=[self.request_a.id]),
            "editar item do catalogo": reverse("service_item_catalog_update", args=[self.catalog_a.id]),
        }
        for name, url in routes.items():
            with self.subTest(route=name):
                self.assert_denied(self.client.get(url), name)

    def test_mei_b_cannot_write_to_mei_a_objects(self):
        writes = {
            "novo item no servico": (reverse("service_item_expense_create", args=[self.job_a.id]), {"name": "x"}),
            "novo horario no servico": (
                reverse("service_work_log_create", args=[self.job_a.id]),
                {"work_date": "2026-06-10", "start_time": "08:00", "end_time": "09:00"},
            ),
            "cronometro do servico": (reverse("service_clock_action", args=[self.job_a.id]), {"action": "start"}),
            "status do servico": (reverse("service_job_status_action", args=[self.job_a.id]), {"action": "finish"}),
            "editar servico": (reverse("service_job_update", args=[self.job_a.id]), {"title": "hackeado"}),
            "status do pedido": (
                reverse("service_request_status_action", args=[self.request_a.id]),
                {"action": "cancel"},
            ),
            "editar cliente": (reverse("mei_client_edit", args=[self.contract_a.id]), {"name": "hackeado"}),
            "desativar item do catalogo": (reverse("service_item_catalog_deactivate", args=[self.catalog_a.id]), {}),
        }
        for name, (url, data) in writes.items():
            with self.subTest(route=name):
                self.assert_denied(self.client.post(url, data), name)

        self.job_a.refresh_from_db()
        self.request_a.refresh_from_db()
        self.company_a.refresh_from_db()
        self.catalog_a.refresh_from_db()
        self.assertEqual(self.job_a.title, "Servico do A")
        self.assertEqual(self.job_a.status, ServiceJob.Status.PLANNED)
        self.assertEqual(self.job_a.work_logs.count(), 0)
        self.assertEqual(self.job_a.item_expenses.count(), 0)
        self.assertEqual(self.request_a.title, "Pedido do A")
        self.assertNotEqual(self.company_a.name, "hackeado")
        self.assertTrue(self.catalog_a.is_active)

    def test_selecting_another_meis_contract_does_not_expose_it(self):
        response = self.client.get(reverse("employee_dashboard"), {"contract": str(self.contract_a.id)}, follow=True)

        self.assertNotContains(response, self.company_a.name)

    def test_mei_b_lists_never_include_mei_a_data(self):
        for name in ("mei_contract", "mei_reports", "service_job_list", "service_request_list", "mei_panel"):
            with self.subTest(screen=name):
                response = self.client.get(reverse(name), follow=True)
                self.assertNotContains(response, "Servico do A")
                self.assertNotContains(response, "Pedido do A")
                self.assertNotContains(response, "Relatorio do A")
                self.assertNotContains(response, "Item privado do A")
                self.assertNotContains(response, self.company_a.name)

    def test_public_links_only_reveal_their_own_token(self):
        anonymous = self.client_class()

        ok = anonymous.get(reverse("public_service_report_conference", args=[self.report_a.conference_token]))
        unknown = anonymous.get(
            reverse("public_service_report_conference", args=["00000000-0000-0000-0000-000000000000"])
        )

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(unknown.status_code, 404)

    def test_anonymous_user_is_redirected_from_private_routes(self):
        anonymous = self.client_class()
        for url in (
            reverse("mei_service_report_detail", args=[self.report_a.id]),
            reverse("service_job_detail", args=[self.job_a.id]),
            reverse("mei_client_edit", args=[self.contract_a.id]),
        ):
            with self.subTest(url=url):
                response = anonymous.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])
