import csv
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .exports import build_pdf, build_xlsx, safe_filename
from .forms import ProductionEntryForm, ProductionSheetForm
from .models import ProductionEntry, ProductionSheet, format_minutes


def _default_operator(user):
    name = user.get_full_name().strip()
    if name:
        return name
    from companies.models import Employee

    employee_name = (
        Employee.objects.filter(user=user).exclude(full_name="").values_list("full_name", flat=True).first()
    )
    return employee_name or ""


def _sheet_for(request, sheet_id):
    return get_object_or_404(ProductionSheet, id=sheet_id, owner=request.user)


def _totals_display(sheet):
    totals = sheet.totals()
    return {
        "total": format_minutes(totals["total"]),
        "guincho": format_minutes(totals[ProductionEntry.Destination.GUINCHO]),
        "implemento": format_minutes(totals[ProductionEntry.Destination.IMPLEMENTO]),
        "pending": totals["pending"],
    }


@login_required
def sheet_list(request):
    sheets = list(ProductionSheet.objects.filter(owner=request.user).prefetch_related("entries"))
    rows = []
    for sheet in sheets:
        start, end = sheet.date_range()
        rows.append({"sheet": sheet, "totals": _totals_display(sheet), "start": start, "end": end,
                     "count": len(sheet.entries.all())})
    open_rows = [r for r in rows if r["sheet"].is_open]
    closed_rows = [r for r in rows if not r["sheet"].is_open]
    return render(request, "production/sheet_list.html", {"open_rows": open_rows, "closed_rows": closed_rows})


