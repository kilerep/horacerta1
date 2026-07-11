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
    path("<uuid:organization_id>/", views.organization_dashboard, name="organization_dashboard"),
    path("<uuid:organization_id>/membros/", views.organization_members, name="organization_members"),
    path(
        "<uuid:organization_id>/membros/convidar/",
        views.organization_member_invite,
        name="organization_member_invite",
    ),
]
