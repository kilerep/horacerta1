from copy import deepcopy
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from . import views as service_views
from .forms import ServiceJobForm
from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceItemUnit, ServiceJob
from .workflow import planned_status_for_service


TRAVEL_SERVICE_TEMPLATE = {
    "name": "Viagem a trabalho e prestação de contas",
    "category_slugs": ("administrativo-escritorio", "aulas-consultoria", "automotivo"),
    "title": "Viagem a trabalho e atendimento externo",
    "description": (
        "Realizar viagem a trabalho ou atendimento externo conforme o destino, período e objetivo combinados com a empresa. "
        "Registrar os períodos efetivamente trabalhados e as despesas relacionadas ao serviço para formar uma prestação de contas clara."
    ),
    "notes": (
        "Antes da viagem, confirme com a empresa quais despesas podem ser reembolsadas, limites, necessidade de comprovantes, "
        "forma de aprovação e prazo de entrega. Somente despesas marcadas como usadas entram no total do documento."
    ),
    "billing_mode": ServiceJob.BillingMode.HOURLY,
    "items": (
        {"name": "Combustível", "type": ServiceItemExpense.ItemType.FUEL, "unit": ServiceItemUnit.LITER},
        {"name": "Pedágio", "type": ServiceItemExpense.ItemType.TOLL, "unit": ServiceItemUnit.SERVICE},
        {"name": "Estacionamento", "type": ServiceItemExpense.ItemType.PARKING, "unit": ServiceItemUnit.SERVICE},
        {"name": "Alimentação", "type": ServiceItemExpense.ItemType.FOOD, "unit": ServiceItemUnit.SERVICE},
        {"name": "Hospedagem", "type": ServiceItemExpense.ItemType.EXPENSE, "unit": ServiceItemUnit.SERVICE},
        {"name": "Passagem ou deslocamento", "type": ServiceItemExpense.ItemType.EXPENSE, "unit": ServiceItemUnit.SERVICE},
    ),
}


def _category_for_travel():
    categories = ServiceCategory.objects.filter(
        is_active=True,
        slug__in=TRAVEL_SERVICE_TEMPLATE["category_slugs"],
    )
    by_slug = {category.slug: category for category in categories}
    for slug in TRAVEL_SERVICE_TEMPLATE["category_slugs"]:
        if slug in by_slug:
            return by_slug[slug]
    return None


def _create_travel_items(job):
    created = 0
    existing_names = {name.casefold() for name in job.item_expenses.values_list("name", flat=True)}
    for item in TRAVEL_SERVICE_TEMPLATE["items"]:
        if item["name"].casefold() in existing_names:
            continue
        ServiceItemExpense.objects.create(
            service_job=job,
            type=item["type"],
            name=item["name"],
            description=(
                "Despesa sugerida para prestação de contas. Revise quantidade, valor, comprovante e necessidade. "
                "Marque como usado somente quando a despesa realmente ocorrer."
            ),
            unit=item["unit"],
            quantity=Decimal("1.00"),
            unit_value=Decimal("0.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        created += 1
    return created


@login_required
def service_start(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    return render(request, "services/service_start.html")


@login_required
def service_trip_create(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    service_template = deepcopy(TRAVEL_SERVICE_TEMPLATE)
    initial = {
        "category": _category_for_travel(),
        "title": service_template["title"],
        "description": service_template["description"],
        "notes": service_template["notes"],
        "billing_mode": service_template["billing_mode"],
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
                created_items = _create_travel_items(job)
                status = planned_status_for_service(job, requested_status=requested_status)
                if job.status != status:
                    job.status = status
                    job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(
                request,
                (
                    "Viagem criada. Foram adicionadas "
                    f"{created_items} despesas sugeridas sem valor. Revise e marque como usadas somente quando ocorrerem."
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
            "form_title": "Nova viagem a trabalho",
            "form_subtitle": (
                "Organize cliente, destino, período, horas e despesas. Depois, envie uma prestação de contas profissional por link."
            ),
            "is_edit": False,
            "item_type_choices": ServiceItemExpense.ItemType.choices,
            "item_unit_choices": ServiceItemCatalog._meta.get_field("unit").choices,
            "client_address_map": service_views._client_address_map(request.user),
            "selected_service_template": service_template,
        },
    )
