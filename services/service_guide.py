from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from . import views as service_views
from .forms import ServiceJobForm
from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceItemUnit, ServiceJob
from .workflow import planned_status_for_service


TRAVEL_CATEGORY_SLUGS = (
    "administrativo-escritorio",
    "aulas-consultoria",
    "assistencia-tecnica",
    "automotivo",
)

TRAVEL_PRESET_ITEMS = (
    {
        "name": "Pedágio",
        "type": ServiceItemExpense.ItemType.TOLL,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o trecho, a data e a referência do comprovante quando houver.",
    },
    {
        "name": "Combustível",
        "type": ServiceItemExpense.ItemType.FUEL,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o abastecimento relacionado ao atendimento e a referência do comprovante.",
    },
    {
        "name": "Estacionamento",
        "type": ServiceItemExpense.ItemType.PARKING,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o local, o período e a referência do comprovante.",
    },
    {
        "name": "Alimentação em viagem",
        "type": ServiceItemExpense.ItemType.FOOD,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Use somente quando a política da empresa ou o combinado permitir reembolso.",
    },
    {
        "name": "Hospedagem ou passagem",
        "type": ServiceItemExpense.ItemType.EXPENSE,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o período, a finalidade e a referência da reserva ou do comprovante.",
    },
)


def _travel_category():
    categories = ServiceCategory.objects.filter(is_active=True, slug__in=TRAVEL_CATEGORY_SLUGS)
    by_slug = {category.slug: category for category in categories}
    for slug in TRAVEL_CATEGORY_SLUGS:
        if slug in by_slug:
            return by_slug[slug]
    return None


def _create_travel_preset_items(job):
    existing_names = {name.casefold() for name in job.item_expenses.values_list("name", flat=True)}
    created = 0
    for preset in TRAVEL_PRESET_ITEMS:
        if preset["name"].casefold() in existing_names:
            continue
        ServiceItemExpense.objects.create(
            service_job=job,
            type=preset["type"],
            name=preset["name"],
            description=preset["description"],
            unit=preset["unit"],
            quantity=Decimal("1.00"),
            unit_value=Decimal("0.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        created += 1
    return created


@login_required
def service_start_guide(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    return render(request, "services/service_start_guide.html")


@login_required
def service_travel_create(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    category = _travel_category()
    initial = {
        "category": category,
        "title": "Viagem de trabalho e atendimento externo",
        "description": (
            "Realizar atendimento externo conforme o objetivo combinado com a empresa, registrando os períodos "
            "efetivamente trabalhados, as atividades executadas, os deslocamentos necessários e as despesas relacionadas."
        ),
        "notes": (
            "Antes da viagem, confirme destino, responsável, datas, política de reembolso, limites de despesas e documentos "
            "exigidos. Durante o atendimento, registre cada período de trabalho e marque somente as despesas realmente "
            "utilizadas. No encerramento, gere a prestação de contas com horas, consumo e referências de comprovantes."
        ),
        "billing_mode": ServiceJob.BillingMode.HOURLY,
    }

    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user)
        if form.is_valid():
            submit_action = (request.POST.get("submit_action") or "").strip()
            requested_status = ServiceJob.Status.DRAFT if submit_action == "draft" else ServiceJob.Status.PLANNED
            with transaction.atomic():
                job = form.save(status=ServiceJob.Status.DRAFT)
                service_views._create_planned_items(
                    job,
                    service_views._planned_item_rows_from_post(request.POST),
                )
                created_items = _create_travel_preset_items(job)
                status = planned_status_for_service(job, requested_status=requested_status)
                if job.status != status:
                    job.status = status
                    job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(
                request,
                (
                    "Atendimento externo criado. "
                    f"{created_items} despesas comuns foram adicionadas sem valor; mantenha apenas as que realmente usar."
                ),
            )
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user, initial=initial)

    return render(
        request,
        "services/service_job_form.html",
        {
            "form": form,
            "form_title": "Novo serviço — viagem e atendimento externo",
            "form_subtitle": (
                "Organize o combinado com a empresa, registre as horas de cada dia e feche o serviço com uma prestação "
                "de contas de despesas. Os valores começam zerados para você revisar."
            ),
            "is_edit": False,
            "item_type_choices": ServiceItemExpense.ItemType.choices,
            "item_unit_choices": ServiceItemCatalog._meta.get_field("unit").choices,
            "client_address_map": service_views._client_address_map(request.user),
        },
    )
