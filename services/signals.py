from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ServiceJob, ServiceRequest


REQUEST_TO_JOB_FIELDS = (
    ("preferred_date", "start_date"),
    ("preferred_time", "planned_start_time"),
    ("address_zipcode", "service_zip_code"),
    ("address_street", "service_street"),
    ("address_number", "service_number"),
    ("address_complement", "service_complement"),
    ("address_neighborhood", "service_district"),
    ("address_city", "service_city"),
    ("address_state", "service_state"),
    ("address_reference", "service_reference"),
)


def _guided_request_kind(service_request):
    """Reconhece os cenários guiados sem criar campo novo ou migration."""
    category_slug = getattr(getattr(service_request, "category", None), "slug", "")
    searchable = f"{service_request.title or ''} {service_request.description or ''}".casefold()
    if category_slug == "eventos-sonorizacao":
        return "evento"
    travel_terms = ("viagem", "atendimento externo", "reembolso", "destino:")
    if any(term in searchable for term in travel_terms):
        return "viagem"
    return ""


def _template_for_request(service_request):
    """Identifica o modelo pela descrição completa inserida no pedido guiado."""
    from .service_templates import SERVICE_TEMPLATES

    description = service_request.description or ""
    for template in SERVICE_TEMPLATES:
        template_description = template.get("description") or ""
        if template_description and template_description in description:
            return template
    return None


def _apply_template_defaults(template, job):
    from .service_templates import _create_template_items

    _create_template_items(job, template)

    for definition in template.get("items", ()):
        item = job.item_expenses.filter(name__iexact=definition["name"]).first()
        if not item:
            continue
        changed_fields = []
        if item.type != definition["type"]:
            item.type = definition["type"]
            changed_fields.append("type")
        if item.unit != definition["unit"]:
            item.unit = definition["unit"]
            changed_fields.append("unit")
        if changed_fields:
            item.save(update_fields=[*changed_fields, "updated_at"])

    job_changed_fields = []
    if job.billing_mode == ServiceJob.BillingMode.UNDEFINED:
        job.billing_mode = template["billing_mode"]
        job_changed_fields.append("billing_mode")
        if job.billing_mode == ServiceJob.BillingMode.HOURLY and job.contract_id:
            job.hourly_rate_snapshot = job.contract.hourly_rate or 0
            job_changed_fields.append("hourly_rate_snapshot")

    template_notes = (template.get("notes") or "").strip()
    if template_notes and template_notes not in (job.notes or ""):
        job.notes = f"{(job.notes or '').strip()}\n\n{template_notes}".strip()
        job_changed_fields.append("notes")

    if job_changed_fields:
        job.save(update_fields=[*dict.fromkeys(job_changed_fields), "updated_at"])


def _apply_guided_defaults(service_request, job):
    template = _template_for_request(service_request)
    if template:
        _apply_template_defaults(template, job)
        return

    kind = _guided_request_kind(service_request)
    if kind == "viagem":
        from .service_guide import _create_travel_preset_items

        _create_travel_preset_items(job)
        return
    if kind == "evento":
        from .service_templates import get_service_template

        _apply_template_defaults(get_service_template("evento-sonorizacao"), job)


@receiver(post_save, sender=ServiceRequest)
def copy_request_context_to_service(sender, instance, **kwargs):
    """Leva agenda, local e sugestões do pedido para o serviço sem sobrescrever dados revisados."""
    if not instance.converted_service_id:
        return

    job = ServiceJob.objects.filter(pk=instance.converted_service_id).first()
    if not job:
        return

    changed_fields = []
    for request_field, job_field in REQUEST_TO_JOB_FIELDS:
        request_value = getattr(instance, request_field, None)
        job_value = getattr(job, job_field, None)
        if request_value not in (None, "") and job_value in (None, ""):
            setattr(job, job_field, request_value)
            changed_fields.append(job_field)

    if job.start_date and not job.end_date:
        job.end_date = job.start_date
        changed_fields.append("end_date")

    if changed_fields:
        address_parts = [
            job.service_street,
            job.service_number,
            job.service_complement,
            job.service_district,
            job.service_city,
            job.service_state,
        ]
        if not job.service_location:
            job.service_location = ", ".join(part for part in address_parts if part)
            if job.service_location:
                changed_fields.append("service_location")

        job.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])

    _apply_guided_defaults(instance, job)
