from django.contrib import admin

from .models import ServiceCategory, ServiceJob


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ServiceJob)
class ServiceJobAdmin(admin.ModelAdmin):
    list_display = ("title", "professional", "client", "category", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("title", "description", "manual_client_name", "client__name", "professional__email")
    readonly_fields = ("public_token", "created_at", "updated_at", "finished_at")
