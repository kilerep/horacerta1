from django.db import migrations


DEFAULT_CATEGORIES = [
    (
        "servico-geral",
        "Serviço geral",
        "Para trabalhos avulsos que não se encaixam em uma categoria específica.",
        "briefcase",
    ),
    (
        "eletrica",
        "Elétrica",
        "Trocas, instalações, manutenção elétrica, tomadas, disjuntores e revisões.",
        "zap",
    ),
    (
        "hidraulica",
        "Hidráulica",
        "Reparos, instalações, vazamentos, torneiras, registros e tubulações.",
        "droplets",
    ),
    (
        "manutencao",
        "Manutenção",
        "Pequenos reparos, ajustes, consertos e serviços de conservação.",
        "wrench",
    ),
    (
        "ar-condicionado",
        "Ar-condicionado",
        "Instalação, limpeza, manutenção preventiva e corretiva.",
        "wind",
    ),
    (
        "montagem-instalacao",
        "Montagem/instalação",
        "Montagem de móveis, instalação de suportes, equipamentos ou acessórios.",
        "package",
    ),
    (
        "informatica-ti",
        "Informática/TI",
        "Suporte técnico, instalação, configuração, redes e manutenção de computadores.",
        "monitor",
    ),
    (
        "pintura-e-reparos",
        "Pintura e reparos",
        "Pintura, acabamento, pequenos consertos e ajustes estruturais simples.",
        "paintbrush",
    ),
    (
        "entrega-viagem",
        "Entrega/viagem",
        "Deslocamentos, entregas, viagens, paradas, despesas e registros de percurso.",
        "route",
    ),
    (
        "visita-tecnica",
        "Visita técnica",
        "Avaliação, diagnóstico, vistoria ou levantamento antes da execução de um serviço.",
        "clipboard-check",
    ),
    (
        "outros",
        "Outros",
        "Categoria livre para casos que não se encaixam nas opções anteriores.",
        "more-horizontal",
    ),
]


def seed_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("services", "ServiceCategory")
    for index, (slug, name, description, icon_name) in enumerate(DEFAULT_CATEGORIES, start=1):
        ServiceCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "icon_name": icon_name,
                "is_active": True,
                "sort_order": index,
            },
        )


def unseed_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("services", "ServiceCategory")
    ServiceCategory.objects.filter(slug__in=[item[0] for item in DEFAULT_CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
