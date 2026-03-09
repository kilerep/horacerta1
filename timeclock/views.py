import csv
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from accounts.models import User
from companies.models import Company
from .models import ActivityReportRequest, Contract, Punch
from .services import build_daily_summary, filter_punches_by_period, format_hhmm


def _only_employee(user):
    return getattr(user, "role", None) == User.Role.FUNCIONARIO


def _get_system_owner_user():
    owner_email = "sistema.empresa@horacerta.local"
    owner_user, created = User.objects.get_or_create(
        email=owner_email,
        defaults={
            "username": owner_email,
            "role": User.Role.EMPRESA,
        },
    )
    if created:
        owner_user.set_unusable_password()
        owner_user.save(update_fields=["password"])
    return owner_user


@login_required
def employee_dashboard(request):
    if not _only_employee(request.user):
        return redirect("dashboard")

    create_company_errors = []
    create_company_initial = {
        "company_name": "",
        "hourly_rate": "30",
    }

    contracts = Contract.objects.filter(employee_user=request.user, is_active=True).select_related("company")
    pending_report_requests = ActivityReportRequest.objects.filter(
        employee_user=request.user,
        is_answered=False,
    ).select_related("company", "requested_by")[:20]

    if request.method == "POST" and request.POST.get("action") == "respond_activity_request":
        request_id = (request.POST.get("request_id") or "").strip()
        response_text = (request.POST.get("response_text") or "").strip()
        contract_id = (request.POST.get("contract") or "").strip()

        report_request = get_object_or_404(
            ActivityReportRequest,
            id=request_id,
            employee_user=request.user,
            is_answered=False,
        )
        if response_text:
            report_request.response_text = response_text
            report_request.is_answered = True
            report_request.responded_at = timezone.now()
            report_request.save(update_fields=["response_text", "is_answered", "responded_at"])

        redirect_url = request.path
        if contract_id:
            redirect_url = f"{redirect_url}?contract={contract_id}"
        return redirect(redirect_url)

    if request.method == "POST" and request.POST.get("action") == "create_test_contract":
        company_name = (request.POST.get("company_name") or "").strip()
        hourly_rate_raw = (request.POST.get("hourly_rate") or "30").strip()
        create_company_initial["company_name"] = company_name
        create_company_initial["hourly_rate"] = hourly_rate_raw

        if not company_name:
            create_company_errors.append("Informe o nome da empresa.")

        try:
            hourly_rate = Decimal(hourly_rate_raw)
            if hourly_rate <= 0:
                create_company_errors.append("O valor/hora precisa ser maior que zero.")
        except (InvalidOperation, ValueError):
            create_company_errors.append("Valor/hora invalido.")
            hourly_rate = Decimal("30")

        if not create_company_errors:
            owner_user = _get_system_owner_user()
            company = Company.objects.create(
                name=company_name,
                email=None,
                owner=owner_user,
            )
            contract = Contract.objects.create(
                employee_user=request.user,
                company=company,
                hourly_rate=hourly_rate,
                is_active=True,
            )

            employee_profile = getattr(request.user, "employee_profile", None)
            if employee_profile and not employee_profile.companies.filter(id=company.id).exists():
                employee_profile.companies.add(company)

            return redirect(f"{request.path}?contract={contract.id}")

    contracts = Contract.objects.filter(employee_user=request.user, is_active=True).select_related("company")

    if not contracts.exists():
        return render(
            request,
            "accounts/dashboard_funcionario.html",
            {
                "no_contracts": True,
                "contracts": [],
                "create_company_errors": create_company_errors,
                "create_company_initial": create_company_initial,
                "pending_report_requests": pending_report_requests,
            },
        )

    selected_contract_id = request.GET.get("contract") or str(contracts.first().id)
    selected_contract = get_object_or_404(Contract, id=selected_contract_id, employee_user=request.user)

    if request.method == "POST" and request.POST.get("action") == "punch":
        note = (request.POST.get("note") or "").strip()
        Punch.objects.create(
            contract=selected_contract,
            timestamp=timezone.now(),
            note=note,
        )
        return redirect(f"{request.path}?contract={selected_contract.id}")

    date_from_raw = request.GET.get("date_from") or request.GET.get("start")
    date_to_raw = request.GET.get("date_to") or request.GET.get("end")

    qs = Punch.objects.filter(contract=selected_contract)

    today = timezone.localdate()
    start_today = timezone.make_aware(datetime.combine(today, time.min))
    end_today = timezone.make_aware(datetime.combine(today, time.max))
    punches_today = qs.filter(timestamp__range=(start_today, end_today)).order_by("timestamp")

    qs_filtered, date_from, date_to = filter_punches_by_period(qs, date_from_raw, date_to_raw)
    if not date_from and not date_to:
        first_day = today.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(first_day, time.min))
        end_dt = timezone.make_aware(datetime.combine(today, time.max))
        qs_filtered = qs.filter(timestamp__range=(start_dt, end_dt))

    total_punches_today = punches_today.count()
    today_summary, _today_columns = build_daily_summary(punches_today, min_punch_columns=4)
    status_today = today_summary[0]["status"] if today_summary else "INCOMPLETO"
    now_local = timezone.localtime()
    current_hour = now_local.hour
    if 5 <= current_hour <= 11:
        greeting = "Bom dia"
    elif 12 <= current_hour <= 17:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"
    day_status_label = "Dia fechado" if total_punches_today % 2 == 0 else "Dia em andamento"

    history_filtered = list(qs_filtered.order_by("timestamp"))
    history_days, history_punch_columns = build_daily_summary(history_filtered, min_punch_columns=4)

    context = {
        "contracts": contracts,
        "selected_contract": selected_contract,
        "punches_today": punches_today,
        "total_punches_today": total_punches_today,
        "status_today": status_today,
        "greeting": greeting,
        "today_date": now_local.date(),
        "day_status_label": day_status_label,
        "history": qs_filtered.order_by("-timestamp")[:200],
        "history_days": history_days,
        "history_punch_columns": range(1, history_punch_columns + 1),
        "date_from": date_from_raw or "",
        "date_to": date_to_raw or "",
        "no_contracts": False,
        "create_company_errors": create_company_errors,
        "create_company_initial": create_company_initial,
        "pending_report_requests": pending_report_requests,
    }
    return render(request, "accounts/dashboard_funcionario.html", context)


