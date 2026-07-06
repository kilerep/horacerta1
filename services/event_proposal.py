from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import ServiceItemExpense, ServiceJob


def _format_brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_quantity(value):
    value = Decimal(value or 0)
    if value == value.to_integral():
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def _redirect_if_not_mei(request):
    if request.user.role != User.Role.FUNCIONARIO:
        messages.error(request, "A área de propostas é exclusiva do prestador.")
        return redirect("dashboard")
    return None


def _jobs_for_user(user):
    return (
        ServiceJob.objects.filter(professional=user)
        .select_related("professional", "category", "client", "contract")
        .prefetch_related("item_expenses")
    )


def _included_items(job):
    return [
        item
        for item in job.item_expenses.all()
        if item.usage_status
        in (
            ServiceItemExpense.UsageStatus.PLANNED,
            ServiceItemExpense.UsageStatus.QUOTED,
            ServiceItemExpense.UsageStatus.PURCHASED,
            ServiceItemExpense.UsageStatus.USED,
            ServiceItemExpense.UsageStatus.PARTIALLY_USED,
        )
    ]


def _professional_name(job):
    return job.professional.get_full_name() or job.professional.email or job.professional.username


def _proposal_context(job, request=None):
    items = _included_items(job)
    event_date = job.start_date.strftime("%d/%m/%Y") if job.start_date else "A combinar"
    time_parts = []
    if job.planned_start_time:
        time_parts.append(job.planned_start_time.strftime("%H:%M"))
    if job.planned_end_time:
        time_parts.append(job.planned_end_time.strftime("%H:%M"))
    planned_time = " até ".join(time_parts) if time_parts else "A combinar"
    public_url = reverse("public_service_event_proposal", args=[job.public_token])
    if request is not None:
        public_url = request.build_absolute_uri(public_url)

    return {
        "job": job,
        "professional_name": _professional_name(job),
        "professional_contact": job.professional.email or job.professional.username,
        "event_date": event_date,
        "planned_time": planned_time,
        "service_address": job.full_service_address or job.service_location_summary or "A combinar",
        "included_items": items,
        "package_value": job.fixed_labor_value,
        "package_value_brl": _format_brl(job.fixed_labor_value),
        "public_url": public_url,
        "generated_at": timezone.localtime(),
    }


def _is_fixed_package(job):
    return job.billing_mode == ServiceJob.BillingMode.FIXED and job.fixed_labor_value is not None


def _proposal_message(context):
    job = context["job"]
    item_count = len(context["included_items"])
    return "\n".join(
        [
            "Olá, segue a proposta comercial do evento:",
            "",
            f"Evento/serviço: {job.title}",
            f"Data: {context['event_date']}",
            f"Horário previsto: {context['planned_time']}",
            f"Local: {context['service_address']}",
            f"Composição técnica: {item_count} item(ns) incluso(s) no pacote.",
            f"Valor fechado do pacote: {context['package_value_brl']}",
            "",
            "Veja todos os detalhes, itens inclusos e condições:",
            context["public_url"],
        ]
    )


@login_required
def service_event_proposal_list(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    jobs = [job for job in _jobs_for_user(request.user) if _is_fixed_package(job)]
    return render(request, "services/service_event_proposal_list.html", {"jobs": jobs})


@login_required
def service_event_proposal_detail(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_jobs_for_user(request.user), id=job_id)
    if not _is_fixed_package(job):
        messages.error(
            request,
            "Defina o serviço como Valor fixo e informe o valor fechado do pacote antes de gerar a proposta.",
        )
        return redirect("service_job_update", job_id=job.id)
    return render(request, "services/service_event_proposal.html", _proposal_context(job, request=request))


@login_required
def service_event_proposal_whatsapp(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_jobs_for_user(request.user), id=job_id)
    if not _is_fixed_package(job):
        messages.error(request, "Informe o valor fechado do pacote antes de enviar a proposta.")
        return redirect("service_job_update", job_id=job.id)

    now = timezone.now()
    update_fields = ["preview_sent_at", "updated_at"]
    if not job.preview_generated_at:
        job.preview_generated_at = now
        update_fields.append("preview_generated_at")
    job.preview_sent_at = now
    if job.status in (ServiceJob.Status.DRAFT, ServiceJob.Status.PLANNED):
        job.status = ServiceJob.Status.SENT
        update_fields.extend(["status", "finished_at"])
    job.save(update_fields=update_fields)

    context = _proposal_context(job, request=request)
    digits = "".join(ch for ch in job.client_whatsapp if ch.isdigit())
    message = quote(_proposal_message(context), safe="")
    if digits:
        destination = f"https://wa.me/55{digits}?text={message}" if len(digits) <= 11 else f"https://wa.me/{digits}?text={message}"
    else:
        destination = f"https://wa.me/?text={message}"
    return redirect(destination)


def public_service_event_proposal(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract")
        .prefetch_related("item_expenses"),
        public_token=token,
        preview_generated_at__isnull=False,
        billing_mode=ServiceJob.BillingMode.FIXED,
    )
    if not job.preview_first_viewed_at:
        job.preview_first_viewed_at = timezone.now()
        job.save(update_fields=["preview_first_viewed_at", "updated_at"])
    return render(request, "services/public_service_event_proposal.html", _proposal_context(job, request=request))
