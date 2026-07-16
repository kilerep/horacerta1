from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import EditorialArticle, EditorialCategory


@override_settings(SECURE_SSL_REDIRECT=False, APP_BASE_URL="https://horacertagestao.com.br")
class EditorialPortalTests(TestCase):
    def setUp(self):
        self.category = EditorialCategory.objects.create(
            name="Gestão de teste",
            slug="gestao-teste",
            description="Conteúdos de gestão.",
            sort_order=1,
        )
        self.article = EditorialArticle.objects.create(
            category=self.category,
            content_type=EditorialArticle.ContentType.NEWS,
            status=EditorialArticle.Status.PUBLISHED,
            title="Prestadores organizam melhor o primeiro atendimento",
            summary="Um resumo claro para o teste editorial.",
            body="Conteúdo original com orientações práticas para prestadores de serviço.",
            author_name="Equipe HoraCerta",
            source_name="Fonte oficial de teste",
            source_url="https://example.com/fonte",
            is_featured=True,
        )

    def test_public_list_shows_only_published_and_current_articles(self):
        EditorialArticle.objects.create(
            category=self.category,
            status=EditorialArticle.Status.DRAFT,
            title="Rascunho privado",
            summary="Não deve aparecer.",
            body="Rascunho.",
        )
        EditorialArticle.objects.create(
            category=self.category,
            status=EditorialArticle.Status.PUBLISHED,
            title="Publicação agendada",
            summary="Ainda não deve aparecer.",
            body="Agendada.",
            published_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("editorial:article_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.title)
        self.assertNotContains(response, "Rascunho privado")
        self.assertNotContains(response, "Publicação agendada")
        self.assertContains(response, "Política editorial")
        self.assertContains(response, reverse("editorial:feed"))

    def test_filters_by_category_type_and_text(self):
        response = self.client.get(
            reverse("editorial:article_list"),
            {"categoria": self.category.slug, "tipo": EditorialArticle.ContentType.NEWS, "q": "primeiro"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.title)
        self.assertEqual(response.context["selected_category"], self.category.slug)
        self.assertEqual(response.context["selected_type"], EditorialArticle.ContentType.NEWS)

    def test_detail_contains_transparency_and_newsarticle_schema(self):
        response = self.client.get(self.article.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.title)
        self.assertContains(response, "Fonte consultada")
        self.assertContains(response, self.article.source_name)
        self.assertContains(response, '"@type": "NewsArticle"', html=False)
        self.assertContains(response, '"datePublished"', html=False)
        self.assertContains(response, "Política editorial")

    def test_draft_detail_returns_404(self):
        self.article.status = EditorialArticle.Status.DRAFT
        self.article.save()

        response = self.client.get(self.article.get_absolute_url())

        self.assertEqual(response.status_code, 404)

    def test_landing_shows_featured_content_and_public_navigation(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal do Prestador")
        self.assertContains(response, self.article.title)
        self.assertContains(response, reverse("editorial:article_list"))

    def test_feed_contains_only_public_content(self):
        response = self.client.get(reverse("editorial:feed"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/rss+xml")
        self.assertContains(response, self.article.title)
        self.assertContains(response, self.article.summary)

    def test_sitemap_contains_public_article(self):
        response = self.client.get(reverse("django.contrib.sitemaps.views.sitemap"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.get_absolute_url())

    def test_source_requires_source_name(self):
        article = EditorialArticle(
            category=self.category,
            title="Fonte sem identificação",
            summary="Resumo.",
            body="Conteúdo.",
            source_url="https://example.com/sem-nome",
        )

        with self.assertRaisesMessage(Exception, "Informe o nome da fonte"):
            article.full_clean()

    def test_starter_content_command_is_idempotent(self):
        call_command("seed_editorial_starter_content")
        first_count = EditorialArticle.objects.count()
        call_command("seed_editorial_starter_content")

        self.assertEqual(EditorialArticle.objects.count(), first_count)
        self.assertGreaterEqual(first_count, 4)
        self.assertTrue(EditorialArticle.objects.filter(status=EditorialArticle.Status.PUBLISHED).exists())
