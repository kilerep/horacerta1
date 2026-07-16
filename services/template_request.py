from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from . import views as service_views
from .forms import ServiceRequestItemForm
from .models import ServiceCategory, ServiceJob, ServiceRequest, ServiceRequestItem
from .service_guide import GuidedServiceRequestForm
from .service_templates import get_service_template


def _category_for_template(template):
    categories = ServiceCategory.objects.filter(is_active=True, slug__in=template["category_slugs"])
    categories_by_slug = {category.slug: category for category in categories}
    for slug in template["category_slugs"]:
        if slug in categories_by_slug:
            return categories_by_slug[slug]
    return None


def _request_description(template):
    checklist = "\n".join(f"- {step}" for step in template.get("checklist", ()))
    return (
        f"Necessidade informada pelo cliente:\n\n"
        f"Escopo sugerido para confirmar:\n{template['description']}\n\n"
        f"Pontos de conferência:\n{checklist}"
    ).strip()


def _create_template_request_items(service_request, template):
    existing_names = {name.casefold() for name in service_request.quick_items.values_list("name", flat=True)}
    created = 0
    for item in template.get("items", ()):
        if item["name"].casefold() in existing_names:
            continue
        ServiceRequestItem.objects.create(
            service_request=service_request,
            name=item["name"],
            quantity=Decimal("1.00"),
            note="Sugestão do modelo. Confirme necessidade, quantidade e valor com o cliente.",
            estimated_unit_value=None,
        )
        existing_names.add(item["name"].casefold())
        created += 1
    return created


def _apply_template_to_converted_job(job, template):
    changed_fields = []
    if job.billing_mode == ServiceJob.BillingMode.UNDEFINED:
        job.billing_mode = template["billing_mode"]
        changed_fields.append("billing_mode")
        if job.billing_mode == ServiceJob.BillingMode.HOURLY and job.contract_id:
            job.hourly_rate_snapshot = job.contract.hourly_rate or Decimal("0.00")
            changed_fields.append("hourly_rate_snapshot")

    template_notes = (template.get("notes") or "").strip()
    if template_notes and template_notes not in (job.notes or ""):
        job.notes = f"{(job.notes or '').strip()}\n\n{template_notes}".strip()
        changed_fields.append("notes")

    if changed_fields:
        job.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])


@login_required
def service_request_create_from_template(request, template_slug):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    service_template = get_service_template(template_slug)
    category = _category_for_template(service_template)
    initial = {
        "category": category,
        "title": service_template["title"],
        "description": _request_description(service_template),
        "source": ServiceRequest.Source.WHATSAPP,
    }

    if request.method == "POST":
        form = GuidedServiceRequestForm(request.POST, user=request.user)
        item_form = ServiceRequestItemForm(request.POST, prefix="quick")
        item_form_has_data = item_form.has_item_data()
        item_form_is_valid = item_form.is_valid() if item_form_has_data else True
        if form.is_valid() and item_form_is_valid:
            submit_action = (request.POST.get("submit_action") or "").strip()
            with transaction.atomic():
                service_request = form.save()
                if item_form_has_data:
                    item_form.service_request = service_request
                    item_form.save()
                created_items = _create_template_request_items(service_request, service_template)
                if submit_action == "convert":
                    job = service_views._convert_service_request_to_job(service_request)
                    _apply_template_to_converted_job(job, service_template)
                    messages.success(
                        request,
                        (
                            "Pedido transformado em rascunho de serviço. "
                            f"{created_items} item(ns) do modelo foram preparados sem preço automático."
                        ),
                    )
                    return redirect("service_job_detail", job_id=job.id)
            messages.success(
                request,
                (
                    "Pedido salvo para completar depois. "
                    f"{created_items} item(ns) sugerido(s) ficaram registrados sem preço automático."
                ),
            )
            return redirect("service_request_detail", request_id=service_request.id)
    else:
        form = GuidedServiceRequestForm(user=request.user, initial=initial)
        item_form = ServiceRequestItemForm(prefix="quick")

    return render(
        request,
        "services/service_guided_request_form.html",
        {
            "form": form,
            "item_form": item_form,
            "scenario": f"template:{template_slug}",
            "scenario_title": f"Pedido — {service_template['name']}",
            "scenario_subtitle": (
                "Use este roteiro para registrar o que chegou pelo WhatsApp. Salve enquanto negocia ou abra o serviço "
                "quando o combinado estiver pronto."
            ),
            "scenario_result_hint": (
                "O pedido será criado com escopo, checklist e itens sugeridos. Quantidades e valores continuam sob sua revisão."
            ),
        },
    )
