from django.urls import path

from . import views

urlpatterns = [
    path("me/servicos/", views.service_job_list, name="service_job_list"),
    path("me/servicos/novo/", views.service_job_create, name="service_job_create"),
    path("me/servicos/<uuid:job_id>/", views.service_job_detail, name="service_job_detail"),
]
