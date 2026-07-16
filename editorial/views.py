from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static

from .models import EditorialArticle, EditorialCategory


def _public_base_url(request):
    return (settings.APP_BASE_URL or f"{request.scheme}://{request.get_host()}").rstrip("/")


def _public_context(request, path, *, image_url=""):
    base_url = _public_base_url(request)
    canonical_url = f"{base_url}{path}"
    fallback_image = f"{base_url}{static('pwa/icon-512.png')}"
    return {
        "site_url": base_url,
        "canonical_url": canonical_url,
        "og_url": canonical_url,
        "og_image_url": image_url or fallback_image,
    }


def article_list(request):
    queryset = EditorialArticle.objects.published().select_related("category", "author")
    query = (request.GET.get("q") or "").strip()
    category_slug = (request.GET.get("categoria") or "").strip()
    content_type = (request.GET.get("tipo") or "").strip()

    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(summary__icontains=query) | Q(body__icontains=query))
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)
    if content_type in EditorialArticle.ContentType.values:
        queryset = queryset.filter(content_type=content_type)

    paginator = Paginator(queryset, 12)
    page = paginator.get_page(request.GET.get("pagina"))
    context = _public_context(request, "/conteudos/")
    context.update(
        {
            "page": page,
            "categories": EditorialCategory.objects.filter(is_active=True),
            "content_types": EditorialArticle.ContentType.choices,
            "query": query,
            "selected_category": category_slug,
            "selected_type": content_type,
            "featured_articles": EditorialArticle.objects.published()
            .filter(is_featured=True)
            .select_related("category")[:3],
        }
    )
    return render(request, "editorial/article_list.html", context)


def article_detail(request, slug):
    article = get_object_or_404(
        EditorialArticle.objects.published().select_related("category", "author"),
        slug=slug,
    )
    base_url = _public_base_url(request)
    image_url = f"{base_url}{article.cover_image.url}" if article.cover_image else ""
    context = _public_context(request, article.get_absolute_url(), image_url=image_url)
    context.update(
        {
            "article": article,
            "related_articles": EditorialArticle.objects.published()
            .filter(category=article.category)
            .exclude(pk=article.pk)
            .select_related("category")[:3],
        }
    )
    return render(request, "editorial/article_detail.html", context)


def editorial_policy(request):
    context = _public_context(request, "/conteudos/politica-editorial/")
    return render(request, "editorial/editorial_policy.html", context)
