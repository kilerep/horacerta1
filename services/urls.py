from django.urls import path

from . import views

urlpatterns = [
    path("me/servicos/", views.service_job_list, name="service_job_list"),
    path("me/servicos/novo/", views.service_job_create, name="service_job_create"),
    path("me/servicos/<uuid:job_id>/", views.service_job_detail, name="service_job_detail"),
    path("me/servicos/<uuid:job_id>/horarios/novo/", views.service_work_log_create, name="service_work_log_create"),
    path("me/servicos/<uuid:job_id>/itens/novo/", views.service_item_expense_create, name="service_item_expense_create"),
    path("me/servicos/<uuid:job_id>/status/", views.service_job_status_action, name="service_job_status_action"),
]
