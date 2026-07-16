import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class EditorialCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.CharField(max_length=220, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Categoria editorial"
        verbose_name_plural = "Categorias editoriais"
        indexes = [
            models.Index(fields=["is_active", "sort_order", "name"], name="edit_category_active_idx"),
        ]

    def __str__(self):
        return self.name


class EditorialArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(
            status=EditorialArticle.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=timezone.now(),
        )


class EditorialArticle(models.Model):
    class ContentType(models.TextChoices):
        NEWS = "NEWS", "Notícia"
        GUIDE = "GUIDE", "Guia prático"
        ANALYSIS = "ANALYSIS", "Análise"
        OPPORTUNITY = "OPPORTUNITY", "Oportunidade"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        PUBLISHED = "PUBLISHED", "Publicado"
        ARCHIVED = "ARCHIVED", "Arquivado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        EditorialCategory,
        on_delete=models.PROTECT,
        related_name="articles",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="editorial_articles",
        null=True,
        blank=True,
    )
    content_type = models.CharField(max_length=20, choices=ContentType.choices, default=ContentType.GUIDE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    summary = models.CharField(max_length=360)
    body = models.TextField()
    author_name = models.CharField(max_length=120, default="Equipe HoraCerta")
    cover_image = models.ImageField(upload_to="editorial/covers/", null=True, blank=True)
    cover_alt = models.CharField(max_length=180, blank=True, default="")
    source_name = models.CharField(max_length=160, blank=True, default="")
    source_url = models.URLField(blank=True, default="")
    source_published_at = models.DateTimeField(null=True, blank=True)
    correction_note = models.TextField(blank=True, default="")
    seo_title = models.CharField(max_length=70, blank=True, default="")
    meta_description = models.CharField(max_length=160, blank=True, default="")
    is_featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EditorialArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Publicação"
        verbose_name_plural = "Publicações"
        indexes = [
            models.Index(fields=["status", "-published_at"], name="edit_article_pub_idx"),
            models.Index(fields=["is_featured", "status", "-published_at"], name="edit_article_feature_idx"),
            models.Index(fields=["category", "status", "-published_at"], name="edit_article_category_idx"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if self.source_url and not self.source_name:
            errors["source_name"] = "Informe o nome da fonte quando houver um link externo."
        if self.cover_image and not self.cover_alt:
            errors["cover_alt"] = "Descreva a imagem de capa para acessibilidade."
        if self.status == self.Status.PUBLISHED:
            if not self.summary.strip():
                errors["summary"] = "Informe um resumo antes de publicar."
            if not self.body.strip():
                errors["body"] = "Informe o conteúdo antes de publicar."
            if not self.author_name.strip():
                errors["author_name"] = "Informe o autor ou a equipe responsável."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:200] or "conteudo"
            candidate = base_slug
            suffix = 2
            while EditorialArticle.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base_slug[:190]}-{suffix}"
                suffix += 1
            self.slug = candidate
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.author_name = (self.author_name or "Equipe HoraCerta").strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("editorial:article_detail", args=[self.slug])

    @property
    def estimated_reading_minutes(self):
        words = len((self.body or "").split())
        return max(1, round(words / 220))

    @property
    def schema_type(self):
        return "NewsArticle" if self.content_type == self.ContentType.NEWS else "Article"

    @property
    def public_title(self):
        return self.seo_title or self.title

    @property
    def public_description(self):
        return self.meta_description or self.summary
