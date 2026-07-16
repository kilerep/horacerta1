from django.urls import path

from . import views


urlpatterns = [
    path("", views.organization_entry, name="organization_entry"),
    path("nova/", views.organization_setup, name="organization_setup"),
    path("convites/", views.organization_invites, name="organization_invites"),
    path(
        "convites/<uuid:membership_id>/aceitar/",
        views.organization_invite_accept,
        name="organization_invite_accept",
    ),
    path("prestador/convites/", views.provider_link_invites, name="provider_link_invites"),
    path(
        "prestador/convites/<uuid:link_id>/aceitar/",
        views.provider_link_accept,
        name="provider_link_accept",
    ),
    path(
        "prestador/convites/<uuid:link_id>/recusar/",
        views.provider_link_decline,
        name="provider_link_decline",
    ),
    path("<uuid:organization_id>/", views.organization_dashboard, name="organization_dashboard"),
    path("<uuid:organization_id>/membros/", views.organization_members, name="organization_members"),
    path(
        "<uuid:organization_id>/membros/convidar/",
        views.organization_member_invite,
        name="organization_member_invite",
    ),
    path("<uuid:organization_id>/prestadores/", views.organization_providers, name="organization_providers"),
    path(
        "<uuid:organization_id>/prestadores/convidar/",
        views.organization_provider_invite,
        name="organization_provider_invite",
    ),
    path(
        "<uuid:organization_id>/prestadores/<uuid:link_id>/suspender/",
        views.organization_provider_suspend,
        name="organization_provider_suspend",
    ),
    path(
        "<uuid:organization_id>/prestadores/<uuid:link_id>/reativar/",
        views.organization_provider_resume,
        name="organization_provider_resume",
    ),
    path(
        "<uuid:organization_id>/prestadores/<uuid:link_id>/encerrar/",
        views.organization_provider_end,
        name="organization_provider_end",
    ),
]
