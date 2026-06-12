from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.mei_context import mei_contracts_for_user

from .forms import ServiceItemExpenseForm, ServiceJobForm, ServiceWorkLogForm
from .models import ServiceCategory, ServiceItemExpense, ServiceJob


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


def _service_job_detail_context(job, *, work_log_form=None, item_form=None):
    work_logs = job.work_logs.all()
    items = job.item_expenses.all()
    used_items = [item for item in items if item.is_chargeable]
    not_used_items = [
        item
        for item in items
        if item.usage_status in ServiceItemExpense.NON_CHARGEABLE_USAGE_STATUSES
    ]
    other_items = [
        item
        for item in items
        if item not in used_items and item not in not_used_items
    ]
    return {
        "job": job,
        "work_logs": work_logs,
        "used_items": used_items,
        "not_used_items": not_used_items,
        "other_items": other_items,
        "work_log_form": work_log_form or ServiceWorkLogForm(service_job=job),
        "item_form": item_form or ServiceItemExpenseForm(service_job=job),
        "is_finished": job.status == ServiceJob.Status.FINISHED,
        "summary": {
            "total_hours": job.total_hours_label,
            "labor_total_brl": _format_brl(job.labor_total),
            "used_items_total_brl": _format_brl(job.used_items_total),
            "not_used_items_total_brl": _format_brl(job.not_used_items_total),
            "estimated_total_brl": _format_brl(job.estimated_total),
            "labor_mode": "Valor fixo" if job.fixed_labor_value is not None else "Por hora",
        },
    }


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

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    return render(request, "services/service_job_detail.html", _service_job_detail_context(job))


@login_required
def service_work_log_create(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if job.status == ServiceJob.Status.FINISHED:
        messages.error(request, "Reabra o servico antes de alterar horarios.")
        return redirect("service_job_detail", job_id=job.id)

    form = ServiceWorkLogForm(request.POST or None, service_job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Horario do servico adicionado.")
        return redirect("service_job_detail", job_id=job.id)

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    return render(request, "services/service_job_detail.html", _service_job_detail_context(job, work_log_form=form))


@login_required
def service_item_expense_create(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if job.status == ServiceJob.Status.FINISHED:
        messages.error(request, "Reabra o servico antes de alterar itens e despesas.")
        return redirect("service_job_detail", job_id=job.id)

    form = ServiceItemExpenseForm(request.POST or None, service_job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Item/despesa adicionado.")
        return redirect("service_job_detail", job_id=job.id)

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    return render(request, "services/service_job_detail.html", _service_job_detail_context(job, item_form=form))


@login_required
def service_job_status_action(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if request.method != "POST":
        return redirect("service_job_detail", job_id=job.id)

    action = (request.POST.get("action") or "").strip()
    with transaction.atomic():
        if action == "finish":
            job.status = ServiceJob.Status.FINISHED
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Servico finalizado. Agora voce pode gerar o relatorio para o cliente.")
        elif action == "reopen":
            job.status = ServiceJob.Status.IN_PROGRESS
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Servico reaberto para ajustes.")
        else:
            messages.error(request, "Acao invalida para este servico.")

    return redirect("service_job_detail", job_id=job.id)