@login_required
@require_POST
def create_manual_punches(request):
    if not _only_employee(request.user):
        return JsonResponse({"ok": False, "errors": ["Perfil sem permissao para esta operacao."]}, status=403)

    contract_id = (request.POST.get("contract") or "").strip()
    manual_date_raw = (request.POST.get("manual_date") or "").strip()
    note = (request.POST.get("note") or "").strip()
    raw_times = request.POST.getlist("times")

    errors = []
    if not contract_id:
        errors.append("Selecione um contrato.")
    if not manual_date_raw:
        errors.append("Informe a data do lancamento.")
    if not note:
        errors.append("A justificativa e obrigatoria.")

    launch_date = None
    if manual_date_raw:
        try:
            launch_date = datetime.strptime(manual_date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Data invalida.")

    parsed_times = []
    invalid_times = []
    for raw_value in raw_times:
        value = (raw_value or "").strip()
        if not value:
            continue
        try:
            parsed_times.append(datetime.strptime(value, "%H:%M").time())
        except ValueError:
            invalid_times.append(value)

    if invalid_times:
        errors.append("Horario invalido: %s." % ", ".join(invalid_times))
    if not parsed_times:
        errors.append("Informe pelo menos 1 horario.")

    seen_hm = set()
    duplicated_payload_hm = []
    for value in parsed_times:
        hm = (value.hour, value.minute)
        if hm in seen_hm:
            duplicated_payload_hm.append(f"{value.hour:02d}:{value.minute:02d}")
        else:
            seen_hm.add(hm)
    if duplicated_payload_hm:
        unique_dup = sorted(set(duplicated_payload_hm))
        errors.append("Horarios duplicados no lancamento: %s." % ", ".join(unique_dup))

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    contract = Contract.objects.filter(
        id=contract_id,
        employee_user=request.user,
        is_active=True,
    ).first()
    if not contract:
        return JsonResponse({"ok": False, "errors": ["Contrato invalido ou inativo."]}, status=400)

    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(launch_date, time.min), tz)
    day_end = timezone.make_aware(datetime.combine(launch_date, time.max), tz)
    existing_hm = {
        (local_ts.hour, local_ts.minute)
        for ts in Punch.objects.filter(contract=contract, timestamp__range=(day_start, day_end)).values_list(
            "timestamp", flat=True
        )
        for local_ts in [timezone.localtime(ts, tz)]
    }

    requested_hm = {(item.hour, item.minute) for item in parsed_times}
    duplicated_existing = sorted(f"{hour:02d}:{minute:02d}" for hour, minute in requested_hm if (hour, minute) in existing_hm)
    if duplicated_existing:
        return JsonResponse(
            {
                "ok": False,
                "errors": [
                    "Ja existe batida para este contrato/data nos horarios: %s." % ", ".join(duplicated_existing)
                ],
            },
            status=400,
        )

    ordered_hm = sorted(requested_hm)
    with transaction.atomic():
        for hour, minute in ordered_hm:
            manual_timestamp = timezone.make_aware(
                datetime.combine(launch_date, time(hour=hour, minute=minute)),
                tz,
            )
            Punch.objects.create(
                contract=contract,
                timestamp=manual_timestamp,
                note=note,
                is_manual=True,
            )

    return JsonResponse(
        {
            "ok": True,
            "created_count": len(ordered_hm),
            "contract_id": str(contract.id),
        }
    )


