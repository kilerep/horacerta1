import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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
        form = ProductionSheetForm(initial={"operator_name": _default_operator(request.user)})
    equipment_suggestions = (
        ProductionSheet.objects.filter(owner=request.user).order_by("equipment")
        .values_list("equipment", flat=True).distinct()
    )
    return render(request, "production/sheet_form.html", {"form": form, "equipment_suggestions": equipment_suggestions})


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
