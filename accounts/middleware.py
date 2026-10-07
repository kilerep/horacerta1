"""Middlewares de proteção de dados privados no navegador."""

from __future__ import annotations

from django.utils.cache import patch_vary_headers

# Rotas que continuam cacheáveis pelo service worker (páginas públicas iguais
# para todo mundo). Tudo o mais em HTML é privado ou dependente de sessão.
PUBLIC_CACHEABLE_PATHS = {"/help/", "/terms/", "/privacy/"}


class PrivateResponseNoStoreMiddleware:
    """Marca como ``no-store, private`` toda resposta HTML de quem está logado.

    Evita que o navegador guarde no cache HTTP ou no bfcache (botão Voltar após
    o logout) telas com dados de clientes, valores e relatórios. Só define o
    cabeçalho quando a view não definiu um próprio, e sempre acrescenta
    ``Vary: Cookie`` para HTML dependente de sessão.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if not (user is not None and user.is_authenticated):
            return response
        if request.path in PUBLIC_CACHEABLE_PATHS:
            return response

        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type:
            return response

        if not response.has_header("Cache-Control"):
            response["Cache-Control"] = "no-store, private"
        patch_vary_headers(response, ("Cookie",))
        return response
