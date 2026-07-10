from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import ServiceCategory


class PremiumServiceCategoryTests(TestCase):
    def test_global_service_categories_can_be_seeded_idempotently(self):
        expected = {
            "reformas-obras": "Reformas e obras",
            "limpeza-conservacao": "Limpeza e conservação",
            "jardinagem-paisagismo": "Jardinagem e paisagismo",
            "marcenaria-serralheria": "Marcenaria e serralheria",
            "assistencia-tecnica": "Assistência técnica",
            "automotivo": "Automotivo",
            "beleza-bem-estar": "Beleza e bem-estar",
            "eventos-sonorizacao": "Eventos e sonorização",
            "fotografia-video": "Fotografia e vídeo",
            "aulas-consultoria": "Aulas e consultoria",
            "administrativo-escritorio": "Administrativo e escritório",
            "seguranca-monitoramento": "Segurança e monitoramento",
        }
        output = StringIO()

        call_command("seed_premium_service_categories", stdout=output)
        call_command("seed_premium_service_categories", stdout=output)

        categories = ServiceCategory.objects.filter(slug__in=expected.keys())
        self.assertEqual(categories.count(), len(expected))
        for category in categories:
            self.assertEqual(category.name, expected[category.slug])
            self.assertTrue(category.is_active)
            self.assertGreaterEqual(category.sort_order, 20)
            self.assertTrue(category.description)
            self.assertTrue(category.icon_name)
        self.assertIn("Categorias criadas: 12", output.getvalue())
        self.assertIn("Categorias atualizadas: 12", output.getvalue())
