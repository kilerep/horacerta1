from django.contrib import admin

from .models import ProductionEntry, ProductionSheet


class ProductionEntryInline(admin.TabularInline):
    model = ProductionEntry
    extra = 0


@admin.register(ProductionSheet)
class ProductionSheetAdmin(admin.ModelAdmin):
    list_display = ("equipment", "owner", "company_name", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("equipment", "company_name", "owner__email")
    inlines = [ProductionEntryInline]
