from copy import deepcopy
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render

from . import views as service_views
from .forms import ServiceJobForm
from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceItemUnit, ServiceJob
from .workflow import planned_status_for_service


SERVICE_TEMPLATES = (
    {
        "slug": "visita-tecnica-diagnostico",
        "name": "Visita técnica e diagnóstico",
        "group": "Técnicos e manutenção",
        "category_label": "Manutenção / assistência técnica",
        "category_slugs": ("manutencao", "assistencia-tecnica"),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Visita técnica e diagnóstico",
        "summary": "Para avaliar o local, identificar a causa e apresentar a solução antes da execução.",
        "description": (
            "Realizar visita técnica para inspeção do local ou equipamento, levantamento das condições atuais, "
            "identificação do problema e registro das recomendações. A execução de reparos, troca de peças ou "
            "serviços adicionais dependerá de confirmação posterior do cliente."
        ),
        "notes": (
            "O cliente deve garantir acesso ao local e informar ocorrências anteriores relevantes. O diagnóstico "
            "representa a condição observada no momento da visita e não substitui laudo técnico quando exigido."
        ),
        "checklist": ("Confirmar acesso e contato", "Inspecionar local/equipamento", "Registrar diagnóstico", "Apresentar próximos passos"),
        "items": (
            {"name": "Deslocamento técnico", "type": ServiceItemExpense.ItemType.EXPENSE, "unit": ServiceItemUnit.SERVICE},
            {"name": "Diagnóstico técnico", "type": ServiceItemExpense.ItemType.OTHER, "unit": ServiceItemUnit.SERVICE},
        ),
    },
    {
        "slug": "manutencao-preventiva",
        "name": "Manutenção preventiva",
        "group": "Técnicos e manutenção",
        "category_label": "Manutenção",
        "category_slugs": ("manutencao", "assistencia-tecnica"),
        "billing_mode": ServiceJob.BillingMode.HOURLY,
        "title": "Manutenção preventiva programada",
        "summary": "Para revisões periódicas, conservação e redução de falhas.",
        "description": (
            "Executar manutenção preventiva conforme os pontos acessíveis no atendimento, incluindo inspeção visual, "
            "limpeza técnica quando aplicável, reaperto, testes funcionais e registro de anomalias encontradas."
        ),
        "notes": (
            "Peças, reparos corretivos e serviços fora do escopo serão informados antes da execução. O cliente deve "
            "disponibilizar acesso, desligamentos e informações do equipamento quando necessários."
        ),
        "checklist": ("Inspeção inicial", "Limpeza e ajustes", "Testes funcionais", "Pendências e próxima visita"),
        "items": (
            {"name": "Material de limpeza técnica", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Consumíveis de manutenção", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "instalacao-tecnica",
        "name": "Instalação técnica",
        "group": "Técnicos e manutenção",
        "category_label": "Elétrica / instalação",
        "category_slugs": ("eletrica", "assistencia-tecnica", "seguranca-monitoramento"),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Instalação e testes de funcionamento",
        "summary": "Para equipamentos, pontos elétricos, redes, câmeras e instalações em geral.",
        "description": (
            "Realizar a instalação no local combinado, incluindo montagem, fixação, conexões acessíveis, configuração "
            "básica e testes de funcionamento. O serviço será entregue com orientação inicial de uso."
        ),
        "notes": (
            "Adequações civis, elétricas ou de infraestrutura não descritas serão tratadas separadamente. O cliente "
            "deve confirmar o ponto de instalação, acesso, energia e autorizações do local."
        ),
        "checklist": ("Conferir local e infraestrutura", "Instalar e conectar", "Configurar", "Testar e orientar cliente"),
        "items": (
            {"name": "Kit de fixação", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Cabos e conectores", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "limpeza-recorrente",
        "name": "Limpeza recorrente",
        "group": "Conservação e ambiente",
        "category_label": "Limpeza e conservação",
        "category_slugs": ("limpeza-conservacao",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Limpeza e conservação do ambiente",
        "summary": "Para residências, escritórios, áreas comuns e rotinas semanais ou mensais.",
        "description": (
            "Executar limpeza e conservação das áreas combinadas, priorizando superfícies acessíveis, pisos, banheiros, "
            "mobiliário e retirada de resíduos comuns. Atividades especiais devem ser descritas antes do atendimento."
        ),
        "notes": (
            "O cliente deve informar materiais delicados, restrições de acesso, presença de animais e descarte especial. "
            "Limpeza pós-obra pesada, altura, produtos perigosos ou remoção de entulho não estão incluídos sem confirmação."
        ),
        "checklist": ("Conferir áreas e prioridades", "Executar limpeza", "Revisar pontos críticos", "Registrar conclusão"),
        "items": (
            {"name": "Produtos de limpeza", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Sacos para resíduos", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "jardinagem-manutencao",
        "name": "Jardinagem e manutenção externa",
        "group": "Conservação e ambiente",
        "category_label": "Jardinagem e paisagismo",
        "category_slugs": ("jardinagem-paisagismo",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Manutenção de jardim e área externa",
        "summary": "Para corte, poda leve, limpeza e conservação periódica.",
        "description": (
            "Executar manutenção das áreas verdes combinadas, incluindo corte, poda leve, limpeza, organização e "
            "recolhimento dos resíduos gerados dentro do limite informado."
        ),
        "notes": (
            "Podas de risco, árvores de grande porte, aplicação de produtos controlados e retirada externa de grande "
            "volume dependem de avaliação e autorização específicas."
        ),
        "checklist": ("Inspecionar área", "Executar corte/poda", "Organizar canteiros", "Recolher resíduos"),
        "items": (
            {"name": "Saco de substrato", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Retirada de resíduos verdes", "type": ServiceItemExpense.ItemType.EXPENSE, "unit": ServiceItemUnit.SERVICE},
        ),
    },
    {
        "slug": "pequena-reforma-reparos",
        "name": "Pequena reforma e reparos",
        "group": "Obras e fabricação",
        "category_label": "Reformas e obras",
        "category_slugs": ("reformas-obras",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Reparos e pequena reforma",
        "summary": "Para correções localizadas, acabamento e manutenção predial leve.",
        "description": (
            "Executar os reparos descritos no local combinado, com preparação da área, aplicação dos materiais previstos, "
            "acabamento compatível com o escopo e limpeza básica do ponto atendido."
        ),
        "notes": (
            "Problemas ocultos, danos estruturais, alterações de projeto e serviços adicionais serão comunicados antes "
            "de qualquer mudança de escopo. Documentos técnicos obrigatórios permanecem responsabilidade das partes habilitadas."
        ),
        "checklist": ("Proteger área", "Preparar superfície", "Executar reparo", "Revisar acabamento"),
        "items": (
            {"name": "Material de preparação", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Material de acabamento", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "assistencia-tecnica",
        "name": "Assistência técnica",
        "group": "Técnicos e manutenção",
        "category_label": "Assistência técnica",
        "category_slugs": ("assistencia-tecnica", "manutencao"),
        "billing_mode": ServiceJob.BillingMode.UNDEFINED,
        "title": "Atendimento de assistência técnica",
        "summary": "Para diagnóstico, reparo, configuração e entrega de equipamento.",
        "description": (
            "Receber ou inspecionar o equipamento, registrar sintomas informados, executar diagnóstico e realizar somente "
            "os reparos, configurações ou substituições confirmados pelo cliente."
        ),
        "notes": (
            "Dados armazenados, senhas, acessórios entregues e condições externas devem ser informados pelo cliente. "
            "Peças e serviços adicionais precisam de aprovação antes da aplicação."
        ),
        "checklist": ("Registrar sintomas e acessórios", "Diagnosticar", "Confirmar reparo", "Testar e entregar"),
        "items": (
            {"name": "Peça de reposição", "type": ServiceItemExpense.ItemType.PART, "unit": ServiceItemUnit.UNIT},
            {"name": "Consumíveis técnicos", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "servico-automotivo",
        "name": "Serviço automotivo",
        "group": "Mobilidade",
        "category_label": "Automotivo",
        "category_slugs": ("automotivo",),
        "billing_mode": ServiceJob.BillingMode.UNDEFINED,
        "title": "Ordem de serviço automotiva",
        "summary": "Para manutenção, instalação de acessórios, estética e atendimento móvel.",
        "description": (
            "Executar inspeção e serviço automotivo conforme a solicitação registrada, identificando veículo, condição "
            "inicial, atividades autorizadas, peças aplicadas e testes realizados."
        ),
        "notes": (
            "O cliente deve informar falhas anteriores, modificações e restrições do veículo. Serviços não autorizados, "
            "danos preexistentes e problemas não relacionados ao escopo devem ser registrados separadamente."
        ),
        "checklist": ("Identificar veículo", "Registrar condição inicial", "Executar serviço", "Testar e entregar"),
        "items": (
            {"name": "Peça ou acessório", "type": ServiceItemExpense.ItemType.PART, "unit": ServiceItemUnit.UNIT},
            {"name": "Produto automotivo", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.UNIT},
        ),
    },
    {
        "slug": "evento-sonorizacao",
        "name": "Evento e sonorização",
        "group": "Eventos e conteúdo",
        "category_label": "Eventos e sonorização",
        "category_slugs": ("eventos-sonorizacao",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Pacote técnico de sonorização para evento",
        "summary": "Para festas, cerimônias, palestras, música ao vivo e operação técnica.",
        "description": (
            "Fornecer, montar, testar e operar os equipamentos descritos para o evento, respeitando local, horários, "
            "programação e condições de energia previamente informadas. Ao final, realizar desmontagem e conferência."
        ),
        "notes": (
            "O cliente deve garantir acesso, energia adequada, proteção contra clima e responsável no local. Horas extras, "
            "mudança de endereço, aumento de estrutura ou equipamentos adicionais dependem de novo combinado."
        ),
        "checklist": ("Confirmar programação e acesso", "Montar equipamentos", "Testar operação", "Desmontar e conferir"),
        "items": (
            {"name": "Caixa de som ativa", "type": ServiceItemExpense.ItemType.OTHER, "unit": ServiceItemUnit.UNIT},
            {"name": "Microfone", "type": ServiceItemExpense.ItemType.OTHER, "unit": ServiceItemUnit.UNIT},
            {"name": "Kit de cabos", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "fotografia-video",
        "name": "Fotografia e vídeo",
        "group": "Eventos e conteúdo",
        "category_label": "Fotografia e vídeo",
        "category_slugs": ("fotografia-video",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Captação e entrega de conteúdo",
        "summary": "Para eventos, ensaios, vídeos institucionais e produção de conteúdo.",
        "description": (
            "Realizar captação de fotografia e/ou vídeo conforme briefing, duração e locais definidos, seguida do tratamento "
            "e entrega dos materiais selecionados no formato e prazo combinados."
        ),
        "notes": (
            "Quantidade de arquivos, revisões, prazo, direitos de uso, autorização de imagem e armazenamento devem ser "
            "confirmados antes da execução. Arquivos brutos não estão incluídos salvo indicação expressa."
        ),
        "checklist": ("Confirmar briefing", "Preparar equipamento", "Captar conteúdo", "Selecionar, editar e entregar"),
        "items": (
            {"name": "Deslocamento", "type": ServiceItemExpense.ItemType.EXPENSE, "unit": ServiceItemUnit.SERVICE},
            {"name": "Entrega digital", "type": ServiceItemExpense.ItemType.OTHER, "unit": ServiceItemUnit.SERVICE},
        ),
    },
    {
        "slug": "aula-consultoria",
        "name": "Aula, treinamento ou consultoria",
        "group": "Conhecimento e escritório",
        "category_label": "Aulas e consultoria",
        "category_slugs": ("aulas-consultoria",),
        "billing_mode": ServiceJob.BillingMode.HOURLY,
        "title": "Sessão de aula ou consultoria",
        "summary": "Para orientação técnica, diagnóstico de negócio, treinamento e acompanhamento.",
        "description": (
            "Realizar sessão conforme objetivo definido com o cliente, incluindo preparação, encontro, orientações práticas "
            "e registro dos próximos passos. Entregáveis adicionais devem ser descritos separadamente."
        ),
        "notes": (
            "Resultados dependem da participação e aplicação pelo cliente. Materiais, gravação, suporte posterior e novas "
            "sessões somente estão incluídos quando descritos no combinado."
        ),
        "checklist": ("Confirmar objetivo", "Preparar conteúdo", "Realizar sessão", "Registrar próximos passos"),
        "items": (
            {"name": "Material de apoio", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "apoio-administrativo",
        "name": "Apoio administrativo",
        "group": "Conhecimento e escritório",
        "category_label": "Administrativo e escritório",
        "category_slugs": ("administrativo-escritorio",),
        "billing_mode": ServiceJob.BillingMode.HOURLY,
        "title": "Apoio administrativo e organização",
        "summary": "Para cadastros, documentos, backoffice, planilhas e rotinas de escritório.",
        "description": (
            "Executar as atividades administrativas descritas, seguindo prioridades, fontes de informação e critérios "
            "fornecidos pelo cliente, com registro do que foi concluído e das pendências identificadas."
        ),
        "notes": (
            "O cliente é responsável pela legitimidade dos dados, acessos e autorizações fornecidos. Atividades contábeis, "
            "jurídicas ou privativas de profissão regulamentada não fazem parte do modelo."
        ),
        "checklist": ("Confirmar prioridades", "Receber acessos/documentos", "Executar atividades", "Entregar resumo e pendências"),
        "items": (
            {"name": "Material de escritório", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
    {
        "slug": "seguranca-monitoramento",
        "name": "Segurança e monitoramento",
        "group": "Técnicos e manutenção",
        "category_label": "Segurança e monitoramento",
        "category_slugs": ("seguranca-monitoramento",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Instalação de segurança e monitoramento",
        "summary": "Para câmeras, alarmes, sensores, controle de acesso e configuração.",
        "description": (
            "Instalar e configurar os dispositivos descritos, executar conexões acessíveis, testes de imagem ou acionamento "
            "e orientar o cliente sobre operação básica e limitações do sistema."
        ),
        "notes": (
            "O cliente deve definir áreas autorizadas, responsáveis por acesso e regras de privacidade. O serviço não garante "
            "prevenção absoluta de incidentes e não substitui projeto técnico quando exigido."
        ),
        "checklist": ("Confirmar pontos e privacidade", "Instalar dispositivos", "Configurar e testar", "Orientar responsáveis"),
        "items": (
            {"name": "Câmera ou sensor", "type": ServiceItemExpense.ItemType.PART, "unit": ServiceItemUnit.UNIT},
            {"name": "Fonte e conectores", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
            {"name": "Cabo", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.METER},
        ),
    },
    {
        "slug": "beleza-bem-estar",
        "name": "Beleza e bem-estar",
        "group": "Atendimento pessoal",
        "category_label": "Beleza e bem-estar",
        "category_slugs": ("beleza-bem-estar",),
        "billing_mode": ServiceJob.BillingMode.FIXED,
        "title": "Atendimento de beleza e bem-estar",
        "summary": "Para serviços agendados, pacotes, atendimento domiciliar e acompanhamento.",
        "description": (
            "Realizar o atendimento descrito, confirmando preferências, condições relevantes informadas pelo cliente, "
            "produtos utilizados e orientações de cuidado após o serviço."
        ),
        "notes": (
            "O cliente deve informar alergias, sensibilidades e condições que possam afetar o atendimento. O modelo não "
            "substitui avaliação de profissional de saúde nem autoriza procedimentos fora da habilitação do prestador."
        ),
        "checklist": ("Confirmar serviço e preferências", "Verificar restrições informadas", "Executar atendimento", "Orientar cuidados"),
        "items": (
            {"name": "Produto de atendimento", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.UNIT},
            {"name": "Material descartável", "type": ServiceItemExpense.ItemType.MATERIAL, "unit": ServiceItemUnit.PACKAGE},
        ),
    },
)


def get_service_template(template_slug):
    for template in SERVICE_TEMPLATES:
        if template["slug"] == template_slug:
            return deepcopy(template)
    raise Http404("Modelo de serviço não encontrado.")


def _category_for_template(template):
    categories = ServiceCategory.objects.filter(is_active=True, slug__in=template["category_slugs"])
    category_by_slug = {category.slug: category for category in categories}
    for slug in template["category_slugs"]:
        if slug in category_by_slug:
            return category_by_slug[slug]
    return None


def _templates_for_display():
    active_slugs = set(ServiceCategory.objects.filter(is_active=True).values_list("slug", flat=True))
    result = []
    for template in SERVICE_TEMPLATES:
        item = deepcopy(template)
        item["category_available"] = any(slug in active_slugs for slug in template["category_slugs"])
        result.append(item)
    return result


def _create_template_items(job, template):
    existing_names = {name.casefold() for name in job.item_expenses.values_list("name", flat=True)}
    created = 0
    for item in template["items"]:
        if item["name"].casefold() in existing_names:
            continue
        ServiceItemExpense.objects.create(
            service_job=job,
            type=item["type"],
            name=item["name"],
            description="Sugestão do modelo. Revise quantidade, valor e necessidade antes de enviar ao cliente.",
            unit=item["unit"],
            quantity=Decimal("1.00"),
            unit_value=Decimal("0.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        created += 1
    return created


@login_required
def service_template_library(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    return render(
        request,
        "services/service_template_library.html",
        {
            "service_templates": _templates_for_display(),
            "template_count": len(SERVICE_TEMPLATES),
        },
    )


@login_required
def service_job_create_from_template(request, template_slug):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    service_template = get_service_template(template_slug)
    category = _category_for_template(service_template)
    initial = {
        "category": category,
        "title": service_template["title"],
        "description": service_template["description"],
        "notes": service_template["notes"],
        "billing_mode": service_template["billing_mode"],
    }

    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user)
        if form.is_valid():
            submit_action = (request.POST.get("submit_action") or "").strip()
            posted_status = (request.POST.get("status") or "").strip()
            if submit_action == "draft":
                requested_status = ServiceJob.Status.DRAFT
            elif posted_status in ServiceJob.Status.values:
                requested_status = posted_status
            else:
                requested_status = ServiceJob.Status.PLANNED
            with transaction.atomic():
                job = form.save(status=ServiceJob.Status.DRAFT)
                service_views._create_planned_items(job, service_views._planned_item_rows_from_post(request.POST))
                created_items = _create_template_items(job, service_template)
                status = planned_status_for_service(job, requested_status=requested_status)
                if job.status != status:
                    job.status = status
                    job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(
                request,
                f"Serviço criado com o modelo {service_template['name']}. {created_items} item(ns) sugerido(s) foram adicionado(s) sem preço.",
            )
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user, initial=initial)

    return render(
        request,
        "services/service_job_form.html",
        {
            "form": form,
            "form_title": f"Novo serviço — {service_template['name']}",
            "form_subtitle": (
                "O modelo preenche um escopo inicial e adiciona itens sugeridos sem preço. Revise cliente, categoria, "
                "texto, valores, prazo e responsabilidades antes de compartilhar."
            ),
            "is_edit": False,
            "item_type_choices": ServiceItemExpense.ItemType.choices,
            "item_unit_choices": ServiceItemCatalog._meta.get_field("unit").choices,
            "client_address_map": service_views._client_address_map(request.user),
            "selected_service_template": service_template,
        },
    )
