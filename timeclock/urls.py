from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accounts/landing.html"), name="landing"),
    path("me/", views.employee_dashboard, name="employee_dashboard"),
    path("me/qr-presencial/<str:token>/", views.qr_presence_checkin, name="qr_presence_checkin"),
    path("me/manual-punches/", views.create_manual_punches, name="create_manual_punches"),
    path("me/export/", views.export_default, name="export_default"),
    path("me/export/csv/", views.export_csv, name="export_csv"),
    path("me/export/xlsx/", views.export_xlsx, name="export_xlsx"),
    path("me/export/pdf/", views.export_pdf, name="export_pdf"),
]
