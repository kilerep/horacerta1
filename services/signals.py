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
    """Reconhece pedidos guiados sem depender de campo novo ou migration."""
    category_slug = getattr(getattr(service_request, "category", None), "slug", "")
    searchable = f"{service_request.title or ''} {service_request.description or ''}".casefold()
    if category_slug == "eventos-sonorizacao":
        return "evento"
    travel_terms = ("viagem", "atendimento externo", "reembolso", "destino:")
    if any(term in searchable for term in travel_terms):
        return "viagem"
    return ""


def _apply_guided_defaults(service_request, job):
    kind = _guided_request_kind(service_request)
    if kind == "viagem":
        from .service_guide import _create_travel_preset_items

        _create_travel_preset_items(job)
        return
    if kind == "evento":
        from .service_templates import _create_template_items, get_service_template

        template = get_service_template("evento-sonorizacao")
        _create_template_items(job, template)
        template_notes = (template.get("notes") or "").strip()
        if template_notes and template_notes not in (job.notes or ""):
            job.notes = f"{(job.notes or '').strip()}\n\n{template_notes}".strip()
            job.save(update_fields=["notes", "updated_at"])


@receiver(post_save, sender=ServiceRequest)
def copy_request_schedule_and_address_to_service(sender, instance, **kwargs):
    """Leva o pedido para o serviço sem apagar dados já revisados pelo prestador."""
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
