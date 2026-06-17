from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract, Punch, ServiceReport

from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceJob, ServiceRequest, ServiceWorkLog


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class ServiceJobAreaTests(TestCase):
    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="mei.services@example.com",
            email="mei.services@example.com",
            password="Senha@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.other_user = User.objects.create_user(
            username="other.services@example.com",
            email="other.services@example.com",
            password="Senha@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.company_owner = User.objects.create_user(
            username="company.services@example.com",
            email="company.services@example.com",
            password="Senha@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Cliente Servicos A",
            owner=self.company_owner,
            email="cliente-a@example.com",
        )
        self.employee = Employee.objects.create(
            user=self.mei_user,
            company=self.company,
            full_name="MEI Servicos",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate="95.00",
            start_date=timezone.localdate() - timedelta(days=5),
            is_active=True,
        )
        self.other_company = Company.objects.create(
            name="Cliente Servicos B",
            owner=self.company_owner,
            email="cliente-b@example.com",
        )
        self.other_employee = Employee.objects.create(
            user=self.other_user,
            company=self.other_company,
            full_name="Outro MEI",
            is_active=True,
        )
        self.other_contract = Contract.objects.create(
            employee=self.other_employee,
            company=self.other_company,
            hourly_rate="130.00",
            start_date=timezone.localdate() - timedelta(days=3),
            is_active=True,
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.mei_user)

    def test_default_categories_are_seeded_once(self):
        expected_slugs = {
            "servico-geral",
            "eletrica",
            "hidraulica",
            "manutencao",
            "ar-condicionado",
            "montagem-instalacao",
            "informatica-ti",
            "pintura-e-reparos",
            "entrega-viagem",
            "visita-tecnica",
            "outros",
        }
        self.assertEqual(set(ServiceCategory.objects.values_list("slug", flat=True)), expected_slugs)

    def test_personal_catalog_crud_favorite_deactivate_and_user_isolation(self):
        item = ServiceItemCatalog.objects.create(
            professional=self.mei_user,
            category=self.category,
            item_type=ServiceItemExpense.ItemType.PART,
            name="Disjuntor 20A",
            unit="UNIT",
            estimated_unit_value=Decimal("35.00"),
            default_quantity=Decimal("2.00"),
        )
        other_item = ServiceItemCatalog.objects.create(
            professional=self.other_user,
            category=self.category,
            item_type=ServiceItemExpense.ItemType.PART,
            name="Disjuntor 32A",
            unit="UNIT",
            estimated_unit_value=Decimal("55.00"),
        )

        list_response = self.client.get(reverse("service_item_catalog_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Disjuntor 20A")
        self.assertNotContains(list_response, "Disjuntor 32A")
        self.assertEqual(self.client.get(reverse("service_item_catalog_update", args=[other_item.id])).status_code, 404)

        update_response = self.client.post(
            reverse("service_item_catalog_update", args=[item.id]),
            {
                "category": self.category.id,
                "item_type": ServiceItemExpense.ItemType.PART,
                "name": "Disjuntor 20A bipolar",
                "description": "Estimativa pessoal",
                "unit": "UNIT",
                "estimated_unit_value": "42.00",
                "default_quantity": "1.00",
                "favorite": "on",
                "is_active": "on",
            },
            follow=True,
        )
        item.refresh_from_db()
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(item.name, "Disjuntor 20A bipolar")
        self.assertEqual(item.estimated_unit_value, Decimal("42.00"))
        self.assertTrue(item.favorite)

        favorite_response = self.client.post(reverse("service_item_catalog_toggle_favorite", args=[item.id]), follow=True)
        item.refresh_from_db()
        self.assertEqual(favorite_response.status_code, 200)
        self.assertFalse(item.favorite)

        deactivate_response = self.client.post(reverse("service_item_catalog_deactivate", args=[item.id]), follow=True)
        item.refresh_from_db()
        self.assertEqual(deactivate_response.status_code, 200)
        self.assertFalse(item.is_active)

    def test_catalog_search_service_item_creation_preview_and_last_used_value(self):
        before_punch_count = Punch.objects.count()
        catalog_item = ServiceItemCatalog.objects.create(
            professional=self.mei_user,
            category=self.category,
            item_type=ServiceItemExpense.ItemType.PART,
            name="Disjuntor 20A",
            description="Curva C",
            unit="UNIT",
            estimated_unit_value=Decimal("35.00"),
            default_quantity=Decimal("2.00"),
        )

        search_response = self.client.get(reverse("service_item_catalog_search"), {"q": "disj"})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["items"][0]["name"], "Disjuntor 20A")

        create_response = self.client.post(
            reverse("service_job_create"),
            {
                "client_mode": "casual",
                "manual_client_name": "John",
                "manual_client_whatsapp": "11999999999",
                "manual_client_email": "",
                "service_zip_code": "89000000",
                "service_street": "Rua X",
                "service_number": "120",
                "service_complement": "",
                "service_district": "Centro",
                "service_city": "Blumenau",
                "service_state": "SC",
                "service_reference": "",
                "category": self.category.id,
                "title": "Troca de disjuntores",
                "description": "Trocar disjuntores.",
                "start_date": timezone.localdate().isoformat(),
                "planned_start_time": "08:00",
                "planned_end_time": "",
                "billing_mode": ServiceJob.BillingMode.UNDEFINED,
                "hourly_rate_snapshot": "",
                "fixed_labor_value": "",
                "notes": "",
                "planned_item_catalog_id": str(catalog_item.id),
                "planned_item_name": "Disjuntor 20A",
                "planned_item_type": ServiceItemExpense.ItemType.PART,
                "planned_item_unit": "UNIT",
                "planned_item_quantity": "3.00",
                "planned_item_unit_value": "42.00",
                "planned_item_description": "Valor ajustado antes da previa",
                "planned_item_update_catalog_price": "0",
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        job = ServiceJob.objects.get(title="Troca de disjuntores")
        service_item = job.item_expenses.get(name="Disjuntor 20A")
        catalog_item.refresh_from_db()
        self.assertEqual(service_item.catalog_item, catalog_item)
        self.assertEqual(service_item.unit_value, Decimal("42.00"))
        self.assertEqual(catalog_item.estimated_unit_value, Decimal("42.00"))
        self.assertEqual(catalog_item.last_used_value, Decimal("42.00"))
        self.assertIsNotNone(catalog_item.last_used_at)

        self.client.post(reverse("service_job_preview_generate", args=[job.id]), follow=True)
        self.client.logout()
        preview_response = self.client.get(reverse("public_service_job_preview", args=[job.public_token]))
        self.assertContains(preview_response, "Disjuntor 20A")
        self.assertContains(preview_response, "R$ 126,00")
        self.client.force_login(self.mei_user)

        self.client.post(
            reverse("service_item_expense_update", args=[job.id, service_item.id]),
            {
                "catalog_item": catalog_item.id,
                "type": ServiceItemExpense.ItemType.PART,
                "name": "Disjuntor 20A",
                "description": "Valor real editado",
                "unit": "UNIT",
                "quantity": "3.00",
                "unit_value": "45.00",
                "usage_status": ServiceItemExpense.UsageStatus.USED,
                "receipt_note": "",
                "update_catalog_price": "on",
            },
            follow=True,
        )
        service_item.refresh_from_db()
        catalog_item.refresh_from_db()
        self.assertEqual(service_item.total_value, Decimal("135.00"))
        self.assertEqual(job.item_expenses.get(id=service_item.id).usage_status, ServiceItemExpense.UsageStatus.USED)
        self.assertEqual(catalog_item.last_used_value, Decimal("45.00"))
        self.assertEqual(catalog_item.estimated_unit_value, Decimal("45.00"))
        job.refresh_from_db()
        self.assertEqual(job.used_items_total, Decimal("135.00"))
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_save_new_service_item_to_catalog_from_service_detail(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            manual_client_name="John",
            category=self.category,
            title="Visita eletrica",
            description="Servico avulso.",
            service_location="Rua A, 10",
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.UNDEFINED,
        )

        response = self.client.post(
            reverse("service_item_expense_create", args=[job.id]),
            {
                "type": ServiceItemExpense.ItemType.MATERIAL,
                "name": "Fita isolante premium",
                "description": "Preta",
                "unit": "ROLL",
                "quantity": "1.00",
                "unit_value": "12.00",
                "usage_status": ServiceItemExpense.UsageStatus.PLANNED,
                "receipt_note": "",
                "save_to_catalog": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        catalog_item = ServiceItemCatalog.objects.get(professional=self.mei_user, name="Fita isolante premium")
        service_item = job.item_expenses.get(name="Fita isolante premium")
        self.assertEqual(service_item.catalog_item, catalog_item)
        self.assertEqual(catalog_item.estimated_unit_value, Decimal("12.00"))
        self.assertEqual(catalog_item.last_used_value, Decimal("12.00"))

    def test_services_tab_opens_with_empty_state(self):
        response = self.client.get(reverse("service_job_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Serviços")
        self.assertContains(response, "Ações rápidas")
        self.assertContains(response, "Resumo da área")
        self.assertContains(response, "Filtrar serviços")
        self.assertContains(response, "Pedidos de serviço")
        self.assertContains(response, "Nenhum serviço encontrado.")
        self.assertContains(response, "Catálogo de itens")
        self.assertContains(response, "sem alterar seu histórico normal")

    def test_new_service_page_has_legible_client_select_and_guidance(self):
        response = self.client.get(reverse("service_job_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente do serviço")
        self.assertContains(response, "Local do serviço")
        self.assertContains(response, "Previsão de atendimento")
        self.assertContains(response, "Buscar pelo CEP")
        self.assertContains(response, "Cliente Servicos A - R$ 95.00/h")
        self.assertContains(response, "Trocas, instalações, manutenção elétrica")
        self.assertNotContains(response, "Contract&lt;")

    def test_create_registered_client_service_with_manual_address_and_hourly_billing(self):
        before_punch_count = Punch.objects.count()

        response = self.client.post(
            reverse("service_job_create"),
            {
                "client_mode": "registered",
                "contract": str(self.contract.id),
                "manual_client_name": "",
                "manual_client_whatsapp": "",
                "manual_client_email": "",
                "service_zip_code": "01001-000",
                "service_street": "Praca da Se",
                "service_number": "100",
                "service_complement": "Sala 2",
                "service_district": "Se",
                "service_city": "Sao Paulo",
                "service_state": "SP",
                "service_reference": "Proximo ao metro",
                "category": str(self.category.id),
                "title": "Revisao eletrica",
                "description": "Revisao de tomadas e quadro.",
                "notes": "Levar testador.",
                "start_date": "2026-06-10",
                "planned_start_time": "08:00",
                "planned_end_time": "11:30",
                "billing_mode": ServiceJob.BillingMode.HOURLY,
                "hourly_rate_snapshot": "120.00",
                "fixed_labor_value": "",
                "submit_action": "create",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        job = ServiceJob.objects.get(title="Revisao eletrica")
        self.assertEqual(job.status, ServiceJob.Status.PLANNED)
        self.assertEqual(job.contract, self.contract)
        self.assertEqual(job.client, self.company)
        self.assertEqual(job.service_location, "Praca da Se, 100, Sala 2, Se, Sao Paulo, SP")
        self.assertEqual(job.service_zip_code, "01001-000")
        self.assertEqual(job.planned_start_time.strftime("%H:%M"), "08:00")
        self.assertEqual(job.planned_end_time.strftime("%H:%M"), "11:30")
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.HOURLY)
        self.assertEqual(job.hourly_rate_snapshot, Decimal("120.00"))
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_create_casual_client_service(self):
        response = self.client.post(
            reverse("service_job_create"),
            {
                "client_mode": "casual",
                "contract": "",
                "manual_client_name": "Maria Silva",
                "manual_client_whatsapp": "11999999999",
                "manual_client_email": "maria@example.com",
                "service_street": "Rua das Flores",
                "service_number": "45",
                "service_district": "Centro",
                "service_city": "Campinas",
                "service_state": "SP",
                "category": str(ServiceCategory.objects.get(slug="visita-tecnica").id),
                "title": "Visita tecnica",
                "description": "Avaliar instalacao.",
                "notes": "",
                "start_date": "2026-06-12",
                "planned_start_time": "14:00",
                "planned_end_time": "15:00",
                "billing_mode": ServiceJob.BillingMode.UNDEFINED,
                "hourly_rate_snapshot": "",
                "fixed_labor_value": "",
                "submit_action": "draft",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        job = ServiceJob.objects.get(title="Visita tecnica")
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)
        self.assertIsNone(job.contract)
        self.assertIsNone(job.client)
        self.assertEqual(job.manual_client_name, "Maria Silva")
        self.assertEqual(job.manual_client_whatsapp, "11999999999")
        self.assertEqual(job.manual_client_email, "maria@example.com")
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.UNDEFINED)
        self.assertEqual(job.hourly_rate_snapshot, Decimal("0.00"))
        self.assertIsNone(job.fixed_labor_value)

    def test_create_service_with_fixed_labor_value(self):
        response = self.client.post(
            reverse("service_job_create"),
            {
                "client_mode": "registered",
                "contract": str(self.contract.id),
                "category": str(ServiceCategory.objects.get(slug="manutencao").id),
                "title": "Manutencao avulsa",
                "description": "Ajustes gerais.",
                "service_city": "Sao Paulo",
                "service_state": "SP",
                "billing_mode": ServiceJob.BillingMode.FIXED,
                "fixed_labor_value": "350.00",
                "hourly_rate_snapshot": "",
                "submit_action": "create",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        job = ServiceJob.objects.get(title="Manutencao avulsa")
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.FIXED)
        self.assertEqual(job.fixed_labor_value, Decimal("350.00"))
        self.assertEqual(job.hourly_rate_snapshot, Decimal("0.00"))

    def test_create_draft_service_with_category_and_existing_client(self):
        response = self.client.post(
            reverse("service_job_create"),
            {
                "contract": str(self.contract.id),
                "manual_client_name": "",
                "category": str(self.category.id),
                "title": "Troca de disjuntor",
                "description": "Trocar disjuntor e revisar tomadas.",
                "service_location": "Rua A, 123",
                "start_date": timezone.localdate().isoformat(),
                "end_date": "",
                "status": ServiceJob.Status.DRAFT,
                "billing_mode": ServiceJob.BillingMode.HOURLY,
                "hourly_rate_snapshot": "0",
                "fixed_labor_value": "",
                "notes": "Cliente pediu orçamento separado de materiais.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        job = ServiceJob.objects.get(title="Troca de disjuntor")
        self.assertEqual(job.professional, self.mei_user)
        self.assertEqual(job.contract, self.contract)
        self.assertEqual(job.client, self.company)
        self.assertEqual(job.category, self.category)
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)
        self.assertEqual(job.hourly_rate_snapshot, self.contract.hourly_rate)
        self.assertContains(response, "Troca de disjuntor")

    def test_create_in_progress_service_without_fixed_client(self):
        category = ServiceCategory.objects.get(slug="visita-tecnica")
        response = self.client.post(
            reverse("service_job_create"),
            {
                "contract": "",
                "manual_client_name": "Cliente avulso",
                "category": str(category.id),
                "title": "Vistoria inicial",
                "description": "Avaliar local antes da execução.",
                "service_location": "",
                "start_date": "",
                "end_date": "",
                "status": ServiceJob.Status.IN_PROGRESS,
                "billing_mode": ServiceJob.BillingMode.HOURLY,
                "hourly_rate_snapshot": "80.00",
                "fixed_labor_value": "",
                "notes": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        job = ServiceJob.objects.get(title="Vistoria inicial")
        self.assertIsNone(job.contract)
        self.assertIsNone(job.client)
        self.assertEqual(job.manual_client_name, "Cliente avulso")
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)

    def test_add_service_work_log_and_calculate_total_hours(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Servico com horarios",
            status=ServiceJob.Status.IN_PROGRESS,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=self.contract.hourly_rate,
        )

        response = self.client.post(
            reverse("service_work_log_create", args=[job.id]),
            {
                "work_date": "2026-06-10",
                "start_time": "08:00",
                "end_time": "11:30",
                "description": "Troca de tomadas",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        log = ServiceWorkLog.objects.get(service_job=job)
        self.assertEqual(log.duration_minutes, 210)
        job.refresh_from_db()
        self.assertEqual(job.total_hours_label, "03:30")
        self.assertEqual(job.labor_total, self.contract.hourly_rate * job.total_hours_decimal)
        self.assertContains(response, "03:30")
        self.assertContains(response, "Troca de tomadas")

    def test_work_log_rejects_end_time_before_start_time(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Servico horario invalido",
            status=ServiceJob.Status.IN_PROGRESS,
        )

        response = self.client.post(
            reverse("service_work_log_create", args=[job.id]),
            {
                "work_date": "2026-06-10",
                "start_time": "11:30",
                "end_time": "08:00",
                "description": "Horario invertido",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceWorkLog.objects.filter(service_job=job).exists())
        self.assertContains(response, "Horario final precisa ser maior que o inicial")

    def test_add_items_and_calculate_chargeable_and_non_chargeable_totals(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Servico com itens",
            status=ServiceJob.Status.IN_PROGRESS,
        )

        used_response = self.client.post(
            reverse("service_item_expense_create", args=[job.id]),
            {
                "type": ServiceItemExpense.ItemType.MATERIAL,
                "name": "Tomada 10A",
                "description": "",
                "quantity": "2",
                "unit_value": "15.00",
                "usage_status": ServiceItemExpense.UsageStatus.USED,
                "receipt_note": "",
            },
            follow=True,
        )
        not_used_response = self.client.post(
            reverse("service_item_expense_create", args=[job.id]),
            {
                "type": ServiceItemExpense.ItemType.MATERIAL,
                "name": "Cabo 2,5mm",
                "description": "",
                "quantity": "1",
                "unit_value": "40.00",
                "usage_status": ServiceItemExpense.UsageStatus.NOT_USED,
                "receipt_note": "Sera devolvido",
            },
            follow=True,
        )
        toll_response = self.client.post(
            reverse("service_item_expense_create", args=[job.id]),
            {
                "type": ServiceItemExpense.ItemType.TOLL,
                "name": "Pedagio",
                "description": "Viagem ate Sao Paulo",
                "quantity": "1",
                "unit_value": "42.00",
                "usage_status": ServiceItemExpense.UsageStatus.USED,
                "receipt_note": "",
            },
            follow=True,
        )

        self.assertEqual(used_response.status_code, 200)
        self.assertEqual(not_used_response.status_code, 200)
        self.assertEqual(toll_response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(ServiceItemExpense.objects.get(name="Tomada 10A").total_value, Decimal("30.00"))
        self.assertEqual(ServiceItemExpense.objects.get(name="Cabo 2,5mm").total_value, Decimal("40.00"))
        self.assertEqual(ServiceItemExpense.objects.get(name="Pedagio").total_value, Decimal("42.00"))
        self.assertEqual(job.used_items_total, Decimal("72.00"))
        self.assertEqual(job.not_used_items_total, Decimal("40.00"))
        self.assertEqual(job.estimated_total, Decimal("72.00"))
        self.assertContains(toll_response, "Itens usados")
        self.assertContains(toll_response, "Itens não usados/devolvidos")

    def test_service_detail_shows_professional_layout_totals_and_report_state(self):
        before_punch_count = Punch.objects.count()
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Troca de disjuntores",
            description="Troca de disjuntores e teste do quadro.",
            service_street="Rua X",
            service_number="120",
            service_city="Blumenau",
            service_state="SC",
            service_location="Rua X, 120, Blumenau, SC",
            start_date=timezone.localdate(),
            planned_start_time=datetime.strptime("08:00", "%H:%M").time(),
            planned_end_time=datetime.strptime("11:00", "%H:%M").time(),
            status=ServiceJob.Status.IN_PROGRESS,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("100.00"),
            notes="Cliente pediu teste final.",
        )

        self.client.post(
            reverse("service_work_log_create", args=[job.id]),
            {
                "work_date": "2026-06-11",
                "start_time": "08:00",
                "end_time": "10:30",
                "description": "Troca de disjuntores",
            },
        )
        self.client.post(
            reverse("service_work_log_create", args=[job.id]),
            {
                "work_date": "2026-06-11",
                "start_time": "10:45",
                "end_time": "11:15",
                "description": "Teste do quadro",
            },
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Disjuntor 20A",
            quantity=Decimal("2"),
            unit_value=Decimal("35.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Cabo reserva",
            quantity=Decimal("1"),
            unit_value=Decimal("40.00"),
            usage_status=ServiceItemExpense.UsageStatus.NOT_USED,
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.TOLL,
            name="Pedagio",
            quantity=Decimal("1"),
            unit_value=Decimal("42.00"),
            usage_status=ServiceItemExpense.UsageStatus.PURCHASED,
        )

        response = self.client.get(reverse("service_job_detail", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Troca de disjuntores")
        self.assertContains(response, "Cliente Servicos A")
        self.assertContains(response, "Rua X 120 - Blumenau/SC")
        self.assertContains(response, "Horas previstas")
        self.assertContains(response, "03:00")
        self.assertContains(response, "Execução do serviço")
        self.assertContains(response, "Total trabalhado")
        self.assertContains(response, "03:00")
        self.assertContains(response, "Mão de obra")
        self.assertContains(response, "R$ 300,00")
        self.assertContains(response, "Itens usados/cobrados")
        self.assertContains(response, "Disjuntor 20A")
        self.assertContains(response, "Itens não usados/devolvidos")
        self.assertContains(response, "Cabo reserva")
        self.assertContains(response, "Itens previstos")
        self.assertContains(response, "Pedagio")
        self.assertContains(response, "R$ 370,00")
        self.assertContains(response, "Quando terminar, finalize o serviço")
        self.assertEqual(Punch.objects.count(), before_punch_count)

        finish_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "finish"},
            follow=True,
        )
        self.assertContains(finish_response, "Gerar relatório")
        self.assertNotContains(finish_response, "Enviar WhatsApp")
        self.assertNotContains(finish_response, "PDF")

    def test_planned_service_detail_prioritizes_start_actions_before_finish(self):
        before_punch_count = Punch.objects.count()
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            manual_client_name="John",
            category=self.category,
            title="Servico planejado visual",
            service_street="Rua X",
            service_number="120",
            service_city="Blumenau",
            service_state="SC",
            start_date=timezone.localdate(),
            planned_start_time=datetime.strptime("08:00", "%H:%M").time(),
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.UNDEFINED,
        )

        response = self.client.get(reverse("service_job_detail", args=[job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O que fazer agora")
        self.assertContains(response, "Iniciar trabalho")
        self.assertContains(response, "Adicionar período manual")
        self.assertContains(response, "Adicionar item")
        self.assertContains(response, "Nenhum período de trabalho registrado ainda.")
        self.assertContains(response, "O relatório final fica disponível depois que o serviço for finalizado.")
        self.assertNotContains(response, '<button class="btn" type="submit">Finalizar serviço</button>', html=True)
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_finished_service_blocks_new_work_logs_and_items_then_reopens(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Servico para finalizar",
            status=ServiceJob.Status.IN_PROGRESS,
        )

        finish_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "finish"},
            follow=True,
        )
        job.refresh_from_db()
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(job.status, ServiceJob.Status.FINISHED)
        self.assertIsNotNone(job.finished_at)
        self.assertContains(finish_response, "Serviço finalizado")

        blocked_log_response = self.client.post(
            reverse("service_work_log_create", args=[job.id]),
            {
                "work_date": "2026-06-10",
                "start_time": "08:00",
                "end_time": "09:00",
                "description": "Bloqueado",
            },
            follow=True,
        )
        blocked_item_response = self.client.post(
            reverse("service_item_expense_create", args=[job.id]),
            {
                "type": ServiceItemExpense.ItemType.OTHER,
                "name": "Bloqueado",
                "quantity": "1",
                "unit_value": "1",
                "usage_status": ServiceItemExpense.UsageStatus.USED,
            },
            follow=True,
        )
        self.assertFalse(ServiceWorkLog.objects.filter(service_job=job).exists())
        self.assertFalse(ServiceItemExpense.objects.filter(service_job=job).exists())
        self.assertContains(blocked_log_response, "Reabra o servico")
        self.assertContains(blocked_item_response, "Reabra o servico")

        reopen_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "reopen"},
            follow=True,
        )
        job.refresh_from_db()
        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(job.status, ServiceJob.Status.IN_PROGRESS)
        self.assertIsNone(job.finished_at)

    def test_service_status_flow_can_start_archive_and_reopen(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Fluxo de status",
            description="Servico pronto para iniciar.",
            service_location="Rua A, 10",
            start_date=timezone.localdate(),
            status=ServiceJob.Status.PLANNED,
        )

        start_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "start"},
            follow=True,
        )
        job.refresh_from_db()
        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(job.status, ServiceJob.Status.IN_PROGRESS)
        self.assertContains(start_response, "Finalizar serviço")

        archive_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "archive"},
            follow=True,
        )
        job.refresh_from_db()
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(job.status, ServiceJob.Status.ARCHIVED)
        self.assertContains(archive_response, "Restaurar serviço")

        restore_response = self.client.post(
            reverse("service_job_status_action", args=[job.id]),
            {"action": "restore"},
            follow=True,
        )
        job.refresh_from_db()
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(job.status, ServiceJob.Status.PLANNED)

    def test_list_and_filters_by_status_and_category(self):
        draft = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Rascunho eletrica",
            status=ServiceJob.Status.DRAFT,
        )
        finished = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=ServiceCategory.objects.get(slug="hidraulica"),
            title="Finalizado hidraulica",
            status=ServiceJob.Status.FINISHED,
        )

        status_response = self.client.get(reverse("service_job_list"), {"status": ServiceJob.Status.DRAFT})
        self.assertContains(status_response, draft.title)
        self.assertContains(status_response, "Completar dados")
        self.assertNotContains(status_response, finished.title)

        category_response = self.client.get(reverse("service_job_list"), {"category": "hidraulica"})
        self.assertContains(category_response, finished.title)
        self.assertContains(category_response, "Gerar relatório")
        self.assertNotContains(category_response, draft.title)

        search_response = self.client.get(reverse("service_job_list"), {"q": "hidraulica"})
        self.assertContains(search_response, finished.title)
        self.assertNotContains(search_response, draft.title)

    def test_create_manual_service_request_for_casual_client_list_filter_and_whatsapp(self):
        before_punch_count = Punch.objects.count()

        response = self.client.post(
            reverse("service_request_create"),
            {
                "client_mode": "casual",
                "contract": "",
                "client_name": "Cliente Pedido Avulso",
                "client_whatsapp": "11999999999",
                "client_email": "pedido@example.com",
                "address_zipcode": "01001-000",
                "address_street": "Praca da Se",
                "address_number": "100",
                "address_complement": "Sala 8",
                "address_neighborhood": "Se",
                "address_city": "Sao Paulo",
                "address_state": "sp",
                "address_reference": "Proximo ao metro",
                "category": str(self.category.id),
                "title": "Pedido de revisao eletrica",
                "description": "Cliente pediu avaliacao do quadro.",
                "urgency": ServiceRequest.Urgency.HIGH,
                "preferred_date": "2026-06-20",
                "preferred_time": "09:30",
                "source": ServiceRequest.Source.WHATSAPP,
                "submit_action": "save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        service_request = ServiceRequest.objects.get(title="Pedido de revisao eletrica")
        self.assertEqual(service_request.professional, self.mei_user)
        self.assertIsNone(service_request.client)
        self.assertEqual(service_request.client_name, "Cliente Pedido Avulso")
        self.assertEqual(service_request.address_state, "SP")
        self.assertEqual(service_request.status, ServiceRequest.Status.NEW)
        self.assertEqual(Punch.objects.count(), before_punch_count)

        list_response = self.client.get(reverse("service_request_list"))
        self.assertContains(list_response, "Pedido de revisao eletrica")
        self.assertContains(list_response, "Novo")

        filtered_response = self.client.get(reverse("service_request_list"), {"status": ServiceRequest.Status.NEW})
        self.assertContains(filtered_response, "Pedido de revisao eletrica")

        whatsapp_response = self.client.get(reverse("service_request_whatsapp", args=[service_request.id]))
        self.assertEqual(whatsapp_response.status_code, 302)
        self.assertIn("https://wa.me/5511999999999?text=", whatsapp_response["Location"])
        self.assertIn("Pedido%20de%20revisao%20eletrica", whatsapp_response["Location"])

    def test_create_registered_client_service_request(self):
        response = self.client.post(
            reverse("service_request_create"),
            {
                "client_mode": "registered",
                "contract": str(self.contract.id),
                "client_name": "",
                "client_whatsapp": "",
                "client_email": "",
                "address_city": "Sao Paulo",
                "address_state": "SP",
                "category": str(ServiceCategory.objects.get(slug="manutencao").id),
                "title": "Pedido cliente cadastrado",
                "description": "Cliente cadastrado pediu manutencao.",
                "urgency": ServiceRequest.Urgency.NORMAL,
                "preferred_date": "2026-06-21",
                "preferred_time": "10:00",
                "source": ServiceRequest.Source.PHONE,
                "submit_action": "save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        service_request = ServiceRequest.objects.get(title="Pedido cliente cadastrado")
        self.assertEqual(service_request.contract, self.contract)
        self.assertEqual(service_request.client, self.company)
        self.assertEqual(service_request.client_name, self.company.name)
        self.assertEqual(service_request.source, ServiceRequest.Source.PHONE)

    def test_service_request_conversion_creates_draft_service_and_preserves_history(self):
        before_punch_count = Punch.objects.count()
        service_request = ServiceRequest.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            client=self.company,
            client_name=self.company.name,
            client_whatsapp="11988887777",
            category=self.category,
            title="Converter pedido em servico",
            description="Trocar tomadas e revisar quadro.",
            address_zipcode="01001-000",
            address_street="Rua A",
            address_number="50",
            address_neighborhood="Centro",
            address_city="Sao Paulo",
            address_state="SP",
            address_reference="Portaria",
            preferred_date=datetime(2026, 6, 22).date(),
            preferred_time=datetime.strptime("14:30", "%H:%M").time(),
            urgency=ServiceRequest.Urgency.URGENT,
            source=ServiceRequest.Source.REFERRAL,
        )

        response = self.client.post(reverse("service_request_convert", args=[service_request.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        service_request.refresh_from_db()
        self.assertEqual(service_request.status, ServiceRequest.Status.CONVERTED)
        self.assertIsNotNone(service_request.converted_service)
        job = service_request.converted_service
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)
        self.assertEqual(job.contract, self.contract)
        self.assertEqual(job.client, self.company)
        self.assertEqual(job.manual_client_whatsapp, "11988887777")
        self.assertEqual(job.title, service_request.title)
        self.assertEqual(job.description, service_request.description)
        self.assertEqual(job.service_zip_code, service_request.address_zipcode)
        self.assertEqual(job.service_street, service_request.address_street)
        self.assertEqual(job.service_number, service_request.address_number)
        self.assertEqual(job.service_district, service_request.address_neighborhood)
        self.assertEqual(job.service_city, service_request.address_city)
        self.assertEqual(job.service_state, service_request.address_state)
        self.assertEqual(job.service_reference, service_request.address_reference)
        self.assertEqual(job.start_date, service_request.preferred_date)
        self.assertEqual(job.planned_start_time, service_request.preferred_time)
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.UNDEFINED)
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_service_request_save_and_convert_from_form_for_casual_client(self):
        response = self.client.post(
            reverse("service_request_create"),
            {
                "client_mode": "casual",
                "contract": "",
                "client_name": "Maria Pedido",
                "client_whatsapp": "11977776666",
                "client_email": "",
                "address_street": "Rua das Flores",
                "address_number": "45",
                "address_city": "Campinas",
                "address_state": "SP",
                "category": str(self.category.id),
                "title": "Pedido convertido direto",
                "description": "Transformar no envio do formulario.",
                "urgency": ServiceRequest.Urgency.NORMAL,
                "preferred_date": "2026-06-23",
                "preferred_time": "08:00",
                "source": ServiceRequest.Source.OTHER,
                "submit_action": "convert",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        service_request = ServiceRequest.objects.get(title="Pedido convertido direto")
        self.assertEqual(service_request.status, ServiceRequest.Status.CONVERTED)
        job = service_request.converted_service
        self.assertEqual(job.manual_client_name, "Maria Pedido")
        self.assertEqual(job.manual_client_whatsapp, "11977776666")
        self.assertEqual(job.status, ServiceJob.Status.DRAFT)

    def test_other_user_cannot_see_or_convert_service_request(self):
        service_request = ServiceRequest.objects.create(
            professional=self.other_user,
            contract=self.other_contract,
            client=self.other_company,
            client_name=self.other_company.name,
            category=self.category,
            title="Pedido de outro usuario",
            description="Isolamento de usuario.",
        )

        list_response = self.client.get(reverse("service_request_list"))
        detail_response = self.client.get(reverse("service_request_detail", args=[service_request.id]))
        convert_response = self.client.post(reverse("service_request_convert", args=[service_request.id]))

        self.assertNotContains(list_response, service_request.title)
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(convert_response.status_code, 404)

    def test_user_cannot_see_or_open_other_users_service(self):
        other_job = ServiceJob.objects.create(
            professional=self.other_user,
            contract=self.other_contract,
            category=self.category,
            title="Servico de outro usuario",
            status=ServiceJob.Status.IN_PROGRESS,
        )

        list_response = self.client.get(reverse("service_job_list"))
        self.assertNotContains(list_response, other_job.title)

        detail_response = self.client.get(reverse("service_job_detail", args=[other_job.id]))
        self.assertEqual(detail_response.status_code, 404)

    def test_service_creation_does_not_change_normal_history(self):
        start = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()))
        Punch.objects.create(contract=self.contract, timestamp=start + timedelta(hours=8))
        Punch.objects.create(contract=self.contract, timestamp=start + timedelta(hours=10))
        before_count = Punch.objects.count()

        ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Servico separado do historico",
            status=ServiceJob.Status.IN_PROGRESS,
        )

        self.assertEqual(Punch.objects.count(), before_count)
        history_response = self.client.get(reverse("mei_history"), {"contract": str(self.contract.id)})
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.context["summary_total_punches"], 2)
        self.assertNotContains(history_response, "Servico separado do historico")

    def test_existing_reports_pdf_and_whatsapp_still_work(self):
        today = timezone.localdate()
        report = ServiceReport.objects.create(
            company=self.company,
            employee=self.employee,
            contract=self.contract,
            report_date=today,
            date_from=today,
            date_to=today,
            title="Relatorio de horas preservado",
            status=ServiceReport.Status.SENT,
            summary_payload={
                "company": self.company.name,
                "professional": self.employee.full_name,
                "period": {"label": f"{today:%d/%m/%Y}"},
                "total_hours": "02:00",
                "estimated_value_brl": "R$ 190,00",
                "days": [],
            },
        )
        report.ensure_conference_link()
        report.save()

        reports_response = self.client.get(reverse("mei_reports"), {"contract": str(self.contract.id)})
        pdf_response = self.client.get(reverse("mei_service_report_pdf", args=[report.id]))
        whatsapp_response = self.client.get(reverse("mei_service_report_whatsapp", args=[report.id]))

        self.assertEqual(reports_response.status_code, 200)
        self.assertContains(reports_response, "Relatorio de horas preservado")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertEqual(whatsapp_response.status_code, 302)

    def test_service_preview_flow_public_link_whatsapp_and_estimated_values(self):
        before_punch_count = Punch.objects.count()
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            manual_client_name="John",
            manual_client_whatsapp="11999999999",
            category=self.category,
            title="Troca de disjuntores",
            description="Trocar disjuntores da casa e revisar quadro.",
            service_street="Rua X",
            service_number="120",
            service_district="Centro",
            service_city="Blumenau",
            service_state="SC",
            service_location="Rua X, 120, Centro, Blumenau, SC",
            start_date=timezone.localdate(),
            planned_start_time=datetime.strptime("08:00", "%H:%M").time(),
            planned_end_time=datetime.strptime("11:00", "%H:%M").time(),
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("100.00"),
            notes="Valores sujeitos a ajuste conforme compra real.",
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.PART,
            name="Disjuntor 20A",
            quantity=Decimal("2"),
            unit_value=Decimal("35.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Fita isolante",
            quantity=Decimal("2"),
            unit_value=Decimal("8.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )

        generate_response = self.client.post(reverse("service_job_preview_generate", args=[job.id]), follow=True)
        job.refresh_from_db()
        self.assertEqual(generate_response.status_code, 200)
        self.assertIsNotNone(job.preview_generated_at)
        self.assertContains(generate_response, "Status: Gerada")
        self.assertContains(generate_response, "R$ 86,00")
        self.assertContains(generate_response, "R$ 300,00")
        self.assertContains(generate_response, "R$ 386,00")

        self.client.logout()
        preview_response = self.client.get(reverse("public_service_job_preview", args=[job.public_token]))
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Prévia do serviço")
        self.assertContains(preview_response, "John")
        self.assertContains(preview_response, "Rua X, 120, Centro, Blumenau, SC")
        self.assertContains(preview_response, "Disjuntor 20A")
        self.assertContains(preview_response, "Total estimado do serviço")
        self.assertContains(preview_response, "Os valores desta prévia podem ser ajustados")
        self.assertNotContains(preview_response, "Registrar horario")
        job.refresh_from_db()
        self.assertIsNotNone(job.preview_first_viewed_at)

        self.client.force_login(self.mei_user)
        whatsapp_response = self.client.get(reverse("service_job_preview_whatsapp", args=[job.id]))
        job.refresh_from_db()
        self.assertEqual(whatsapp_response.status_code, 302)
        self.assertIn("https://wa.me/?text=", whatsapp_response["Location"])
        self.assertIn("Itens%20previstos%3A%20R%24%2086%2C00", whatsapp_response["Location"])
        self.assertIn("M%C3%A3o%20de%20obra%20estimada%3A%20R%24%20300%2C00", whatsapp_response["Location"])
        self.assertIn("Total%20estimado%3A%20R%24%20386%2C00", whatsapp_response["Location"])
        self.assertIsNotNone(job.preview_sent_at)
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_service_quote_whatsapp_message_and_quoted_item_update(self):
        before_punch_count = Punch.objects.count()
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            manual_client_name="John",
            category=self.category,
            title="Troca de disjuntores",
            description="Trocar disjuntores da casa.",
            service_location="Rua X, 120",
            start_date=timezone.localdate(),
            planned_start_time=datetime.strptime("08:00", "%H:%M").time(),
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.UNDEFINED,
        )
        quoted_item = ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.PART,
            name="Disjuntor 20A",
            description="marca/modelo se disponivel",
            quantity=Decimal("2"),
            unit_value=Decimal("35.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        used_item = ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Fita isolante",
            quantity=Decimal("1"),
            unit_value=Decimal("15.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )

        detail_response = self.client.get(reverse("service_job_detail", args=[job.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Pedir cotação")
        self.assertContains(detail_response, "Copiar mensagem")
        self.assertContains(detail_response, "Abrir WhatsApp")
        self.assertContains(detail_response, "Valores cotados são estimativas até a execução do serviço.")
        self.assertContains(detail_response, "* 2 x Disjuntor 20A — marca/modelo se disponivel")

        generate_response = self.client.post(reverse("service_job_quote_generate", args=[job.id]), follow=True)
        job.refresh_from_db()
        self.assertEqual(generate_response.status_code, 200)
        self.assertContains(generate_response, "Cotacao gerada")
        self.assertIsNotNone(job.quote_message_generated_at)
        self.assertEqual(job.quote_item_count, 1)
        self.assertIn("Troca de disjuntores", job.quote_last_message)
        self.assertIn("Disjuntor 20A", job.quote_last_message)

        whatsapp_response = self.client.get(reverse("service_job_quote_whatsapp", args=[job.id]))
        job.refresh_from_db()
        self.assertEqual(whatsapp_response.status_code, 302)
        self.assertIn("https://wa.me/?text=", whatsapp_response["Location"])
        self.assertIn("Troca%20de%20disjuntores", whatsapp_response["Location"])
        self.assertIn("Disjuntor%2020A", whatsapp_response["Location"])
        self.assertIn("disponibilidade", whatsapp_response["Location"])
        self.assertIsNotNone(job.quote_message_generated_at)
        self.assertEqual(job.quote_item_count, 1)
        self.assertIn("Pode me passar os valores e disponibilidade?", job.quote_last_message)

        update_response = self.client.post(
            reverse("service_item_expense_update", args=[job.id, quoted_item.id]),
            {
                "type": ServiceItemExpense.ItemType.PART,
                "name": "Disjuntor 20A",
                "description": "Cotado na loja A",
                "quantity": "3.00",
                "unit_value": "42.00",
                "usage_status": ServiceItemExpense.UsageStatus.QUOTED,
                "receipt_note": "",
            },
            follow=True,
        )
        quoted_item.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(update_response.status_code, 200)
        self.assertContains(update_response, "Cotado")
        self.assertEqual(quoted_item.quantity, Decimal("3.00"))
        self.assertEqual(quoted_item.unit_value, Decimal("42.00"))
        self.assertEqual(quoted_item.total_value, Decimal("126.00"))
        self.assertEqual(quoted_item.usage_status, ServiceItemExpense.UsageStatus.QUOTED)
        self.assertEqual(job.used_items_total, used_item.total_value)

        self.client.post(reverse("service_job_preview_generate", args=[job.id]), follow=True)
        self.client.logout()
        preview_response = self.client.get(reverse("public_service_job_preview", args=[job.public_token]))
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Disjuntor 20A")
        self.assertContains(preview_response, "Cotado")
        self.assertContains(preview_response, "R$ 126,00")
        self.assertEqual(Punch.objects.count(), before_punch_count)

    def test_service_without_planned_items_shows_quote_guidance_only(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            manual_client_name="John",
            category=self.category,
            title="Servico sem itens previstos",
            status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.UNDEFINED,
        )

        detail_response = self.client.get(reverse("service_job_detail", args=[job.id]))
        generate_response = self.client.post(reverse("service_job_quote_generate", args=[job.id]), follow=True)

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Adicione itens previstos para gerar uma cotação.")
        self.assertNotContains(detail_response, "/cotacao/gerar/")
        self.assertNotContains(detail_response, "Abrir WhatsApp")
        self.assertEqual(generate_response.status_code, 200)
        self.assertContains(generate_response, "Adicione itens previstos")

    def _create_finished_report_ready_service(self):
        job = ServiceJob.objects.create(
            professional=self.mei_user,
            contract=self.contract,
            category=self.category,
            title="Instalacao eletrica sala",
            description="Troca de tomadas e revisao do quadro.",
            service_location="Rua A, 123",
            status=ServiceJob.Status.REPORT_SENT,
            billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=self.contract.hourly_rate,
            notes="Servico finalizado sem pendencias.",
        )
        ServiceWorkLog.objects.create(
            service_job=job,
            work_date=timezone.localdate(),
            start_time=datetime.strptime("08:00", "%H:%M").time(),
            end_time=datetime.strptime("11:30", "%H:%M").time(),
            description="Troca de tomadas",
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Tomada 10A",
            quantity=Decimal("2"),
            unit_value=Decimal("15.00"),
            usage_status=ServiceItemExpense.UsageStatus.USED,
        )
        ServiceItemExpense.objects.create(
            service_job=job,
            type=ServiceItemExpense.ItemType.MATERIAL,
            name="Cabo 2,5mm",
            quantity=Decimal("1"),
            unit_value=Decimal("40.00"),
            usage_status=ServiceItemExpense.UsageStatus.NOT_USED,
            receipt_note="Material sera devolvido.",
        )
        job.refresh_from_db()
        return job

    def test_public_service_report_opens_without_login_and_records_first_view(self):
        job = self._create_finished_report_ready_service()
        self.client.logout()

        response = self.client.get(reverse("public_service_job_report", args=[job.public_token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relatório de serviço")
        self.assertContains(response, "Instalacao eletrica sala")
        self.assertContains(response, "03:30")
        self.assertContains(response, "Tomada 10A")
        self.assertContains(response, "Cabo 2,5mm")
        self.assertContains(response, "R$ 362,50")
        self.assertNotContains(response, "Registrar horario")
        job.refresh_from_db()
        self.assertIsNotNone(job.public_report_first_viewed_at)

    def test_service_report_pdf_is_separate_pdf(self):
        job = self._create_finished_report_ready_service()

        response = self.client.get(reverse("service_job_report_pdf", args=[job.id]))
        public_response = self.client.get(reverse("public_service_job_report_pdf", args=[job.public_token]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("horacerta_servico_", response["Content-Disposition"])
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response["Content-Type"], "application/pdf")

    def test_service_report_whatsapp_message_uses_real_totals(self):
        job = self._create_finished_report_ready_service()

        response = self.client.get(reverse("service_job_report_whatsapp", args=[job.id]))

        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertIn("https://wa.me/?text=", location)
        self.assertIn("Instalacao%20eletrica%20sala", location)
        self.assertIn("Horas%20realizadas%3A%2003%3A30", location)
        self.assertIn("M%C3%A3o%20de%20obra%3A%20R%24%20332%2C50", location)
        self.assertIn("Itens%2Fdespesas%3A%20R%24%2030%2C00", location)
        self.assertIn("Total%20do%20servi%C3%A7o%3A%20R%24%20362%2C50", location)

    def test_other_user_cannot_open_internal_service_report_actions(self):
        job = self._create_finished_report_ready_service()
        self.client.force_login(self.other_user)

        pdf_response = self.client.get(reverse("service_job_report_pdf", args=[job.id]))
        whatsapp_response = self.client.get(reverse("service_job_report_whatsapp", args=[job.id]))

        self.assertEqual(pdf_response.status_code, 404)
        self.assertEqual(whatsapp_response.status_code, 404)

