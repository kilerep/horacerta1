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

    def test_company_user_has_no_mei_bottom_nav(self):
        owner = User.objects.create_user(username="empresa-shell@example.com", email="empresa-shell@example.com",
                                         password="Teste@12345", role=User.Role.EMPRESA)
        Company.objects.create(owner=owner, name="Empresa Shell", email="empresa-shell@example.com")
        self.client.force_login(owner)

        html = self.client.get(reverse("dashboard_empresa"), follow=True).content.decode()

        self.assertNotIn('class="bottom-nav"', html)
        self.assertIn('class="hc-icon"', html)


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
        self.assertIn(f'href="{reverse("service_job_create")}"', html)
        self.assertIn("Serviço rápido", html)

    def test_no_duplicate_stat_wall_or_eyebrow(self):
        html = self.client.get(reverse("mei_panel")).content.decode()

        self.assertNotIn("summary-cards", html)
        self.assertNotIn("Visão do profissional", html)
        self.assertNotIn("Clientes vinculados", html)
        self.assertEqual(html.count("<h1"), 1)
