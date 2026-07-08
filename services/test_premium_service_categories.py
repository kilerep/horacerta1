from django.test import TestCase

from .models import ServiceCategory


class PremiumServiceCategoryTests(TestCase):
    def test_global_service_categories_are_available_for_professionals(self):
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

        categories = ServiceCategory.objects.filter(slug__in=expected.keys())

        self.assertEqual(categories.count(), len(expected))
        for category in categories:
            self.assertEqual(category.name, expected[category.slug])
            self.assertTrue(category.is_active)
            self.assertGreaterEqual(category.sort_order, 20)
            self.assertTrue(category.description)
            self.assertTrue(category.icon_name)
