"""Resposta customizada de bloqueio do django-axes.

Sem isso, o axes mostra uma página HTML genérica em inglês quando bloqueia
uma tentativa de login. Para o login customizado (/login/), preferimos
re-renderizar a própria tela de login com a mensagem em português que já
existia antes do axes entrar em cena. Para qualquer outra rota protegida
(hoje, só o /admin/login/), uma resposta simples também em português.
"""
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

LOCKOUT_MESSAGE = (
    "Muitas tentativas de login com dados incorretos. "
    "Aguarde alguns minutos antes de tentar novamente."
)


def axes_lockout_response(request, original_response=None, credentials=None):
    if request.path == reverse("login"):
        from accounts.forms import LoginForm

        # Precisa rodar a validação (mesmo que ela mesma acuse "senha
        # incorreta") para o form ganhar cleaned_data e permitir anexar um
        # erro geral com add_error(None, ...) — é isso que o template
        # exibe no .error-box via {{ form.non_field_errors }}.
        form = LoginForm(request, data=request.POST if request.method == "POST" else None)
        form.is_valid()
        form.errors.clear()
        form.add_error(None, LOCKOUT_MESSAGE)
        return render(request, "accounts/login.html", {"form": form}, status=429)

    return HttpResponse(LOCKOUT_MESSAGE, status=429, content_type="text/plain; charset=utf-8")
