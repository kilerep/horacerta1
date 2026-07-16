from decimal import Decimal
from html import escape
from io import BytesIO
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import views as service_views
from .models import ServiceItemExpense, ServiceJob


EXPENSE_TYPES = {
    ServiceItemExpense.ItemType.EXPENSE,
    ServiceItemExpense.ItemType.TOLL,
    ServiceItemExpense.ItemType.FUEL,
    ServiceItemExpense.ItemType.PARKING,
    ServiceItemExpense.ItemType.FOOD,
}


DOCUMENT_CACHE_CONTROL = "private, no-store, no-cache, max-age=0, must-revalidate"


def _format_brl(value):
    amount = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _filename_part(value):
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "servico"


def _period_label(job, work_logs):
    dates = [log.work_date for log in work_logs]
    start = min(dates) if dates else job.start_date
    end = max(dates) if dates else job.end_date or job.start_date
    if start and end and start != end:
        return f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
    if start:
        return f"{start:%d/%m/%Y}"
    return "Não informado"


def _professional_contact(job, *, is_public=False):
    employee = getattr(getattr(job, "contract", None), "employee", None)
    phone = (getattr(employee, "phone", "") or "").strip()
    if phone:
        return phone
    if is_public:
        return ""
    return job.professional.email or job.professional.username


def _secure_document_response(response):
    response["Cache-Control"] = DOCUMENT_CACHE_CONTROL
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _record_public_document_view(job):
    if job.public_report_first_viewed_at:
        return job.public_report_first_viewed_at
    viewed_at = timezone.now()
    updated = ServiceJob.objects.filter(
        pk=job.pk,
        public_report_first_viewed_at__isnull=True,
    ).update(public_report_first_viewed_at=viewed_at)
    if updated:
        job.public_report_first_viewed_at = viewed_at
    else:
        job.refresh_from_db(fields=["public_report_first_viewed_at"])
    return job.public_report_first_viewed_at


def _accountability_context(job, request=None, *, is_public=False):
    work_logs = list(job.work_logs.all())
    chargeable_items = [
        item
        for item in job.item_expenses.all()
        if item.usage_status in ServiceItemExpense.CHARGEABLE_USAGE_STATUSES
    ]
    expenses = [item for item in chargeable_items if item.type in EXPENSE_TYPES]
    materials = [item for item in chargeable_items if item.type not in EXPENSE_TYPES]
    expense_total = sum((item.total_value for item in expenses), Decimal("0.00"))
    material_total = sum((item.total_value for item in materials), Decimal("0.00"))
    professional_name = (
        getattr(getattr(job.contract, "employee", None), "full_name", "")
        or job.professional.get_full_name()
        or job.professional.email
        or job.professional.username
    )
    public_url = ""
    whatsapp_url = ""
    if request is not None and job.status == ServiceJob.Status.REPORT_SENT:
        public_url = request.build_absolute_uri(reverse("public_service_accountability", args=[job.public_token]))
        whatsapp_message = (
            "Olá, segue a prestação de contas do serviço "
            f"{job.title}:\n{public_url}"
        )
        whatsapp_url = f"https://wa.me/?text={quote(whatsapp_message)}"
    return {
        "job": job,
        "is_public": is_public,
        "professional_name": professional_name,
        "professional_contact": _professional_contact(job, is_public=is_public),
        "client_name": job.client_display_name,
        "service_address": job.full_service_address or job.service_location_summary,
        "period_label": _period_label(job, work_logs),
        "work_logs": work_logs,
        "expenses": expenses,
        "materials": materials,
        "public_url": public_url,
        "whatsapp_url": whatsapp_url,
        "summary": {
            "total_hours": job.total_hours_label,
            "labor_total_brl": _format_brl(job.labor_total),
            "expense_total_brl": _format_brl(expense_total),
            "material_total_brl": _format_brl(material_total),
            "grand_total_brl": _format_brl(job.labor_total + expense_total + material_total),
        },
    }


