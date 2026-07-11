from django.contrib import admin

from .models import HiringOrganization, OrganizationAuditEvent, OrganizationMember, ProviderOrganizationLink


@admin.register(HiringOrganization)
class HiringOrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "legal_name", "cnpj", "status", "created_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "legal_name", "cnpj", "email", "whatsapp")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "status", "joined_at", "ended_at")
    list_filter = ("role", "status")
    search_fields = ("organization__name", "user__email", "user__username")
    readonly_fields = ("invited_at", "joined_at", "ended_at", "created_at", "updated_at")


@admin.register(ProviderOrganizationLink)
class ProviderOrganizationLinkAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "provider",
        "status",
        "initiated_by",
        "share_services",
        "share_hours",
        "share_reports",
        "share_financial_values",
    )
    list_filter = ("status", "initiated_by", "share_financial_values")
    search_fields = ("organization__name", "provider__email", "provider__username")
    readonly_fields = ("started_at", "ended_at", "created_at", "updated_at")


@admin.register(OrganizationAuditEvent)
class OrganizationAuditEventAdmin(admin.ModelAdmin):
    list_display = ("organization", "event_type", "summary", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("organization__name", "summary", "target_type", "target_id")
    readonly_fields = (
        "organization",
        "actor",
        "event_type",
        "target_type",
        "target_id",
        "summary",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
