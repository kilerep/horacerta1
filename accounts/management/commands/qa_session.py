"""Abre uma sessao de teste local para os agentes-persona usarem o HoraCerta.

So funciona com DEBUG=True e e-mails .test (nunca em producao). Cria o usuario se
precisar (prestador com cenario de demonstracao, ou a empresa cliente desse cenario)
e imprime o valor do cookie `sessionid` para usar no navegador ou no qa/tools/navegar.py.

    (Git Bash) export DEBUG=True APP_BASE_URL=http://127.0.0.1:8765
    python manage.py qa_session --persona prestador --email ana@horacerta.test
    python manage.py qa_session --persona empresa
    python manage.py qa_session --persona novo --email novo@horacerta.test
"""

from io import StringIO

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import BaseCommand, CommandError, call_command

from accounts.models import User

PASSWORD = "Teste@12345"


class Command(BaseCommand):
    help = "Cria/usa um usuario de teste local e imprime o sessionid (somente DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument("--persona", choices=["prestador", "empresa", "novo"], default="prestador")
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("qa_session só funciona com DEBUG=True.")
        persona = options["persona"]
        email = (options["email"] or "").strip().lower()

        if persona == "prestador":
            email = email or "qa.prestador@horacerta.test"
            self._require_test_email(email)
            if not User.objects.filter(email=email).exists():
                call_command("seed_local_demo_scenarios", "--email", email, "--password", PASSWORD, stdout=StringIO())
            user = User.objects.get(email=email)
        elif persona == "empresa":
            if not User.objects.filter(email="demo.cliente@horacerta.test").exists():
                call_command("seed_local_demo_scenarios", "--email", "qa.prestador@horacerta.test",
                             "--password", PASSWORD, stdout=StringIO())
            user = User.objects.get(email="demo.cliente@horacerta.test")
        else:
            email = email or "qa.novo@horacerta.test"
            self._require_test_email(email)
            user, created = User.objects.get_or_create(
                email=email, defaults={"username": email, "role": User.Role.FUNCIONARIO, "is_active": True}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()

        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.create()
        self.stdout.write(session.session_key)

    @staticmethod
    def _require_test_email(email):
        if not email.endswith(".test"):
            raise CommandError("Use um e-mail local no domínio .test.")
