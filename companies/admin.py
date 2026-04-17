from django.contrib import admin
from .models import (
    Company,
    CompanyFeatureOverride,
    CompanySubscription,
    Employee,
    Feature,
    Plan,
    PlanFeature,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "owner", "created_at")
    search_fields = ("name", "email", "owner__email")
    ordering = ("-created_at",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "user", "is_active", "created_at")
    search_fields = ("full_name", "user__email", "company__name")
    list_filter = ("company", "is_active")
    ordering = ("full_name",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tier", "is_active", "updated_at")
    search_fields = ("name", "code")
    list_filter = ("is_active",)
    ordering = ("tier",)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "required_role", "is_active", "updated_at")
    search_fields = ("code", "name", "category")
    list_filter = ("category", "required_role", "is_active")
    ordering = ("category", "code")


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ("plan", "feature", "is_enabled", "limit_value", "updated_at")
    search_fields = ("plan__name", "plan__code", "feature__code", "feature__name")
    list_filter = ("plan", "is_enabled")
    ordering = ("plan__tier", "feature__code")


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "plan", "status", "is_current", "starts_at", "ends_at", "updated_at")
    search_fields = ("company__name", "plan__name", "plan__code", "external_customer_id", "external_subscription_id")
    list_filter = ("status", "is_current", "plan")
    ordering = ("-updated_at",)


@admin.register(CompanyFeatureOverride)
class CompanyFeatureOverrideAdmin(admin.ModelAdmin):
    list_display = ("company", "feature", "mode", "expires_at", "updated_at")
    search_fields = ("company__name", "feature__code", "feature__name", "reason")
    list_filter = ("mode", "feature")
    ordering = ("-updated_at",)
