from decimal import Decimal
from html import escape
from io import BytesIO
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from accounts.models import User
from accounts.mei_context import mei_contracts_for_user

from .forms import PlannedServiceItemForm, ServiceItemCatalogForm, ServiceItemExpenseForm, ServiceJobForm, ServiceWorkLogForm
from .models import ServiceCategory, ServiceItemCatalog, ServiceItemExpense, ServiceJob, ServiceWorkLog


def _redirect_if_not_mei(request):
    if request.user.role != User.Role.FUNCIONARIO:
        messages.error(request, "A area de servicos e exclusiva do prestador.")
        return redirect("dashboard")
    return None


def _format_brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_optional_brl(value):
    if value is None:
        return "Valor ainda não definido."
    return _format_brl(value)


def _format_quantity(value):
    value = Decimal(value or 0)
    if value == value.to_integral():
        return str(value.to_integral())
    return f"{value.normalize()}".replace(".", ",")


def _filename_part(value):
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "servico"


def _service_jobs_for_user(user):
    return ServiceJob.objects.filter(professional=user).select_related("category", "client", "contract")


def _catalog_items_for_user(user):
    return ServiceItemCatalog.objects.filter(professional=user).select_related("category")


def _planned_item_rows_from_post(post_data):
    names = post_data.getlist("planned_item_name")
    types = post_data.getlist("planned_item_type")
    quantities = post_data.getlist("planned_item_quantity")
    values = post_data.getlist("planned_item_unit_value")
    descriptions = post_data.getlist("planned_item_description")
    units = post_data.getlist("planned_item_unit")
    catalog_ids = post_data.getlist("planned_item_catalog_id")
    save_flags = set(post_data.getlist("planned_item_save_to_catalog"))
    update_flags = set(post_data.getlist("planned_item_update_catalog_price"))
    rows = []
    for index, name in enumerate(names):
        name = (name or "").strip()
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "type": types[index] if index < len(types) and types[index] else ServiceItemExpense.ItemType.MATERIAL,
                "catalog_item": catalog_ids[index] if index < len(catalog_ids) else "",
                "unit": units[index] if index < len(units) and units[index] else "UNIT",
                "quantity": quantities[index] if index < len(quantities) and quantities[index] else "1",
                "unit_value": values[index] if index < len(values) and values[index] else "0",
                "description": descriptions[index] if index < len(descriptions) else "",
                "save_to_catalog": "on" if str(index) in save_flags else "",
                "update_catalog_price": "on" if str(index) in update_flags else "",
            }
        )
    return rows


def _create_planned_items(job, rows):
    for row in rows:
        form = PlannedServiceItemForm(row, service_job=job)
        if form.is_valid():
            form.save()


def _mark_preview_updated(job):
    if job.preview_generated_at:
        job.preview_updated_at = timezone.now()
        job.save(update_fields=["preview_updated_at", "updated_at"])


def _quote_items_for_job(job):
    return [
        item
        for item in job.item_expenses.all()
        if item.usage_status in (ServiceItemExpense.UsageStatus.PLANNED, ServiceItemExpense.UsageStatus.QUOTED)
    ]


def _service_quote_message(job, quote_items):
    lines = [
        "Olá, preciso de uma cotação dos itens abaixo:",
        "",
        f"Serviço: {job.title}",
        "",
        "Itens:",
        "",
    ]
    for item in quote_items:
        note = (item.description or item.receipt_note or "").strip()
        note_text = f" - {note[:90]}" if note else ""
        lines.append(f"* {_format_quantity(item.quantity)} x {item.name}{note_text}")
    lines.extend(
        [
            "",
            "Pode me passar os valores e disponibilidade?",
            "",
            "Obrigado.",
        ]
    )
    return "\n".join(lines)


