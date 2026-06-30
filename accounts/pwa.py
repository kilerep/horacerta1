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
    """Página de fallback quando não há conexão disponível."""
    return render(request, "offline.html")


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
                "description": "Veja clientes e contratos",
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


@login_required
@require_POST
def register_push_subscription(request):
    """Recebe a tentativa de inscrição e informa o estado real do recurso.

    O produto ainda não persiste subscriptions nem possui provedor de envio. Em vez
    de afirmar que notificações push foram ativadas, devolvemos uma resposta clara
    para o front-end tratar como recurso indisponível.
    """
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Formato de inscrição inválido."}, status=400)

    logger.info("Tentativa de ativar push recebida para usuário autenticado; persistência ainda não configurada.")
    return JsonResponse(
        {
            "enabled": False,
            "message": "Notificações push ainda não estão disponíveis neste ambiente.",
        },
        status=501,
    )


@login_required
@require_GET
def status(request):
    """Expõe somente capacidades verificáveis pelo servidor."""
    return JsonResponse(
        {
            "pwa_available": True,
            "service_worker_url": reverse("pwa_service_worker"),
            "offline_fallback_url": reverse("offline"),
            "push_notifications_available": False,
            "user_role": request.user.role,
        }
    )
