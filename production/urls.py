from django.urls import path

from . import shipment_views as sv
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
    path("me/relatorios-producao/notas/", sv.shipment_list, name="shipment_list"),
    path("me/relatorios-producao/notas/nova/", sv.shipment_create, name="shipment_create"),
    path("me/relatorios-producao/notas/<uuid:note_id>/", sv.shipment_detail, name="shipment_detail"),
    path("me/relatorios-producao/notas/<uuid:note_id>/editar/", sv.shipment_edit, name="shipment_edit"),
    path("me/relatorios-producao/notas/<uuid:note_id>/enviar/", sv.shipment_send, name="shipment_send"),
    path("me/relatorios-producao/notas/<uuid:note_id>/excluir/", sv.shipment_delete, name="shipment_delete"),
    path("me/relatorios-producao/notas/<uuid:note_id>/corrigir/", sv.shipment_replace, name="shipment_replace"),
    path("me/relatorios-producao/notas/<uuid:note_id>/whatsapp/<str:role>/", sv.shipment_whatsapp, name="shipment_whatsapp"),
    path("nota-envio/<uuid:token>/", sv.shipment_public, name="shipment_public"),
    path("nota-envio/<uuid:token>/visto/", sv.shipment_public_seen, name="shipment_public_seen"),
    path("nota-envio/<uuid:token>/autorizar/", sv.shipment_public_authorize, name="shipment_public_authorize"),
    path("me/relatorios-producao/notas/<uuid:note_id>/pdf/", sv.shipment_pdf, name="shipment_pdf"),
    path("me/relatorios-producao/notas/<uuid:note_id>/excel/", sv.shipment_xlsx, name="shipment_xlsx"),
    path("nota-envio/<uuid:token>/pdf/", sv.shipment_public_pdf, name="shipment_public_pdf"),
    path("nota-envio/<uuid:token>/excel/", sv.shipment_public_xlsx, name="shipment_public_xlsx"),
]
