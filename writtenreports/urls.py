from django.urls import path

from . import views

urlpatterns = [
    path("me/relatorios/escritos/", views.report_list, name="written_report_list"),
    path("me/relatorios/escritos/novo/", views.report_create, name="written_report_create"),
    path("me/relatorios/escritos/<uuid:report_id>/", views.report_detail, name="written_report_detail"),
    path("me/relatorios/escritos/<uuid:report_id>/editar/", views.report_edit, name="written_report_edit"),
    path("me/relatorios/escritos/<uuid:report_id>/emitir/", views.report_issue, name="written_report_issue"),
    path("me/relatorios/escritos/<uuid:report_id>/excluir/", views.report_delete, name="written_report_delete"),
    path("me/relatorios/escritos/<uuid:report_id>/pdf/", views.report_pdf, name="written_report_pdf"),
    path("me/relatorios/escritos/<uuid:report_id>/whatsapp/", views.report_whatsapp, name="written_report_whatsapp"),
    path("relatorio-escrito/<uuid:token>/", views.report_public, name="written_report_public"),
    path("relatorio-escrito/<uuid:token>/pdf/", views.report_public_pdf, name="written_report_public_pdf"),
]
