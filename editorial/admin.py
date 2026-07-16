from django.contrib import admin
from django.utils import timezone

from .models import EditorialArticle, EditorialCategory


@admin.register(EditorialCategory)
class EditorialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(EditorialArticle)
class EditorialArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "content_type",
        "category",
        "status",
        "is_featured",
        "author_name",
        "published_at",
        "updated_at",
    )
    list_filter = ("status", "content_type", "category", "is_featured", "published_at")
    search_fields = ("title", "summary", "body", "author_name", "source_name")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("author",)
    date_hierarchy = "published_at"
    readonly_fields = ("created_at", "updated_at")
    actions = ("publish_selected", "archive_selected")
    fieldsets = (
        (
            "Publicação",
            {
                "fields": (
                    "title",
                    "slug",
                    "category",
                    "content_type",
                    "status",
                    "is_featured",
                    "published_at",
                )
            },
        ),
        ("Conteúdo", {"fields": ("summary", "body", "cover_image", "cover_alt")}),
        ("Autoria", {"fields": ("author", "author_name")}),
        (
            "Fonte e transparência",
            {"fields": ("source_name", "source_url", "source_published_at", "correction_note")},
        ),
        ("SEO", {"fields": ("seo_title", "meta_description")}),
        ("Controle", {"fields": ("created_at", "updated_at")}),
    )

    @admin.action(description="Publicar conteúdos selecionados")
    def publish_selected(self, request, queryset):
        queryset.filter(published_at__isnull=True).update(published_at=timezone.now())
        queryset.update(status=EditorialArticle.Status.PUBLISHED)

    @admin.action(description="Arquivar conteúdos selecionados")
    def archive_selected(self, request, queryset):
        queryset.update(status=EditorialArticle.Status.ARCHIVED, is_featured=False)
