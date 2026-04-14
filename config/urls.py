
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views

urlpatterns = [
    # Landing page (publica)
    path("", account_views.landing_view, name="landing"),

    # Admin
    path("admin/", admin.site.urls),

    # Accounts (login, signup, dashboard, help, terms)
    path("", include("accounts.urls")),

    # Timeclock (dashboard MEI /me/, exportação, notas)
    path("", include("timeclock.urls")),
]

# arquivos de mídia
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
