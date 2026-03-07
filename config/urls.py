from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
   path("", TemplateView.as_view(template_name="accounts/landing.html"), name="landing"),
    path("admin/", admin.site.urls),

    # Accounts (signup/login/dashboard/help/terms)
    path("", include("accounts.urls")),

    # Timeclock (MEI dashboard /me/, export, note edit...)
    path("", include("timeclock.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
