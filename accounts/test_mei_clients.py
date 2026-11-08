from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, Punch


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiClientsPageTests(TestCase):
    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="mei-clientes@example.com",
            email="mei-clientes@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        owner = User.objects.create_user(
            username="owner-clientes@example.com",
            email="owner-clientes@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.company = Company.objects.create(
            name="Cliente de Teste",
            owner=owner,
            email="cliente-teste@example.com",
        )
        employee = Employee.objects.create(
            user=self.mei_user,
            company=self.company,
            full_name="Prestador de Teste",
            is_active=True,
        )
        self.contract = Contract.objects.create(
            employee=employee,
            company=self.company,
            hourly_rate=Decimal("75.00"),
            start_date=timezone.localdate() - timedelta(days=7),
            is_active=True,
        )
        Punch.objects.create(contract=self.contract, timestamp=timezone.now() - timedelta(hours=2))
        Punch.objects.create(contract=self.contract, timestamp=timezone.now() - timedelta(hours=1))

    def test_mei_clients_page_exposes_search_filters_and_client_summary(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_contract"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.company.name)
        self.assertContains(response, 'data-client-filter-form')
        self.assertContains(response, 'data-client-search')
        self.assertContains(response, 'data-client-status-filter')
        self.assertContains(response, 'data-client-filter-empty')
        self.assertContains(response, 'data-client-details-toggle')
        self.assertContains(response, "Próximo fechamento")

    def test_contract_query_selects_only_the_mei_own_contract(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_contract"), {"contract": self.contract.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_contract"].id, self.contract.id)
        self.assertContains(response, 'aria-expanded="true"')
        self.assertContains(response, "Fechar detalhes")

    def test_mei_cannot_open_another_professionals_client_by_query_parameter(self):
        other_mei = User.objects.create_user(
            username="outro-mei-clientes@example.com",
            email="outro-mei-clientes@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.client.force_login(other_mei)

        response = self.client.get(reverse("mei_contract"), {"contract": self.contract.id})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["active_contract"])
        self.assertNotContains(response, self.company.name)
