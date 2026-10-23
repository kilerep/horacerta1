"""Acabamento da lista de servicos (lote 5): cada servico aparece uma vez so, o tour
nao abre sozinho por cima da tela, CEP sem alert() nativo e textos acentuados."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract


def section(html, marker, end_marker):
    start = html.index(marker)
    return html[start:html.index(end_marker, start)]


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ServiceListShowsEachJobOnceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="lista@example.com", email="lista@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=self.user, name="Cliente Lista")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Lista", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)

    def _job(self, title, status, **extra):
        return ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=self.category, title=title, status=status,
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("50.00"), **extra,
        )

    def test_today_pending_and_others_do_not_repeat(self):
        self._job("Troca de chuveiro hoje", ServiceJob.Status.PLANNED, start_date=timezone.localdate())
        self._job("Orcar quadro novo", ServiceJob.Status.DRAFT)
        self._job("Servico ja entregue", ServiceJob.Status.REPORT_SENT)

        html = self.client.get(reverse("service_job_list")).content.decode()
        today = section(html, 'id="services-today"', "</section>")
        pending = section(html, 'id="services-pending"', "</section>")
        others = html[html.index("Outros serviços"):]

        self.assertIn("Troca de chuveiro hoje", today)
        self.assertNotIn("Troca de chuveiro hoje", pending)
        self.assertNotIn("Troca de chuveiro hoje", others)
        self.assertIn("Orcar quadro novo", pending)
        self.assertNotIn("Orcar quadro novo", others)
        self.assertIn("Servico ja entregue", others)

    def test_search_still_lists_everything_that_matches(self):
        self._job("Chuveiro A", ServiceJob.Status.DRAFT)

        html = self.client.get(reverse("service_job_list"), {"q": "Chuveiro"}).content.decode()

        self.assertIn("Resultado da busca", html)
        self.assertIn("Chuveiro A", html)

    def test_quick_filter_label_has_accent(self):
        self.assertContains(self.client.get(reverse("service_job_list")), "Em execução")


class FinishingTouchesTests(SimpleTestCase):
    def read(self, rel):
        return (Path(settings.BASE_DIR) / rel).read_text(encoding="utf-8")

    def test_cep_messages_show_inline_instead_of_alert_popups(self):
        form = self.read("templates/services/service_job_form.html")

        self.assertNotIn("alert(", form)
        self.assertIn("data-cep-notice", form)
        self.assertIn('aria-live="polite"', form)

    def test_visible_labels_are_accented(self):
        self.assertEqual(ServiceJob.Status.IN_PROGRESS.label, "Em execução")
        forms_py = self.read("services/forms.py")
        for old in ('"Valor unitario"', '"Observacao"', '"Titulo do servico"'):
            self.assertNotIn(old, forms_py)