@login_required
def edit_punch_note(request, punch_id):
    punch = get_object_or_404(Punch, id=punch_id, contract__employee_user=request.user)
    contract_id = request.GET.get("contract") or str(punch.contract.id)

    if request.method == "POST":
        punch.note = (request.POST.get("note") or "").strip()
        punch.save(update_fields=["note"])
        return redirect(f"/me/?contract={contract_id}")

    return render(request, "accounts/punch_note_edit.html", {"punch": punch, "contract_id": contract_id})


@login_required
def export_csv(request):
    if not _only_employee(request.user):
        return redirect("dashboard")

    contract_id = request.GET.get("contract")
    contract = get_object_or_404(Contract, id=contract_id, employee_user=request.user)

    base_punches = Punch.objects.filter(contract=contract).order_by("timestamp")
    punches, _start, _end = filter_punches_by_period(
        base_punches,
        request.GET.get("date_from") or request.GET.get("start"),
        request.GET.get("date_to") or request.GET.get("end"),
    )
    daily_rows, max_punches = build_daily_summary(punches, min_punch_columns=4)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="horacerta_{contract.company.name}.csv"'

    writer = csv.writer(response)
    header = ["Empresa", "Data"]
    for idx in range(1, max_punches + 1):
        header.append(f"Batida {idx}")
    header.extend(["Observacoes", "Total Horas (HH:MM)", "Status"])
    writer.writerow(header)

    for row in sorted(daily_rows, key=lambda x: x["date"], reverse=True):
        writer.writerow(
            [
                contract.company.name,
                row["date"].strftime("%d/%m/%Y"),
                *row["punch_columns"],
                row["notes_summary"],
                row["total_hours_hhmm"],
                row["status"],
            ]
        )

    return response


@login_required
def export_default(request):
    return export_pdf(request)