def _service_report_context(job, request=None):
    work_logs = list(job.work_logs.all())
    items = list(job.item_expenses.all())
    used_items = [item for item in items if item.is_chargeable]
    planned_items = [
        item
        for item in items
        if item.usage_status
        in (
            ServiceItemExpense.UsageStatus.PLANNED,
            ServiceItemExpense.UsageStatus.QUOTED,
            ServiceItemExpense.UsageStatus.PURCHASED,
        )
    ]
    not_used_items = [
        item
        for item in items
        if item.usage_status in ServiceItemExpense.NON_CHARGEABLE_USAGE_STATUSES
    ]
    professional_name = (
        getattr(getattr(job.contract, "employee", None), "full_name", "")
        or job.professional.get_full_name()
        or job.professional.email
        or job.professional.username
    )
    professional_contact = job.professional.email or getattr(job.professional, "username", "")
    period_start = job.start_date
    period_end = job.end_date
    if work_logs:
        work_dates = [log.work_date for log in work_logs]
        period_start = period_start or min(work_dates)
        period_end = period_end or max(work_dates)
    if period_start and period_end and period_start != period_end:
        period_label = f"{period_start:%d/%m/%Y} a {period_end:%d/%m/%Y}"
    elif period_start:
        period_label = f"{period_start:%d/%m/%Y}"
    else:
        period_label = "-"
    public_url = ""
    preview_public_url = ""
    if request is not None:
        public_url = request.build_absolute_uri(reverse("public_service_job_report", args=[job.public_token]))
        preview_public_url = request.build_absolute_uri(reverse("public_service_job_preview", args=[job.public_token]))
    emitted_at = timezone.localtime()
    return {
        "job": job,
        "professional_name": professional_name,
        "professional_contact": professional_contact,
        "client_name": job.client_display_name,
        "client_whatsapp": job.client_whatsapp,
        "service_address": job.full_service_address,
        "period_label": period_label,
        "work_logs": work_logs,
        "planned_items": planned_items,
        "used_items": used_items,
        "not_used_items": not_used_items,
        "emitted_at": emitted_at,
        "public_url": public_url,
        "preview_public_url": preview_public_url,
        "summary": {
            "total_hours": job.total_hours_label,
            "labor_total_brl": _format_brl(job.labor_total),
            "used_items_total_brl": _format_brl(job.used_items_total),
            "not_used_items_total_brl": _format_brl(job.not_used_items_total),
            "preview_items_total_brl": _format_brl(job.preview_items_total),
            "preview_labor_total_brl": _format_optional_brl(job.preview_labor_total),
            "preview_estimated_total_brl": _format_optional_brl(job.preview_estimated_total),
            "estimated_total_brl": _format_brl(job.estimated_total),
            "labor_mode": "Valor fixo" if job.fixed_labor_value is not None else "Por hora",
        },
    }


