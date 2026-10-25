"""Todas as rotas internas abertas por cada tipo de usuario: nenhuma pode dar erro 500.

Percorre o roteador inteiro (menos admin, landing e arquivos estaticos), monta a URL
com objetos reais do cenario de QA e faz GET como visitante, prestador, empresa e
administrador interno. Rotas so de POST respondem 405, o que tambem e aceitavel aqui.
"""

from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from .fixtures import build_world

SKIP_PREFIXES = ("admin/", "static/", "media/", "__debug__")
SKIP_NAMES = {"landing", "logout", "password_reset_confirm", "pwa_service_worker"}


def iter_routes(patterns, prefix=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from iter_routes(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern) and entry.name:
            yield prefix + str(entry.pattern), entry.name, list(entry.pattern.regex.groupindex)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class AllRoutesNoServerErrorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def _kwargs(self, route, params):
        w = self.w
        values = {
            "job_id": w["job"].id if w["job"] else None,
            "sheet_id": w["sheet"].id,
            "entry_id": w["entry"].id,
            "report_id": w["report"].id,
            "contract_id": w["contract"].id,
            "employee_id": w["employee"].id,
            "company_id": w["company"].id,
            "location_id": w["location"].id,
            "punch_id": w["punch"].id if w["punch"] else None,
            "item_id": None,
            "request_id": None,
            "notification_id": None,
            "token": None,
        }
        if "catalogo/" in route:
            values["item_id"] = w["catalog_item"].id if w["catalog_item"] else None
        elif "itens/" in route:
            values["item_id"] = w["job_item"].id if w["job_item"] else None
        if "servicos/pedidos/" in route:
            values["request_id"] = w["service_request"].id if w["service_request"] else None
        elif "problemas-horario/" in route or "interno/solicitacoes/" in route:
            values["request_id"] = w["correction"].id if w["correction"] else None
        if route.startswith("me/notificacoes/"):
            values["notification_id"] = w["mei_notice"].id
        elif route.startswith("empresa/notificacoes/"):
            values["notification_id"] = w["company_notice"].id
        if route.startswith("conferencia/relatorio/"):
            values["token"] = w["report"].conference_token
        elif route.startswith("relatorio-producao/"):
            values["token"] = w["sheet"].share_token
        elif route.startswith("servicos/") and w["job"]:
            values["token"] = w["job"].public_token
        elif route.startswith("me/qr-presencial/"):
            values["token"] = w["location"].qr_token
        kwargs = {}
        for name in params:
            if values.get(name) is None:
                return None
            kwargs[name] = values[name]
        return kwargs

    def _routes(self):
        for route, name, params in iter_routes(get_resolver().url_patterns):
            if route.startswith(SKIP_PREFIXES) or name in SKIP_NAMES:
                continue
            yield route, name, params

    def _sweep(self, user):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        errors, skipped, visited = [], [], 0
        for route, name, params in self._routes():
            kwargs = self._kwargs(route, params)
            if kwargs is None:
                skipped.append(route)
                continue
            url = reverse(name, kwargs=kwargs)
            try:
                status = self.client.get(url).status_code
            except Exception as exc:  # erro nao tratado vira falha listada, nao derruba a varredura
                status = f"{type(exc).__name__}: {exc}"[:160]
            visited += 1
            if not isinstance(status, int) or status >= 500:
                errors.append(f"{url} -> {status}")
        return errors, skipped, visited

    def test_visitor(self):
        errors, _, visited = self._sweep(None)
        self.assertGreater(visited, 100)
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def test_prestador(self):
        errors, skipped, visited = self._sweep(self.w["mei"])
        # Rotas sem objeto no cenario ficam de fora; a lista deve continuar curta.
        self.assertLessEqual(len(skipped), 5, skipped)
        self.assertGreater(visited, 100)
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def test_empresa(self):
        errors, _, visited = self._sweep(self.w["company_user"])
        self.assertGreater(visited, 100)
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def test_admin_interno(self):
        errors, _, visited = self._sweep(self.w["staff"])
        self.assertGreater(visited, 100)
        self.assertEqual(errors, [], "\n" + "\n".join(errors))
