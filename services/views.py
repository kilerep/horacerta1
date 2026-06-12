from decimal import Decimal
from html import escape
from io import BytesIO
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
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


def _filename_part(value):
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "servico"


def _service_jobs_for_user(user):
    return ServiceJob.objects.filter(professional=user).select_related("category", "client", "contract")


def _service_report_context(job, request=None):
    work_logs = list(job.work_logs.all())
    items = list(job.item_expenses.all())
    used_items = [item for item in items if item.is_chargeable]
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
    if request is not None:
        public_url = request.build_absolute_uri(reverse("public_service_job_report", args=[job.public_token]))
    emitted_at = timezone.localtime()
    return {
        "job": job,
        "professional_name": professional_name,
        "client_name": job.client_display_name,
        "period_label": period_label,
        "work_logs": work_logs,
        "used_items": used_items,
        "not_used_items": not_used_items,
        "emitted_at": emitted_at,
        "public_url": public_url,
        "summary": {
            "total_hours": job.total_hours_label,
            "labor_total_brl": _format_brl(job.labor_total),
            "used_items_total_brl": _format_brl(job.used_items_total),
            "not_used_items_total_brl": _format_brl(job.not_used_items_total),
            "estimated_total_brl": _format_brl(job.estimated_total),
            "labor_mode": "Valor fixo" if job.fixed_labor_value is not None else "Por hora",
        },
    }


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
    report_context = _service_report_context(job)
    return {
        "job": job,
        "work_logs": work_logs,
        "used_items": used_items,
        "not_used_items": not_used_items,
        "other_items": other_items,
        "work_log_form": work_log_form or ServiceWorkLogForm(service_job=job),
        "item_form": item_form or ServiceItemExpenseForm(service_job=job),
        "is_finished": job.status == ServiceJob.Status.FINISHED,
        "summary": report_context["summary"],
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
            submit_action = (request.POST.get("submit_action") or "").strip()
            posted_status = (request.POST.get("status") or "").strip()
            if submit_action == "draft":
                status = ServiceJob.Status.DRAFT
            elif posted_status in ServiceJob.Status.values:
                status = posted_status
            else:
                status = ServiceJob.Status.IN_PROGRESS
            job = form.save(status=status)
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


@login_required
def service_job_report_pdf(request, job_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    job = get_object_or_404(
        _service_jobs_for_user(request.user).prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
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
    public_url = request.build_absolute_uri(reverse("public_service_job_report", args=[job.public_token]))
    report = _service_report_context(job, request=request)
    message = "\n".join(
        [
            "Olá, segue o relatório do serviço realizado:",
            "",
            f"Serviço: {job.title}",
            f"Cliente: {report['client_name']}",
            f"Total de horas: {report['summary']['total_hours']}",
            f"Itens/despesas usados: {report['summary']['used_items_total_brl']}",
            f"Mão de obra: {report['summary']['labor_total_brl']}",
            f"Total geral: {report['summary']['estimated_total_brl']}",
            "",
            "Acesse o relatório:",
            public_url,
        ]
    )
    return redirect(f"https://wa.me/?text={quote(message, safe='')}")


def public_service_job_report(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
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
        Paragraph(f"Emitido em {timezone.localtime():%d/%m/%Y %H:%M}", styles["Small"]),
        Spacer(1, 10),
    ]

    summary_rows = [
        ["Status", job.get_status_display()],
        ["Prestador", report["professional_name"]],
        ["Cliente", report["client_name"]],
        ["Categoria", job.category.name],
        ["Local", job.service_location or "-"],
        ["Período", report["period_label"]],
        ["Serviço", job.title],
    ]
    story.extend([
        _pdf_table(summary_rows, [3.6 * cm, 13.4 * cm], header=False),
        Spacer(1, 10),
        Paragraph("Descrição", styles["Heading2"]),
        Paragraph(_pdf_text(job.description or "Sem descrição registrada."), styles["Normal"]),
        Spacer(1, 10),
        Paragraph("Horários do serviço", styles["Heading2"]),
    ])

    work_rows = [["Data", "Início", "Fim", "Descrição", "Total"]]
    for log in report["work_logs"]:
        work_rows.append([
            f"{log.work_date:%d/%m/%Y}",
            f"{log.start_time:%H:%M}",
            f"{log.end_time:%H:%M}",
            Paragraph(_pdf_text(log.description), styles["Small"]),
            log.duration_label,
        ])
    if len(work_rows) == 1:
        work_rows.append(["-", "-", "-", "Nenhum horário registrado.", "-"])
    story.extend([_pdf_table(work_rows, [2.5 * cm, 2 * cm, 2 * cm, 7.5 * cm, 2.2 * cm]), Spacer(1, 10)])

    story.append(Paragraph("Itens/despesas usados", styles["Heading2"]))
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
    not_used_rows = [["Nome", "Qtd.", "Valor", "Status", "Observação"]]
    for item in report["not_used_items"]:
        not_used_rows.append([
            Paragraph(_pdf_text(item.name), styles["Small"]),
            str(item.quantity),
            _format_brl(item.total_value),
            item.short_usage_status,
            Paragraph(_pdf_text(item.receipt_note or item.description), styles["Small"]),
        ])
    if len(not_used_rows) == 1:
        not_used_rows.append(["-", "-", "R$ 0,00", "-", "-"])
    story.extend([_pdf_table(not_used_rows, [5.2 * cm, 1.8 * cm, 2.4 * cm, 2.7 * cm, 4.3 * cm]), Spacer(1, 10)])

    totals_rows = [
        ["Total de horas", report["summary"]["total_hours"]],
        ["Valor da mão de obra", report["summary"]["labor_total_brl"]],
        ["Total de itens/despesas usados", report["summary"]["used_items_total_brl"]],
        ["Total geral do serviço", report["summary"]["estimated_total_brl"]],
    ]
    story.extend([
        Paragraph("Resumo de valores", styles["Heading2"]),
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
    response["Content-Disposition"] = f'attachment; filename="relatorio_servico_{client_part}_{date_part}.pdf"'
    return response