@login_required
def sheet_create(request):
    if request.method == "POST":
        form = ProductionSheetForm(request.POST)
        if form.is_valid():
            sheet = form.save(commit=False)
            sheet.owner = request.user
            sheet.save()
            messages.success(request, "Relatório criado. Agora anote o primeiro item.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
    else:
        initial = {"operator_name": _default_operator(request.user)}
        last = ProductionSheet.objects.filter(owner=request.user).exclude(supervisor_whatsapp="").first()
        if last:  # quase sempre e o mesmo encarregado: ja deixa preenchido
            initial.update(supervisor_name=last.supervisor_name, supervisor_whatsapp=last.supervisor_whatsapp)
        form = ProductionSheetForm(initial=initial)
    return render(request, "production/sheet_form.html", {
        "form": form, "equipment_suggestions": _equipment_suggestions(request.user),
    })


def _equipment_suggestions(user):
    return (
        ProductionSheet.objects.filter(owner=user).order_by("equipment")
        .values_list("equipment", flat=True).distinct()
    )


@login_required
def sheet_edit(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    if request.method == "POST":
        form = ProductionSheetForm(request.POST, instance=sheet)
        if form.is_valid():
            form.save()
            messages.success(request, "Dados do relatório atualizados.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
    else:
        form = ProductionSheetForm(instance=sheet)
    return render(request, "production/sheet_form.html", {
        "form": form, "sheet": sheet, "equipment_suggestions": _equipment_suggestions(request.user),
    })


def _file_response(content, content_type, filename, inline=False):
    response = HttpResponse(content, content_type=content_type)
    disposition = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@login_required
def sheet_xlsx(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    return _file_response(build_xlsx(sheet), XLSX_TYPE, safe_filename(sheet, "xlsx"))


@login_required
def sheet_pdf(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    return _file_response(build_pdf(sheet), "application/pdf", safe_filename(sheet, "pdf"),
                          inline=request.GET.get("ver") == "1")


def public_sheet_pdf(request, token):
    """Link enviado pelo WhatsApp: abre o PDF sem login, so com o codigo secreto."""
    sheet = get_object_or_404(ProductionSheet, share_token=token)
    return _file_response(build_pdf(sheet), "application/pdf", safe_filename(sheet, "pdf"), inline=True)


def public_sheet_xlsx(request, token):
    sheet = get_object_or_404(ProductionSheet, share_token=token)
    return _file_response(build_xlsx(sheet), XLSX_TYPE, safe_filename(sheet, "xlsx"))


def _share_links(request, sheet):
    return {
        "pdf": request.build_absolute_uri(reverse("production_public_pdf", args=[sheet.share_token])),
        "xlsx": request.build_absolute_uri(reverse("production_public_xlsx", args=[sheet.share_token])),
    }


def _whatsapp_message(sheet, links=None):
    totals = _totals_display(sheet)
    start, end = sheet.date_range()
    lines = [f"*Relatório de produção - {sheet.equipment}*"]
    if sheet.company_name:
        lines.append(f"Empresa: {sheet.company_name}")
    if sheet.operator_name:
        lines.append(f"Operador: {sheet.operator_name}")
    if start:
        period = start.strftime("%d/%m") if start == end else f"{start:%d/%m} a {end:%d/%m}"
        lines.append(f"Período: {period}")
    lines.append("")
    for e in sheet.entries.all():
        parts = [e.work_date.strftime("%d/%m"), e.item_code or "sem código"]
        if e.destination:
            parts.append(e.get_destination_display())
        if e.start_time:
            parts.append(e.start_time.strftime("%H:%M") + (f"-{e.end_time:%H:%M}" if e.end_time else " (sem fim)"))
        if e.duration_label:
            parts.append(e.duration_label)
        if e.note:
            parts.append(e.note)
        lines.append(" · ".join(parts))
    lines.append("")
    lines.append(f"*Total: {totals['total']}* (Guincho {totals['guincho']} | Implemento {totals['implemento']})")
    if totals["pending"]:
        lines.append(f"{totals['pending']} item(ns) sem horário de fim, fora do total.")
    if links:
        lines.append("")
        lines.append(f"PDF: {links['pdf']}")
        lines.append(f"Excel: {links['xlsx']}")
    return "\n".join(lines)


@login_required
def sheet_whatsapp(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    text = quote(_whatsapp_message(sheet, _share_links(request, sheet)), safe="")
    digits = sheet.supervisor_whatsapp
    if digits:
        number = digits if len(digits) > 11 else f"55{digits}"
        return redirect(f"https://wa.me/{number}?text={text}")
    return redirect(f"https://wa.me/?text={text}")


def _code_suggestions(user):
    codes = (
        ProductionEntry.objects.filter(sheet__owner=user).exclude(item_code="")
        .order_by("-created_at").values_list("item_code", flat=True)
    )
    seen = []
    for code in codes:
        if code not in seen:
            seen.append(code)
        if len(seen) >= 30:
            break
    return seen


@login_required
def sheet_detail(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    if request.method == "POST":
        if not sheet.is_open:
            messages.error(request, "Este relatório está fechado. Reabra para anotar mais itens.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
        form = ProductionEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.sheet = sheet
            entry.save()
            if entry.is_running:
                messages.success(request, "Item salvo. Quando terminar, toque nele e anote o fim.")
            else:
                messages.success(request, "Item salvo.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
    else:
        form = ProductionEntryForm(initial={"work_date": timezone.localdate()})
    entries = list(sheet.entries.all())
    return render(request, "production/sheet_detail.html", {
        "sheet": sheet,
        "entries": entries,
        "form": form,
        "totals": _totals_display(sheet),
        "code_suggestions": _code_suggestions(request.user),
        "pdf_filename": safe_filename(sheet, "pdf"),
    })


@login_required
def entry_edit(request, sheet_id, entry_id):
    sheet = _sheet_for(request, sheet_id)
    entry = get_object_or_404(ProductionEntry, id=entry_id, sheet=sheet)
    if request.method == "POST":
        if not sheet.is_open:
            messages.error(request, "Este relatório está fechado. Reabra para editar.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
        form = ProductionEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, "Item atualizado.")
            return redirect("production_sheet_detail", sheet_id=sheet.id)
    else:
        form = ProductionEntryForm(instance=entry)
    return render(request, "production/entry_form.html", {"sheet": sheet, "entry": entry, "form": form})


@login_required
@require_POST
def entry_delete(request, sheet_id, entry_id):
    sheet = _sheet_for(request, sheet_id)
    entry = get_object_or_404(ProductionEntry, id=entry_id, sheet=sheet)
    if not sheet.is_open:
        messages.error(request, "Este relatório está fechado. Reabra para remover itens.")
    else:
        entry.delete()
        messages.success(request, "Item removido.")
    return redirect("production_sheet_detail", sheet_id=sheet.id)


@login_required
@require_POST
def sheet_status(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    action = request.POST.get("action")
    if action == "close" and sheet.is_open:
        sheet.close()
        sheet.save(update_fields=["status", "closed_at", "updated_at"])
        messages.success(request, "Relatório fechado. Você pode exportar ou imprimir para entregar.")
    elif action == "reopen" and not sheet.is_open:
        sheet.reopen()
        sheet.save(update_fields=["status", "closed_at", "updated_at"])
        messages.success(request, "Relatório reaberto.")
    return redirect("production_sheet_detail", sheet_id=sheet.id)


@login_required
def sheet_csv(request, sheet_id):
    sheet = _sheet_for(request, sheet_id)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    safe_name = "".join(c for c in sheet.equipment if c.isalnum() or c in "-_") or "relatorio"
    response["Content-Disposition"] = f'attachment; filename="relatorio-{safe_name}.csv"'
    response.write("﻿")  # abre com acentos certos no Excel
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Empresa", sheet.company_name])
    writer.writerow(["Operador", sheet.operator_name])
    writer.writerow(["Máquina", sheet.equipment])
    writer.writerow([])
    writer.writerow(["Data", "Código", "Destino", "Início", "Fim", "Horas", "Observação"])
    for e in sheet.entries.all():
        writer.writerow([
            e.work_date.strftime("%d/%m/%Y"), e.item_code, e.get_destination_display(),
            e.start_time.strftime("%H:%M") if e.start_time else "", e.end_time.strftime("%H:%M") if e.end_time else "",
            e.duration_label, e.note,
        ])
    totals = _totals_display(sheet)
    writer.writerow([])
    writer.writerow(["Total", "", "", "", "", totals["total"]])
    writer.writerow(["Guincho", "", "", "", "", totals["guincho"]])
    writer.writerow(["Implemento", "", "", "", "", totals["implemento"]])
    return response
