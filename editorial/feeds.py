from django.contrib.syndication.views import Feed
from django.urls import reverse_lazy

from .models import EditorialArticle


class LatestEditorialFeed(Feed):
    title = "HoraCerta — Portal do prestador"
    link = reverse_lazy("editorial:article_list")
    description = "Notícias, guias e análises para prestadores de serviço e empresas contratantes."

    def items(self):
        return EditorialArticle.objects.published().select_related("category")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.summary

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_categories(self, item):
        return [item.category.name, item.get_content_type_display()]

    def item_author_name(self, item):
        return item.author_name
