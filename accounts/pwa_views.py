"""
Views para PWA (Progressive Web App)
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from accounts.models import User
import json
import logging

logger = logging.getLogger(__name__)


def offline(request):
    """Página offline para PWA"""
    return render(request, 'offline.html')


@require_http_methods(["GET"])
def manifest(request):
    """Servir manifest.json com dados dinâmicos"""
    
    manifest_data = {
        "id": "/",
        "name": "HoraCerta - Gestão de Horas",
        "short_name": "HoraCerta",
        "description": "Plataforma de gestão de horas entre empresa e MEI. Controle suas horas, clientes e serviços na palma da mão.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#0b1220",
        "theme_color": "#0b1220",
        "lang": "pt-BR",
        "categories": ["productivity", "business"],
        "screenshots": [
            {
                "src": "/static/screenshots/screenshot-540x720.png",
                "sizes": "540x720",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "Dashboard do HoraCerta"
            },
            {
                "src": "/static/screenshots/screenshot-1280x720.png",
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide",
                "label": "Dashboard em tablet"
            }
        ],
        "icons": [
            {
                "src": "/static/pwa/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/pwa/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/pwa/icon-maskable-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": "/static/pwa/icon-maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable"
            }
        ],
        "shortcuts": [
            {
                "name": "Registrar Ponto",
                "short_name": "Ponto",
                "description": "Registre suas horas rapidamente",
                "url": "/timeclock/me/",
                "icons": [
                    {
                        "src": "/static/pwa/shortcut-punch-96.png",
                        "sizes": "96x96",
                        "type": "image/png"
                    }
                ]
            },
            {
                "name": "Meus Clientes",
                "short_name": "Clientes",
                "description": "Veja seus clientes e contratos",
                "url": "/app/clientes/",
                "icons": [
                    {
                        "src": "/static/pwa/shortcut-clients-96.png",
                        "sizes": "96x96",
                        "type": "image/png"
                    }
                ]
            },
            {
                "name": "Meus Serviços",
                "short_name": "Serviços",
                "description": "Gerencie seus serviços e pedidos",
                "url": "/services/",
                "icons": [
                    {
                        "src": "/static/pwa/shortcut-services-96.png",
                        "sizes": "96x96",
                        "type": "image/png"
                    }
                ]
            }
        ],
        "prefer_related_applications": False
    }
    
    return JsonResponse(manifest_data, content_type='application/manifest+json')


@csrf_exempt
@require_http_methods(["POST"])
def register_push_subscription(request):
    """Registrar subscription de push notification"""
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    try:
        data = json.loads(request.body)
        
        # Aqui você pode armazenar a subscription no banco de dados
        # Por enquanto, apenas retornar sucesso
        
        logger.info(f"Push subscription registrada para usuário {request.user.id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Notificações push ativadas com sucesso',
            'timestamp': timezone.now().isoformat()
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except Exception as e:
        logger.error(f"Erro ao registrar push subscription: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def pwa_status(request):
    """Retornar status do PWA para o usuário"""
    
    return JsonResponse({
        'pwa_installed': True,
        'service_worker_active': True,
        'notifications_enabled': True,
        'offline_mode': True,
        'user': {
            'id': request.user.id,
            'email': request.user.email,
            'role': request.user.role,
        }
    })


@require_http_methods(["GET"])
def service_worker(request):
    """Servir service worker com versão dinâmica"""
    from django.http import FileResponse
    from django.conf import settings
    
    sw_path = settings.BASE_DIR / 'static' / 'js' / 'sw.js'
    
    response = FileResponse(open(sw_path, 'rb'), content_type='application/javascript')
    response['Cache-Control'] = 'public, max-age=3600'  # Cache por 1 hora
    response['Service-Worker-Allowed'] = '/'
    
    return response
