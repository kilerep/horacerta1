from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.mei_context import mei_contracts_for_user

from .forms import ServiceJobForm
from .models import ServiceCategory, ServiceJob


def _redirect_if_not_mei(request):
    if request.user.role != User.Role.FUNCIONARIO:
        messages.error(request, "A area de servicos e exclusiva do prestador.")
        return redirect("dashboard")
    return None


def _format_brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _service_jobs_for_user(user):
    return ServiceJob.objects.filter(professional=user).select_related("category", "client", "contract")


@login_required
def service_job_list(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    categories = ServiceCategory.objects.filter(is_active=True)
    contracts = mei_contracts_for_user(request.user, include_inactive_contracts=True)
    jobs = _service_jobs_for_user(request.user)

    selected_status = (request.GET.get("status") or "").strip()
    selected_category = (request.GET.get("category") or "").strip()
    selected_contract = (request.GET.get("contract") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if selected_status:
        jobs = jobs.filter(status=selected_status)
    if selected_category:
        jobs = jobs.filter(category__slug=selected_category)
    if selected_contract:
        jobs = jobs.filter(contract_id=selected_contract)
    if date_from:
        jobs = jobs.filter(Q(start_date__gte=date_from) | Q(start_date__isnull=True, created_at__date__gte=date_from))
    if date_to:
        jobs = jobs.filter(Q(start_date__lte=date_to) | Q(start_date__isnull=True, created_at__date__lte=date_to))

    all_jobs = _service_jobs_for_user(request.user)
    status_counts = all_jobs.aggregate(
        in_progress=Count("id", filter=Q(status=ServiceJob.Status.IN_PROGRESS)),
        finished=Count("id", filter=Q(status=ServiceJob.Status.FINISHED)),
        drafts=Count("id", filter=Q(status=ServiceJob.Status.DRAFT)),
    )
    fixed_total = all_jobs.aggregate(total=Sum("fixed_labor_value"))["total"] or Decimal("0.00")

    context = {
        "jobs": jobs,
        "categories": categories,
        "contracts": contracts,
        "status_choices": ServiceJob.Status.choices,
        "selected_status": selected_status,
        "selected_category": selected_category,
        "selected_contract": selected_contract,
        "date_from": date_from,
        "date_to": date_to,
        "summary": {
            "in_progress": status_counts["in_progress"] or 0,
            "finished": status_counts["finished"] or 0,
            "drafts": status_counts["drafts"] or 0,
            "fixed_total_brl": _format_brl(fixed_total),
        },
    }
    return render(request, "services/service_job_list.html", context)


@login_required
def service_job_create(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user)
        if form.is_valid():
            job = form.save()
            messages.success(request, "Servico salvo com sucesso.")
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user)

    return render(request, "services/service_job_form.html", {"form": form})


@login_required
def service_job_detail(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    return render(request, "services/service_job_detail.html", {"job": job})

