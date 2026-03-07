
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Landing page
    path("", TemplateView.as_view(template_name="accounts/landing.html"), name="landing"),

    # Admin
    path("admin/", admin.site.urls),

    # Accounts (login, signup, dashboard, help, terms)
    path("", include("accounts.urls")),

    # Timeclock (dashboard MEI /me/, exportação, notas)
    path("", include("timeclock.urls")),
]

# arquivos de mídia
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)