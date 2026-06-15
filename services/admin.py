from django.contrib import admin

from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceJob, ServiceRequest, ServiceWorkLog


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
    readonly_fields = (
        "public_token",
        "preview_generated_at",
        "preview_sent_at",
        "preview_first_viewed_at",
        "preview_updated_at",
        "quote_message_generated_at",
        "quote_item_count",
        "quote_last_message",
        "created_at",
        "updated_at",
        "finished_at",
    )


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "professional", "client_name", "category", "status", "source", "created_at")
    list_filter = ("status", "source", "urgency", "category")
    search_fields = ("title", "description", "client_name", "client_whatsapp", "professional__email")
    readonly_fields = ("converted_service", "created_at", "updated_at")


@admin.register(ServiceWorkLog)
class ServiceWorkLogAdmin(admin.ModelAdmin):
    list_display = ("service_job", "work_date", "start_time", "end_time", "duration_minutes")
    list_filter = ("work_date",)
    search_fields = ("service_job__title", "description")
    readonly_fields = ("duration_minutes", "created_at", "updated_at")


@admin.register(ServiceItemExpense)
class ServiceItemExpenseAdmin(admin.ModelAdmin):
    list_display = ("name", "service_job", "type", "usage_status", "quantity", "unit", "unit_value", "total_value")
    list_filter = ("type", "usage_status")
    search_fields = ("name", "description", "receipt_note", "service_job__title")
    readonly_fields = ("total_value", "created_at", "updated_at")


@admin.register(ServiceItemCatalog)
class ServiceItemCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "professional", "category", "item_type", "unit", "estimated_unit_value", "last_used_value", "favorite", "is_active")
    list_filter = ("item_type", "unit", "favorite", "is_active", "category")
    search_fields = ("name", "description", "professional__email", "professional__username")
    readonly_fields = ("last_used_value", "last_used_at", "created_at", "updated_at")