def _service_job_detail_context(job, *, work_log_form=None, item_form=None):
    work_logs = job.work_logs.all()
    items = job.item_expenses.all()
    used_items = [item for item in items if item.is_chargeable]
    expense_type_values = {
        ServiceItemExpense.ItemType.EXPENSE,
        ServiceItemExpense.ItemType.TOLL,
        ServiceItemExpense.ItemType.FUEL,
        ServiceItemExpense.ItemType.PARKING,
        ServiceItemExpense.ItemType.FOOD,
    }
    expense_items = [item for item in items if item.type in expense_type_values]
    not_used_items = [
        item
        for item in items
        if item.usage_status in ServiceItemExpense.NON_CHARGEABLE_USAGE_STATUSES
    ]
    pending_items = [
        item
        for item in items
        if item not in used_items and item not in not_used_items
    ]
    quote_items = _quote_items_for_job(job)
    quote_message = _service_quote_message(job, quote_items) if quote_items else ""
    open_work_log = next((log for log in work_logs if log.end_time is None), None)
    has_work_logs = bool(work_logs)
    has_chargeable_items = bool(used_items)
    can_finish_service = (
        job.status
        in (
            ServiceJob.Status.DRAFT,
            ServiceJob.Status.PLANNED,
            ServiceJob.Status.SENT,
            ServiceJob.Status.SCHEDULED,
            ServiceJob.Status.IN_PROGRESS,
        )
        and not open_work_log
        and (job.status == ServiceJob.Status.IN_PROGRESS or has_work_logs or has_chargeable_items)
    )
    report_context = _service_report_context(job)
    return {
        "job": job,
        "work_logs": work_logs,
        "used_items": used_items,
        "expense_items": expense_items,
        "not_used_items": not_used_items,
        "pending_items": pending_items,
        "quote_items": quote_items,
        "quote_message": quote_message,
        "quote_whatsapp_url": reverse("service_job_quote_whatsapp", args=[job.id]),
        "open_work_log": open_work_log,
        "work_log_form": work_log_form or ServiceWorkLogForm(service_job=job),
        "item_form": item_form or ServiceItemExpenseForm(service_job=job),
        "is_finished": job.status == ServiceJob.Status.FINISHED,
        "is_draft": job.status == ServiceJob.Status.DRAFT,
        "is_archived": job.status == ServiceJob.Status.ARCHIVED,
        "has_work_logs": has_work_logs,
        "has_chargeable_items": has_chargeable_items,
        "can_finish_service": can_finish_service,
        "can_edit_entries": job.status in (
            ServiceJob.Status.DRAFT,
            ServiceJob.Status.PLANNED,
            ServiceJob.Status.SENT,
            ServiceJob.Status.SCHEDULED,
            ServiceJob.Status.IN_PROGRESS,
        ),
        "summary": report_context["summary"],
        "preview_status_label": job.preview_status_label,
        "preview_generated_at": job.preview_generated_at,
        "preview_sent_at": job.preview_sent_at,
        "preview_first_viewed_at": job.preview_first_viewed_at,
        "preview_updated_at": job.preview_updated_at,
        "preview_generate_url": reverse("service_job_preview_generate", args=[job.id]),
        "preview_public_url": reverse("public_service_job_preview", args=[job.public_token]),
        "preview_whatsapp_url": reverse("service_job_preview_whatsapp", args=[job.id]),
        "report_public_url": reverse("public_service_job_report", args=[job.public_token]),
        "report_pdf_url": reverse("service_job_report_pdf", args=[job.id]),
        "report_whatsapp_url": reverse("service_job_report_whatsapp", args=[job.id]),
        "public_report_first_viewed_at": job.public_report_first_viewed_at,
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
    search_query = (request.GET.get("q") or "").strip()

    if selected_status:
        jobs = jobs.filter(status=selected_status)
    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(manual_client_name__icontains=search_query)
            | Q(client__name__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )
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
        archived=Count("id", filter=Q(status=ServiceJob.Status.ARCHIVED)),
    )
    estimated_total = sum(
        (job.estimated_total for job in all_jobs.prefetch_related("work_logs", "item_expenses")),
        Decimal("0.00"),
    )
    has_advanced_filters = bool(selected_category or selected_contract or date_from or date_to)

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
        "search_query": search_query,
        "has_advanced_filters": has_advanced_filters,
        "status_filter_urls": {
            "all": reverse("service_job_list"),
            "in_progress": f"{reverse('service_job_list')}?status={ServiceJob.Status.IN_PROGRESS}",
            "finished": f"{reverse('service_job_list')}?status={ServiceJob.Status.FINISHED}",
            "drafts": f"{reverse('service_job_list')}?status={ServiceJob.Status.DRAFT}",
            "archived": f"{reverse('service_job_list')}?status={ServiceJob.Status.ARCHIVED}",
        },
        "summary": {
            "in_progress": status_counts["in_progress"] or 0,
            "finished": status_counts["finished"] or 0,
            "drafts": status_counts["drafts"] or 0,
            "archived": status_counts["archived"] or 0,
            "estimated_total_brl": _format_brl(estimated_total),
        },
    }
    return render(request, "services/service_job_list.html", context)


