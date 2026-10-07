"""Detalhe do servico (prestador, celular): sem repeticao, so o que tem conteudo, e a
separacao clara entre "para o cliente" (previa) e "para a loja" (cotacao)."""

from datetime import date, time
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceItemExpense, ServiceItemUnit, ServiceJob, ServiceWorkLog
from timeclock.models import Contract


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ServiceDetailCleanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="detalhe@example.com", email="detalhe@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=self.user, name="Cliente Detalhe")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Detalhe", is_active=True)
        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)

    def _job(self, **extra):
        data = dict(
            professional=self.user, contract=self.contract, category=self.category, title="Servico limpo",
            status=ServiceJob.Status.PLANNED, billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("50.00"),
        )
        data.update(extra)
        return ServiceJob.objects.create(**data)

    def _item(self, job, status, name="Disjuntor"):
        return ServiceItemExpense.objects.create(
            service_job=job, type=ServiceItemExpense.ItemType.MATERIAL, name=name, unit=ServiceItemUnit.UNIT,
            quantity=Decimal("2.00"), unit_value=Decimal("10.00"), usage_status=status,
        )

    def _html(self, job):
        return self.client.get(reverse("service_job_detail", args=[job.id])).content.decode()

    def test_back_link_is_in_the_header_not_among_the_actions(self):
        html = self._html(self._job())

        head = html[: html.index('class="card next-card"')]
        next_card = html[html.index('class="card next-card"'): html.index('id="execution"')]
        self.assertIn("Voltar para Serviços", head)
        self.assertNotIn("Voltar", next_card)

    def test_new_service_does_not_show_empty_metrics_or_empty_item_lists(self):
        html = self._html(self._job())

        self.assertIn("Nenhum período de trabalho registrado ainda.", html)
        execution = html[html.index('id="execution"'): html.index('id="items"')]
        self.assertNotIn("Períodos</span>", execution)
        self.assertNotIn("Não iniciado", html)
        self.assertIn("Nenhum item registrado ainda.", html)
        for empty in ("Nenhum item pendente", "Nenhum item usado", "Nenhum item não usado"):
            self.assertNotIn(empty, html)

    def test_only_the_item_lists_that_have_content_are_shown(self):
        job = self._job()
        self._item(job, ServiceItemExpense.UsageStatus.USED, name="Cabo usado")

        html = self._html(job)

        self.assertIn("Itens usados/cobrados", html)
        self.assertNotIn("Itens não usados/devolvidos", html)
        self.assertNotIn("Nenhum item registrado ainda.", html)

    def test_work_log_metrics_appear_once_there_is_a_period(self):
        job = self._job()
        ServiceWorkLog.objects.create(
            service_job=job, work_date=timezone.localdate(), start_time=time(9, 0), end_time=time(10, 0)
        )

        html = self._html(job)

        self.assertIn("Períodos</span>", html)
        self.assertIn("Total trabalhado", html)

    def test_numbers_are_not_repeated_across_blocks(self):
        job = self._job(planned_start_time=time(9, 0), planned_end_time=time(11, 0), start_date=date(2026, 10, 20))
        ServiceWorkLog.objects.create(
            service_job=job, work_date=timezone.localdate(), start_time=time(9, 0), end_time=time(10, 0)
        )

        html = self._html(job)

        self.assertEqual(html.count("<span>Horas previstas</span>"), 1)
        self.assertEqual(html.count("<span>Total trabalhado</span>"), 1)
        self.assertEqual(html.count("<span>Status da prévia</span>"), 0)
        self.assertIn("<span>Mão de obra</span>", html)
        self.assertIn("<span>Itens usados</span>", html)

    def test_quote_has_a_single_whatsapp_button_and_preview_is_a_separate_box(self):
        job = self._job()
        self._item(job, ServiceItemExpense.UsageStatus.PLANNED, name="Item cotado")

        html = self._html(job)

        self.assertEqual(html.count("Abrir WhatsApp"), 1)
        self.assertNotIn("WhatsApp cotação", html)
        client_box = html.index('id="send-client"')
        store_box = html.index('id="send-store"')
        self.assertLess(client_box, store_box)
        self.assertIn("Prévia (para o cliente)", html)
        self.assertIn("Cotação oficial (para a loja)", html)
        self.assertLess(html.index("Prévia (para o cliente)"), html.index("Cotação oficial (para a loja)"))

    def test_secondary_client_actions_are_folded(self):
        job = self._job(manual_client_name="Fulano", client=None, contract=None)

        html = self._html(job)

        self.assertIn("Salvar cliente em Meus clientes", html)
        more = html.index("Mais opções do cliente")
        self.assertLess(more, html.index("Salvar cliente em Meus clientes"))
        self.assertEqual(html.count("Editar</a>"), 1)
