from django.contrib import admin

from .models import ProductionEntry, ProductionSheet, ShipmentItem, ShipmentNote, ShipmentRecipient


class ProductionEntryInline(admin.TabularInline):
    model = ProductionEntry
    extra = 0


@admin.register(ProductionSheet)
class ProductionSheetAdmin(admin.ModelAdmin):
    list_display = ("equipment", "owner", "company_name", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("equipment", "company_name", "owner__email")
    inlines = [ProductionEntryInline]


class ShipmentItemInline(admin.TabularInline):
    model = ShipmentItem
    extra = 0
    can_delete = False


class ShipmentRecipientInline(admin.TabularInline):
    model = ShipmentRecipient
    extra = 0
    can_delete = False
    readonly_fields = ("token", "viewed_at", "authorized_at")


@admin.register(ShipmentNote)
class ShipmentNoteAdmin(admin.ModelAdmin):
    """Somente consulta: nota enviada e prova, nem o admin altera ou apaga."""

    list_display = ("number", "owner", "destination_company", "status", "departed_at")
    list_filter = ("status",)
    search_fields = ("destination_company", "owner__email", "items__production_order", "items__drawing_number")
    inlines = [ShipmentItemInline, ShipmentRecipientInline]

    def has_change_permission(self, request, obj=None):
        return obj is None or not obj.is_locked

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.is_locked
