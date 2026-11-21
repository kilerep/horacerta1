"""UX dos servicos no celular: o detalhe do servico prioriza o que o prestador usa
(executar, itens), recolhe o secundario (checklist, endereco, mais acoes) e o
formulario de novo servico pede so o essencial primeiro. So layout/copy: a
logica de negocio nao muda."""

from datetime import time
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class ServiceUxLayoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ux-serv@example.com", email="ux-serv@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=self.user, name="Cliente UX")
        employee = Employee.objects.create(user=self.user, company=company, full_name="UX", is_active=True)
        from datetime import date

        self.contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.client.force_login(self.user)

    def _job(self, **extra):
        data = dict(
            professional=self.user, contract=self.contract, category=self.category, title="Servico UX",
            status=ServiceJob.Status.PLANNED, billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("50.00"),
        )
        data.update(extra)
        return ServiceJob.objects.create(**data)

    def _detail(self, job):
        return self.client.get(reverse("service_job_detail", args=[job.id])).content.decode()

    def test_detail_puts_execution_and_items_before_the_checklist(self):
        html = self._detail(self._job())

        positions = [html.index(marker) for marker in (
            "O que fazer agora", "Execução do serviço", "Itens usados e despesas", "Previsto x realizado",
            "Combinado", "Itens previstos", "Checklist do serviço", "Relatório final",
        )]
        self.assertEqual(positions, sorted(positions))

    def test_checklist_is_collapsed_and_reports_how_many_items_are_missing(self):
        html = self._detail(self._job())

        self.assertIn('<details class="health-details">', html)
        self.assertNotIn('<details class="health-details" open', html)
        self.assertIn("data-health-count", html)

    def test_combinado_hides_empty_rows_and_does_not_repeat_the_header(self):
        html = self._detail(self._job())

        self.assertNotIn("Ver endereço e observações", html)
        self.assertNotIn("<span>Ponto de referência</span>", html)
        self.assertNotIn("<span>Hora prevista</span>", html)
        self.assertNotIn("<span>Título</span>", html)

    def test_combinado_shows_only_filled_rows_inside_a_collapsed_block(self):
        html = self._detail(self._job(notes="Levar escada", service_reference="Portão azul"))

        self.assertIn('<details class="more-data">', html)
        self.assertIn("<span>Observações</span><strong>Levar escada</strong>", html)
        self.assertIn("<span>Ponto de referência</span><strong>Portão azul</strong>", html)
        self.assertNotIn("Observacoes", html)

    def test_next_card_shows_two_secondary_actions_and_folds_the_rest(self):
        html = self._detail(self._job())

        card = html[html.index('class="card next-card"'): html.index("Execução do serviço")]
        self.assertIn('<details class="more-actions">', card)
        self.assertIn("Mais ações", card)
        # nada some: as acoes extras continuam no HTML, dentro de "Mais ações"
        self.assertIn("Pedir cotação", card)

    def test_accents_in_detail_and_card(self):
        job = self._job()

        detail = self._detail(job)
        listing = self.client.get(reverse("service_job_list")).content.decode()

        self.assertIn("Relatório final", detail)
        self.assertNotIn("Relatorio final", detail)
        self.assertIn("Previsão:", listing)
        self.assertIn("Próxima ação:", listing)
        self.assertNotIn("Previsao:", listing)

    def test_new_service_form_asks_the_essentials_first(self):
        html = self.client.get(reverse("service_job_create")).content.decode()

        more = html.index('<details class="os-more"')
        self.assertLess(html.index("Cliente do serviço"), html.index("Sobre o serviço"))
        self.assertLess(html.index("Sobre o serviço"), more)
        # valor/hora e obrigatorio no modo por hora: precisa estar FORA do bloco opcional
        self.assertLess(html.index('name="hourly_rate_snapshot"'), more)
        self.assertLess(html.index("Como cobrar"), more)
        for later in ("Local do serviço", "Previsão de atendimento", "Itens previstos"):
            self.assertGreater(html.index(later, more), more)
        self.assertNotIn('<details class="os-more" open', html)
        self.assertIn("Local, data e itens previstos (opcional)", html)

    def test_form_details_open_by_themselves_when_there_are_errors(self):
        response = self.client.post(
            reverse("service_job_create"),
            {"client_mode": "casual", "manual_client_name": "Fulano", "category": str(self.category.id),
             "title": "Servico", "planned_start_time": "10:00", "planned_end_time": "09:00",
             "billing_mode": "HOURLY", "hourly_rate_snapshot": "80", "submit_action": "create"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('<details class="os-more" open', response.content.decode())

    def test_creating_a_service_with_only_the_essentials_still_works(self):
        response = self.client.post(
            reverse("service_job_create"),
            {"client_mode": "casual", "manual_client_name": "Fulano", "category": str(self.category.id),
             "title": "So o essencial", "billing_mode": "HOURLY", "hourly_rate_snapshot": "80",
             "submit_action": "create"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ServiceJob.objects.filter(professional=self.user, title="So o essencial").exists())

    def test_edit_form_keeps_the_details_open(self):
        job = self._job(planned_start_time=time(9, 0))

        html = self.client.get(reverse("service_job_update", args=[job.id])).content.decode()

        self.assertIn('<details class="os-more" open', html)
