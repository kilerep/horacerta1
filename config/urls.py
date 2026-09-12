import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts import pwa
from accounts import views as account_views

# Caminho do admin do Django configurável por env var. Deixar em "/admin/" (o
# padrão) funciona, mas é o primeiro caminho que qualquer bot de varredura
# tenta. Para reduzir a exposição, defina ADMIN_URL_PATH no .env (ex.:
# "gestao-interna-x7f") — o acesso continua exigindo autenticação de staff
# normalmente, isso só tira o caminho do lugar óbvio.
ADMIN_URL_PATH = os.getenv("ADMIN_URL_PATH", "admin").strip("/") + "/"

urlpatterns = [
    path("", account_views.landing_view, name="landing"),
    path("manifest.webmanifest", pwa.manifest, name="pwa_manifest"),
    path("sw.js", pwa.service_worker, name="pwa_service_worker"),
    path("offline/", pwa.offline, name="offline"),
    path(ADMIN_URL_PATH, admin.site.urls),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(template_name="registration/password_change_form.html"),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
    path("", include("accounts.urls")),
    path("", include("services.urls")),
    path("api/push/subscribe/", pwa.register_push_subscription, name="register_push"),
    path("api/pwa/status/", pwa.status, name="pwa_status"),
    path("", include("timeclock.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
