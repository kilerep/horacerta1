from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Accounts (signup/login/dashboard/help/terms)
    path("", include("accounts.urls")),

    # Timeclock (MEI dashboard /me/, export, note edit...)
    path("", include("timeclock.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
