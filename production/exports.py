"""Exportacao do relatorio de producao: planilha Excel (.xlsx) e PDF com tabela formatada.

As duas saidas usam as mesmas linhas (rows) para nunca divergirem entre si.
"""

from io import BytesIO

from django.utils import timezone

from .models import ProductionEntry, format_minutes, pending_note

from accounts import print_theme as pt  # noqa: E402

# Mesmo visual dos PDFs (accounts/print_theme.py): tinta grafite, papel quente, sem azul.
INK = pt.INK
RULE = pt.RULE
PAPER = pt.PAPER
GUINCHO_FILL = pt.SAND
IMPLEMENTO_FILL = pt.SAGE
PENDING_FILL = pt.WARN_SOFT


def sheet_rows(sheet):
    """Linhas da tabela, ja na ordem de exibicao."""
    rows = []
    for e in sheet.entries.all():
        rows.append({
            "date": e.work_date,
            "code": e.item_code or "",
            "quantity": e.quantity,
            "destination": e.get_destination_display() if e.destination else "",
            "destination_key": e.destination,
            "start": e.start_time,
            "end": e.end_time,
            "minutes": e.duration_minutes,
            "note": e.note or "",
        })
    return rows


def period_label(sheet):
    start, end = sheet.date_range()
    if not start:
        return "Sem itens"
    if start == end:
        return start.strftime("%d/%m/%Y")
    return f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"


def info_pairs(sheet):
    pairs = [("Máquina", sheet.equipment)]
    if sheet.company_name:
        pairs.append(("Empresa", sheet.company_name))
    if sheet.operator_name:
        pairs.append(("Operador", sheet.operator_name))
    if sheet.supervisor_name:
        pairs.append(("Encarregado", sheet.supervisor_name))
    pairs.append(("Período", period_label(sheet)))
    pairs.append(("Situação", sheet.get_status_display()))
    return pairs


def safe_filename(sheet, ext):
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in sheet.equipment).strip("-") or "relatorio"
    return f"relatorio-{name}.{ext}"


# --------------------------------------------------------------------- Excel


def build_xlsx(sheet):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    base = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    thin = Side(style="thin", color=RULE)
    border = Border(bottom=thin)
    head_border = Border(bottom=Side(style="medium", color=INK))
    columns = [("Data", 13), ("Código", 17), ("Qtd.", 8), ("Destino", 14), ("Início", 10), ("Fim", 14), ("Horas", 11),
               ("Observação", 40)]
    last_col = get_column_letter(len(columns))
    ws.sheet_view.showGridLines = False  # visual de documento: so os filetes que desenhamos

    # faixa terracota fina no topo, como nos PDFs
    for c in range(1, len(columns) + 1):
        ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor=pt.ACCENT)
    ws.row_dimensions[1].height = 5
    ws["A2"] = f"Relatório de produção · {sheet.equipment}"
    ws["A2"].font = Font(name="Georgia", size=18, bold=True, color=INK)
    ws["A2"].alignment = Alignment(vertical="center")
    ws.merge_cells(f"A2:{last_col}2")
    ws.row_dimensions[2].height = 34

    row = 3
    info_rule = Border(bottom=Side(style="hair", color=RULE))
    for label, value in info_pairs(sheet):
        label_cell = ws.cell(row=row, column=1, value=label)
        label_cell.font = Font(name="Arial", size=9, color=pt.MUTED)
        label_cell.alignment = Alignment(vertical="center")
        cell = ws.cell(row=row, column=2, value=value)
        cell.font = Font(name="Arial", size=11, bold=True, color=INK)
        cell.alignment = Alignment(vertical="center")
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        for c in range(1, 5):
            ws.cell(row=row, column=c).border = info_rule
        ws.row_dimensions[row].height = 19
        row += 1

    header_row = row + 1
    for idx, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx, value=title)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=INK)
        cell.alignment = Alignment(horizontal="right" if title in ("Horas", "Qtd.") else "left", vertical="center",
                                   indent=1)
        cell.border = head_border
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[header_row].height = 26

    rows = sheet_rows(sheet)
    first_data = header_row + 1
    for i, item in enumerate(rows):
        r = first_data + i
        values = [
            item["date"], item["code"], item["quantity"], item["destination"], item["start"],
            item["end"] if item["end"] else ("em andamento" if item["minutes"] is None else None),
            item["minutes"] / 1440 if item["minutes"] is not None else None, item["note"],
        ]
        fill = None
        if item["minutes"] is None:
            fill = PatternFill("solid", fgColor=PENDING_FILL)
        elif i % 2:
            fill = PatternFill("solid", fgColor=PAPER)
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.font = base
            cell.border = border
            cell.alignment = Alignment(vertical="center", horizontal="right" if c in (3, 7) else "left",
                                       wrap_text=(c == 8), indent=1)
            if fill:
                cell.fill = fill
        ws.cell(row=r, column=1).number_format = "DD/MM/YYYY"
        ws.cell(row=r, column=3).number_format = "0"
        ws.cell(row=r, column=5).number_format = "HH:MM"
        ws.cell(row=r, column=6).number_format = "HH:MM"
        ws.cell(row=r, column=7).number_format = "[H]:MM"
        ws.cell(row=r, column=7).font = Font(name="Arial", size=10, bold=True, color=INK)
        ws.row_dimensions[r].height = 21
        if item["minutes"] is None:
            ws.cell(row=r, column=6).font = Font(name="Arial", size=10, italic=True, color=pt.ACCENT)
        dest_key = item["destination_key"]
        if dest_key and item["minutes"] is not None:
            is_guincho = dest_key == ProductionEntry.Destination.GUINCHO
            dest_cell = ws.cell(row=r, column=4)
            dest_cell.fill = PatternFill("solid", fgColor=GUINCHO_FILL if is_guincho else IMPLEMENTO_FILL)
            dest_cell.font = Font(name="Arial", size=10, bold=True, color="7A5410" if is_guincho else "3E5B37")
    last_data = first_data + max(len(rows), 1) - 1

    # Totais gravados como VALOR (nao formula): visualizadores de celular (WhatsApp,
    # iPhone, Drive) nao recalculam formulas e mostravam a celula vazia.
    sums = sheet.totals()
    pieces = sum(item["quantity"] or 0 for item in rows)
    total_row = last_data + 2
    totals = [
        ("Total de horas", sums["total"] / 1440, "[H]:MM"),
        ("Guincho", sums[ProductionEntry.Destination.GUINCHO] / 1440, "[H]:MM"),
        ("Implemento", sums[ProductionEntry.Destination.IMPLEMENTO] / 1440, "[H]:MM"),
        ("Peças produzidas", pieces, "0"),
    ]
    for offset, (label, amount, fmt) in enumerate(totals):
        r = total_row + offset
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
        label_cell = ws.cell(row=r, column=4, value=label)
        label_cell.font = bold
        label_cell.alignment = Alignment(horizontal="right")
        value_cell = ws.cell(row=r, column=7, value=amount)
        value_cell.number_format = fmt
        is_total = offset == 0
        label_cell.font = Font(name="Georgia" if is_total else "Arial", size=12 if is_total else 10, bold=True,
                               color=INK)
        value_cell.font = Font(name="Georgia" if is_total else "Arial", size=14 if is_total else 11, bold=True,
                               color=pt.ACCENT if is_total else INK)
        value_cell.alignment = Alignment(horizontal="right", vertical="center", indent=1)
        for c in range(4, 8):
            cell = ws.cell(row=r, column=c)
            cell.fill = PatternFill("solid", fgColor=pt.ACCENT_SOFT if is_total else PAPER)
            cell.border = Border(top=Side(style="medium", color=INK)) if is_total else border
        ws.row_dimensions[r].height = 28 if is_total else 20
    pending = sum(1 for item in rows if item["minutes"] is None)
    note_row = total_row + len(totals) + 1
    if pending:
        ws.cell(row=note_row, column=1,
                value=pending_note(pending)).font = Font(name="Arial", size=9, italic=True)
        note_row += 1
    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    ws.cell(row=note_row, column=1, value=f"Gerado pelo HoraCerta em {generated}.").font = Font(
        name="Arial", size=8, italic=True, color=pt.MUTED)

    ws.freeze_panes = ws.cell(row=first_data, column=1)
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{last_col}{last_data}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ----------------------------------------------------------------------- PDF


