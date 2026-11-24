"""2026-11-23: vocabulário jurídico do HoraCerta.

O HoraCerta organiza horários e serviços de PRESTADORES DE SERVIÇOS (autônomos, MEI, pequenas
empresas de serviços) para os seus CLIENTES. Ele não é sistema de RH, não é ponto eletrônico e
não emite documento fiscal. Palavras erradas em telas, PDFs, e-mails ou mensagens podem ser usadas
como prova contra o prestador, contra o cliente dele ou contra o HoraCerta:

- CLT arts. 2º, 3º e 9º (vínculo de emprego / subordinação) e art. 442-B (autônomo): nada de
  "funcionário", "empregado", "patrão", "chefe", "expediente", "hora extra", "banco de horas",
  "salário", "holerite", "admissão", "demissão", "rescisão", "carga horária", "subordinado".
- Portaria MTP 671/2021 (registro eletrônico de ponto): nada de "espelho de ponto", "folha de
  ponto", "bater ponto", "ponto eletrônico", "jornada" (ver também SemVocabularioDePontoTests).
- Código de Defesa do Consumidor (arts. 6º, III e IV; 31; 37): nada de "validade jurídica",
  "documento oficial", "homologado", "assinatura digital", "nota fiscal" como promessa.
- Regras do produto: nada de cobrança/fatura como função do sistema.

Exceções documentadas:
- "encarregado"/"supervisor" só na produção e no romaneio, onde nomeiam quem RECEBE o documento
  na empresa do cliente (nunca chefe do prestador).
- "nota fiscal" só nos avisos que dizem que o HoraCerta NÃO emite / o documento NÃO substitui
  nota fiscal (transparência exigida pelo CDC).

Identificadores de código (valor gravado "FUNCIONARIO", nome de template, rotas) continuam como
estão: só o texto que a pessoa vê é verificado.
"""

import io
import re
import tokenize
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

User = get_user_model()

TERMOS_DE_RISCO = {
    "funcionário": r"\bfuncion[aá]ri[oa]s?\b",
    "empregado/empregador": r"\bempregad[oa]s?\b|\bempregador(?:es|a|as)?\b",
    "patrão": r"\bpatr(?:ão|ao|oa|oas|ões|oes)\b",
    "chefe": r"\bchefes?\b",
    "colaborador": r"\bcolaborador(?:es|a|as)?\b",
    "expediente": r"\bexpedientes?\b",
    "turno": r"\bturnos?\b",
    "hora extra": r"\bhoras?[ -]extras?\b",
    "banco de horas": r"\bbanco de horas\b",
    "salário": r"\bsal[aá]ri[oa]s?\b",
    "holerite": r"\bholerites?\b",
    "admissão": r"\badmiss(?:ão|ao|ões|oes)\b",
    "demissão": r"\bdemiss(?:ão|ao|ões|oes)\b|\bdemitid[oa]s?\b",
    "rescisão": r"\brescis(?:ão|ao|ões|oes|ória|oria)\b",
    "desligamento": r"\bdesligamentos?\b",
    "carga horária": r"\bcarga hor[aá]ria\b",
    "subordinado": r"\bsubordinad[oa]s?\b|\bsubordinação\b|\bsubordinacao\b",
    "advertência": r"\badvert[eê]ncias?\b",
    "recursos humanos": r"\brecursos humanos\b",
    "vínculo empregatício": r"\bv[ií]nculo empregat[ií]cio\b",
    "espelho/folha de ponto": r"\b(?:espelho|folha|cartão|cartao|marcação|marcacao|registro) de ponto\b",
    "ponto eletrônico": r"\bponto eletr[oô]nico\b|\bbater (?:o )?ponto\b|\bportaria\s*(?:mtp\s*)?n?º?\s*671\b",
    "jornada": r"\bjornadas?\b",
    "validade jurídica": r"\bvalidade jur[ií]dica\b|\bvalor jur[ií]dico\b",
    "documento oficial": r"\bdocumentos? oficia(?:l|is)\b|\bcomprovantes? (?:oficia(?:l|is)|lega(?:l|is)|fisca(?:l|is))\b",
    "homologado": r"\bhomologad[oa]s?\b",
    "nota fiscal": r"\bnotas? fisca(?:l|is)\b|\bcupom fiscal\b|\b(?:documento|recibo) fiscal\b",
    "assinatura digital": r"\bassinatura (?:digital|eletr[oô]nica)\b|\bcertificad[oa] digital\b",
    "cobrança/fatura": r"\bcobran[cç]as?\b|\bfaturas?\b|\bfaturamento\b|\binadimpl\w*",
}
TERMOS = {nome: re.compile(rx, re.IGNORECASE) for nome, rx in TERMOS_DE_RISCO.items()}
# "RH" só em maiúsculas (não confundir com outras siglas/palavras).
TERMOS["RH"] = re.compile(r"\bRH\b")

