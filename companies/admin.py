from django.contrib import admin
from .models import Company, Employee


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "owner", "created_at")
    search_fields = ("name", "email", "owner__email")
    ordering = ("-created_at",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "companies_list", "user", "is_active", "created_at")
    search_fields = ("full_name", "user__email", "companies__name")
    list_filter = ("companies", "is_active")
    filter_horizontal = ("companies",)
    ordering = ("full_name",)

    def companies_list(self, obj):
        return ", ".join(obj.companies.values_list("name", flat=True)) or "-"

    companies_list.short_description = "Companies"
