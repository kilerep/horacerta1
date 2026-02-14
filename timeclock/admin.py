from django.contrib import admin
from .models import Contract, Punch


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("company", "employee_user", "hourly_rate", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("company__name", "employee_user__email", "employee_user__username")


@admin.register(Punch)
class PunchAdmin(admin.ModelAdmin):
    list_display = ("contract", "timestamp", "created_at")
    list_filter = ("contract__company",)
    search_fields = ("contract__company__name", "contract__employee_user__email")
    readonly_fields = ("timestamp", "created_at")
