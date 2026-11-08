"""Lote G (out/2026): pedidos com contagem nos filtros, pedido com link de volta discreto,
catalogo compacto e orcamento sem totais repetidos."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from services.models import ServiceCategory, ServiceItemCatalog, ServiceRequest

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class LoteGTests(TestCase):
    def setUp(self):
        self.mei = User.objects.create_user(username="g@example.com", email="g@example.com", password="Teste@12345",
                                            role=User.Role.FUNCIONARIO)
        self.client.force_login(self.mei)
        self.category = ServiceCategory.objects.get(slug="servico-geral")

    def _request(self, **extra):
        data = dict(professional=self.mei, category=self.category, title="Trocar tomada", client_name="Ana")
        data.update(extra)
        return ServiceRequest.objects.create(**data)

    def test_request_list_shows_counts_inside_filters_without_stat_grid(self):
        self._request()
        self._request(title="Outro", status=ServiceRequest.Status.IN_REVIEW)

        html = self.client.get(reverse("service_request_list")).content.decode()

        self.assertNotIn("request-stats", html)
        self.assertIn('Novo <b class="request-chip__count">1</b>', html)
        self.assertIn('Em análise <b class="request-chip__count">1</b>', html)
        self.assertIn("Transformar em serviço", html)

    def test_request_detail_back_link_does_not_compete_with_primary_action(self):
        req = self._request()

        html = self.client.get(reverse("service_request_detail", args=[req.id])).content.decode()

        self.assertIn('class="back-link"', html)
        self.assertNotIn('<a class="btn" href="%s">Voltar</a>' % reverse("service_request_list"), html)

    def test_catalog_row_has_no_duplicated_code_and_status_cells(self):
        ServiceItemCatalog.objects.create(professional=self.mei, name="Disjuntor 20A", internal_code="DJ-20")

        html = self.client.get(reverse("service_item_catalog_list")).content.decode()

        self.assertIn("DJ-20 — Disjuntor 20A", html)
        self.assertNotIn("<span>Código</span>", html)
        self.assertNotIn("<span>Status</span>", html)
        self.assertIn("nunca", html)
