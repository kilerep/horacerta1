PREMIUM_SERVICE_CATEGORIES = (
    {
        "slug": "reformas-obras",
        "name": "Reformas e obras",
        "description": "Obras pequenas, acabamentos, pisos, revestimentos, reparos estruturais simples e acompanhamento de execução.",
        "icon_name": "hammer",
        "sort_order": 20,
    },
    {
        "slug": "limpeza-conservacao",
        "name": "Limpeza e conservação",
        "description": "Limpeza residencial, comercial, pós-obra, higienização, conservação periódica e organização de ambientes.",
        "icon_name": "sparkles",
        "sort_order": 21,
    },
    {
        "slug": "jardinagem-paisagismo",
        "name": "Jardinagem e paisagismo",
        "description": "Corte de grama, poda, manutenção de jardim, plantio, irrigação simples e cuidado de áreas externas.",
        "icon_name": "leaf",
        "sort_order": 22,
    },
    {
        "slug": "marcenaria-serralheria",
        "name": "Marcenaria e serralheria",
        "description": "Móveis sob medida, ajustes, portas, grades, suportes, estruturas metálicas leves e reparos técnicos.",
        "icon_name": "drill",
        "sort_order": 23,
    },
    {
        "slug": "assistencia-tecnica",
        "name": "Assistência técnica",
        "description": "Diagnóstico, manutenção e reparo de equipamentos, eletrodomésticos, eletrônicos e máquinas leves.",
        "icon_name": "cpu",
        "sort_order": 24,
    },
    {
        "slug": "automotivo",
        "name": "Automotivo",
        "description": "Serviços móveis, manutenção leve, estética automotiva, inspeção, instalação de acessórios e suporte técnico.",
        "icon_name": "car",
        "sort_order": 25,
    },
    {
        "slug": "beleza-bem-estar",
        "name": "Beleza e bem-estar",
        "description": "Atendimentos profissionais de beleza, estética não médica, cuidados pessoais e serviços por agenda.",
        "icon_name": "scissors",
        "sort_order": 26,
    },
    {
        "slug": "eventos-sonorizacao",
        "name": "Eventos e sonorização",
        "description": "Montagem, operação, desmontagem, som, iluminação, apoio técnico, fotografia e estrutura para eventos.",
        "icon_name": "music",
        "sort_order": 27,
    },
    {
        "slug": "fotografia-video",
        "name": "Fotografia e vídeo",
        "description": "Cobertura, captação, edição, ensaios, conteúdo para negócios, eventos, imóveis e redes sociais.",
        "icon_name": "camera",
        "sort_order": 28,
    },
    {
        "slug": "aulas-consultoria",
        "name": "Aulas e consultoria",
        "description": "Aulas particulares, treinamentos, consultorias, mentoria, diagnóstico e acompanhamento profissional.",
        "icon_name": "graduation-cap",
        "sort_order": 29,
    },
    {
        "slug": "administrativo-escritorio",
        "name": "Administrativo e escritório",
        "description": "Rotinas administrativas, organização de documentos, atendimento, cadastro, suporte operacional e backoffice.",
        "icon_name": "file-text",
        "sort_order": 30,
    },
    {
        "slug": "seguranca-monitoramento",
        "name": "Segurança e monitoramento",
        "description": "Instalação, configuração e manutenção de câmeras, alarmes, controle de acesso e monitoramento técnico.",
        "icon_name": "shield-check",
        "sort_order": 31,
    },
)


def ensure_premium_service_categories(ServiceCategory, selected_slugs=None):
    selected = set(selected_slugs or [item["slug"] for item in PREMIUM_SERVICE_CATEGORIES])
    created = 0
    updated = 0
    categories = {}

    for item in PREMIUM_SERVICE_CATEGORIES:
        if item["slug"] not in selected:
            continue
        category, was_created = ServiceCategory.objects.update_or_create(
            slug=item["slug"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "icon_name": item["icon_name"],
                "sort_order": item["sort_order"],
                "is_active": True,
            },
        )
        categories[item["slug"]] = category
        created += int(was_created)
        updated += int(not was_created)

    return categories, created, updated