@login_required
def service_item_catalog_list(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    q = (request.GET.get("q") or "").strip()
    show_inactive = request.GET.get("inactive") == "1"
    items = _catalog_items_for_user(request.user)
    if not show_inactive:
        items = items.filter(is_active=True)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(
        request,
        "services/service_item_catalog_list.html",
        {
            "catalog_items": items,
            "q": q,
            "show_inactive": show_inactive,
        },
    )


@login_required
def service_item_catalog_create(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    if request.method == "POST":
        form = ServiceItemCatalogForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Item salvo no catalogo.")
            return redirect("service_item_catalog_list")
    else:
        form = ServiceItemCatalogForm(user=request.user)
    return render(
        request,
        "services/service_item_catalog_form.html",
        {"form": form, "form_title": "Novo item do catalogo"},
    )


@login_required
def service_item_catalog_update(request, item_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    item = get_object_or_404(_catalog_items_for_user(request.user), id=item_id)
    if request.method == "POST":
        form = ServiceItemCatalogForm(request.POST, user=request.user, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Item do catalogo atualizado.")
            return redirect("service_item_catalog_list")
    else:
        form = ServiceItemCatalogForm(user=request.user, instance=item)
    return render(
        request,
        "services/service_item_catalog_form.html",
        {"form": form, "form_title": "Editar item do catalogo", "catalog_item": item},
    )


@login_required
def service_item_catalog_toggle_favorite(request, item_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    item = get_object_or_404(_catalog_items_for_user(request.user), id=item_id)
    if request.method == "POST":
        item.favorite = not item.favorite
        item.save(update_fields=["favorite", "updated_at"])
        messages.success(request, "Favorito atualizado.")
    return redirect("service_item_catalog_list")


@login_required
def service_item_catalog_deactivate(request, item_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    item = get_object_or_404(_catalog_items_for_user(request.user), id=item_id)
    if request.method == "POST":
        item.is_active = False
        item.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Item desativado.")
    return redirect("service_item_catalog_list")


@login_required
def service_item_catalog_seed_suggestions(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    if request.method != "POST":
        return redirect("service_item_catalog_list")

    categories = {category.slug: category for category in ServiceCategory.objects.filter(slug__in=["eletrica", "entrega-viagem"])}
    suggestions = [
        ("eletrica", ServiceItemExpense.ItemType.PART, "Disjuntor 20A", "UNIT"),
        ("eletrica", ServiceItemExpense.ItemType.PART, "Disjuntor 32A", "UNIT"),
        ("eletrica", ServiceItemExpense.ItemType.MATERIAL, "Tomada 10A", "UNIT"),
        ("eletrica", ServiceItemExpense.ItemType.MATERIAL, "Tomada 20A", "UNIT"),
        ("eletrica", ServiceItemExpense.ItemType.MATERIAL, "Fita isolante", "ROLL"),
        ("eletrica", ServiceItemExpense.ItemType.MATERIAL, "Cabo 2,5mm", "METER"),
        ("eletrica", ServiceItemExpense.ItemType.MATERIAL, "Cabo 4mm", "METER"),
        ("entrega-viagem", ServiceItemExpense.ItemType.TOLL, "Pedagio", "UNIT"),
        ("entrega-viagem", ServiceItemExpense.ItemType.FUEL, "Combustivel", "LITER"),
        ("entrega-viagem", ServiceItemExpense.ItemType.PARKING, "Estacionamento", "UNIT"),
        ("entrega-viagem", ServiceItemExpense.ItemType.FOOD, "Alimentacao", "UNIT"),
        ("entrega-viagem", ServiceItemExpense.ItemType.EXPENSE, "Diaria/deslocamento", "SERVICE"),
    ]
    created = 0
    for slug, item_type, name, unit in suggestions:
        if ServiceItemCatalog.objects.filter(professional=request.user, name__iexact=name, is_active=True).exists():
            continue
        ServiceItemCatalog.objects.create(
            professional=request.user,
            category=categories.get(slug),
            item_type=item_type,
            name=name,
            unit=unit,
            estimated_unit_value=None,
        )
        created += 1
    messages.success(request, f"{created} sugestoes adicionadas sem preco estimado.")
    return redirect("service_item_catalog_list")


@login_required
def service_item_catalog_search(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    q = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    items = _catalog_items_for_user(request.user).filter(is_active=True)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category_id:
        items = items.filter(Q(category_id=category_id) | Q(category__isnull=True))
    items = items.order_by("-favorite", "name")[:10]
    return JsonResponse(
        {
            "items": [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "description": item.description,
                    "item_type": item.item_type,
                    "item_type_label": item.get_item_type_display(),
                    "unit": item.unit,
                    "unit_label": item.get_unit_display(),
                    "estimated_unit_value": str(item.estimated_unit_value or ""),
                    "last_used_value": str(item.last_used_value or ""),
                    "last_used_at": timezone.localtime(item.last_used_at).strftime("%d/%m/%Y") if item.last_used_at else "",
                    "default_quantity": str(item.default_quantity),
                    "favorite": item.favorite,
                }
                for item in items
            ]
        }
    )


@login_required
def service_job_create(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user)
        if form.is_valid():
            submit_action = (request.POST.get("submit_action") or "").strip()
            posted_status = (request.POST.get("status") or "").strip()
            if submit_action == "draft":
                status = ServiceJob.Status.DRAFT
            elif posted_status in ServiceJob.Status.values:
                status = posted_status
            else:
                status = ServiceJob.Status.PLANNED
            with transaction.atomic():
                job = form.save(status=status)
                _create_planned_items(job, _planned_item_rows_from_post(request.POST))
            messages.success(request, "Servico salvo com sucesso.")
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user)

    return render(
        request,
        "services/service_job_form.html",
        {
            "form": form,
            "form_title": "Novo serviço",
            "form_subtitle": "Cadastre um trabalho específico com cliente, local, previsão de atendimento, itens e relatório final.",
            "is_edit": False,
            "item_type_choices": ServiceItemExpense.ItemType.choices,
            "item_unit_choices": ServiceItemCatalog._meta.get_field("unit").choices,
        },
    )


@login_required
def service_job_update(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user, instance=job)
        if form.is_valid():
            job = form.save(status=job.status)
            _mark_preview_updated(job)
            messages.success(request, "Dados do servico atualizados.")
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user, instance=job)

    return render(
        request,
        "services/service_job_form.html",
        {
            "form": form,
            "form_title": "Editar serviço",
            "form_subtitle": "Atualize cliente, local, descrição e previsão deste serviço.",
            "is_edit": True,
            "job": job,
        },
    )


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
    if job.status not in (
        ServiceJob.Status.DRAFT,
        ServiceJob.Status.PLANNED,
        ServiceJob.Status.SENT,
        ServiceJob.Status.SCHEDULED,
        ServiceJob.Status.IN_PROGRESS,
    ):
        messages.error(request, "Reabra o servico antes de alterar horarios.")
        return redirect("service_job_detail", job_id=job.id)

    form = ServiceWorkLogForm(request.POST or None, service_job=job)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            if job.status != ServiceJob.Status.IN_PROGRESS:
                job.status = ServiceJob.Status.IN_PROGRESS
                job.save(update_fields=["status", "finished_at", "updated_at"])
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
    if job.status not in (
        ServiceJob.Status.DRAFT,
        ServiceJob.Status.PLANNED,
        ServiceJob.Status.SENT,
        ServiceJob.Status.SCHEDULED,
        ServiceJob.Status.IN_PROGRESS,
    ):
        messages.error(request, "Reabra o servico antes de alterar itens e despesas.")
        return redirect("service_job_detail", job_id=job.id)

    form = ServiceItemExpenseForm(request.POST or None, service_job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        _mark_preview_updated(job)
        messages.success(request, "Item/despesa adicionado.")
        return redirect("service_job_detail", job_id=job.id)

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    return render(request, "services/service_job_detail.html", _service_job_detail_context(job, item_form=form))


@login_required
def service_item_expense_update(request, job_id, item_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    item = get_object_or_404(job.item_expenses, id=item_id)
    if job.status == ServiceJob.Status.ARCHIVED:
        messages.error(request, "Reabra o servico antes de alterar itens.")
        return redirect("service_job_detail", job_id=job.id)
    if request.method == "POST":
        form = ServiceItemExpenseForm(request.POST, service_job=job, instance=item)
        if form.is_valid():
            form.save()
            _mark_preview_updated(job)
            messages.success(request, "Item atualizado.")
        else:
            messages.error(request, "Revise os dados do item.")
    return redirect("service_job_detail", job_id=job.id)


@login_required
def service_job_quote_whatsapp(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user).prefetch_related("item_expenses"), id=job_id)
    quote_items = _quote_items_for_job(job)
    if not quote_items:
        messages.error(request, "Adicione itens previstos para gerar uma mensagem de cotacao.")
        return redirect("service_job_detail", job_id=job.id)

    message = _service_quote_message(job, quote_items)
    job.quote_message_generated_at = timezone.now()
    job.quote_item_count = len(quote_items)
    job.save(update_fields=["quote_message_generated_at", "quote_item_count", "updated_at"])
    return redirect(f"https://wa.me/?text={quote(message, safe='')}")


@login_required
def service_clock_action(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if request.method != "POST":
        return redirect("service_job_detail", job_id=job.id)
    if job.status in (ServiceJob.Status.FINISHED, ServiceJob.Status.ARCHIVED):
        messages.error(request, "Reabra o servico antes de registrar execucao.")
        return redirect("service_job_detail", job_id=job.id)

    action = (request.POST.get("action") or "").strip()
    now = timezone.localtime()
    with transaction.atomic():
        open_log = job.work_logs.filter(end_time__isnull=True).order_by("-created_at").first()
        if action == "start":
            if open_log:
                messages.error(request, "Ja existe um periodo de trabalho aberto neste servico.")
            else:
                ServiceWorkLog.objects.create(
                    service_job=job,
                    work_date=now.date(),
                    start_time=now.time().replace(second=0, microsecond=0),
                    description="Trabalho iniciado pelo cronometro",
                )
                if job.status != ServiceJob.Status.IN_PROGRESS:
                    job.status = ServiceJob.Status.IN_PROGRESS
                    job.save(update_fields=["status", "finished_at", "updated_at"])
                messages.success(request, "Trabalho iniciado.")
        elif action == "stop":
            if not open_log:
                messages.error(request, "Nenhum periodo aberto para encerrar.")
            else:
                open_log.end_time = now.time().replace(second=0, microsecond=0)
                open_log.save()
                messages.success(request, "Periodo de trabalho encerrado.")
    return redirect("service_job_detail", job_id=job.id)


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
        if action == "send_preview" and job.status in (ServiceJob.Status.DRAFT, ServiceJob.Status.PLANNED):
            job.status = ServiceJob.Status.SENT
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Prévia marcada como enviada ao cliente.")
        elif action == "schedule" and job.status in (ServiceJob.Status.DRAFT, ServiceJob.Status.PLANNED, ServiceJob.Status.SENT):
            job.status = ServiceJob.Status.SCHEDULED
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Serviço agendado.")
        elif action == "start" and job.status in (
            ServiceJob.Status.DRAFT,
            ServiceJob.Status.PLANNED,
            ServiceJob.Status.SENT,
            ServiceJob.Status.SCHEDULED,
        ):
            job.status = ServiceJob.Status.IN_PROGRESS
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Serviço iniciado.")
        elif action == "finish" and job.status in (
            ServiceJob.Status.DRAFT,
            ServiceJob.Status.PLANNED,
            ServiceJob.Status.SENT,
            ServiceJob.Status.SCHEDULED,
            ServiceJob.Status.IN_PROGRESS,
        ):
            if job.work_logs.filter(end_time__isnull=True).exists():
                messages.error(request, "Encerre o periodo aberto antes de finalizar o servico.")
                return redirect("service_job_detail", job_id=job.id)
            has_work_logs = job.work_logs.exists()
            has_chargeable_items = job.item_expenses.filter(
                usage_status__in=ServiceItemExpense.CHARGEABLE_USAGE_STATUSES
            ).exists()
            if not (job.status == ServiceJob.Status.IN_PROGRESS or has_work_logs or has_chargeable_items):
                messages.error(request, "Registre periodos trabalhados ou confirme itens usados antes de finalizar o servico.")
                return redirect("service_job_detail", job_id=job.id)
            job.status = ServiceJob.Status.FINISHED
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Serviço finalizado. Agora você pode gerar o relatório para o cliente.")
        elif action == "reopen" and job.status in (ServiceJob.Status.FINISHED, ServiceJob.Status.ARCHIVED):
            job.status = ServiceJob.Status.IN_PROGRESS
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Serviço reaberto para ajustes.")
        elif action == "archive" and job.status != ServiceJob.Status.ARCHIVED:
            job.status = ServiceJob.Status.ARCHIVED
            job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(request, "Serviço arquivado.")
        else:
            messages.error(request, "Acao invalida para este servico.")

    return redirect("service_job_detail", job_id=job.id)


@login_required
def service_job_preview_generate(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user), id=job_id)
    if request.method != "POST":
        return redirect("service_job_detail", job_id=job.id)

    now = timezone.now()
    update_fields = ["updated_at"]
    if not job.preview_generated_at:
        job.preview_generated_at = now
        update_fields.append("preview_generated_at")
        messages.success(request, "Prévia gerada. O link público já pode ser enviado ao cliente.")
    else:
        job.preview_updated_at = now
        update_fields.append("preview_updated_at")
        messages.success(request, "Prévia atualizada.")
    job.save(update_fields=update_fields)
    return redirect("service_job_detail", job_id=job.id)


@login_required
def service_job_report_pdf(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    if job.status != ServiceJob.Status.FINISHED:
        messages.error(request, "Finalize o servico antes de gerar o PDF do servico.")
        return redirect("service_job_detail", job_id=job.id)
    return _service_job_pdf_response(job)


@login_required
def service_job_report_whatsapp(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    if job.status != ServiceJob.Status.FINISHED:
        messages.error(request, "Finalize o servico antes de enviar o relatorio pelo WhatsApp.")
        return redirect("service_job_detail", job_id=job.id)
    public_url = request.build_absolute_uri(reverse("public_service_job_report", args=[job.public_token]))
    report = _service_report_context(job, request=request)
    message = "\n".join(
        [
            "Olá, segue o relatório do serviço:",
            "",
            f"Serviço: {job.title}",
            f"Cliente: {report['client_name']}",
            f"Horas realizadas: {report['summary']['total_hours']}",
            f"Mão de obra: {report['summary']['labor_total_brl']}",
            f"Itens/despesas: {report['summary']['used_items_total_brl']}",
            f"Total do serviço: {report['summary']['estimated_total_brl']}",
            "",
            "Acesse o relatório:",
            public_url,
        ]
    )
    return redirect(f"https://wa.me/?text={quote(message, safe='')}")


@login_required
def service_job_preview_whatsapp(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(_service_jobs_for_user(request.user).prefetch_related("item_expenses"), id=job_id)
    public_url = request.build_absolute_uri(reverse("public_service_job_preview", args=[job.public_token]))
    report = _service_report_context(job, request=request)
    planned_date = f"{job.start_date:%d/%m/%Y}" if job.start_date else "a combinar"
    planned_time = f" às {job.planned_start_time:%H:%M}" if job.planned_start_time else ""
    message = "\n".join(
        [
            "Olá, segue a prévia do serviço combinado:",
            "",
            f"Serviço: {job.title}",
            f"Data prevista: {planned_date}{planned_time}",
            f"Local: {job.service_location_summary or job.full_service_address or '-'}",
            f"Itens previstos: {report['summary']['preview_items_total_brl']}",
            f"Mão de obra estimada: {report['summary']['preview_labor_total_brl']}",
            f"Total estimado: {report['summary']['preview_estimated_total_brl']}",
            "",
            "Acesse a prévia:",
            public_url,
            "",
            "Observação: os valores podem ser ajustados conforme compra real dos materiais e execução do serviço.",
        ]
    )
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
    return redirect(f"https://wa.me/?text={quote(message, safe='')}")


def public_service_job_preview(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
        preview_generated_at__isnull=False,
    )
    if not job.preview_first_viewed_at:
        job.preview_first_viewed_at = timezone.now()
        job.save(update_fields=["preview_first_viewed_at", "updated_at"])
    return render(
        request,
        "services/public_service_job_report.html",
        {**_service_report_context(job, request=request), "is_preview": True},
    )


def public_service_job_report(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
        status=ServiceJob.Status.FINISHED,
    )
    if not job.public_report_first_viewed_at:
        job.public_report_first_viewed_at = timezone.now()
        job.save(update_fields=["public_report_first_viewed_at", "updated_at"])
    return render(request, "services/public_service_job_report.html", _service_report_context(job, request=request))


def public_service_job_report_pdf(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
        status=ServiceJob.Status.FINISHED,
    )
    return _service_job_pdf_response(job)


def _pdf_text(value, default="-"):
    return escape(str(value if value not in (None, "") else default))


def _pdf_table(rows, col_widths, *, header=True):
    table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def _service_job_pdf_response(job):
    report = _service_report_context(job)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title="HoraCerta - Relatório de serviço",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].fontSize = 18
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 15

    story = [
        Paragraph("HoraCerta", styles["Title"]),
        Paragraph("Relatório de serviço", styles["Heading2"]),
        Paragraph(f"Data de emissao: {timezone.localtime():%d/%m/%Y %H:%M}", styles["Small"]),
        Spacer(1, 10),
    ]

    summary_rows = [
        ["Status", job.get_status_display()],
        ["Prestador", report["professional_name"]],
        ["Contato", report["professional_contact"] or "-"],
        ["Cliente", report["client_name"]],
        ["WhatsApp", report["client_whatsapp"] or "-"],
        ["Categoria", job.category.name],
        ["Endereco/local", report["service_address"] or "-"],
        ["Data prevista", report["period_label"]],
        ["Serviço", job.title],
    ]
    story.extend([
        _pdf_table(summary_rows, [3.6 * cm, 13.4 * cm], header=False),
        Spacer(1, 10),
        Paragraph("Descrição", styles["Heading2"]),
        Paragraph(_pdf_text(job.description or "Sem descrição registrada."), styles["Normal"]),
        Spacer(1, 10),
        Paragraph("Horas realizadas", styles["Heading2"]),
    ])

    work_rows = [["Data", "Início", "Fim", "Atividade", "Total"]]
    for log in report["work_logs"]:
        work_rows.append([
            f"{log.work_date:%d/%m/%Y}",
            f"{log.start_time:%H:%M}",
            f"{log.end_time:%H:%M}" if log.end_time else "Em andamento",
            Paragraph(_pdf_text(log.description), styles["Small"]),
            log.duration_label if log.end_time else "-",
        ])
    if len(work_rows) == 1:
        work_rows.append(["-", "-", "-", "Nenhuma hora realizada registrada.", "-"])
    story.extend([_pdf_table(work_rows, [2.5 * cm, 2 * cm, 2 * cm, 7.5 * cm, 2.2 * cm]), Spacer(1, 10)])

    story.append(Paragraph("Itens usados/cobrados", styles["Heading2"]))
    used_rows = [["Nome", "Tipo", "Qtd.", "Unitário", "Total"]]
    for item in report["used_items"]:
        used_rows.append([
            Paragraph(_pdf_text(item.name), styles["Small"]),
            item.get_type_display(),
            str(item.quantity),
            _format_brl(item.unit_value),
            _format_brl(item.total_value),
        ])
    if len(used_rows) == 1:
        used_rows.append(["-", "-", "-", "-", "R$ 0,00"])
    story.extend([_pdf_table(used_rows, [6 * cm, 3.2 * cm, 2 * cm, 2.5 * cm, 2.7 * cm]), Spacer(1, 10)])

    story.append(Paragraph("Itens não usados/devolvidos", styles["Heading2"]))
    not_used_rows = [["Nome", "Tipo", "Qtd.", "Valor", "Status"]]
    for item in report["not_used_items"]:
        not_used_rows.append([
            Paragraph(_pdf_text(item.name), styles["Small"]),
            item.get_type_display(),
            str(item.quantity),
            _format_brl(item.total_value),
            item.short_usage_status,
        ])
    if len(not_used_rows) == 1:
        not_used_rows.append(["-", "-", "-", "R$ 0,00", "-"])
    story.extend([_pdf_table(not_used_rows, [5.2 * cm, 3 * cm, 1.8 * cm, 2.5 * cm, 3.9 * cm]), Spacer(1, 10)])

    totals_rows = [
        ["Total de horas", report["summary"]["total_hours"]],
        ["Mão de obra", report["summary"]["labor_total_brl"]],
        ["Total de itens/despesas usados", report["summary"]["used_items_total_brl"]],
        ["Total do serviço", report["summary"]["estimated_total_brl"]],
    ]
    story.extend([
        Paragraph("Resumo", styles["Heading2"]),
        _pdf_table(totals_rows, [7 * cm, 9.5 * cm], header=False),
        Spacer(1, 10),
        Paragraph("Observações finais", styles["Heading2"]),
        Paragraph(_pdf_text(job.notes or "Sem observações finais."), styles["Normal"]),
        Spacer(1, 10),
        Paragraph("Relatório gerado pelo HoraCerta.", styles["Small"]),
    ])

    doc.build(story)
    client_part = _filename_part(report["client_name"])
    date_part = timezone.localdate().strftime("%Y%m%d")
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="horacerta_servico_{client_part}_{date_part}.pdf"'
    return response

