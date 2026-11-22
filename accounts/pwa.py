"""Endpoints públicos e autenticados do Progressive Web App do HoraCerta."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


def offline(request):
    """Modo sem internet. Pagina generica (sem dado pessoal no HTML), guardada pelo
    service worker; le do aparelho a lista de clientes e a fila de registros.
    O JS da fila vai embutido para a pagina funcionar inteira a partir do cache."""
    from django.contrib.staticfiles import finders

    from accounts.models import User

    def read_static(name):
        with open(finders.find(name), encoding="utf-8") as handle:
            return handle.read()

    return render(
        request,
        "offline.html",
        {
            "offline_store_js": read_static("js/offline_store.js"),
            "offline_mirror_js": read_static("js/offline_mirror.js"),
            "offline_app_js": read_static("js/offline_app.js"),
            "tokens_css": read_static("css/design_tokens.css"),
            "theme_names_json": json.dumps([value for value, _label in User.VisualTheme.choices]),
        },
    )


@require_GET
def ping(request):
    """Sonda mínima de alcance do servidor, usada pela página offline e pelo
    aviso de conexão do app.

    ``navigator.onLine`` só diz se o aparelho tem uma interface de rede ativa
    (Wi-Fi conectado, por exemplo) — não se o servidor responde de verdade.
    Um fetch real a esta rota é a única prova confiável de que voltamos a
    conseguir falar com o HoraCerta. Pública, sem sessão e nunca cacheada.
    """
    response = HttpResponse(status=204)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def manifest(request):
    """Serve o manifest com rotas atuais do produto."""
    manifest_data = {
        "id": "/",
        "name": "HoraCerta - Gestão de Horas",
        "short_name": "HoraCerta",
        "description": "Gestão de horas, clientes, serviços e relatórios para MEIs e prestadores de serviço.",
        "start_url": reverse("landing"),
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": "#0b1220",
        "background_color": "#0b1220",
        "categories": ["business", "productivity"],
        "lang": "pt-BR",
        "screenshots": [
            {
                "src": static("screenshots/screenshot-540x720.png"),
                "sizes": "540x720",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "Visão do HoraCerta em celular",
            },
            {
                "src": static("screenshots/screenshot-1280x720.png"),
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide",
                "label": "Visão do HoraCerta em tela ampla",
            },
        ],
        "icons": [
            {"src": static("pwa/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("pwa/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {
                "src": static("pwa/icon-maskable-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": static("pwa/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {
                "name": "Registrar horário",
                "short_name": "Horários",
                "description": "Abra o registro de horas",
                "url": reverse("employee_dashboard"),
                "icons": [{"src": static("pwa/shortcut-punch-96.png"), "sizes": "96x96", "type": "image/png"}],
            },
            {
                "name": "Meus clientes",
                "short_name": "Clientes",
                "description": "Veja seus clientes, horas e valores",
                "url": reverse("mei_contract"),
                "icons": [{"src": static("pwa/shortcut-clients-96.png"), "sizes": "96x96", "type": "image/png"}],
            },
            {
                "name": "Meus serviços",
                "short_name": "Serviços",
                "description": "Gerencie pedidos e serviços",
                "url": reverse("service_job_list"),
                "icons": [{"src": static("pwa/shortcut-services-96.png"), "sizes": "96x96", "type": "image/png"}],
            },
        ],
        "prefer_related_applications": False,
    }
    response = HttpResponse(
        json.dumps(manifest_data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@require_GET
def service_worker(request):
    """Serve o service worker no escopo raiz do domínio."""
    service_worker_path = settings.BASE_DIR / "static" / "js" / "sw.js"
    if not service_worker_path.exists():
        raise Http404("Service worker não encontrado.")

    response = HttpResponse(
        service_worker_path.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    return response


def _json_body(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


@login_required
@require_POST
def register_push_subscription(request):
    """Guarda o aparelho que aceitou receber avisos (endpoint + chaves do navegador)."""
    from accounts.models import PushSubscription
    from accounts.push import push_enabled

    if not push_enabled():
        return JsonResponse({"enabled": False, "error": "Avisos no celular ainda não estão ligados no servidor."}, status=501)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Formato de inscrição inválido."}, status=400)
    endpoint = str(payload.get("endpoint") or "").strip()
    keys = payload.get("keys") if isinstance(payload.get("keys"), dict) else {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or len(endpoint) > 2000 or not p256dh or not auth \
            or len(p256dh) > 255 or len(auth) > 255:
        return JsonResponse({"error": "Inscrição incompleta."}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:300],
        },
    )
    return JsonResponse({"enabled": True, "devices": request.user.push_subscriptions.count()})


@login_required
@require_POST
def unregister_push_subscription(request):
    """Desliga os avisos do aparelho (so apaga inscricao do proprio usuario)."""
    from accounts.models import PushSubscription

    payload = _json_body(request) or {}
    endpoint = str(payload.get("endpoint") or "").strip()
    deleted, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete() if endpoint else (0, None)
    return JsonResponse({"enabled": False, "removed": deleted})


@login_required
@require_POST
def push_test(request):
    """Manda um aviso de teste para os aparelhos do proprio usuario."""
    from accounts.push import send_push_to_user

    sent = send_push_to_user(
        request.user,
        title="HoraCerta",
        body="Pronto! Os avisos estão chegando neste aparelho.",
        url=reverse("mei_profile"),
        tag="hc-teste",
    )
    return JsonResponse({"sent": sent})


@login_required
@require_GET
def status(request):
    """Expõe somente capacidades verificáveis pelo servidor."""
    from accounts.push import push_enabled

    return JsonResponse(
        {
            "pwa_available": True,
            "service_worker_url": reverse("pwa_service_worker"),
            "offline_fallback_url": reverse("offline"),
            "push_notifications_available": push_enabled(),
            "user_role": request.user.role,
        }
    )
