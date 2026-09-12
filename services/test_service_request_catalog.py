from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from services.models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceItemUnit, ServiceRequest


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class ServiceRequestCatalogSearchTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="catalogo-pedido@example.com",
            email="catalogo-pedido@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.other_professional = User.objects.create_user(
            username="outro-catalogo@example.com",
            email="outro-catalogo@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.category = ServiceCategory.objects.create(
            name="Elétrica",
            slug="eletrica-test",
            description="Serviços elétricos.",
        )
        self.catalog_item = ServiceItemCatalog.objects.create(
            professional=self.professional,
            category=self.category,
            internal_code="MAT-2042",
            item_type=ServiceItemExpense.ItemType.MATERIAL,
            name="Fita isolante profissional",
            description="Rolo de fita isolante.",
            unit=ServiceItemUnit.ROLL,
            estimated_unit_value=Decimal("12.50"),
            default_quantity=Decimal("2.00"),
        )
        ServiceItemCatalog.objects.create(
            professional=self.other_professional,
            category=self.category,
            internal_code="MAT-2042",
            item_type=ServiceItemExpense.ItemType.MATERIAL,
            name="Item privado de outro prestador",
            unit=ServiceItemUnit.UNIT,
            estimated_unit_value=Decimal("99.90"),
        )
        self.service_request = ServiceRequest.objects.create(
            professional=self.professional,
            client_name="Cliente avulso",
            category=self.category,
            title="Troca de tomada",
            description="Solicitação de teste.",
        )

    def test_catalog_search_finds_own_item_by_internal_code_only(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_item_catalog_search"), {"q": "MAT-2042"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], str(self.catalog_item.id))
        self.assertEqual(payload["items"][0]["internal_code"], "MAT-2042")
        self.assertEqual(payload["items"][0]["name"], "Fita isolante profissional")
        self.assertEqual(payload["items"][0]["estimated_unit_value"], "12.50")
        self.assertEqual(payload["items"][0]["default_quantity"], "2.00")

    def test_request_detail_exposes_catalog_search_for_quick_items(self):
        self.client.force_login(self.professional)

        response = self.client.get(reverse("service_request_detail", args=[self.service_request.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-request-item-catalog-search')
        self.assertContains(response, 'data-request-item-catalog-results')
        self.assertContains(response, "Código interno ou nome do item")
        self.assertContains(response, reverse("service_item_catalog_search"))

    def test_other_professional_cannot_open_or_search_the_request_items(self):
        self.client.force_login(self.other_professional)

        detail_response = self.client.get(reverse("service_request_detail", args=[self.service_request.id]))
        search_response = self.client.get(reverse("service_item_catalog_search"), {"q": "MAT-2042"})

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(len(search_response.json()["items"]), 1)
        self.assertEqual(search_response.json()["items"][0]["name"], "Item privado de outro prestador")
