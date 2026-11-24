from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from .models import ServiceCategory, ServiceItemCatalog


User = get_user_model()


class SeedPremiumServiceCatalogCommandTests(TestCase):
    def setUp(self):
        self.professional = User.objects.create_user(
            username="catalogo-premium@example.test",
            email="catalogo-premium@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )

    def test_command_creates_idempotent_items_for_selected_category(self):
        output = StringIO()
        args = (
            "seed_premium_service_catalog",
            "--email",
            self.professional.email,
            "--category",
            "eventos-sonorizacao",
        )

        call_command(*args, stdout=output)
        call_command(*args, stdout=output)

        category = ServiceCategory.objects.get(slug="eventos-sonorizacao")
        items = ServiceItemCatalog.objects.filter(professional=self.professional, category=category)
        self.assertEqual(items.count(), 4)
        self.assertTrue(items.filter(name="Caixa ativa", internal_code__startswith="EVE-").exists())
        self.assertTrue(items.filter(name="Mesa de som").exists())
        self.assertIn("Itens criados: 4", output.getvalue())
        self.assertIn("Itens ignorados por já existirem: 4", output.getvalue())

    def test_command_rejects_unknown_category(self):
        with self.assertRaisesMessage(CommandError, "Categorias desconhecidas"):
            call_command(
                "seed_premium_service_catalog",
                "--email",
                self.professional.email,
                "--category",
                "categoria-inexistente",
            )

    def test_command_rejects_unknown_professional(self):
        with self.assertRaisesMessage(CommandError, "Prestador não encontrado"):
            call_command("seed_premium_service_catalog", "--email", "nao-existe@example.test")
