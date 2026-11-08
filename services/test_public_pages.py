"""Paginas publicas de Servicos (o que o CLIENTE FINAL abre, sem conta, no celular).

Regras: sem texto interno do sistema, hierarquia prestador -> total -> quando/onde ->
o que sera feito -> itens -> contato, um unico estilo, pouca informacao pessoal,
sem indexacao em buscadores."""

from datetime import date, time
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob, ServiceWorkLog
from timeclock.models import Contract

INTERNAL_TEXT = (
    "Natureza da folha",
    "Checklist profissional",
    "Logística do atendimento",
    "Presença/GPS",
    "rastreamento contínuo",
    "Conferência e aceite",
    "Folha profissional",
    "ART/RRT",
    "playbook",
    "Link público",
)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class PublicServicePagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="prestador@example.com", email="prestador@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO, first_name="Carlos",
        )
        company = Company.objects.create(owner=self.user, name="Cliente Silva")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Carlos Eletricista", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("80.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")

    def _job(self, **extra):
        data = dict(
            professional=self.user, contract=self.contract, category=self.category, title="Troca de quadro de luz",
            description="Trocar disjuntores e organizar o quadro.", service_street="Rua das Flores", service_number="120",
            service_city="Blumenau", service_state="SC", start_date=date(2026, 10, 20),
            planned_start_time=time(9, 0), planned_end_time=time(12, 0), status=ServiceJob.Status.PLANNED,
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("80.00"),
            preview_generated_at=timezone.now(), manual_client_whatsapp="11999998888",
        )
        data.update(extra)
        job = ServiceJob.objects.create(**data)
        ServiceItemExpense.objects.create(
            service_job=job, type=ServiceItemExpense.ItemType.MATERIAL, name="Disjuntor 20A",
            unit=ServiceItemUnit.UNIT, quantity=Decimal("3.00"), unit_value=Decimal("42.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        return job

    def _preview(self, job):
        return self.client.get(reverse("public_service_job_preview", args=[job.public_token]))

    def test_preview_has_no_internal_text(self):
        html = self._preview(self._job()).content.decode()

        for text in INTERNAL_TEXT:
            self.assertNotIn(text, html, text)

    def test_preview_reads_in_the_right_order_for_a_30_second_decision(self):
        html = self._preview(self._job()).content.decode()

        order = [html.index(marker) for marker in (
            "Carlos Eletricista", "Total estimado do serviço", "Quando e onde", "O que será feito",
            "Itens previstos", "Dúvidas?",
        )]
        self.assertEqual(order, sorted(order))
        self.assertIn("<title>Orçamento - Troca de quadro de luz</title>", html)

    def test_preview_shows_who_for_whom_and_the_honest_estimate_note(self):
        response = self._preview(self._job())

        self.assertContains(response, "De <strong>Carlos Eletricista</strong> para")
        self.assertContains(response, "Valores estimados e sujeitos à confirmação")
        self.assertContains(response, "Disjuntor 20A")
        self.assertContains(response, "A combinar", count=0)  # data, horario e local preenchidos

    def test_preview_fills_unknown_fields_with_a_combinar(self):
        job = self._job(start_date=None, planned_start_time=None, planned_end_time=None,
                        service_street="", service_number="", service_city="", service_state="")

        html = self._preview(job).content.decode()

        self.assertEqual(html.count("A combinar"), 3)

    def test_public_page_does_not_leak_the_clients_own_whatsapp(self):
        html = self._preview(self._job()).content.decode()

        self.assertNotIn("11999998888", html)

    def test_contact_card_offers_an_email_reply_with_a_subject(self):
        html = self._preview(self._job()).content.decode()

        self.assertIn('href="mailto:prestador@example.com?subject=Troca%20de%20quadro%20de%20luz"', html)

    def test_pages_are_not_indexable_and_share_one_style(self):
        job = self._job()
        preview = self._preview(job).content.decode()
        proposal_job = self._job(billing_mode=ServiceJob.BillingMode.FIXED, fixed_labor_value=Decimal("1450.00"))
        proposal = self.client.get(
            reverse("public_service_event_proposal", args=[proposal_job.public_token])
        ).content.decode()

        for html in (preview, proposal):
            self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
            self.assertIn("Estilo unico das paginas publicas de Servicos", html)
            self.assertNotIn("font-family:Arial", html)

    def test_proposal_keeps_fixed_value_without_item_prices_and_shows_the_provider(self):
        job = self._job(billing_mode=ServiceJob.BillingMode.FIXED, fixed_labor_value=Decimal("1450.00"))

        response = self.client.get(reverse("public_service_event_proposal", args=[job.public_token]))

        self.assertContains(response, "Proposta de evento")
        self.assertContains(response, "De <strong>Carlos Eletricista</strong> para")
        self.assertContains(response, "R$ 1.450,00")
        self.assertContains(response, "Valor fechado")
        self.assertNotContains(response, "R$ 42,00")
        html = response.content.decode()
        self.assertLess(html.index("Investimento do pacote"), html.index("Quando e onde"))

    def test_final_report_hides_empty_sections_and_shows_totals_first(self):
        job = self._job(status=ServiceJob.Status.REPORT_SENT)
        item = job.item_expenses.first()
        item.usage_status = ServiceItemExpense.UsageStatus.USED
        item.save()
        ServiceWorkLog.objects.create(
            service_job=job, work_date=date(2026, 10, 20), start_time=time(9, 0), end_time=time(11, 30),
            description="Troca concluida.",
        )

        response = self.client.get(reverse("public_service_job_report", args=[job.public_token]))
        html = response.content.decode()

        self.assertContains(response, "Relatório de serviço")
        self.assertContains(response, "02:30")
        self.assertContains(response, "Disjuntor 20A")
        self.assertNotIn("Não cobrados", html)
        self.assertNotIn("Nenhum item", html)
        self.assertLess(html.index("Total do serviço"), html.index("Horas trabalhadas"))
        for text in INTERNAL_TEXT:
            self.assertNotIn(text, html, text)

    def test_final_report_lists_non_charged_items_only_when_there_are_some(self):
        job = self._job(status=ServiceJob.Status.REPORT_SENT)
        item = job.item_expenses.first()
        item.usage_status = ServiceItemExpense.UsageStatus.RETURNED
        item.save()

        response = self.client.get(reverse("public_service_job_report", args=[job.public_token]))

        self.assertContains(response, "Não cobrados")
        self.assertContains(response, "Não entram no total")
