from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from uuid import uuid4

from companies.models import Company, CompanyAttendancePolicy, CompanyAuthorizedLocation, Employee, InternalAdminActionLog
from timeclock.models import ActivityReportRequest, Contract, Punch, PunchCorrectionLog, PunchCorrectionRequest, ServiceReport
from accounts.mei_context import MEI_SELECTED_CONTRACT_SESSION_KEY
from .forms import CompanyAttendancePolicyForm, CompanyAuthorizedLocationForm
from .services import MeiLinkError, create_or_link_mei_by_email

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class InternalDashboardTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="Admin@12345",
            role=User.Role.EMPRESA,
        )
        self.company_owner = User.objects.create_user(
            username="owner-interno@example.com",
            email="owner-interno@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.employee_user = User.objects.create_user(
            username="mei-interno@example.com",
            email="mei-interno@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.company = Company.objects.create(
            name="Empresa Painel Interno",
            owner=self.company_owner,
            email="painel@example.com",
        )
        self.employee = Employee.objects.create(
            user=self.employee_user,
            company=self.company,
            full_name="MEI Painel",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate="100.00",
            start_date=timezone.localdate() - timedelta(days=1),
            is_active=True,
        )
        Punch.objects.create(contract=self.contract, timestamp=timezone.now())

    def test_superuser_can_access_internal_dashboard(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("internal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Painel interno")
        self.assertEqual(response.context["total_users"], User.objects.count())
        self.assertEqual(response.context["total_companies"], Company.objects.count())
        self.assertEqual(response.context["total_employees"], Employee.objects.count())
        self.assertEqual(response.context["total_punches"], Punch.objects.count())
        self.assertContains(response, self.company.name)

    def test_staff_user_cannot_access_internal_dashboard(self):
        staff_user = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="Staff@12345",
            role=User.Role.EMPRESA,
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("internal_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_regular_user_gets_403(self):
        self.client.force_login(self.company_owner)

        response = self.client.get(reverse("internal_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_internal_backoffice_routes(self):
        self.client.force_login(self.admin_user)
        routes = [
            reverse("internal_dashboard"),
            reverse("internal_companies"),
            reverse("internal_company_detail", args=[self.company.id]),
            reverse("internal_employees"),
            reverse("internal_employee_detail", args=[self.employee.id]),
            reverse("internal_punches"),
            reverse("internal_punch_detail", args=[Punch.objects.first().id]),
            reverse("internal_correction_requests"),
            reverse("internal_corrections"),
            reverse("internal_notifications"),
            reverse("internal_audit"),
        ]

        for url in routes:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_internal_backoffice_routes(self):
        self.client.force_login(self.company_owner)
        routes = [
            reverse("internal_dashboard"),
            reverse("internal_companies"),
            reverse("internal_company_detail", args=[self.company.id]),
            reverse("internal_employees"),
            reverse("internal_employee_detail", args=[self.employee.id]),
            reverse("internal_punches"),
            reverse("internal_punch_detail", args=[Punch.objects.first().id]),
            reverse("internal_correction_requests"),
            reverse("internal_corrections"),
            reverse("internal_notifications"),
            reverse("internal_audit"),
        ]

        for url in routes:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_staff_user_cannot_access_internal_backoffice_routes(self):
        staff_user = User.objects.create_user(
            username="staff-routes@example.com",
            email="staff-routes@example.com",
            password="Staff@12345",
            role=User.Role.EMPRESA,
            is_staff=True,
        )
        self.client.force_login(staff_user)
        routes = [
            reverse("internal_dashboard"),
            reverse("internal_companies"),
            reverse("internal_company_detail", args=[self.company.id]),
            reverse("internal_employees"),
            reverse("internal_employee_detail", args=[self.employee.id]),
            reverse("internal_punches"),
            reverse("internal_punch_detail", args=[Punch.objects.first().id]),
            reverse("internal_correction_requests"),
            reverse("internal_corrections"),
            reverse("internal_notifications"),
            reverse("internal_audit"),
        ]

        for url in routes:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_company_sidebar_does_not_show_internal_links(self):
        self.client.force_login(self.company_owner)

        response = self.client.get(reverse("dashboard_empresa"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Painel interno")
        self.assertNotContains(response, "Notificacoes internas")

    def test_mei_sidebar_does_not_show_internal_links(self):
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("employee_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Painel interno")
        self.assertNotContains(response, "Notificacoes internas")

    def test_superuser_can_correct_punch_time_from_internal_detail(self):
        punch = Punch.objects.first()
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("internal_punch_detail", args=[punch.id]),
            {
                "action": "change_time",
                "new_datetime": "2026-05-19T06:50",
                "reason": "Correção solicitada pelo usuário.",
            },
        )

        self.assertEqual(response.status_code, 302)
        punch.refresh_from_db()
        self.assertEqual(timezone.localtime(punch.timestamp).strftime("%Y-%m-%d %H:%M"), "2026-05-19 06:50")
        self.assertTrue(
            PunchCorrectionLog.objects.filter(
                punch=punch,
                action_type=PunchCorrectionLog.ActionType.TIME_CHANGED,
            ).exists()
        )

    def test_superuser_can_cancel_punch_from_internal_detail(self):
        punch = Punch.objects.first()
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("internal_punch_detail", args=[punch.id]),
            {
                "action": "cancel",
                "reason": "Registro feito por engano.",
            },
        )

        self.assertEqual(response.status_code, 302)
        punch.refresh_from_db()
        self.assertTrue(punch.is_cancelled)
        self.assertFalse(Punch.objects.filter(id=punch.id).exists())
        self.assertTrue(Punch.all_objects.filter(id=punch.id).exists())

    def test_employee_can_submit_punch_correction_request(self):
        punch = Punch.objects.first()
        self.client.force_login(self.employee_user)

        response = self.client.post(
            reverse("mei_punch_correction_request"),
            {
                "problem_date": timezone.localdate().strftime("%Y-%m-%d"),
                "problem_type": PunchCorrectionRequest.ProblemType.EXTRA_PUNCH,
                "contract": str(self.contract.id),
                "punch": str(punch.id),
                "description": "Registrei uma batida a mais durante teste.",
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj = PunchCorrectionRequest.objects.get(employee=self.employee)
        self.assertEqual(request_obj.status, PunchCorrectionRequest.Status.OPEN)
        self.assertEqual(request_obj.company_id, self.company.id)
        self.assertEqual(request_obj.punch_id, punch.id)

    def test_superuser_can_review_punch_correction_request(self):
        request_obj = PunchCorrectionRequest.objects.create(
            employee=self.employee,
            user=self.employee_user,
            company=self.company,
            contract=self.contract,
            punch=Punch.objects.first(),
            problem_date=timezone.localdate(),
            problem_type=PunchCorrectionRequest.ProblemType.WRONG_TIME,
            description="Horario errado.",
        )
        self.client.force_login(self.admin_user)

        detail_response = self.client.get(reverse("internal_correction_request_detail", args=[request_obj.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Registros daquele dia")

        response = self.client.post(
            reverse("internal_correction_request_detail", args=[request_obj.id]),
            {
                "status": PunchCorrectionRequest.Status.CORRECTED,
                "admin_response": "Corrigido pelo backoffice.",
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, PunchCorrectionRequest.Status.CORRECTED)
        self.assertEqual(request_obj.resolved_by_id, self.admin_user.id)
        self.assertTrue(request_obj.resolved_at)

    def test_superuser_can_deactivate_and_activate_employee_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("internal_employee_detail", args=[self.employee.id]),
            {"action": "deactivate_user", "description": "Bloqueio administrativo."},
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.employee.user.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertFalse(self.employee.user.is_active)
        self.assertTrue(
            InternalAdminActionLog.objects.filter(
                target_type="employee",
                target_id=str(self.employee.id),
                action="deactivate_user",
            ).exists()
        )

        response = self.client.post(
            reverse("internal_employee_detail", args=[self.employee.id]),
            {"action": "activate_user", "description": "Reativacao administrativa."},
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.employee.user.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.user.is_active)

    def test_superuser_can_deactivate_company_and_save_internal_note(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("internal_company_detail", args=[self.company.id]),
            {"action": "deactivate_company", "description": "Pausa administrativa."},
        )

        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)

        response = self.client.post(
            reverse("internal_company_detail", args=[self.company.id]),
            {
                "action": "save_company_note",
                "internal_note": "Cliente em acompanhamento.",
                "description": "Nota interna atualizada.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.internal_note, "Cliente em acompanhamento.")
        self.assertTrue(
            InternalAdminActionLog.objects.filter(
                target_type="company",
                target_id=str(self.company.id),
                action="save_company_note",
            ).exists()
        )


class CreateOrLinkMeiServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="rh@example.com",
            email="rh@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(name="Empresa A", owner=self.owner, email="empresa-a@example.com")

    def test_create_new_email_creates_user_employee_and_contract(self):
        result = create_or_link_mei_by_email(
            company=self.company,
            full_name="MEI Novo",
            mei_email="mei.novo@example.com",
            password="Senha@12345",
            contract_payload={"hourly_rate": "90.00"},
        )

        self.assertTrue(result.user_created)
        self.assertTrue(result.employee_created)
        self.assertTrue(result.contract_created)
        self.assertEqual(result.user.role, User.Role.FUNCIONARIO)
        self.assertTrue(Employee.objects.filter(user=result.user, company=self.company).exists())
        self.assertTrue(Contract.objects.filter(employee=result.employee, company=self.company).exists())

    def test_existing_mei_email_links_without_changing_password(self):
        existing_user = User.objects.create_user(
            username="mei.existente@example.com",
            email="mei.existente@example.com",
            password="Original@12345",
            role=User.Role.FUNCIONARIO,
        )
        old_password_hash = existing_user.password

        result = create_or_link_mei_by_email(
            company=self.company,
            full_name="MEI Existente",
            mei_email="mei.existente@example.com",
            password=None,
            contract_payload={"hourly_rate": "120.00"},
        )

        existing_user.refresh_from_db()
        self.assertFalse(result.user_created)
        self.assertTrue(result.linked_existing_user)
        self.assertEqual(existing_user.password, old_password_hash)
        self.assertTrue(Employee.objects.filter(user=existing_user, company=self.company).exists())
        self.assertTrue(Contract.objects.filter(employee=result.employee, company=self.company).exists())

    def test_existing_link_for_same_company_is_blocked(self):
        existing_user = User.objects.create_user(
            username="mei.vinculado@example.com",
            email="mei.vinculado@example.com",
            password="Original@12345",
            role=User.Role.FUNCIONARIO,
        )
        Employee.objects.create(
            user=existing_user,
            company=self.company,
            full_name="MEI Vinculado",
            is_active=True,
        )

        with self.assertRaises(MeiLinkError) as exc:
            create_or_link_mei_by_email(
                company=self.company,
                full_name="MEI Vinculado",
                mei_email="mei.vinculado@example.com",
                contract_payload={"hourly_rate": "110.00"},
            )

        self.assertEqual(exc.exception.code, "already_linked_company")

    def test_email_from_company_account_is_blocked(self):
        conflicting_user = User.objects.create_user(
            username="conta.empresa@example.com",
            email="conta.empresa@example.com",
            password="Empresa@12345",
            role=User.Role.EMPRESA,
        )

        with self.assertRaises(MeiLinkError) as exc:
            create_or_link_mei_by_email(
                company=self.company,
                full_name="MEI Conflito",
                mei_email=conflicting_user.email,
                contract_payload={"hourly_rate": "100.00"},
            )

        self.assertEqual(exc.exception.code, "email_role_conflict")


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiMultiCompanyContextTests(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(
            username="owner-a@example.com",
            email="owner-a@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.owner_b = User.objects.create_user(
            username="owner-b@example.com",
            email="owner-b@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company_a = Company.objects.create(name="Empresa A", owner=self.owner_a, email="a@example.com")
        self.company_b = Company.objects.create(name="Empresa B", owner=self.owner_b, email="b@example.com")

        self.mei_user = User.objects.create_user(
            username="mei.multi@example.com",
            email="mei.multi@example.com",
            password="Senha@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.employee_a = Employee.objects.create(
            user=self.mei_user,
            company=self.company_a,
            full_name="MEI Multi A",
            is_active=True,
        )
        self.employee_b = Employee.objects.create(
            user=self.mei_user,
            company=self.company_b,
            full_name="MEI Multi B",
            is_active=True,
        )
        self.contract_a = Contract.objects.create(
            employee=self.employee_a,
            company=self.company_a,
            hourly_rate="80.00",
            start_date=timezone.localdate() - timedelta(days=10),
            is_active=True,
        )
        self.contract_b = Contract.objects.create(
            employee=self.employee_b,
            company=self.company_b,
            hourly_rate="120.00",
            start_date=timezone.localdate() - timedelta(days=5),
            is_active=True,
        )
        self.owner_b_company_admin = User.objects.create_user(
            username="owner-b-admin@example.com",
            email="owner-b-admin@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.other_company = Company.objects.create(
            name="Empresa C",
            owner=self.owner_b_company_admin,
            email="c@example.com",
        )
        self.other_employee = Employee.objects.create(
            user=self.mei_user,
            company=self.other_company,
            full_name="MEI Multi C",
            is_active=True,
        )
        self.other_contract = Contract.objects.create(
            employee=self.other_employee,
            company=self.other_company,
            hourly_rate="140.00",
            start_date=timezone.localdate() - timedelta(days=3),
            is_active=True,
        )
        self.client.force_login(self.mei_user)

    def test_mei_panel_persists_selected_contract_in_session(self):
        response_selected = self.client.get(reverse("mei_panel"), {"contract": str(self.contract_a.id)})
        self.assertEqual(response_selected.status_code, 200)
        self.assertEqual(response_selected.context["selected_contract"].id, self.contract_a.id)

        response_followup = self.client.get(reverse("mei_panel"))
        self.assertEqual(response_followup.status_code, 200)
        self.assertEqual(response_followup.context["selected_contract"].id, self.contract_a.id)

    def test_mei_history_isolated_by_selected_contract(self):
        now = timezone.now()
        Punch.objects.create(contract=self.contract_a, timestamp=now - timedelta(hours=6))
        Punch.objects.create(contract=self.contract_a, timestamp=now - timedelta(hours=5))
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=4))
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=3))
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=2))
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=1))

        response_a = self.client.get(reverse("mei_history"), {"contract": str(self.contract_a.id)})
        response_b = self.client.get(reverse("mei_history"), {"contract": str(self.contract_b.id)})

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(response_a.context["summary_total_punches"], 2)
        self.assertEqual(response_b.context["summary_total_punches"], 4)

    def test_mei_reports_and_requests_follow_selected_contract(self):
        ServiceReport.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            report_date=timezone.localdate(),
            title="Relatorio A",
            description="Servico na empresa A",
        )
        ServiceReport.objects.create(
            company=self.company_b,
            employee=self.employee_b,
            contract=self.contract_b,
            report_date=timezone.localdate(),
            title="Relatorio B",
            description="Servico na empresa B",
        )
        ActivityReportRequest.objects.create(
            company=self.company_a,
            employee=self.employee_a,
            contract=self.contract_a,
            requested_by=self.owner_a,
            subject="Req A",
            instruction="Instrucao A",
        )
        ActivityReportRequest.objects.create(
            company=self.company_b,
            employee=self.employee_b,
            contract=self.contract_b,
            requested_by=self.owner_b,
            subject="Req B",
            instruction="Instrucao B",
        )

        response_a = self.client.get(reverse("mei_reports"), {"contract": str(self.contract_a.id)})
        response_b = self.client.get(reverse("mei_reports"), {"contract": str(self.contract_b.id)})

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertTrue(all(item.contract_id == self.contract_a.id for item in response_a.context["reports"]))
        self.assertTrue(all(item.contract_id == self.contract_b.id for item in response_b.context["reports"]))
        self.assertTrue(all(item.contract_id == self.contract_a.id for item in response_a.context["pending_requests"]))
        self.assertTrue(all(item.contract_id == self.contract_b.id for item in response_b.context["pending_requests"]))

    def test_mei_profile_updates_selected_contract_employee(self):
        response = self.client.post(
            reverse("mei_profile"),
            {
                "selected_contract": str(self.contract_b.id),
                "full_name": "MEI Atualizado B",
                "document": self.employee_b.document,
                "phone": self.employee_b.phone,
                "address": self.employee_b.address,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.employee_a.refresh_from_db()
        self.employee_b.refresh_from_db()
        self.assertEqual(self.employee_b.full_name, "MEI Atualizado B")
        self.assertNotEqual(self.employee_a.full_name, "MEI Atualizado B")

    def test_header_company_name_follows_selected_contract(self):
        response = self.client.get(reverse("mei_reports"), {"contract": str(self.contract_b.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["header_company_name"], self.company_b.name)

    def test_employee_dashboard_warns_and_falls_back_when_session_contract_invalid(self):
        session = self.client.session
        session[MEI_SELECTED_CONTRACT_SESSION_KEY] = str(uuid4())
        session.save()

        response = self.client.get(reverse("employee_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["selected_contract"] is not None)
        self.assertTrue(response.context["context_warning"])

    def test_export_csv_uses_session_selected_contract_when_contract_query_missing(self):
        self.client.get(reverse("mei_panel"), {"contract": str(self.contract_b.id)})
        now = timezone.now()
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=2))
        Punch.objects.create(contract=self.contract_b, timestamp=now - timedelta(hours=1))

        response = self.client.get(reverse("export_csv"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn(self.company_b.name, content)
        self.assertNotIn(self.company_a.name, content)

    def test_export_csv_blocks_invalid_requested_contract(self):
        response = self.client.get(reverse("export_csv"), {"contract": str(uuid4())})
        self.assertEqual(response.status_code, 400)

    def test_company_cannot_access_other_company_mei_profile(self):
        self.client.force_login(self.owner_a)
        response = self.client.get(reverse("company_mei_profile", args=[self.employee_b.id]))
        self.assertEqual(response.status_code, 404)


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class CompanyAttendanceReliabilityTests(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(
            username="reliability-owner-a@example.com",
            email="reliability-owner-a@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.owner_b = User.objects.create_user(
            username="reliability-owner-b@example.com",
            email="reliability-owner-b@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company_a = Company.objects.create(
            name="Empresa Confiavel A",
            owner=self.owner_a,
            email="confiavel-a@example.com",
        )
        self.company_b = Company.objects.create(
            name="Empresa Confiavel B",
            owner=self.owner_b,
            email="confiavel-b@example.com",
        )
        self.location_b = CompanyAuthorizedLocation.objects.create(
            company=self.company_b,
            name="Filial B",
            address_or_description="Rua B",
            latitude="-23.550520",
            longitude="-46.633308",
            allowed_radius_m=120,
            is_active=True,
        )

    def test_page_load_creates_policy_for_company(self):
        self.client.force_login(self.owner_a)
        response = self.client.get(reverse("company_attendance_reliability"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CompanyAttendancePolicy.objects.filter(company=self.company_a).exists())

    def test_save_policy_free_mode_disables_location_and_qr_flags(self):
        self.client.force_login(self.owner_a)
        policy = CompanyAttendancePolicy.objects.create(
            company=self.company_a,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            require_qr=True,
            qr_requirement=CompanyAttendancePolicy.QrRequirement.FIRST_PUNCH,
            default_allowed_radius_m=150,
        )

        response = self.client.post(
            reverse("company_attendance_reliability"),
            {
                "action": "save_policy",
                "validation_mode": CompanyAttendancePolicy.ValidationMode.FREE,
                "require_location": "on",
                "require_qr": "on",
                "qr_requirement": CompanyAttendancePolicy.QrRequirement.FIRST_AND_LAST,
                "default_allowed_radius_m": "120",
                "default_location": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        policy.refresh_from_db()
        self.assertEqual(policy.validation_mode, CompanyAttendancePolicy.ValidationMode.FREE)
        self.assertFalse(policy.require_location)
        self.assertFalse(policy.require_qr)
        self.assertEqual(policy.qr_requirement, CompanyAttendancePolicy.QrRequirement.NONE)

    def test_create_location_attaches_to_logged_company(self):
        self.client.force_login(self.owner_a)

        response = self.client.post(
            reverse("company_attendance_reliability"),
            {
                "action": "save_location",
                "name": "Matriz A",
                "address_or_description": "Rua A, 100",
                "latitude": "-23.559000",
                "longitude": "-46.660000",
                "allowed_radius_m": "180",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = CompanyAuthorizedLocation.objects.get(name="Matriz A")
        self.assertEqual(created.company_id, self.company_a.id)
        self.assertTrue(created.is_active)

    def test_save_location_rejects_foreign_location_id(self):
        self.client.force_login(self.owner_a)
        response = self.client.post(
            reverse("company_attendance_reliability"),
            {
                "action": "save_location",
                "location_id": str(self.location_b.id),
                "name": "Tentativa indevida",
                "address_or_description": "Nao deve salvar",
                "latitude": "-23.550520",
                "longitude": "-46.633308",
                "allowed_radius_m": "120",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Local informado nao pertence a sua empresa.", status_code=400)
        self.assertFalse(CompanyAuthorizedLocation.objects.filter(company=self.company_a, name="Tentativa indevida").exists())
        self.location_b.refresh_from_db()
        self.assertEqual(self.location_b.name, "Filial B")

    def test_toggle_location_rejects_foreign_location_id(self):
        self.client.force_login(self.owner_a)
        response = self.client.post(
            reverse("company_attendance_reliability"),
            {
                "action": "toggle_location",
                "location_id": str(self.location_b.id),
            },
        )

        self.assertEqual(response.status_code, 404)


class CompanyAttendanceReliabilityFormUxTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="reliability-forms-owner@example.com",
            email="reliability-forms-owner@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Empresa Form UX",
            owner=self.owner,
            email="empresa-form-ux@example.com",
        )

    def test_location_form_accepts_comma_coordinates_and_rounds(self):
        form = CompanyAuthorizedLocationForm(
            data={
                "name": "Unidade Centro",
                "address_or_description": "Rua 1",
                "latitude": "-23,5505204",
                "longitude": "-46,6333078",
                "allowed_radius_m": "100",
                "is_active": "on",
            },
            instance=CompanyAuthorizedLocation(company=self.company),
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(str(form.cleaned_data["latitude"]), "-23.550520")
        self.assertEqual(str(form.cleaned_data["longitude"]), "-46.633308")

    def test_location_form_rejects_too_tight_radius(self):
        form = CompanyAuthorizedLocationForm(
            data={
                "name": "Unidade Centro",
                "address_or_description": "Rua 1",
                "latitude": "-23.550520",
                "longitude": "-46.633308",
                "allowed_radius_m": "5",
                "is_active": "on",
            },
            instance=CompanyAuthorizedLocation(company=self.company),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("allowed_radius_m", form.errors)

    def test_policy_form_presential_qr_enforces_location_and_qr(self):
        policy = CompanyAttendancePolicy(company=self.company)
        form = CompanyAttendancePolicyForm(
            data={
                "validation_mode": CompanyAttendancePolicy.ValidationMode.PRESENTIAL_QR,
                "default_allowed_radius_m": "100",
                "default_location": "",
                "qr_requirement": CompanyAttendancePolicy.QrRequirement.FIRST_PUNCH,
            },
            instance=policy,
            company=self.company,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertTrue(form.cleaned_data["require_location"])
        self.assertTrue(form.cleaned_data["require_qr"])
