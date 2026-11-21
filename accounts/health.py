"""Checagens de saude/configuracao do HoraCerta.

Objetivo: pegar falhas SILENCIOSAS de configuracao antes que o usuario perceba
(e-mail em modo console que nunca envia, endereco publico apontando para um IP,
migracao pendente, DEBUG ligado...). Usado pela pagina /interno/saude/ (so
superusuario) e pelo comando ``manage.py check_health``. Nunca expoe segredos.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

OK, WARN, FAIL = "ok", "warn", "fail"


def _check(status, label, detail=""):
    return {"status": status, "label": label, "detail": detail}


def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return _check(OK, "Banco de dados responde")
    except Exception as exc:  # noqa: BLE001 - mostrar a causa ao administrador
        return _check(FAIL, "Banco de dados nao responde", f"{type(exc).__name__}: {exc}")


def check_pending_migrations():
    try:
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception as exc:  # noqa: BLE001
        return _check(WARN, "Nao foi possivel verificar migracoes", f"{type(exc).__name__}: {exc}")
    if pending:
        names = ", ".join(f"{m.app_label}.{m.name}" for m, _backwards in pending[:5])
        return _check(FAIL, f"{len(pending)} migracao(oes) pendente(s)", f"Rode migrate. Ex.: {names}")
    return _check(OK, "Nenhuma migracao pendente")


def check_debug():
    if settings.DEBUG:
        return _check(FAIL, "DEBUG esta LIGADO em producao", "Expoe detalhes internos. Defina DEBUG=False no .env.")
    return _check(OK, "DEBUG desligado")


def check_secret_key():
    key = settings.SECRET_KEY or ""
    if "insecure" in key or len(key) < 40:
        return _check(FAIL, "SECRET_KEY fraca ou de exemplo", "Defina uma chave longa e exclusiva no .env.")
    return _check(OK, "SECRET_KEY definida")


def check_email():
    backend = settings.EMAIL_BACKEND
    if backend.endswith("console.EmailBackend"):
        return _check(
            FAIL,
            "E-mail em modo CONSOLE (nada sai)",
            "A recuperacao de senha nao chega. Defina USE_CONSOLE_EMAIL=False no .env.",
        )
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return _check(FAIL, "E-mail sem usuario/senha SMTP", "Defina EMAIL_HOST_USER e EMAIL_HOST_PASSWORD.")
    if settings.DEFAULT_FROM_EMAIL.endswith(".local"):
        return _check(WARN, "Remetente de e-mail com valor de exemplo", settings.DEFAULT_FROM_EMAIL)
    return _check(OK, "E-mail configurado para envio real", "Confirme com o teste em /interno/email/.")


def check_public_url():
    url = (settings.APP_BASE_URL or "").strip()
    if not url:
        return _check(WARN, "APP_BASE_URL nao definido", "Links de e-mail usam o host da requisicao.")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return _check(FAIL, "Endereco publico sem HTTPS", f"{url} - use https://seu-dominio no .env.")
    if _is_ip(parsed.hostname or ""):
        return _check(FAIL, "Endereco publico e um IP", f"{url} - use o dominio.")
    return _check(OK, "Endereco publico com dominio e HTTPS", url)


def check_secure_cookies():
    if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
        return _check(FAIL, "Cookies sem flag Secure", "Sessao/CSRF trafegariam em HTTP puro.")
    return _check(OK, "Cookies de sessao e CSRF com Secure")


def check_allowed_hosts():
    hosts = settings.ALLOWED_HOSTS or []
    if "*" in hosts:
        return _check(FAIL, "ALLOWED_HOSTS aceita qualquer host (*)")
    return _check(OK, "ALLOWED_HOSTS restrito")


def check_signup_flag():
    if getattr(settings, "MEI_SIGNUP_ENABLED", True):
        return _check(OK, "Cadastro publico de MEI ABERTO", "Feche com MEI_SIGNUP_ENABLED=False se houver abuso.")
    return _check(WARN, "Cadastro publico de MEI FECHADO", "Novas pessoas nao conseguem criar conta.")


def run_checks():
    checks = [
        check_database(),
        check_pending_migrations(),
        check_debug(),
        check_secret_key(),
        check_email(),
        check_public_url(),
        check_secure_cookies(),
        check_allowed_hosts(),
        check_signup_flag(),
    ]
    summary = {
        "fail": sum(1 for c in checks if c["status"] == FAIL),
        "warn": sum(1 for c in checks if c["status"] == WARN),
        "ok": sum(1 for c in checks if c["status"] == OK),
    }
    return {"checks": checks, "summary": summary, "healthy": summary["fail"] == 0}