@login_required
def export_xlsx(request):
    if not _only_employee(request.user):
        return redirect("dashboard")

    contract_id = request.GET.get("contract")
    contract = get_object_or_404(Contract, id=contract_id, employee_user=request.user)

    base_punches = Punch.objects.filter(contract=contract).order_by("timestamp")
    punches, start_date, end_date = filter_punches_by_period(
        base_punches,
        request.GET.get("date_from") or request.GET.get("start"),
        request.GET.get("date_to") or request.GET.get("end"),
    )
    punches = list(punches)

    wb = Workbook()
    ws = wb.active
    ws.title = "Batidas"

    headers = ["Funcionario", "Empresa", "Data", "Hora", "Observacao"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    employee_name = (
        getattr(getattr(contract.employee_user, "employee_profile", None), "full_name", "")
        or contract.employee_user.email
        or contract.employee_user.username
    )

    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        ws.append([employee_name, contract.company.name, local_ts.date(), local_ts.time(), punch.note or ""])

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        row[2].number_format = "DD/MM/YYYY"
        row[3].number_format = "HH:MM"

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 50

    daily_rows, _max_cols = build_daily_summary(punches, min_punch_columns=4)
    total_seconds = sum(row["total_seconds"] for row in daily_rows)
    total_hours_hhmm = format_hhmm(total_seconds)

    ws.append([])
    ws.append(["Resumo", "", "", "", ""])
    ws[f"A{ws.max_row}"].font = Font(bold=True)
    period_label = (
        f"{start_date.strftime('%d/%m/%Y')} ate {end_date.strftime('%d/%m/%Y')}"
        if start_date and end_date
        else "Periodo completo"
    )
    ws.append(["Periodo", period_label, "", "", ""])
    ws.append(["Total de batidas", len(punches), "", "", ""])
    ws.append(["Total de horas", total_hours_hhmm, "", "", ""])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="horacerta_{contract.company.name}_batidas.xlsx"'
    return response


@login_required
def export_pdf(request):
    if not _only_employee(request.user):
        return redirect("dashboard")

    contract_id = request.GET.get("contract")
    contract = get_object_or_404(Contract, id=contract_id, employee_user=request.user)

    base_punches = Punch.objects.filter(contract=contract).order_by("timestamp")
    punches, start_date, end_date = filter_punches_by_period(
        base_punches,
        request.GET.get("date_from") or request.GET.get("start"),
        request.GET.get("date_to") or request.GET.get("end"),
    )
    punches = list(punches)

    employee_name = (
        getattr(getattr(contract.employee_user, "employee_profile", None), "full_name", "")
        or contract.employee_user.email
        or contract.employee_user.username
    )
    period_label = (
        f"{start_date.strftime('%d/%m/%Y')} ate {end_date.strftime('%d/%m/%Y')}"
        if start_date and end_date
        else "Periodo completo"
    )

    daily_rows, max_punches = build_daily_summary(punches, min_punch_columns=4)
    total_seconds = sum(row["total_seconds"] for row in daily_rows)
    total_hours_hhmm = format_hhmm(total_seconds)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("HoraCerta - Resumo de Batidas", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Funcionario:</b> {employee_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Empresa:</b> {contract.company.name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Periodo:</b> {period_label}", styles["Normal"]))
    story.append(Paragraph(f"<b>Total de horas:</b> {total_hours_hhmm}", styles["Normal"]))
    story.append(Paragraph(f"<b>Total de batidas:</b> {len(punches)}", styles["Normal"]))
    story.append(Spacer(1, 10))

    table_headers = ["Data"] + [f"Batida {idx}" for idx in range(1, max_punches + 1)] + ["Total do dia", "Status"]
    table_data = [table_headers]
    for row in daily_rows:
        status_label = "Incompleto" if row["is_incomplete"] else "OK"
        table_data.append(
            [
                row["date"].strftime("%d/%m/%Y"),
                *row["punch_columns"],
                row["total_hours_hhmm"],
                status_label,
            ]
        )

    if len(table_data) == 1:
        table_data.append(["-"] + ["-"] * max_punches + ["00:00", "OK"])

    date_width = 24 * mm
    total_width = 26 * mm
    status_width = 24 * mm
    usable_width = (landscape(A4)[0] - doc.leftMargin - doc.rightMargin) - (
        date_width + total_width + status_width
    )
    each_punch_width = max(16 * mm, usable_width / max(1, max_punches))
    col_widths = [date_width] + [each_punch_width] * max_punches + [total_width, status_width]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20396b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#8ea6d1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 1), (max_punches + 2, -1), "CENTER"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="horacerta_{contract.company.name}_resumo.pdf"'
    return response
