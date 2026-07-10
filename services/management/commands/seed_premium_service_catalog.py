from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError
from django.db import transaction

from services.models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceItemUnit
from services.premium_service_categories import ensure_premium_service_categories


CATALOG_TEMPLATES = {
    "reformas-obras": [
        ("Massa corrida", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Argamassa", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Rejunte", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Diária de ajudante", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "limpeza-conservacao": [
        ("Produto multiuso", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.LITER, Decimal("1.00")),
        ("Desinfetante", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.LITER, Decimal("1.00")),
        ("Saco de lixo", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Diária de limpeza", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "jardinagem-paisagismo": [
        ("Saco de substrato", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Muda/planta", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Retirada de resíduos verdes", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Hora de manutenção de jardim", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.HOUR, Decimal("1.00")),
    ],
    "marcenaria-serralheria": [
        ("Parafusos e fixadores", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Dobradiça", ServiceItemExpense.ItemType.PART, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Chapa/perfil metálico", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.METER, Decimal("1.00")),
        ("Corte ou ajuste técnico", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "assistencia-tecnica": [
        ("Peça de reposição", ServiceItemExpense.ItemType.PART, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Kit de limpeza técnica", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Diagnóstico técnico", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Deslocamento técnico", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "automotivo": [
        ("Produto de limpeza automotiva", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.LITER, Decimal("1.00")),
        ("Peça/acessório automotivo", ServiceItemExpense.ItemType.PART, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Deslocamento automotivo", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Combustível de atendimento", ServiceItemExpense.ItemType.FUEL, ServiceItemUnit.LITER, Decimal("1.00")),
    ],
    "beleza-bem-estar": [
        ("Produto de atendimento", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Material descartável", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.PACKAGE, Decimal("1.00")),
        ("Atendimento por pacote", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Deslocamento do atendimento", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "eventos-sonorizacao": [
        ("Caixa ativa", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("2.00")),
        ("Mesa de som", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Microfone sem fio", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("2.00")),
        ("Kit de cabos", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
    ],
    "fotografia-video": [
        ("Hora de captação", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.HOUR, Decimal("1.00")),
        ("Edição de fotos/vídeo", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Deslocamento de equipe", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Entrega digital", ServiceItemExpense.ItemType.OTHER, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "aulas-consultoria": [
        ("Hora técnica", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.HOUR, Decimal("1.00")),
        ("Material de apoio", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Pacote de acompanhamento", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Relatório/diagnóstico", ServiceItemExpense.ItemType.OTHER, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
    "administrativo-escritorio": [
        ("Hora administrativa", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.HOUR, Decimal("1.00")),
        ("Organização documental", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Cadastro/backoffice", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
        ("Material de escritório", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.UNIT, Decimal("1.00")),
    ],
    "seguranca-monitoramento": [
        ("Câmera de segurança", ServiceItemExpense.ItemType.PART, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Fonte/conector", ServiceItemExpense.ItemType.PART, ServiceItemUnit.UNIT, Decimal("1.00")),
        ("Cabo de rede/coaxial", ServiceItemExpense.ItemType.MATERIAL, ServiceItemUnit.METER, Decimal("1.00")),
        ("Configuração e testes", ServiceItemExpense.ItemType.EXPENSE, ServiceItemUnit.SERVICE, Decimal("1.00")),
    ],
}


class Command(BaseCommand):
    help = "Adiciona sugestões premium de catálogo para um prestador, sem preços estimados."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="E-mail do prestador que receberá os itens sugeridos.")
        parser.add_argument(
            "--category",
            action="append",
            dest="categories",
            help="Slug específico. Pode ser repetido. Se omitido, aplica todas as categorias premium.",
        )

    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        categories_filter = set(options.get("categories") or [])
        unknown_categories = categories_filter - set(CATALOG_TEMPLATES)
        if unknown_categories:
            raise CommandError(f"Categorias desconhecidas: {', '.join(sorted(unknown_categories))}")

        User = get_user_model()
        professional = User.objects.filter(email=email).first()
        if not professional:
            raise CommandError("Prestador não encontrado para o e-mail informado.")

        selected_slugs = sorted(categories_filter or CATALOG_TEMPLATES.keys())
        created = 0
        skipped = 0

        with transaction.atomic():
            categories, _, _ = ensure_premium_service_categories(ServiceCategory, selected_slugs)
            for slug in selected_slugs:
                category = categories[slug]
                for name, item_type, unit, default_quantity in CATALOG_TEMPLATES[slug]:
                    exists = ServiceItemCatalog.objects.filter(
                        professional=professional,
                        name__iexact=name,
                        category=category,
                    ).exists()
                    if exists:
                        skipped += 1
                        continue
                    ServiceItemCatalog.objects.create(
                        professional=professional,
                        category=category,
                        item_type=item_type,
                        name=name,
                        unit=unit,
                        default_quantity=default_quantity,
                        estimated_unit_value=None,
                        favorite=False,
                        is_active=True,
                        description="Sugestão premium do HoraCerta. Revise nome, quantidade e valores antes de usar em serviços reais.",
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Catálogo premium aplicado para {professional.email}."))
        self.stdout.write(f"Itens criados: {created}")
        self.stdout.write(f"Itens ignorados por já existirem: {skipped}")
