"""Servico rapido: 4 campos criam o servico e levam para a tela dele."""

from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from services.models import ServiceJob
from services.quick import parse_brl

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


class ParseBrlTests(SimpleTestCase):
    def test_brazilian_ways_of_writing_money(self):
        for text, value in (("150", "150.00"), ("150,5", "150.50"), ("1.500,00", "1500.00"), ("R$ 89,90", "89.90"),
                            ("1.500", "1500.00"), ("2500.75", "2500.75"), ("", None), ("  ", None)):
            with self.subTest(text=text):
                self.assertEqual(parse_brl(text), Decimal(value) if value else None)

    def test_rejects_garbage(self):
        with self.assertRaises(forms.ValidationError):
            parse_brl("1,2,3")


@override_settings(**BASE)
class QuickServiceViewTests(TestCase):
    def setUp(self):
        self.mei = User.objects.create_user(username="rapido@example.com", email="rapido@example.com",
                                            password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(self.mei)
        self.url = reverse("service_job_quick")

    def test_four_fields_create_a_planned_service_and_open_it(self):
        response = self.client.post(self.url, {
            "client_name": "  Dona   Maria ", "client_whatsapp": "(11) 98888-7777",
            "title": "Trocar chuveiro", "price": "150,00", "start_date": "2026-10-24",
        })

        job = ServiceJob.objects.get(professional=self.mei)
        self.assertRedirects(response, reverse("service_job_detail", args=[job.id]), fetch_redirect_response=False)
        self.assertEqual(job.manual_client_name, "Dona Maria")
        self.assertEqual(job.manual_client_whatsapp, "11988887777")
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.FIXED)
        self.assertEqual(job.fixed_labor_value, Decimal("150.00"))
        self.assertEqual(job.start_date, date(2026, 10, 24))
        self.assertEqual(job.category.slug, "servico-geral")
        self.assertIn(job.status, (ServiceJob.Status.PLANNED, ServiceJob.Status.DRAFT))

    def test_without_price_the_value_stays_open(self):
        self.client.post(self.url, {"client_name": "João", "title": "Orçar reforma"})

        job = ServiceJob.objects.get(professional=self.mei)
        self.assertEqual(job.billing_mode, ServiceJob.BillingMode.UNDEFINED)
        self.assertIsNone(job.fixed_labor_value)

    def test_validation_messages_in_plain_portuguese(self):
        response = self.client.post(self.url, {"client_name": " ", "title": "", "client_whatsapp": "123", "price": "abc,1,2"})

        self.assertContains(response, "Informe o nome do cliente.")
        self.assertContains(response, "Diga em poucas palavras o que vai ser feito.")
        self.assertContains(response, "Use o número com DDD")
        self.assertContains(response, "Digite o valor como 150 ou 150,50.")
        self.assertFalse(ServiceJob.objects.exists())

    def test_page_prefills_today_and_links_to_full_form(self):
        html = self.client.get(self.url).content.decode()

        self.assertIn('type="date"', html)
        self.assertIn(reverse("service_job_create"), html)
        self.assertIn("Criar serviço", html)

    def test_shortcuts_point_to_quick_service(self):
        panel = self.client.get(reverse("mei_panel")).content.decode()
        jobs = self.client.get(reverse("service_job_list")).content.decode()

        self.assertIn(f'href="{self.url}"', panel)
        self.assertIn(f'href="{self.url}"', jobs)

    def test_company_user_is_sent_away(self):
        owner = User.objects.create_user(username="emp-rapido@example.com", email="emp-rapido@example.com",
                                         password="Teste@12345", role=User.Role.EMPRESA)
        self.client.force_login(owner)

        response = self.client.post(self.url, {"client_name": "X", "title": "Y"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServiceJob.objects.exists())

    def test_login_required(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.url).status_code, 302)
