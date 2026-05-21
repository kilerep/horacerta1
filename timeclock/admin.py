from django.contrib import admin
from .models import Contract, Punch, PunchCorrectionLog, PunchCorrectionRequest


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("company", "employee", "hourly_rate", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("company__name", "employee__full_name", "employee__user__email", "employee__user__username")


@admin.register(Punch)
class PunchAdmin(admin.ModelAdmin):
    list_display = ("contract", "timestamp", "is_cancelled", "cancelled_at", "created_at")
    list_filter = ("is_cancelled", "contract__company")
    search_fields = ("contract__company__name", "contract__employee__user__email")
    readonly_fields = ("timestamp", "created_at", "cancelled_at", "cancelled_by")


@admin.register(PunchCorrectionLog)
class PunchCorrectionLogAdmin(admin.ModelAdmin):
    list_display = ("punch", "admin_user", "action_type", "old_status", "new_status", "created_at")
    list_filter = ("action_type", "created_at")
    search_fields = ("punch__id", "admin_user__email", "reason")
    readonly_fields = ("punch", "admin_user", "action_type", "old_datetime", "new_datetime", "old_status", "new_status", "reason", "created_at")


@admin.register(PunchCorrectionRequest)
class PunchCorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "company", "problem_date", "problem_type", "status", "created_at")
    list_filter = ("status", "problem_type", "company")
    search_fields = ("employee__full_name", "user__email", "company__name", "description")
    readonly_fields = ("created_at", "updated_at", "resolved_at")
