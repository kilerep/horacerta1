from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from accounts.models import User

from .event_proposal import _is_fixed_package, _jobs_for_user
from .models import ServiceJob


@login_required
def open_service_event_proposal(request, job_id):
    if request.user.role != User.Role.FUNCIONARIO:
        messages.error(request, "A área de propostas é exclusiva do prestador.")
        return redirect("dashboard")

    job = get_object_or_404(_jobs_for_user(request.user), id=job_id)
    if not _is_fixed_package(job):
        messages.error(
            request,
            "Defina o serviço como Valor fixo e informe o valor fechado do pacote antes de abrir a proposta.",
        )
        return redirect("service_job_update", job_id=job.id)

    if not job.preview_generated_at:
        job.preview_generated_at = timezone.now()
        update_fields = ["preview_generated_at", "updated_at"]
        if job.status == ServiceJob.Status.PLANNED:
            job.status = ServiceJob.Status.SENT
            update_fields.extend(["status", "finished_at"])
        job.save(update_fields=update_fields)
    return redirect("public_service_event_proposal", token=job.public_token)
