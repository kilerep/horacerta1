import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EditorialCategory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=90, unique=True)),
                ("description", models.CharField(blank=True, default="", max_length=220)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Categoria editorial",
                "verbose_name_plural": "Categorias editoriais",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="EditorialArticle",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "content_type",
                    models.CharField(
                        choices=[
                            ("NEWS", "Notícia"),
                            ("GUIDE", "Guia prático"),
                            ("ANALYSIS", "Análise"),
                            ("OPPORTUNITY", "Oportunidade"),
                        ],
                        default="GUIDE",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Rascunho"), ("PUBLISHED", "Publicado"), ("ARCHIVED", "Arquivado")],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(max_length=180)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("summary", models.CharField(max_length=360)),
                ("body", models.TextField()),
                ("author_name", models.CharField(default="Equipe HoraCerta", max_length=120)),
                ("cover_image", models.ImageField(blank=True, null=True, upload_to="editorial/covers/")),
                ("cover_alt", models.CharField(blank=True, default="", max_length=180)),
                ("source_name", models.CharField(blank=True, default="", max_length=160)),
                ("source_url", models.URLField(blank=True, default="")),
                ("source_published_at", models.DateTimeField(blank=True, null=True)),
                ("correction_note", models.TextField(blank=True, default="")),
                ("seo_title", models.CharField(blank=True, default="", max_length=70)),
                ("meta_description", models.CharField(blank=True, default="", max_length=160)),
                ("is_featured", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="editorial_articles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="articles",
                        to="editorial.editorialcategory",
                    ),
                ),
            ],
            options={
                "verbose_name": "Publicação",
                "verbose_name_plural": "Publicações",
                "ordering": ["-published_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="editorialcategory",
            index=models.Index(fields=["is_active", "sort_order", "name"], name="edit_category_active_idx"),
        ),
        migrations.AddIndex(
            model_name="editorialarticle",
            index=models.Index(fields=["status", "-published_at"], name="edit_article_pub_idx"),
        ),
        migrations.AddIndex(
            model_name="editorialarticle",
            index=models.Index(fields=["is_featured", "status", "-published_at"], name="edit_article_feature_idx"),
        ),
        migrations.AddIndex(
            model_name="editorialarticle",
            index=models.Index(fields=["category", "status", "-published_at"], name="edit_article_category_idx"),
        ),
    ]
