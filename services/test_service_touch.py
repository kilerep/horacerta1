"""Servicos no celular: alvos de toque de 44px, texto >= 12px, campos com rotulo e
formularios de edicao recolhidos. Guardas de regressao (leem CSS/templates e a pagina)."""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob
from timeclock.models import Contract

BASE = Path(settings.BASE_DIR)


def read(rel):
    return (BASE / rel).read_text(encoding="utf-8")


class StaticSizesTests(SimpleTestCase):
    def test_global_buttons_and_fields_are_at_least_44px_tall(self):
        css = read("static/css/ui_system.css")

        self.assertRegex(css, r"min-height:\s*44px;\s*padding:\s*0 14px")
        self.assertRegex(css, r"min-height:\s*44px;\s*padding:\s*10px 12px")
        self.assertNotRegex(css, r"min-height:\s*42px;\s*padding:\s*(0 14px|10px 12px)")

    def test_menu_button_and_tour_buttons_are_44px(self):
        shell = read("static/css/app_shell.css")
        tour = read("static/js/product_tour.js")

        self.assertRegex(shell, r"width:\s*44px;\s*height:\s*44px;\s*border-radius:\s*12px")
        self.assertIn("min-height:44px", tour)

    def test_no_text_below_12px_in_services_templates(self):
        for path in (BASE / "templates/services").glob("*.html"):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"font-size:\s*11px", path.name)

    def test_no_short_touch_targets_declared_in_services_templates(self):
        for path in (BASE / "templates/services").glob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"min-height:\s*(34|36)px", path.name)

    def test_filter_chips_and_tour_link_are_touch_sized(self):
        job_list = read("templates/services/service_job_list.html")
        requests = read("templates/services/service_request_list.html")

        self.assertRegex(job_list, r"\.chip\{[^}]*min-height:44px")
        self.assertRegex(job_list, r"\.link-button\{[^}]*min-height:44px")
        self.assertRegex(requests, r"\.request-chip\{[^}]*min-height:44px")
        self.assertRegex(read("templates/services/service_job_health_panel.html"), r"\.calendar-action\{[^}]*min-height:44px")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class FormsAreLabelledAndFoldedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="toque@example.com", email="toque@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=self.user, name="Cliente Toque")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Toque", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)

    def _job_with_item(self):
        job = ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=self.category, title="Servico toque",
            status=ServiceJob.Status.PLANNED, billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("50.00"),
        )
        item = ServiceItemExpense.objects.create(
            service_job=job, type=ServiceItemExpense.ItemType.MATERIAL, name="Cabo", unit=ServiceItemUnit.UNIT,
            quantity=Decimal("2.00"), unit_value=Decimal("10.00"), usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        return job, item

    def test_planned_item_controls_in_the_new_service_form_have_accessible_names(self):
        html = self.client.get(reverse("service_job_create")).content.decode()

        for name in ("planned_item_name", "planned_item_type", "planned_item_unit", "planned_item_quantity",
                     "planned_item_unit_value", "planned_item_description"):
            tag = re.search(r"<(?:input|select)[^>]*name=\"%s\"[^>]*>" % name, html).group(0)
            self.assertIn("aria-label=", tag, name)
        self.assertRegex(html, r"<input[^>]*data-catalog-search[^>]*aria-label=")

    def test_item_card_edit_form_is_folded_and_every_field_has_a_real_label(self):
        job, item = self._job_with_item()

        html = self.client.get(reverse("service_job_detail", args=[job.id])).content.decode()

        self.assertIn('<details class="item-edit">', html)
        self.assertNotIn('<details class="item-edit" open', html)
        for field, suffix in (("quantity", "quantity"), ("unit_value", "unit-value"), ("unit", "unit"), ("usage_status", "status")):
            dom_id = f"item-{item.id}-{suffix}"
            self.assertIn(f'<label for="{dom_id}">', html, field)
            self.assertRegex(html, r'id="%s"[^>]*name="%s"' % (dom_id, field))

    def test_item_edit_still_posts_to_the_same_endpoint(self):
        job, item = self._job_with_item()

        html = self.client.get(reverse("service_job_detail", args=[job.id])).content.decode()

        self.assertIn(f'action="{reverse("service_item_expense_update", args=[job.id, item.id])}"', html)

    def test_checkbox_fields_get_a_touch_sized_row(self):
        job, _item = self._job_with_item()

        html = self.client.get(reverse("service_job_detail", args=[job.id])).content.decode()

        self.assertIn(".field:has(>input[type=checkbox])", html)
        self.assertIn("min-height:44px", html[html.index(".field:has(>input[type=checkbox])"):][:200])
        # o proprio rotulo (a area que recebe o toque) tambem ocupa a linha de 44px
        self.assertIn(".field:has(>input[type=checkbox]) label{margin:0;flex:1;display:flex;align-items:center;min-height:44px}", html)


class ChoiceRowsAreTouchSizedTests(SimpleTestCase):
    def test_client_mode_choices_and_checkbox_lines_are_44px(self):
        for name in ("service_job_form.html", "service_request_form.html"):
            text = read(f"templates/services/{name}")
            self.assertRegex(text, r"\.client-mode label\{[^}]*min-height:44px", name)
        self.assertIn(".rq-field label:has(input[type=checkbox]){display:flex;align-items:center;gap:10px;min-height:44px}",
                      read("templates/services/service_request_form.html"))
        self.assertIn(".checkbox-line{display:flex;align-items:center;gap:10px;min-height:44px}",
                      read("templates/services/service_item_catalog_list.html"))

    def test_catalog_options_checkboxes_in_the_new_service_form_are_44px(self):
        self.assertRegex(read("templates/services/service_job_form.html"), r"\.catalog-options label\{[^}]*min-height:44px")


class ThemeAwareColorsTests(SimpleTestCase):
    def test_event_proposal_notices_use_theme_tokens_not_fixed_pale_colors(self):
        text = read("templates/services/service_event_proposal.html")

        # No tema claro o texto pale (#ffe7ad / #dcffe9) ficava ilegivel (contraste 1,1:1).
        self.assertNotIn("#ffe7ad", text)
        self.assertNotIn("#dcffe9", text)
        self.assertIn("color:var(--warning-text)", text)
        self.assertIn("color:var(--success-text)", text)

    def test_every_theme_defines_the_notice_tokens(self):
        css = read("static/css/design_tokens.css")

        for token in ("--warning-text", "--warning-bg", "--warning-border", "--success-text", "--success-bg", "--success-border"):
            self.assertEqual(css.count(token + ":"), 5, token)  # 5 temas visuais

    def test_proposal_list_has_no_decorative_side_stripe(self):
        self.assertNotIn("border-left:3px", read("templates/services/service_event_proposal_list.html"))
