"""Aba Servicos: navegacao unica Pedidos | Servicos | Mais e vocabulario do fluxo
Pedido -> Orcamento -> Servico -> Relatorio (a "previa" passa a se chamar orcamento)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob, ServiceRequest
from timeclock.models import Contract


def make_mei(email):
    user = User.objects.create_user(username=email, email=email, password="x-Senha-123456", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name=f"Cliente {email}")
    employee = Employee.objects.create(user=user, company=company, full_name=email, is_active=True)
    contract = Contract.objects.create(
        company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
    )
    return user, company, contract


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ServicesNavigationTests(TestCase):
    def setUp(self):
        self.user, self.company, self.contract = make_mei("nav@example.com")
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)

    def _request(self, status, user=None, contract=None, company=None):
        user = user or self.user
        return ServiceRequest.objects.create(
            professional=user, contract=contract or self.contract, client=company or self.company,
            client_name="Cliente", category=self.category, title=f"Pedido {status}", description="d", status=status,
        )

    def _nav(self, url_name):
        html = self.client.get(reverse(url_name)).content.decode()
        start = html.index('id="services-nav"')
        return html[start: html.index("</nav>", start)]

    def test_the_four_index_pages_share_the_same_navigation(self):
        for url_name, active in (
            ("service_job_list", "Serviços"),
            ("service_request_list", "Pedidos"),
            ("service_item_catalog_list", "Mais"),
            ("service_event_proposal_list", "Mais"),
        ):
            with self.subTest(page=url_name):
                nav = self._nav(url_name)
                self.assertIn(">Pedidos", nav)
                self.assertIn(">Serviços</a>", nav)
                self.assertIn("Catálogo de itens", nav)
                self.assertIn("Propostas de evento", nav)

    def test_the_current_section_is_marked(self):
        self.assertIn('aria-current="page"', self._nav("service_request_list"))
        self.assertIn("is-active", self._nav("service_job_list"))
        self.assertIn('class="sn-more is-active"', self._nav("service_item_catalog_list"))
        self.assertNotIn('class="sn-more is-active"', self._nav("service_job_list"))

    def test_orders_badge_counts_only_requests_that_need_the_provider(self):
        for status in (ServiceRequest.Status.NEW, ServiceRequest.Status.WAITING_INFO, ServiceRequest.Status.IN_REVIEW):
            self._request(status)
        for status in (ServiceRequest.Status.CONVERTED, ServiceRequest.Status.REJECTED, ServiceRequest.Status.ARCHIVED):
            self._request(status)

        nav = self._nav("service_job_list")

        self.assertIn('<span class="sn-badge" aria-label="3 pedidos para atender">3</span>', nav)

    def test_no_badge_when_nothing_is_waiting_and_other_providers_are_not_counted(self):
        other, other_company, other_contract = make_mei("outro-nav@example.com")
        self._request(ServiceRequest.Status.NEW, user=other, contract=other_contract, company=other_company)

        self.assertNotIn('<span class="sn-badge"', self._nav("service_job_list"))

    def test_single_order_uses_the_singular(self):
        self._request(ServiceRequest.Status.NEW)

        self.assertIn('aria-label="1 pedido para atender"', self._nav("service_job_list"))

    def test_catalog_and_proposals_are_not_competing_quick_cards_anymore(self):
        html = self.client.get(reverse("service_job_list")).content.decode()

        self.assertEqual(html.count('class="quick-card primary"'), 2)
        self.assertNotIn('class="quick-card muted"', html)

    def test_flow_hint_names_the_whole_flow(self):
        html = self.client.get(reverse("service_job_list")).content.decode()

        for word in ("pedido", "orçamento", "serviço", "relatório"):
            self.assertIn(f"<strong>{word}</strong>", html)

    def test_tour_explains_the_navigation_first(self):
        html = self.client.get(reverse("service_job_list")).content.decode()

        self.assertLess(html.index('selector: "#services-nav"'), html.index('selector: "#services-quick-actions"'))


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class BudgetVocabularyTests(TestCase):
    def setUp(self):
        self.user, self.company, self.contract = make_mei("vocab@example.com")
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)
        self.job = ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=self.category, title="Servico vocab",
            status=ServiceJob.Status.PLANNED, billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("50.00"),
        )
        ServiceItemExpense.objects.create(
            service_job=self.job, type=ServiceItemExpense.ItemType.MATERIAL, name="Item", unit=ServiceItemUnit.UNIT,
            quantity=Decimal("1.00"), unit_value=Decimal("10.00"), usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )

    def test_detail_speaks_orcamento_not_previa(self):
        html = self.client.get(reverse("service_job_detail", args=[self.job.id])).content.decode()

        self.assertIn("Gerar orçamento", html)
        self.assertIn("Orçamento (para o cliente)", html)
        self.assertNotIn("prévia", html.lower())

    def test_generate_message_and_status_use_the_new_word_and_gender(self):
        response = self.client.post(reverse("service_job_preview_generate", args=[self.job.id]), follow=True)

        self.assertContains(response, "Orçamento gerado.")
        self.assertContains(response, "Status: Gerado")
        self.assertContains(response, "Atualizar orçamento")
        self.assertContains(response, "Ver orçamento")
        self.assertNotContains(response, "Prévia")

    def test_whatsapp_text_sent_to_the_client_says_orcamento(self):
        self.client.post(reverse("service_job_preview_generate", args=[self.job.id]))

        response = self.client.get(reverse("service_job_preview_whatsapp", args=[self.job.id]))

        self.assertEqual(response.status_code, 302)
        from urllib.parse import unquote

        text = unquote(response.url)
        self.assertIn("segue o orçamento do serviço combinado", text)
        self.assertIn("Acesse o orçamento:", text)
        self.assertNotIn("prévia", text.lower())

    def test_status_label_after_sending_is_orcamento_enviado(self):
        self.client.post(reverse("service_job_preview_generate", args=[self.job.id]))
        self.job.refresh_from_db()

        self.assertEqual(self.job.get_status_display(), "Orçamento enviado")

    def test_request_message_to_the_client_is_accented_and_uses_the_new_word(self):
        request = ServiceRequest.objects.create(
            professional=self.user, contract=self.contract, client=self.company, client_name="Cliente",
            category=self.category, title="Pedido x", description="d",
        )

        message = request.whatsapp_message

        self.assertIn("Olá, organizei seu pedido", message)
        self.assertIn("montar o orçamento do serviço", message)
        self.assertIn("envio o orçamento para você", message)
        self.assertNotIn("previa", message.lower())


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ServicesNavigationLayoutTests(TestCase):
    def test_more_menu_opens_in_the_flow_and_never_floats_past_the_phone_edge(self):
        user, *_ = make_mei("nav-layout@example.com")
        self.client.force_login(user)

        html = self.client.get(reverse("service_job_list")).content.decode()
        nav = html[html.index('id="services-nav"'): html.index("</nav>", html.index('id="services-nav"'))]

        # Regressao: com position:absolute a lista do "Mais" abria cortada na borda direita no celular.
        self.assertNotIn("position:absolute", nav)
        self.assertIn(".services-nav .sn-more[open]{flex:1 1 100%}", nav)
