from django.urls import path

from . import views

urlpatterns = [
    path("me/servicos/", views.service_job_list, name="service_job_list"),
    path("me/servicos/catalogo/", views.service_item_catalog_list, name="service_item_catalog_list"),
    path("me/servicos/catalogo/novo/", views.service_item_catalog_create, name="service_item_catalog_create"),
    path("me/servicos/catalogo/busca/", views.service_item_catalog_search, name="service_item_catalog_search"),
    path("me/servicos/catalogo/sugestoes/", views.service_item_catalog_seed_suggestions, name="service_item_catalog_seed_suggestions"),
    path("me/servicos/catalogo/<uuid:item_id>/editar/", views.service_item_catalog_update, name="service_item_catalog_update"),
    path("me/servicos/catalogo/<uuid:item_id>/favorito/", views.service_item_catalog_toggle_favorite, name="service_item_catalog_toggle_favorite"),
    path("me/servicos/catalogo/<uuid:item_id>/desativar/", views.service_item_catalog_deactivate, name="service_item_catalog_deactivate"),
    path("me/servicos/novo/", views.service_job_create, name="service_job_create"),
    path("me/servicos/<uuid:job_id>/", views.service_job_detail, name="service_job_detail"),
    path("me/servicos/<uuid:job_id>/editar/", views.service_job_update, name="service_job_update"),
    path("me/servicos/<uuid:job_id>/horarios/novo/", views.service_work_log_create, name="service_work_log_create"),
    path("me/servicos/<uuid:job_id>/cronometro/", views.service_clock_action, name="service_clock_action"),
    path("me/servicos/<uuid:job_id>/itens/novo/", views.service_item_expense_create, name="service_item_expense_create"),
    path("me/servicos/<uuid:job_id>/itens/<uuid:item_id>/", views.service_item_expense_update, name="service_item_expense_update"),
    path("me/servicos/<uuid:job_id>/cotacao/whatsapp/", views.service_job_quote_whatsapp, name="service_job_quote_whatsapp"),
    path("me/servicos/<uuid:job_id>/status/", views.service_job_status_action, name="service_job_status_action"),
    path("me/servicos/<uuid:job_id>/previa/gerar/", views.service_job_preview_generate, name="service_job_preview_generate"),
    path("me/servicos/<uuid:job_id>/previa/whatsapp/", views.service_job_preview_whatsapp, name="service_job_preview_whatsapp"),
    path("me/servicos/<uuid:job_id>/relatorio/pdf/", views.service_job_report_pdf, name="service_job_report_pdf"),
    path("me/servicos/<uuid:job_id>/relatorio/whatsapp/", views.service_job_report_whatsapp, name="service_job_report_whatsapp"),
    path("servicos/previa/<uuid:token>/", views.public_service_job_preview, name="public_service_job_preview"),
    path("servicos/relatorio/<uuid:token>/", views.public_service_job_report, name="public_service_job_report"),
    path("servicos/relatorio/<uuid:token>/pdf/", views.public_service_job_report_pdf, name="public_service_job_report_pdf"),
]
