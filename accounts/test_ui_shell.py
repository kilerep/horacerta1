"""Redesign em lotes (2026-10): menu com icones, barra inferior do celular e Meu resumo enxuto."""

import re

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from companies.models import Company

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


class IconTagTests(SimpleTestCase):
    def test_icon_renders_decorative_svg_by_default(self):
        html = Template('{% load hc_icons %}{% icon "clock" %}').render(Context())

        self.assertIn('<svg class="hc-icon"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('stroke="currentColor"', html)

    def test_icon_with_label_is_announced_and_unknown_name_falls_back(self):
        html = Template('{% load hc_icons %}{% icon "nao-existe" 24 "Arquivo" %}').render(Context())

        self.assertIn('role="img" aria-label="Arquivo"', html)
        self.assertIn('width="24"', html)


@override_settings(**BASE)
class ShellTests(TestCase):
    def setUp(self):
        self.mei = User.objects.create_user(username="shell@example.com", email="shell@example.com",
                                            password="Teste@12345", role=User.Role.FUNCIONARIO)

    def test_mei_menu_uses_svg_icons_and_bottom_nav(self):
        self.client.force_login(self.mei)

        html = self.client.get(reverse("mei_panel")).content.decode()
        sidebar = html[html.index('id="appSidebar"'):html.index("</aside>")]

        self.assertNotIn('<div class="icon">', sidebar)
        self.assertGreaterEqual(sidebar.count('class="hc-icon"'), 10)
        self.assertIn('class="bottom-nav"', html)
        nav = html[html.index('class="bottom-nav"'):]
        for label in ("Registrar", "Resumo", "Serviços", "Clientes", "Mais"):
            self.assertIn(label, nav)
        self.assertIn('aria-current="page"', nav[:nav.index("</nav>")])
        self.assertIn("data-open-menu", nav)

    def test_bottom_nav_marks_services_section_as_current(self):
        self.client.force_login(self.mei)

        html = self.client.get(reverse("service_job_list")).content.decode()
        nav = html[html.index('class="bottom-nav"'):]
        nav = nav[:nav.index("</nav>")]

        self.assertRegex(nav, r'is-active" href="%s" aria-current="page"' % reverse("service_job_list"))

@override_settings(**BASE)
class MeuResumoTests(TestCase):
    def setUp(self):
        self.mei = User.objects.create_user(username="resumo2@example.com", email="resumo2@example.com",
                                            password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(self.mei)

    def test_four_key_numbers_and_quick_service_shortcut(self):
        html = self.client.get(reverse("mei_panel")).content.decode()
        numbers = html[html.index('class="rs-numbers"'):html.index("</section>", html.index('class="rs-numbers"'))]

        self.assertEqual(len(re.findall(r'class="rs-number[ "]', numbers)), 4)
        for label in ("Horas hoje", "Na semana", "No mês", "Valor estimado no mês"):
            self.assertIn(label, numbers)
        self.assertIn(f'href="{reverse("service_job_quick")}"', html)
        self.assertIn("Serviço rápido", html)

    def test_no_duplicate_stat_wall_or_eyebrow(self):
        html = self.client.get(reverse("mei_panel")).content.decode()

        self.assertNotIn("summary-cards", html)
        self.assertNotIn("Visão do profissional", html)
        self.assertNotIn("Clientes vinculados", html)
        self.assertEqual(html.count("<h1"), 1)


@override_settings(**BASE)
class LotesCETests(TestCase):
    """Lotes C/E: historico compacto, notificacoes sem legenda, filtros recolhidos, ajuda dentro do app."""

    def setUp(self):
        from datetime import date, datetime, time, timedelta
        from decimal import Decimal

        from django.utils import timezone

        from companies.models import Employee
        from timeclock.models import Contract, Punch

        self.mei = User.objects.create_user(username="ce@example.com", email="ce@example.com",
                                            password="Teste@12345", role=User.Role.FUNCIONARIO)
        owner = User.objects.create_user(username="ce-cli@example.com", email="ce-cli@example.com",
                                         password="Teste@12345", role=User.Role.EMPRESA)
        company = Company.objects.create(owner=owner, name="Cliente CE", email="ce-cli@example.com")
        employee = Employee.objects.create(user=self.mei, company=company, full_name="Prestador CE", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2026, 1, 1), is_active=True)
        today = timezone.localdate()
        start = timezone.make_aware(datetime.combine(today, time(8, 0)))
        Punch.objects.create(contract=self.contract, timestamp=start)
        Punch.objects.create(contract=self.contract, timestamp=start + timedelta(hours=3))
        self.client.force_login(self.mei)

    def test_history_shows_compact_rows_and_folds_empty_days(self):
        html = self.client.get(reverse("mei_history")).content.decode()
        cards = html[html.index('aria-label="Histórico diário"'):]

        self.assertEqual(cards.count('class="hx-day"'), 1)
        self.assertIn("03:00", cards)
        self.assertIn("Dias sem registro no período", cards)
        self.assertNotIn('<article class="mei-history__day-card"', html)

    def test_registrar_has_short_client_label_and_three_day_numbers(self):
        html = self.client.get(reverse("employee_dashboard")).content.decode()

        self.assertIn('<label for="hcContractSelect">Cliente</label>', html)
        self.assertNotIn("hcClientCurrentTitle", html)
        self.assertEqual(html.count('class="hc-journey-card"'), 3)
        self.assertIn("<title>Registrar horário | HoraCerta</title>", html)

    def test_notifications_without_legend_and_reports_filters_folded(self):
        notifications = self.client.get(reverse("mei_notifications")).content.decode()
        reports = self.client.get(reverse("mei_reports")).content.decode()
        filtered = self.client.get(reverse("mei_reports"), {"q": "x"}).content.decode()

        self.assertNotIn("O que aparece aqui", notifications)
        self.assertIn("Todos os avisos", notifications)
        self.assertIn('<details class="reports-panel reports-filter">', reports)
        self.assertIn('<details class="reports-panel reports-filter" open>', filtered)
        self.assertNotIn("Espaço reservado", reports)

    def test_help_opens_inside_the_app_when_logged_in(self):
        html = self.client.get(reverse("help")).content.decode()

        self.assertIn('id="appSidebar"', html)
        self.assertIn("Voltar ao meu resumo", html)
        self.assertNotIn("Entrar no sistema", html)
        self.assertLess(html.index("Buscar uma dúvida"), html.index("Por onde começar"))

    def test_help_stays_public_for_visitors(self):
        self.client.logout()

        html = self.client.get(reverse("help")).content.decode()

        self.assertNotIn('id="appSidebar"', html)
        self.assertIn("Entrar no HoraCerta", html)
        self.assertIn("Criar conta", html)