# Quem recebe o documento na empresa do cliente: permitido só na produção e no romaneio.
SUPERVISAO = re.compile(r"\b(?:encarregad[oa]s?|supervisor(?:es|a|as)?)\b", re.IGNORECASE)
SUPERVISAO_PERMITIDA_EM = (
    "templates/production/",
    "production/",
    "static/js/production_",
    "static/js/offline_forms.js",  # rascunho de romaneio sem internet
)

# Avisos de transparência (CDC) que podem citar "nota fiscal" para dizer que NÃO é.
AVISOS_PERMITIDOS = [
    re.compile(r"não emite nota fiscal", re.IGNORECASE),
    re.compile(r"não substitui nota fiscal", re.IGNORECASE),
]

# Literais Python que são identificadores internos, nunca exibidos.
_PY_LITERAIS_PERMITIDOS = {
    "FUNCIONARIO",  # valor gravado de User.Role (o rótulo é "Prestador (MEI)")
    "accounts/dashboard_funcionario.html",  # nome do arquivo de template
}

_TEMPLATE_CODE = [
    re.compile(r"<style.*?</style>", re.DOTALL | re.IGNORECASE),
    re.compile(r"\{%.*?%\}", re.DOTALL),
    re.compile(r"\{\{.*?\}\}", re.DOTALL),
    re.compile(r"\{#.*?#\}", re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"""\b(?:id|name|for|href|class|action|src|style|data-[\w-]+)\s*=\s*(?:"[^"]*"|'[^']*')""",
               re.IGNORECASE),
]
_JS_COMMENTS = [
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r"(?m)^\s*//.*$"),
]
_PY_APPS = ("accounts", "companies", "config", "production", "services", "timeclock", "writtenreports")


def _sem_codigo(texto, padroes):
    for padrao in padroes:
        texto = padrao.sub(lambda m: "\n" * m.group(0).count("\n") + " ", texto)
    return texto


def _textos_visiveis(base):
    """(arquivo relativo, linha, texto) de tudo que pode chegar à tela, PDF, e-mail ou mensagem."""
    templates = list((base / "templates").glob("**/*.html")) + list((base / "templates").glob("**/*.txt"))
    for path in sorted(templates):
        rel = path.relative_to(base).as_posix()
        texto = _sem_codigo(path.read_text(encoding="utf-8"), _TEMPLATE_CODE)
        for numero, linha in enumerate(texto.splitlines(), 1):
            yield rel, numero, linha
    for path in sorted(list((base / "static/js").glob("*.js")) + [base / "static/manifest.json"]):
        rel = path.relative_to(base).as_posix()
        texto = _sem_codigo(path.read_text(encoding="utf-8"), _JS_COMMENTS)
        for numero, linha in enumerate(texto.splitlines(), 1):
            yield rel, numero, linha
    for app in _PY_APPS:
        for path in sorted((base / app).rglob("*.py")):
            partes = set(path.relative_to(base).parts)
            if "migrations" in partes or "management" in partes or "tests" in partes:
                continue
            if path.name.startswith("test") or path.name == "urls.py":
                continue
            rel = path.relative_to(base).as_posix()
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
                if is_texto and not is_docstring and tok.string.strip("\"'") not in _PY_LITERAIS_PERMITIDOS:
                    yield rel, tok.start[0], tok.string
                anterior = tok


def ocorrencias_de_risco(base):
    hits = []
    for rel, numero, linha in _textos_visiveis(base):
        limpa = linha
        for aviso in AVISOS_PERMITIDOS:
            limpa = aviso.sub(" ", limpa)
        for nome, padrao in TERMOS.items():
            if padrao.search(limpa):
                hits.append(f"{rel}:{numero} [{nome}] {linha.strip()[:120]}")
        if SUPERVISAO.search(limpa) and not rel.startswith(SUPERVISAO_PERMITIDA_EM):
            hits.append(f"{rel}:{numero} [encarregado/supervisor fora da produção] {linha.strip()[:120]}")
    return hits


