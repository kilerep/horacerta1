from django.core.management import BaseCommand, CommandError
from django.db import transaction

from services.models import ServiceCategory
from services.premium_service_categories import PREMIUM_SERVICE_CATEGORIES, ensure_premium_service_categories


class Command(BaseCommand):
    help = "Cria ou atualiza as categorias premium de serviços de forma idempotente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            action="append",
            dest="categories",
            help="Slug específico. Pode ser repetido. Se omitido, aplica todas as categorias premium.",
        )

    def handle(self, *args, **options):
        available = {item["slug"] for item in PREMIUM_SERVICE_CATEGORIES}
        selected = set(options.get("categories") or available)
        unknown = selected - available
        if unknown:
            raise CommandError(f"Categorias desconhecidas: {', '.join(sorted(unknown))}")

        with transaction.atomic():
            _, created, updated = ensure_premium_service_categories(ServiceCategory, selected)

        self.stdout.write(self.style.SUCCESS("Categorias premium do HoraCerta prontas."))
        self.stdout.write(f"Categorias criadas: {created}")
        self.stdout.write(f"Categorias atualizadas: {updated}")
