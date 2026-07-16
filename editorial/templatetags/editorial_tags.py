from django import template

from editorial.models import EditorialArticle


register = template.Library()


@register.simple_tag
def latest_editorial_articles(limit=3):
    try:
        limit = max(1, min(int(limit), 12))
    except (TypeError, ValueError):
        limit = 3
    featured = list(
        EditorialArticle.objects.published()
        .filter(is_featured=True)
        .select_related("category")[:limit]
    )
    if len(featured) >= limit:
        return featured
    missing = limit - len(featured)
    remaining = (
        EditorialArticle.objects.published()
        .exclude(pk__in=[article.pk for article in featured])
        .select_related("category")[:missing]
    )
    return featured + list(remaining)
