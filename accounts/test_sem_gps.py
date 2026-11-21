"""Guarda: o HoraCerta nao coleta nem mostra a localizacao do aparelho.

O GPS foi desativado em 2026-11 a pedido do dono do produto. Os campos antigos
continuam no banco (legado, para nao apagar dados), mas nenhuma tela, script ou
formulario pode voltar a pedir ou exibir localizacao. O QR presencial segue
funcionando porque e um QR code, nao GPS.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract

BASE_DIR = Path(settings.BASE_DIR)
SCAN_DIRS = (BASE_DIR / "templates", BASE_DIR / "static")
SCAN_SUFFIXES = {".html", ".js", ".txt"}


def _project_front_files():
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SCAN_SUFFIXES:
                yield path


class NoGeolocationInFrontendTests(SimpleTestCase):
    def test_no_template_or_static_js_calls_navigator_geolocation(self):
        offenders = []
        for path in _project_front_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "navigator.geolocation" in text or "getCurrentPosition" in text or "watchPosition" in text:
                offenders.append(str(path.relative_to(BASE_DIR)))

        self.assertEqual(offenders, [], "Arquivos voltaram a pedir a localizacao do aparelho.")

    def test_no_template_has_geo_inputs(self):
        offenders = []
        for path in _project_front_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "geo_latitude" in text or "geo_longitude" in text or "hcGeo" in text:
                offenders.append(str(path.relative_to(BASE_DIR)))

        self.assertEqual(offenders, [])


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class NoGeolocationOnScreensTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="semgps@example.com", email="semgps@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO, first_name="Ana",
        )
        company = Company.objects.create(owner=self.user, name="Cliente Sem GPS")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Ana", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("60.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.client.force_login(self.user)

    def test_punch_page_has_no_location_inputs_or_notice(self):
        response = self.client.get(reverse("employee_dashboard"), {"contract": str(self.contract.id)})

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('name="geo_latitude"', html)
        self.assertNotIn('name="geo_longitude"', html)
        self.assertNotIn('name="geo_accuracy_m"', html)
        self.assertNotIn("hcLocationNote", html)
        self.assertNotIn("confere a localização", html)

    def test_client_form_no_longer_offers_location_requirement(self):
        response = self.client.get(reverse("mei_client_create"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "require_location")
        self.assertNotContains(response, "Exigir localização")

    def test_help_page_does_not_talk_about_gps(self):
        response = self.client.get(reverse("help"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "GPS")
