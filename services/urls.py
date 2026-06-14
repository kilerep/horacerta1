from django.urls import path

from . import views

urlpatterns = [
    path("me/servicos/", views.service_job_list, name="service_job_list"),
    path("me/servicos/novo/", views.service_job_create, name="service_job_create"),
    path("me/servicos/<uuid:job_id>/", views.service_job_detail, name="service_job_detail"),
    path("me/servicos/<uuid:job_id>/editar/", views.service_job_update, name="service_job_update"),
    path("me/servicos/<uuid:job_id>/horarios/novo/", views.service_work_log_create, name="service_work_log_create"),
    path("me/servicos/<uuid:job_id>/cronometro/", views.service_clock_action, name="service_clock_action"),
    path("me/servicos/<uuid:job_id>/itens/novo/", views.service_item_expense_create, name="service_item_expense_create"),
    path("me/servicos/<uuid:job_id>/itens/<uuid:item_id>/", views.service_item_expense_update, name="service_item_expense_update"),
    path("me/servicos/<uuid:job_id>/status/", views.service_job_status_action, name="service_job_status_action"),
    path("me/servicos/<uuid:job_id>/previa/whatsapp/", views.service_job_preview_whatsapp, name="service_job_preview_whatsapp"),
    path("me/servicos/<uuid:job_id>/relatorio/pdf/", views.service_job_report_pdf, name="service_job_report_pdf"),
    path("me/servicos/<uuid:job_id>/relatorio/whatsapp/", views.service_job_report_whatsapp, name="service_job_report_whatsapp"),
    path("servicos/previa/<uuid:token>/", views.public_service_job_preview, name="public_service_job_preview"),
    path("servicos/relatorio/<uuid:token>/", views.public_service_job_report, name="public_service_job_report"),
    path("servicos/relatorio/<uuid:token>/pdf/", views.public_service_job_report_pdf, name="public_service_job_report_pdf"),
]
