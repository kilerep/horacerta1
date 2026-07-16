from django.contrib.sitemaps import Sitemap

from .models import EditorialArticle


class EditorialArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return EditorialArticle.objects.published()

    def lastmod(self, item):
        return item.updated_at
