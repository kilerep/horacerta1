from django.contrib import admin

from .models import WrittenReport


@admin.register(WrittenReport)
class WrittenReportAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "kind", "owner", "status", "issued_at")
    list_filter = ("kind", "status")
    search_fields = ("title", "owner__email")
    readonly_fields = ("snapshot", "share_token", "issued_at", "viewed_at")
