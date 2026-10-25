from django.urls import path

from . import views

urlpatterns = [
    path("me/relatorios-producao/", views.sheet_list, name="production_sheet_list"),
    path("me/relatorios-producao/novo/", views.sheet_create, name="production_sheet_create"),
    path("me/relatorios-producao/<uuid:sheet_id>/", views.sheet_detail, name="production_sheet_detail"),
    path("me/relatorios-producao/<uuid:sheet_id>/editar/", views.sheet_edit, name="production_sheet_edit"),
    path("me/relatorios-producao/<uuid:sheet_id>/whatsapp/", views.sheet_whatsapp, name="production_sheet_whatsapp"),
    path("me/relatorios-producao/<uuid:sheet_id>/status/", views.sheet_status, name="production_sheet_status"),
    path("me/relatorios-producao/<uuid:sheet_id>/csv/", views.sheet_csv, name="production_sheet_csv"),
    path("me/relatorios-producao/<uuid:sheet_id>/excel/", views.sheet_xlsx, name="production_sheet_xlsx"),
    path("me/relatorios-producao/<uuid:sheet_id>/pdf/", views.sheet_pdf, name="production_sheet_pdf"),
    path("relatorio-producao/<uuid:token>/pdf/", views.public_sheet_pdf, name="production_public_pdf"),
    path("relatorio-producao/<uuid:token>/excel/", views.public_sheet_xlsx, name="production_public_xlsx"),
    path("me/relatorios-producao/<uuid:sheet_id>/itens/<uuid:entry_id>/", views.entry_edit, name="production_entry_edit"),
    path("me/relatorios-producao/<uuid:sheet_id>/itens/<uuid:entry_id>/remover/", views.entry_delete, name="production_entry_delete"),
]
