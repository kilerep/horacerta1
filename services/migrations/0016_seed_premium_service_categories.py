from django.db import migrations


PREMIUM_SERVICE_CATEGORIES = [
    (
        "reformas-obras",
        "Reformas e obras",
        "Obras pequenas, acabamentos, pisos, revestimentos, reparos estruturais simples e acompanhamento de execução.",
        "hammer",
        20,
    ),
    (
        "limpeza-conservacao",
        "Limpeza e conservação",
        "Limpeza residencial, comercial, pós-obra, higienização, conservação periódica e organização de ambientes.",
        "sparkles",
        21,
    ),
    (
        "jardinagem-paisagismo",
        "Jardinagem e paisagismo",
        "Corte de grama, poda, manutenção de jardim, plantio, irrigação simples e cuidado de áreas externas.",
        "leaf",
        22,
    ),
    (
        "marcenaria-serralheria",
        "Marcenaria e serralheria",
        "Móveis sob medida, ajustes, portas, grades, suportes, estruturas metálicas leves e reparos técnicos.",
        "drill",
        23,
    ),
    (
        "assistencia-tecnica",
        "Assistência técnica",
        "Diagnóstico, manutenção e reparo de equipamentos, eletrodomésticos, eletrônicos e máquinas leves.",
        "cpu",
        24,
    ),
    (
        "automotivo",
        "Automotivo",
        "Serviços móveis, manutenção leve, estética automotiva, inspeção, instalação de acessórios e suporte técnico.",
        "car",
        25,
    ),
    (
        "beleza-bem-estar",
        "Beleza e bem-estar",
        "Atendimentos profissionais de beleza, estética não médica, cuidados pessoais e serviços por agenda.",
        "scissors",
        26,
    ),
    (
        "eventos-sonorizacao",
        "Eventos e sonorização",
        "Montagem, operação, desmontagem, som, iluminação, apoio técnico, fotografia e estrutura para eventos.",
        "music",
        27,
    ),
    (
        "fotografia-video",
        "Fotografia e vídeo",
        "Cobertura, captação, edição, ensaios, conteúdo para negócios, eventos, imóveis e redes sociais.",
        "camera",
        28,
    ),
    (
        "aulas-consultoria",
        "Aulas e consultoria",
        "Aulas particulares, treinamentos, consultorias, mentoria, diagnóstico e acompanhamento profissional.",
        "graduation-cap",
        29,
    ),
    (
        "administrativo-escritorio",
        "Administrativo e escritório",
        "Rotinas administrativas, organização de documentos, atendimento, cadastro, suporte operacional e backoffice.",
        "file-text",
        30,
    ),
    (
        "seguranca-monitoramento",
        "Segurança e monitoramento",
        "Instalação, configuração e manutenção de câmeras, alarmes, controle de acesso e monitoramento técnico.",
        "shield-check",
        31,
    ),
]


def seed_premium_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("services", "ServiceCategory")
    for slug, name, description, icon_name, sort_order in PREMIUM_SERVICE_CATEGORIES:
        ServiceCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "icon_name": icon_name,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def unseed_premium_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("services", "ServiceCategory")
    ServiceCategory.objects.filter(slug__in=[item[0] for item in PREMIUM_SERVICE_CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0015_rename_services_se_service_5958d7_idx_services_se_service_dc4bba_idx"),
    ]

    operations = [
        migrations.RunPython(seed_premium_categories, unseed_premium_categories),
    ]
