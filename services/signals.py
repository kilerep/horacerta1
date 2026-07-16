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


@receiver(post_save, sender=ServiceRequest)
def copy_request_schedule_and_address_to_service(sender, instance, **kwargs):
    """Leva agenda e local do pedido para o serviço sem sobrescrever dados já revisados."""
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
