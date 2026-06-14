from django.contrib import admin

from .models import ServiceCategory, ServiceItemExpense, ServiceJob, ServiceWorkLog


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
        "created_at",
        "updated_at",
        "finished_at",
    )


@admin.register(ServiceWorkLog)
class ServiceWorkLogAdmin(admin.ModelAdmin):
    list_display = ("service_job", "work_date", "start_time", "end_time", "duration_minutes")
    list_filter = ("work_date",)
    search_fields = ("service_job__title", "description")
    readonly_fields = ("duration_minutes", "created_at", "updated_at")


@admin.register(ServiceItemExpense)
class ServiceItemExpenseAdmin(admin.ModelAdmin):
    list_display = ("name", "service_job", "type", "usage_status", "quantity", "unit_value", "total_value")
    list_filter = ("type", "usage_status")
    search_fields = ("name", "description", "receipt_note", "service_job__title")
    readonly_fields = ("total_value", "created_at", "updated_at")
