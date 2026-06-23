
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views
from accounts.pwa_views import offline

urlpatterns = [
    # Landing page (publica)
    path("", account_views.landing_view, name="landing"),
    path("manifest.webmanifest", account_views.pwa_manifest, name="pwa_manifest"),
    path("sw.js", account_views.pwa_service_worker, name="pwa_service_worker"),
    path("offline/", offline, name="offline"),

    # Admin
    path("admin/", admin.site.urls),

    # Accounts (login, signup, dashboard, help, terms)
    path("", include("accounts.urls")),
    path("", include("services.urls")),
    
    # PWA Push Notifications
    path("api/push/subscribe/", account_views.register_push_subscription, name="register_push"),
    path("api/pwa/status/", account_views.pwa_status, name="pwa_status"),

    # Timeclock (dashboard MEI /me/, exportação, notas)
    path("", include("timeclock.urls")),
]

# arquivos de mídia
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