@login_required
def service_accountability(request, job_id):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    job = get_object_or_404(
        ServiceJob.objects.filter(professional=request.user)
        .select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    context = _accountability_context(job, request=request)
    context.update(
        {
            "pdf_url": reverse("service_accountability_pdf", args=[job.id]),
            "back_url": reverse("service_job_detail", args=[job.id]),
        }
    )
    response = render(request, "services/service_accountability_report.html", context)
    return _secure_document_response(response)


@login_required
def service_accountability_pdf(request, job_id):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    job = get_object_or_404(
        ServiceJob.objects.filter(professional=request.user)
        .select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        id=job_id,
    )
    return _accountability_pdf_response(job)


def public_service_accountability(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
        status=ServiceJob.Status.REPORT_SENT,
    )
    _record_public_document_view(job)
    context = _accountability_context(job, request=request, is_public=True)
    context["pdf_url"] = reverse("public_service_accountability_pdf", args=[job.public_token])
    response = render(request, "services/service_accountability_report.html", context)
    return _secure_document_response(response)


def public_service_accountability_pdf(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract", "contract__employee")
        .prefetch_related("work_logs", "item_expenses"),
        public_token=token,
        status=ServiceJob.Status.REPORT_SENT,
    )
    _record_public_document_view(job)
    return _accountability_pdf_response(job, is_public=True)


def _pdf_text(value, default="-"):
    return escape(str(value if value not in (None, "") else default))


def _table(rows, widths, *, header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
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


def _accountability_pdf_response(job, *, is_public=False):
    report = _accountability_context(job, is_public=True if is_public else True)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.3 * cm,
        leftMargin=1.3 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="HoraCerta - Prestação de contas",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].fontSize = 18
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 15

    story = [
        Paragraph("HoraCerta", styles["Title"]),
        Paragraph("Prestação de contas do serviço", styles["Heading2"]),
        Paragraph(f"Emitido em {timezone.localtime():%d/%m/%Y %H:%M}", styles["Small"]),
        Spacer(1, 10),
        _table(
            [
                ["Prestador", report["professional_name"]],
                ["Contato profissional", report["professional_contact"] or "Não divulgado"],
                ["Cliente/empresa", report["client_name"]],
                ["Serviço", job.title],
                ["Categoria", job.category.name],
                ["Período", report["period_label"]],
                ["Local", report["service_address"] or "-"],
            ],
            [4 * cm, 12.5 * cm],
            header=False,
        ),
        Spacer(1, 10),
        Paragraph("Horas e atividades", styles["Heading2"]),
    ]

    work_rows = [["Data", "Início", "Fim", "Atividade", "Total"]]
    for log in report["work_logs"]:
        work_rows.append(
            [
                f"{log.work_date:%d/%m/%Y}",
                f"{log.start_time:%H:%M}",
                f"{log.end_time:%H:%M}" if log.end_time else "Em andamento",
                Paragraph(_pdf_text(log.description), styles["Small"]),
                log.duration_label if log.end_time else "-",
            ]
        )
    if len(work_rows) == 1:
        work_rows.append(["-", "-", "-", "Nenhum período registrado.", "-"])
    story.extend([_table(work_rows, [2.4 * cm, 1.8 * cm, 1.8 * cm, 8.2 * cm, 2.1 * cm]), Spacer(1, 10)])

    story.append(Paragraph("Despesas do atendimento ou viagem", styles["Heading2"]))
    expense_rows = [["Despesa", "Tipo", "Referência/comprovante", "Total"]]
    for item in report["expenses"]:
        detail = item.receipt_note or item.description or "-"
        expense_rows.append(
            [
                Paragraph(_pdf_text(item.name), styles["Small"]),
                item.get_type_display(),
                Paragraph(_pdf_text(detail), styles["Small"]),
                _format_brl(item.total_value),
            ]
        )
    if len(expense_rows) == 1:
        expense_rows.append(["-", "-", "Nenhuma despesa registrada.", "R$ 0,00"])
    story.extend([_table(expense_rows, [4.5 * cm, 2.8 * cm, 6.7 * cm, 2.5 * cm]), Spacer(1, 10)])

    story.append(Paragraph("Materiais e outros itens consumidos", styles["Heading2"]))
    material_rows = [["Item", "Tipo", "Quantidade", "Total"]]
    for item in report["materials"]:
        material_rows.append(
            [
                Paragraph(_pdf_text(item.name), styles["Small"]),
                item.get_type_display(),
                f"{item.quantity} {item.get_unit_display()}",
                _format_brl(item.total_value),
            ]
        )
    if len(material_rows) == 1:
        material_rows.append(["-", "-", "Nenhum material registrado.", "R$ 0,00"])
    story.extend([_table(material_rows, [6 * cm, 3 * cm, 4.5 * cm, 3 * cm]), Spacer(1, 10)])

    totals = report["summary"]
    story.extend(
        [
            Paragraph("Resumo financeiro", styles["Heading2"]),
            _table(
                [
                    ["Total de horas", totals["total_hours"]],
                    ["Mão de obra", totals["labor_total_brl"]],
                    ["Despesas", totals["expense_total_brl"]],
                    ["Materiais e outros itens", totals["material_total_brl"]],
                    ["Total geral", totals["grand_total_brl"]],
                ],
                [7 * cm, 9.5 * cm],
                header=False,
            ),
            Spacer(1, 10),
            Paragraph("Observações finais", styles["Heading2"]),
            Paragraph(_pdf_text(job.notes or "Sem observações finais."), styles["Normal"]),
            Spacer(1, 8),
            Paragraph(
                "Documento operacional gerado pelo HoraCerta. Comprovantes devem ser mantidos conforme o combinado com a empresa.",
                styles["Small"],
            ),
        ]
    )

    document.build(story)
    client_part = _filename_part(report["client_name"])
    date_part = timezone.localdate().strftime("%Y%m%d")
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="horacerta_prestacao_contas_{client_part}_{date_part}.pdf"'
    return _secure_document_response(response)
