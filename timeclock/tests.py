from datetime import date, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, CompanyAttendancePolicy, CompanyAuthorizedLocation, Employee
from timeclock.models import Contract, Punch, ServiceReport
from .models import PunchCorrectionLog
from .services import cancel_punch, compute_day_total, format_hhmm, format_punch_time, restore_punch, build_daily_summary
from .services import evaluate_punch_confidence

User = get_user_model()


class TimeSummaryServicesTests(SimpleTestCase):
    def _local_dt(self, year, month, day, hour, minute, second=0):
        naive = datetime(year, month, day, hour, minute, second)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def test_four_punches_should_total_eight_minutes_and_complete(self):
        punches = [
            self._local_dt(2026, 2, 19, 20, 59),
            self._local_dt(2026, 2, 19, 21, 2),
            self._local_dt(2026, 2, 19, 21, 6),
            self._local_dt(2026, 2, 19, 21, 11),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, 8 * 60)
        self.assertEqual(format_hhmm(total_seconds), "00:08")
        self.assertFalse(is_incomplete)

    def test_three_punches_should_count_first_pair_and_mark_incomplete(self):
        punches = [
            self._local_dt(2026, 2, 19, 9, 0),
            self._local_dt(2026, 2, 19, 9, 45),
            self._local_dt(2026, 2, 19, 10, 30),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, 45 * 60)
        self.assertEqual(format_hhmm(total_seconds), "00:45")
        self.assertTrue(is_incomplete)

    def test_two_punches_should_compute_exact_difference(self):
        punches = [
            self._local_dt(2026, 2, 19, 8, 10),
            self._local_dt(2026, 2, 19, 12, 25),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, (4 * 60 + 15) * 60)
        self.assertEqual(format_hhmm(total_seconds), "04:15")
        self.assertFalse(is_incomplete)

    def test_zero_punches_should_return_zero_time(self):
        total_seconds, is_incomplete = compute_day_total([])
        self.assertEqual(total_seconds, 0)
        self.assertEqual(format_hhmm(total_seconds), "00:00")
        self.assertFalse(is_incomplete)

    def test_format_punch_time_should_hide_seconds(self):
        ts = self._local_dt(2026, 2, 19, 20, 59, 25)
        self.assertEqual(format_punch_time(ts), "20:59")

    def test_build_daily_summary_ignores_cancelled_punches(self):
        day = self._local_dt(2026, 5, 19, 8, 0)
        punches = [
            SimpleNamespace(timestamp=day, is_cancelled=False),
            SimpleNamespace(timestamp=day + timedelta(hours=1), is_cancelled=True),
            SimpleNamespace(timestamp=day + timedelta(hours=2), is_cancelled=False),
        ]

        rows, _columns = build_daily_summary(punches)

        self.assertEqual(rows[0]["punches_count"], 2)
        self.assertEqual(rows[0]["total_hours_hhmm"], "02:00")
        self.assertFalse(rows[0]["is_incomplete"])


class PunchCorrectionServicesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin.correction@example.com",
            email="admin.correction@example.com",
            password="Admin@12345",
            role=User.Role.EMPRESA,
        )
        self.owner = User.objects.create_user(
            username="owner.correction@example.com",
            email="owner.correction@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(name="Empresa Correcao", owner=self.owner, email="correcao@example.com")
        self.mei_user = User.objects.create_user(
            username="mei.correction@example.com",
            email="mei.correction@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.employee = Employee.objects.create(user=self.mei_user, company=self.company, full_name="MEI Correcao")
        self.contract = Contract.objects.create(employee=self.employee, company=self.company, hourly_rate="100.00")
        self.punch = Punch.objects.create(contract=self.contract, timestamp=timezone.now())

    def test_cancel_and_restore_create_logs_and_toggle_active_manager(self):
        cancel_punch(punch=self.punch, admin_user=self.admin, reason="Registro feito por engano.")
        self.punch.refresh_from_db()

        self.assertTrue(self.punch.is_cancelled)
        self.assertFalse(Punch.objects.filter(id=self.punch.id).exists())
        self.assertTrue(Punch.all_objects.filter(id=self.punch.id).exists())
        self.assertEqual(PunchCorrectionLog.objects.filter(punch=self.punch).count(), 1)

        restore_punch(punch=self.punch, admin_user=self.admin, reason="Revertido apos conferencia.")
        self.punch.refresh_from_db()

        self.assertFalse(self.punch.is_cancelled)
        self.assertTrue(Punch.objects.filter(id=self.punch.id).exists())
        self.assertEqual(PunchCorrectionLog.objects.filter(punch=self.punch).count(), 2)


class PunchConfidenceServicesTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner.geo@example.com",
            email="owner.geo@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Empresa Geo",
            owner=self.owner,
            email="empresa.geo@example.com",
        )
        self.mei_user = User.objects.create_user(
            username="mei.geo@example.com",
            email="mei.geo@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.employee = Employee.objects.create(
            user=self.mei_user,
            company=self.company,
            full_name="MEI GEO",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate="100.00",
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.location = CompanyAuthorizedLocation.objects.create(
            company=self.company,
            name="Matriz",
            address_or_description="Rua A",
            latitude="-23.550520",
            longitude="-46.633308",
            allowed_radius_m=120,
            is_active=True,
        )

    def test_geolocation_policy_without_coordinates_classifies_no_location(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
        )

        result = evaluate_punch_confidence(self.contract, latitude=None, longitude=None, accuracy_m=None)

        self.assertEqual(result["validation_method"], "GEOLOCATION")
        self.assertEqual(result["confidence_status"], Punch.ConfidenceStatus.NO_LOCATION)

    def test_geolocation_policy_classifies_on_site_when_within_radius(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
        )

        result = evaluate_punch_confidence(
            self.contract,
            latitude="-23.550520",
            longitude="-46.633308",
            accuracy_m="15",
        )

        self.assertEqual(result["validation_method"], "GEOLOCATION")
        self.assertEqual(result["confidence_status"], Punch.ConfidenceStatus.ON_SITE)
        self.assertIsNotNone(result["distance_to_location_m"])

    def test_geolocation_policy_classifies_out_of_radius_for_far_point(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
        )

        result = evaluate_punch_confidence(
            self.contract,
            latitude="-23.500000",
            longitude="-46.600000",
            accuracy_m="20",
        )

        self.assertEqual(result["validation_method"], "GEOLOCATION")
        self.assertEqual(result["confidence_status"], Punch.ConfidenceStatus.OUT_OF_RADIUS)

    def test_geolocation_policy_classifies_imprecise_when_accuracy_is_high(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
        )

        result = evaluate_punch_confidence(
            self.contract,
            latitude="-23.550520",
            longitude="-46.633308",
            accuracy_m="350",
        )

        self.assertEqual(result["validation_method"], "GEOLOCATION")
        self.assertEqual(result["confidence_status"], Punch.ConfidenceStatus.IMPRECISE)


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class EmployeeDashboardPunchFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner.dashboard.geo@example.com",
            email="owner.dashboard.geo@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Empresa Dashboard Geo",
            owner=self.owner,
            email="empresa.dashboard.geo@example.com",
        )
        self.mei_user = User.objects.create_user(
            username="mei.dashboard.geo@example.com",
            email="mei.dashboard.geo@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.employee = Employee.objects.create(
            user=self.mei_user,
            company=self.company,
            full_name="MEI Dashboard",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            company=self.company,
            hourly_rate="95.00",
            start_date=timezone.localdate(),
            is_active=True,
        )
        self.location = CompanyAuthorizedLocation.objects.create(
            company=self.company,
            name="Sede",
            address_or_description="Av Principal",
            latitude="-23.550520",
            longitude="-46.633308",
            allowed_radius_m=120,
            is_active=True,
        )
        self.client.force_login(self.mei_user)

    def test_post_punch_persists_geolocation_and_confidence_fields(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
            default_location=self.location,
        )

        response = self.client.post(
            f"{reverse('employee_dashboard')}?contract={self.contract.id}",
            {
                "action": "punch",
                "geo_latitude": "-23.550520",
                "geo_longitude": "-46.633308",
                "geo_accuracy_m": "18.2",
            },
        )

        self.assertEqual(response.status_code, 302)
        punch = Punch.objects.get(contract=self.contract)
        self.assertEqual(punch.validation_method, Punch.ValidationMethod.GEOLOCATION)
        self.assertEqual(punch.confidence_status, Punch.ConfidenceStatus.ON_SITE)
        self.assertIsNotNone(punch.geo_latitude)
        self.assertIsNotNone(punch.geo_longitude)
        self.assertIsNotNone(punch.geo_accuracy_m)
        self.assertIsNotNone(punch.distance_to_location_m)
        self.assertIsNotNone(punch.confidence_checked_at)

    def test_post_punch_ignores_invalid_geo_range_and_classifies_no_location(self):
        CompanyAttendancePolicy.objects.create(
            company=self.company,
            validation_mode=CompanyAttendancePolicy.ValidationMode.GEOLOCATION,
            require_location=True,
            default_allowed_radius_m=120,
        )

        response = self.client.post(
            f"{reverse('employee_dashboard')}?contract={self.contract.id}",
            {
                "action": "punch",
                "geo_latitude": "123.999",
                "geo_longitude": "-190",
                "geo_accuracy_m": "-5",
            },
        )

        self.assertEqual(response.status_code, 302)
        punch = Punch.objects.get(contract=self.contract)
        self.assertIsNone(punch.geo_latitude)
        self.assertIsNone(punch.geo_longitude)
        self.assertIsNone(punch.geo_accuracy_m)
        self.assertEqual(punch.validation_method, Punch.ValidationMethod.GEOLOCATION)
        self.assertEqual(punch.confidence_status, Punch.ConfidenceStatus.NO_LOCATION)


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceReportSharingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner.share@example.com",
            email="owner.share@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Ensimec",
            owner=self.owner,
            email="ensimec@example.com",
            whatsapp="+55 (11) 98888-7777",
        )
        self.mei_user = User.objects.create_user(
            username="mei.share@example.com",
            email="mei.share@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.employee = Employee.objects.create(user=self.mei_user, company=self.company, full_name="MEI Share")
        self.contract = Contract.objects.create(employee=self.employee, company=self.company, hourly_rate="10.00")
        self.report = ServiceReport(
            company=self.company,
            employee=self.employee,
            contract=self.contract,
            report_date=date(2026, 6, 15),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 15),
            title="Relatorio de junho",
            summary_payload={
                "company": "Ensimec",
                "period": {"label": "01/06/2026 ate 15/06/2026"},
                "total_hours": "80:30",
                "estimated_value_brl": "R$ 805,00",
            },
        )
        self.report.ensure_conference_link()
        self.report.save()

    def test_whatsapp_redirect_uses_saved_report_snapshot_and_records_attempt(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_service_report_whatsapp", args=[self.report.id]))

        self.assertEqual(response.status_code, 302)
        redirect_url = response["Location"]
        self.assertTrue(redirect_url.startswith("https://wa.me/5511988887777?"))
        parsed = urlparse(redirect_url)
        text = unquote(parse_qs(parsed.query)["text"][0])
        self.assertIn("Cliente: Ensimec", text)
        self.assertIn("Período: 01/06/2026 até 15/06/2026", text)
        self.assertIn("Total de horas: 80:30", text)
        self.assertIn("Valor estimado: R$ 805,00", text)
        self.assertIn(reverse("public_service_report_conference", args=[self.report.conference_token]), text)
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.whatsapp_sent_attempted_at)

    def test_public_link_records_first_view_once(self):
        url = reverse("public_service_report_conference", args=[self.report.conference_token])

        first_response = self.client.get(url)

        self.assertEqual(first_response.status_code, 200)
        self.report.refresh_from_db()
        first_viewed_at = self.report.conference_first_viewed_at
        self.assertIsNotNone(first_viewed_at)
        self.assertEqual(self.report.status, ServiceReport.Status.VIEWED)
        self.assertEqual(self.report.conference_final_status, ServiceReport.ConferenceStatus.VIEWED)

        self.report.conference_first_viewed_at = first_viewed_at - timedelta(days=1)
        self.report.save(update_fields=["conference_first_viewed_at", "updated_at"])
        expected_first_viewed_at = self.report.conference_first_viewed_at

        second_response = self.client.get(url)

        self.assertEqual(second_response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.conference_first_viewed_at, expected_first_viewed_at)
