"""Configuração do projeto Django HoraCerta."""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

try:
    import dj_database_url
except ImportError:  # pragma: no cover
    dj_database_url = None

try:
    import whitenoise  # noqa: F401
except ImportError:  # pragma: no cover
    whitenoise = None

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = "test" in sys.argv


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


def _load_dotenv(dotenv_path):
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")

DEBUG = _env_bool("DEBUG", False)
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip()
ALLOW_DEBUG_IN_REMOTE = _env_bool("ALLOW_DEBUG_IN_REMOTE", False)

app_base_host = (urlparse(APP_BASE_URL).hostname or "").strip() if APP_BASE_URL else ""
is_remote_host = bool(app_base_host and app_base_host not in {"localhost", "127.0.0.1"})
if DEBUG and is_remote_host and not ALLOW_DEBUG_IN_REMOTE:
    DEBUG = False

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-development-only-set-a-real-secret-key"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY é obrigatória quando DEBUG=False. Configure uma chave exclusiva no arquivo .env do ambiente."
        )

DEFAULT_ALLOWED_HOSTS = [
    "horacertagestao.com.br",
    "www.horacertagestao.com.br",
    "3.128.144.176",
    "127.0.0.1",
    "localhost",
]
ALLOWED_HOSTS = list(DEFAULT_ALLOWED_HOSTS)
for host in [item.strip() for item in os.getenv("ALLOWED_HOSTS", "").split(",") if item.strip()]:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

render_external_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_external_hostname and render_external_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_external_hostname)
if app_base_host and app_base_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(app_base_host)

USE_WHITENOISE = _env_bool("USE_WHITENOISE", not DEBUG) and whitenoise is not None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "companies",
    "services",
    "timeclock",
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Deve ser o último: intercepta tentativas de login bloqueadas antes de
    # qualquer outra view rodar. Protege tanto o login customizado quanto o
    # /admin/ nativo do Django, porque age no nível do backend de autenticação.
    "axes.middleware.AxesMiddleware",
]
if USE_WHITENOISE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.header_profile_media",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    if dj_database_url is None:
        raise ImproperlyConfigured("DATABASE_URL definido, mas dj-database-url não está instalado.")
    try:
        db_config = dj_database_url.parse(DATABASE_URL, conn_max_age=600)
        if db_config.get("ENGINE") != "django.db.backends.sqlite3":
            db_config.setdefault("OPTIONS", {}).setdefault("sslmode", "require")
        DATABASES = {"default": db_config}
    except Exception as exc:
        if _env_bool("STRICT_DATABASE_URL", False):
            raise ImproperlyConfigured(f"DATABASE_URL inválido: {exc}") from exc
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if USE_WHITENOISE and not TESTING:
    STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

AUTHENTICATION_BACKENDS = [
    # Precisa vir primeiro: é ele quem barra a tentativa (retorna None) quando
    # o IP/usuário já estourou o limite de tentativas, antes de qualquer
    # backend real chegar a checar a senha.
    "axes.backends.AxesStandaloneBackend",
    "accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ---------------------------------------------------------------------------
# django-axes — bloqueio de força bruta no login (cobre tanto o login
# customizado quanto o /admin/ nativo do Django, por agir no backend de
# autenticação em vez de em uma view específica).
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.0833  # ~5 minutos, em horas
# Bloqueia pela COMBINAÇÃO IP + usuário (lista dentro de lista — uma lista
# "achatada" faria o axes bloquear por IP OU por usuário isoladamente).
# Assim, uma tentativa errada em uma conta não derruba o acesso de todo
# mundo atrás do mesmo IP (ex: NAT de escritório tentando contas diferentes).
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_RESET_ON_SUCCESS = True
# O site roda atrás de exatamente um proxy reverso confiável (nginx, que
# sempre ACRESCENTA o IP real ao final do X-Forwarded-For via
# $proxy_add_x_forwarded_for) — por isso pegamos o último IP da lista, nunca
# o primeiro, que um cliente poderia forjar livremente.
AXES_IPWARE_PROXY_COUNT = 1
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]
# Sem isso, o axes mostra uma página de bloqueio genérica em inglês. Esta
# função reaproveita a tela de login em português (accounts/axes_lockout.py).
AXES_LOCKOUT_CALLABLE = "accounts.axes_lockout.axes_lockout_response"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

USE_CONSOLE_EMAIL_RAW = os.getenv("USE_CONSOLE_EMAIL")
if USE_CONSOLE_EMAIL_RAW is None:
    USE_CONSOLE_EMAIL = DEBUG
else:
    USE_CONSOLE_EMAIL = USE_CONSOLE_EMAIL_RAW.strip().lower() in ("1", "true", "yes", "on")

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if USE_CONSOLE_EMAIL
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@horacerta.local")

DEFAULT_CSRF_TRUSTED_ORIGINS = [
    "https://horacertagestao.com.br",
    "https://www.horacertagestao.com.br",
    "http://3.128.144.176",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
CSRF_TRUSTED_ORIGINS = list(DEFAULT_CSRF_TRUSTED_ORIGINS)
for origin in [item.strip() for item in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if item.strip()]:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
if render_external_hostname:
    render_origin = f"https://{render_external_hostname}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)
if APP_BASE_URL and APP_BASE_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(APP_BASE_URL)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", False)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
# Sem isso, erros em produção não ficam registrados em lugar nenhum (o Django
# só mostra uma página 500 genérica para o usuário e não sobra rastro). Aqui
# tudo de nível WARNING+ vai para o console (Render/journald/gunicorn já
# capturam stdout/stderr como log), e erros não tratados (nível ERROR) também
# são enviados por e-mail para os endereços em ADMINS, reaproveitando o SMTP
# que já está configurado para reset de senha.
#
# Evolução recomendada: trocar/complementar por um serviço tipo Sentry
# (plano gratuito cobre bem o volume de um MVP) para ter stack trace completo,
# agrupamento de erros repetidos e alertas — e-mail sozinho não escala.
ADMINS = [
    tuple(item.strip() for item in pair.split(":", 1))
    for pair in os.getenv("ADMINS", "").split(",")
    if pair.strip() and ":" in pair
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "level": "WARNING",
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