def build_pdf(sheet):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    page = landscape(A4)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.7 * cm, title=f"Relatório de produção - {sheet.equipment}", author="HoraCerta")
    width = page[0] - doc.leftMargin - doc.rightMargin
    st = pt.styles()

    who = [p for p in (sheet.operator_name and f"Operador {pt.esc(sheet.operator_name)}",
                        sheet.company_name and pt.esc(sheet.company_name)) if p]
    story = pt.header_block(f"Relatório de produção · {sheet.equipment}", [
        " · ".join(who + [f"Período {pt.esc(period_label(sheet))}"]),
    ])
    story.append(pt.info_grid(info_pairs(sheet), width, columns=min(6, len(info_pairs(sheet)))))
    story.append(Spacer(1, 10))

    data = sheet_rows(sheet)
    totals = sheet.totals()
    pieces = sum(item["quantity"] or 0 for item in data)
    story.append(pt.kpi_strip([
        ("Total de horas", format_minutes(totals["total"]), True),
        ("Guincho", format_minutes(totals[ProductionEntry.Destination.GUINCHO]), False),
        ("Implemento", format_minutes(totals[ProductionEntry.Destination.IMPLEMENTO]), False),
        ("Peças produzidas", str(pieces), False),
        ("Itens anotados", str(len(data)), False),
    ], width))
    story.append(Spacer(1, 14))

    rows, fills, cell_fills = [], {}, {}
    for i, item in enumerate(data):
        if item["minutes"] is None:
            fills[i] = PENDING_FILL
        elif item["destination_key"]:
            cell_fills[(i, 3)] = GUINCHO_FILL if item["destination_key"] == ProductionEntry.Destination.GUINCHO else IMPLEMENTO_FILL
        rows.append([
            item["date"].strftime("%d/%m/%Y"),
            item["code"] or "-",
            str(item["quantity"]) if item["quantity"] else "",
            item["destination"] or "-",
            item["start"].strftime("%H:%M") if item["start"] else "",
            item["end"].strftime("%H:%M") if item["end"] else ("em andamento" if item["minutes"] is None else ""),
            format_minutes(item["minutes"]) if item["minutes"] is not None else "",
            item["note"],
        ])
    widths = [2.5, 3.2, 1.6, 2.6, 1.7, 2.5, 2.0]
    widths = [w * cm for w in widths] + [width - sum(widths) * cm]
    story.append(pt.data_table(["Data", "Código", "Qtd.", "Destino", "Início", "Fim", "Horas", "Observação"], rows,
                               widths, numeric_cols=(2, 6), empty_text="Nenhum item anotado.", row_fills=fills,
                               cell_fills=cell_fills))
    story.append(Spacer(1, 14))

    closing = [pt.totals_block([], ("Total de horas", format_minutes(totals["total"])), width * 0.34)]
    if totals["pending"]:
        closing += [Spacer(1, 4), Paragraph(
            pending_note(totals["pending"]), st["small"])]
    story.append(KeepTogether(closing))

    decorate = pt.page_decorator(f"Relatório de produção · {sheet.equipment}")
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
