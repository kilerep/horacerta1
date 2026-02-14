from django.urls import path
from . import views

urlpatterns = [
    path("me/", views.employee_dashboard, name="employee_dashboard"),
    path("me/punch/<uuid:punch_id>/note/", views.edit_punch_note, name="edit_punch_note"),
    path("me/export/", views.export_default, name="export_default"),
    path("me/export/csv/", views.export_csv, name="export_csv"),
    path("me/export/xlsx/", views.export_xlsx, name="export_xlsx"),
    path("me/export/pdf/", views.export_pdf, name="export_pdf"),
]
