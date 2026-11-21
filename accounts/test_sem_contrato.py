"""2026-11-21: o HoraCerta organiza horas e serviços com CLIENTES - não existem contratos.

Nenhum texto que o usuário vê pode falar em "contrato"/"contratos"/"contratual"/"contratado".
Identificadores de código (modelo Contract, contract_id, nomes de URL) continuam como estão;
a rota antiga /me/contrato/ fica mantida para não quebrar links salvos.
"""

import io
import re
import tokenize
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, Punch

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)

PALAVRA = re.compile(r"\bcontrat", re.IGNORECASE)

# Trechos de template que são código, não texto visível.
_TEMPLATE_CODE = [
    re.compile(r"\{%.*?%\}", re.DOTALL),
    re.compile(r"\{\{.*?\}\}", re.DOTALL),
    re.compile(r"\{#.*?#\}", re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"""\b(?:id|name|for|href|class|action|src|data-[\w-]+)\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE),
]

_JS_COMMENTS = [
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r"(?m)^\s*//.*$"),
]

# Literais Python que são identificadores internos, nunca exibidos.
_PY_LITERAIS_PERMITIDOS = {
    "AGUARDANDO_CONTRATO",  # chave interna de estado (timeclock/state.py)
    "me/contrato/",  # rota antiga mantida para não quebrar links salvos
}
_PY_APPS = ("accounts", "companies", "config", "production", "services", "timeclock", "writtenreports")


def _ocorrencias(texto):
    return [m.start() for m in PALAVRA.finditer(texto)]


class SemContratoNosArquivosTests(SimpleTestCase):
    def test_templates_e_scripts_sem_palavra_contrato(self):
        base = Path(settings.BASE_DIR)
        hits = []
        for path in (base / "templates").glob("**/*.html"):
            texto = path.read_text(encoding="utf-8")
            for padrao in _TEMPLATE_CODE:
                texto = padrao.sub(" ", texto)
            for linha in texto.splitlines():
                if PALAVRA.search(linha):
                    hits.append(f"{path.relative_to(base)}: {linha.strip()[:120]}")
        for path in list((base / "static/js").glob("*.js")) + [base / "static/manifest.json"]:
            texto = path.read_text(encoding="utf-8")
            for padrao in _JS_COMMENTS:
                texto = padrao.sub(" ", texto)
            for linha in texto.splitlines():
                if PALAVRA.search(linha):
                    hits.append(f"{path.relative_to(base)}: {linha.strip()[:120]}")
        self.assertEqual(hits, [], hits)

    def test_textos_python_sem_palavra_contrato(self):
        """Mensagens, rótulos de formulário, erros de validação e respostas JSON."""
        base = Path(settings.BASE_DIR)
        hits = []
        for app in _PY_APPS:
            for path in (base / app).rglob("*.py"):
                partes = set(path.relative_to(base).parts)
                if "migrations" in partes or "management" in partes or "tests" in partes:
                    continue
                if path.name.startswith("test"):
                    continue
                fonte = path.read_text(encoding="utf-8")
                anterior = None
                for tok in tokenize.generate_tokens(io.StringIO(fonte).readline):
                    if tok.type in (tokenize.COMMENT, tokenize.NL):
                        continue
                    is_texto = tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1)
                    # Docstrings (string solta como instrução) não aparecem para o usuário.
                    is_docstring = tok.type == tokenize.STRING and (
                        anterior is None or anterior.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
                    )
                    if is_texto and not is_docstring and PALAVRA.search(tok.string):
                        literal = tok.string.strip("\"'")
                        if literal not in _PY_LITERAIS_PERMITIDOS:
                            hits.append(f"{path.relative_to(base)}:{tok.start[0]}: {tok.string[:100]}")
                    anterior = tok
        self.assertEqual(hits, [], hits)


@override_settings(**BASE)
class SemContratoNasTelasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="semcontrato@example.com", email="semcontrato@example.com",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Padaria Central", email="cli-sc@example.com")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Prestador Teste",
                                           is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2025, 1, 1), is_active=True)
        inicio = timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=1), time(8, 0)))
        Punch.objects.create(contract=self.contract, timestamp=inicio)
        Punch.objects.create(contract=self.contract, timestamp=inicio + timedelta(hours=4))
        self.client.force_login(self.user)

    def _assert_sem_contrato(self, url):
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200, url)
        html = response.content.decode().lower()
        # A rota antiga /me/contrato/ pode aparecer em links (href); ela não é texto visível.
        html = re.sub(r"/me/contrato/", "/me/clientes/", html)
        html = html.replace("categoria-clientes-contratos", "categoria-clientes")
        trechos = [html[max(0, i - 60):i + 40] for i in _ocorrencias(html)]
        self.assertEqual(trechos, [], url)

    def test_telas_do_prestador_sem_contrato(self):
        urls = [
            "/me/",
            reverse("mei_panel"),
            reverse("mei_contract"),
            reverse("mei_contract") + f"?contract={self.contract.id}",
            reverse("mei_history"),
            reverse("mei_reports"),
            reverse("service_job_list"),
            reverse("mei_profile"),
            reverse("mei_client_create"),
            reverse("mei_client_edit", args=[self.contract.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self._assert_sem_contrato(url)

    def test_erro_de_registro_manual_fala_em_cliente(self):
        response = self.client.post(reverse("create_manual_punches"), {"manual_date": str(timezone.localdate())})
        erros = " ".join(response.json()["errors"]).lower()
        self.assertIn("selecione o cliente.", erros)
        self.assertNotIn("contrat", erros)

        response = self.client.post(
            reverse("create_manual_punches"),
            {"contract": "00000000-0000-0000-0000-000000000000", "manual_date": str(timezone.localdate()),
             "times": ["08:00"]},
        )
        self.assertEqual(response.json()["errors"], ["Cliente inválido ou inativo."])

    def test_exportacoes_sem_contrato(self):
        for name in ("export_csv", "export_xlsx", "export_pdf"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), {"contract": str(self.contract.id)})
                self.assertEqual(response.status_code, 200)
                corpo = b"".join(response.streaming_content) if response.streaming else response.content
                self.assertNotIn(b"contrat", corpo.lower())
                self.assertNotIn(b"Contrat", corpo)
