from django.contrib import admin
from .models import Company, Employee


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
