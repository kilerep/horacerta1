"""Testes da proteção contra força bruta no login (django-axes).

Cobre duas lacunas identificadas em auditoria de segurança:
1. A implementação manual anterior confiava no primeiro IP de
   X-Forwarded-For, que um cliente pode forjar livremente, para decidir
   por quem contar tentativas — o axes, configurado com
   AXES_IPWARE_PROXY_COUNT=1, olha para o IP real acrescentado pelo nginx.
2. O /admin/ nativo do Django não tinha nenhuma proteção contra força bruta.
   Como o axes age no backend de autenticação (AUTHENTICATION_BACKENDS),
   a mesma configuração cobre login customizado e admin.

Cada teste usa seu próprio IP de origem (via Client(REMOTE_ADDR=...)) para
não competir por lockout com os outros testes: o axes guarda tentativas por
IP+usuário no banco, não em algo que a transação de teste reverta sozinha
entre métodos de uma mesma classe rodando em sequência rápida.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.views import LOGIN_ATTEMPT_LIMIT


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class LoginBruteForceTests(TestCase):
    _next_ip = 1

    def _make_client_and_user(self, suffix):
        LoginBruteForceTests._next_ip += 1
        client = Client(REMOTE_ADDR=f"198.51.100.{LoginBruteForceTests._next_ip}")
        username = f"forca-bruta-{suffix}@example.com"
        User.objects.create_user(
            username=username,
            email=username,
            password="SenhaCorreta@123",
            role=User.Role.FUNCIONARIO,
        )
        return client, username

    def setUp(self):
        self.login_url = reverse("login")

    def test_correct_password_still_logs_in(self):
        client, username = self._make_client_and_user("ok")
        response = client.post(
            self.login_url, {"username": username, "password": "SenhaCorreta@123"}
        )
        self.assertEqual(response.status_code, 302)

    def test_blocks_after_limit_wrong_attempts_from_same_ip(self):
        client, username = self._make_client_and_user("bloqueio")
        # As primeiras (limite - 1) senhas erradas ainda são "só" senha
        # errada: o axes conta a falha mas não bloqueia enquanto não chega
        # no limite configurado.
        for _ in range(LOGIN_ATTEMPT_LIMIT - 1):
            response = client.post(
                self.login_url, {"username": username, "password": "senha-errada"}
            )
            self.assertEqual(response.status_code, 200)

        # Esta é a falha que estoura o limite: já vem bloqueada.
        response = client.post(
            self.login_url, {"username": username, "password": "senha-errada"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Muitas tentativas de login", status_code=429)

        # E continua bloqueado mesmo com a senha certa, até o cooloff passar.
        response = client.post(
            self.login_url, {"username": username, "password": "SenhaCorreta@123"}
        )
        self.assertEqual(response.status_code, 429)

    def test_forged_x_forwarded_for_header_does_not_bypass_limit(self):
        # O nginx real sempre ACRESCENTA o IP verdadeiro ao final do header
        # X-Forwarded-For ($proxy_add_x_forwarded_for); um atacante só
        # controla o que vem antes disso. AXES_IPWARE_PROXY_COUNT=1 faz o
        # axes considerar o IP correto (o de "trás", não o forjado).
        client, username = self._make_client_and_user("forjado")
        for i in range(LOGIN_ATTEMPT_LIMIT - 1):
            response = client.post(
                self.login_url,
                {"username": username, "password": "senha-errada"},
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.9",
            )
            self.assertEqual(response.status_code, 200)

        # Mesmo mudando o IP "forjado" a cada tentativa, o IP real (o
        # último da lista) é sempre o mesmo — então o limite é atingido
        # normalmente, sem bypass.
        response = client.post(
            self.login_url,
            {"username": username, "password": "senha-errada"},
            HTTP_X_FORWARDED_FOR="10.0.0.255, 203.0.113.9",
        )
        self.assertEqual(response.status_code, 429)


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class AdminLoginBruteForceTests(TestCase):
    def test_admin_login_blocks_after_repeated_failures(self):
        username = "admin-seguranca@example.com"
        User.objects.create_superuser(
            username=username, email=username, password="SenhaAdmin@123",
        )
        admin_login_url = reverse("admin:login")
        client = Client(REMOTE_ADDR="198.51.100.200")

        for _ in range(LOGIN_ATTEMPT_LIMIT):
            client.post(
                admin_login_url,
                {"username": username, "password": "senha-errada"},
            )

        response = client.post(
            admin_login_url,
            {"username": username, "password": "SenhaAdmin@123"},
        )
        # Bloqueado: não autentica mesmo com a senha certa.
        self.assertNotIn("_auth_user_id", client.session)