class VocabularioJuridicoTests(SimpleTestCase):
    def test_textos_visiveis_sem_vocabulario_de_risco(self):
        hits = ocorrencias_de_risco(Path(settings.BASE_DIR))
        self.assertEqual(hits, [], "\n".join(hits))

    def test_guarda_pega_palavra_proibida(self):
        """O próprio detector precisa reconhecer as palavras (evita teste que passa sem olhar nada)."""
        exemplos = [
            "Funcionário", "empregado", "Patrão", "chefe", "colaboradores", "expediente", "turno",
            "hora extra", "banco de horas", "salário", "holerite", "admissão", "demissão", "rescisão",
            "desligamento", "carga horária", "subordinado", "advertência", "recursos humanos",
            "espelho de ponto", "bater ponto", "jornada", "validade jurídica", "documento oficial",
            "comprovante legal", "homologado", "nota fiscal", "assinatura digital", "cobrança", "fatura",
            "Portaria 671",
        ]
        for exemplo in exemplos:
            with self.subTest(exemplo=exemplo):
                self.assertTrue(any(p.search(exemplo) for p in TERMOS.values()), exemplo)
        self.assertTrue(TERMOS["RH"].search("Email do RH/Admin"))
        self.assertIsNone(TERMOS["RH"].search("RHode Island rh"))

    def test_avisos_de_transparencia_continuam_permitidos(self):
        limpa = "O HoraCerta não emite nota fiscal."
        for aviso in AVISOS_PERMITIDOS:
            limpa = aviso.sub(" ", limpa)
        self.assertFalse(TERMOS["nota fiscal"].search(limpa))

    def test_rotulo_do_papel_do_prestador(self):
        # O valor gravado continua "FUNCIONARIO"; o que aparece (admin, listas) é "Prestador (MEI)".
        self.assertEqual(User.Role.FUNCIONARIO.value, "FUNCIONARIO")
        self.assertEqual(User.Role.FUNCIONARIO.label, "Prestador (MEI)")
        self.assertNotIn("RH", User.Role.EMPRESA.label)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class RelatorioPagoApareceComoConferidoTests(TestCase):
    """O HoraCerta não controla pagamento: relatório antigo marcado como pago aparece como
    "Conferido pelo cliente". O valor gravado (PAID/paid) não muda."""

    def setUp(self):
        from companies.models import Company, Employee
        from timeclock.models import Contract, ServiceReport

        self.user = User.objects.create_user(username="pago@example.com", email="pago@example.com",
                                             password="x-Senha-123456", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Padaria Sol")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Prestador Teste", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("50.00"),
                                                start_date=date(2026, 1, 1), is_active=True)
        self.report = ServiceReport.objects.create(
            company=company, employee=employee, contract=self.contract, report_date=date(2026, 6, 4),
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 4), title="Relatório antigo",
            status=ServiceReport.Status.PAID, payment_status=ServiceReport.PaymentStatus.PAID,
        )
        self.report.ensure_conference_link()
        self.report.save()
        self.client.force_login(self.user)

    def test_rotulos_nao_falam_em_pago(self):
        from timeclock.models import ServiceReport

        self.assertEqual(ServiceReport.Status.PAID.value, "PAID")
        self.assertEqual(ServiceReport.Status.PAID.label, "Conferido pelo cliente")
        self.assertEqual(ServiceReport.PaymentStatus.PAID.value, "paid")
        self.assertEqual(ServiceReport.PaymentStatus.PAID.label, "Conferido pelo cliente")

    def test_telas_mostram_conferido_pelo_cliente(self):
        from timeclock.models import ServiceReport

        urls = [
            reverse("mei_reports"),
            reverse("mei_reports") + f"?status={ServiceReport.Status.REVIEWED}",
            reverse("mei_service_report_detail", args=[self.report.id]),
            reverse("mei_contract") + f"?contract={self.contract.id}",
        ]
        for url in urls:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertNotRegex(html, r">\s*Pago\s*<")
                self.assertNotIn("Recebido:", html)
        lista = self.client.get(reverse("mei_reports") + f"?status={ServiceReport.Status.REVIEWED}").content.decode()
        self.assertIn("Conferido pelo cliente", lista)
        detalhe = self.client.get(reverse("mei_service_report_detail", args=[self.report.id])).content.decode()
        self.assertIn("Conferido pelo cliente", detalhe)
        publico = self.client_class().get(
            reverse("public_service_report_conference", args=[self.report.conference_token])
        ).content.decode()
        self.assertNotRegex(publico, r"\bPago\b")
