"""Exportacao do relatorio de producao: planilha Excel (.xlsx) e PDF com tabela formatada.

As duas saidas usam as mesmas linhas (rows) para nunca divergirem entre si.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone

from .models import ProductionEntry, format_minutes

BRAND = "1F3A5F"       # azul escuro do cabecalho
BRAND_SOFT = "E8EEF6"  # faixa zebrada
GUINCHO_FILL = "FFF4DB"
IMPLEMENTO_FILL = "E6F0FF"
PENDING_FILL = "FDECEC"


def sheet_rows(sheet):
    """Linhas da tabela, ja na ordem de exibicao."""
    rows = []
    for e in sheet.entries.all():
        rows.append({
            "date": e.work_date,
            "code": e.item_code or "",
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
    from openpyxl.workbook.properties import CalcProperties

    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    base = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    thin = Side(style="thin", color="C9D3E0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    columns = [("Data", 12), ("Código", 16), ("Destino", 13), ("Início", 9), ("Fim", 9), ("Horas", 9), ("Observação", 42)]
    last_col = get_column_letter(len(columns))

    ws["A1"] = f"Relatório de produção - {sheet.equipment}"
    ws["A1"].font = Font(name="Arial", size=15, bold=True, color=BRAND)
    ws.merge_cells(f"A1:{last_col}1")
    ws.row_dimensions[1].height = 24

    row = 3
    for label, value in info_pairs(sheet):
        ws.cell(row=row, column=1, value=label).font = bold
        cell = ws.cell(row=row, column=2, value=value)
        cell.font = base
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        row += 1

    header_row = row + 1
    for idx, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx, value=title)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BRAND)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[header_row].height = 20

    rows = sheet_rows(sheet)
    first_data = header_row + 1
    for i, item in enumerate(rows):
        r = first_data + i
        values = [
            item["date"], item["code"], item["destination"], item["start"], item["end"],
            item["minutes"] / 1440 if item["minutes"] is not None else "sem fim", item["note"],
        ]
        fill = None
        if item["minutes"] is None:
            fill = PatternFill("solid", fgColor=PENDING_FILL)
        elif i % 2:
            fill = PatternFill("solid", fgColor=BRAND_SOFT)
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.font = base
            cell.border = border
            cell.alignment = Alignment(vertical="center", horizontal="left" if c in (2, 7) else "center",
                                       wrap_text=(c == 7))
            if fill:
                cell.fill = fill
        ws.cell(row=r, column=1).number_format = "DD/MM/YYYY"
        ws.cell(row=r, column=4).number_format = "HH:MM"
        ws.cell(row=r, column=5).number_format = "HH:MM"
        ws.cell(row=r, column=6).number_format = "[H]:MM"
        dest_key = item["destination_key"]
        if dest_key and item["minutes"] is not None:
            ws.cell(row=r, column=3).fill = PatternFill(
                "solid", fgColor=GUINCHO_FILL if dest_key == ProductionEntry.Destination.GUINCHO else IMPLEMENTO_FILL)
    last_data = first_data + max(len(rows), 1) - 1

    # Totais com formula: se alguem corrigir uma hora na planilha, o total acompanha.
    total_row = last_data + 2
    hours = f"F{first_data}:F{last_data}"
    dest = f"C{first_data}:C{last_data}"
    totals = [
        ("Total de horas", f"=SUM({hours})"),
        ("Guincho", f'=SUMIF({dest},"Guincho",{hours})'),
        ("Implemento", f'=SUMIF({dest},"Implemento",{hours})'),
    ]
    for offset, (label, formula) in enumerate(totals):
        r = total_row + offset
        label_cell = ws.cell(row=r, column=5, value=label)
        label_cell.font = bold
        label_cell.alignment = Alignment(horizontal="right")
        value_cell = ws.cell(row=r, column=6, value=formula)
        value_cell.number_format = "[H]:MM"
        value_cell.font = Font(name="Arial", size=11 if offset else 12, bold=True, color=BRAND)
        value_cell.alignment = Alignment(horizontal="center")
        value_cell.border = border
        value_cell.fill = PatternFill("solid", fgColor=BRAND_SOFT)
    pending = sum(1 for item in rows if item["minutes"] is None)
    note_row = total_row + len(totals) + 1
    if pending:
        ws.cell(row=note_row, column=1,
                value=f"{pending} item(ns) sem horário de fim ficaram fora do total.").font = Font(name="Arial", size=9, italic=True)
        note_row += 1
    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    ws.cell(row=note_row, column=1, value=f"Gerado pelo HoraCerta em {generated}.").font = Font(
        name="Arial", size=8, italic=True, color="6B7280")

    ws.freeze_panes = ws.cell(row=first_data, column=1)
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{last_col}{last_data}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    wb.calculation = CalcProperties(fullCalcOnLoad=True)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ----------------------------------------------------------------------- PDF


def build_pdf(sheet):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    brand = colors.HexColor("#" + BRAND)
    soft = colors.HexColor("#" + BRAND_SOFT)
    line = colors.HexColor("#C9D3E0")
    muted = colors.HexColor("#6B7280")
    page = landscape(A4)

    title_style = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=brand)
    label_style = ParagraphStyle("l", fontName="Helvetica", fontSize=8, leading=10, textColor=muted)
    value_style = ParagraphStyle("v", fontName="Helvetica-Bold", fontSize=10.5, leading=13)
    cell_style = ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=11)
    head_style = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.white,
                                alignment=TA_CENTER)
    total_label = ParagraphStyle("tl", fontName="Helvetica", fontSize=8.5, leading=10, textColor=muted, alignment=TA_CENTER)
    total_value = ParagraphStyle("tv", fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=brand, alignment=TA_CENTER)

    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(1.5 * cm, 0.9 * cm, f"{sheet.equipment} - gerado pelo HoraCerta em {generated}")
        canvas.drawRightString(page[0] - 1.5 * cm, 0.9 * cm, f"Página {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.5 * cm,
                            title=f"Relatório de produção - {sheet.equipment}", author="HoraCerta")
    width = page[0] - 3 * cm
    story = [Paragraph(escape(f"Relatório de produção - {sheet.equipment}"), title_style), Spacer(1, 8)]

    pairs = info_pairs(sheet)
    info_cells = [[Paragraph(escape(label), label_style), Paragraph(escape(value), value_style)] for label, value in pairs]
    info = Table([info_cells], colWidths=[width / len(pairs)] * len(pairs))
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), soft),
        ("BOX", (0, 0), (-1, -1), 0.6, line),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [info, Spacer(1, 12)]

    headers = ["Data", "Código", "Destino", "Início", "Fim", "Horas", "Observação"]
    data = [[Paragraph(h, head_style) for h in headers]]
    rows = sheet_rows(sheet)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("GRID", (0, 0), (-1, -1), 0.5, line),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"), ("ALIGN", (2, 1), (5, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("FONTNAME", (5, 1), (5, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, item in enumerate(rows, start=1):
        data.append([
            item["date"].strftime("%d/%m/%Y"),
            Paragraph(escape(item["code"] or "-"), cell_style),
            item["destination"] or "-",
            item["start"].strftime("%H:%M") if item["start"] else "-",
            item["end"].strftime("%H:%M") if item["end"] else "-",
            format_minutes(item["minutes"]) if item["minutes"] is not None else "sem fim",
            Paragraph(escape(item["note"]), cell_style),
        ])
        if item["minutes"] is None:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#" + PENDING_FILL)))
        elif i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), soft))
        if item["destination_key"] and item["minutes"] is not None:
            fill = GUINCHO_FILL if item["destination_key"] == ProductionEntry.Destination.GUINCHO else IMPLEMENTO_FILL
            style.append(("BACKGROUND", (2, i), (2, i), colors.HexColor("#" + fill)))
    if not rows:
        data.append(["", "", "", "", "", "", Paragraph("Nenhum item anotado.", cell_style)])
    col_widths = [2.4, 3.4, 2.6, 1.8, 1.8, 1.8]
    col_widths = [w * cm for w in col_widths] + [width - sum(col_widths) * cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    story += [table, Spacer(1, 14)]

    totals = sheet.totals()
    boxes = [
        ("Total de horas", format_minutes(totals["total"])),
        ("Guincho", format_minutes(totals[ProductionEntry.Destination.GUINCHO])),
        ("Implemento", format_minutes(totals[ProductionEntry.Destination.IMPLEMENTO])),
    ]
    total_table = Table([[Paragraph(label, total_label) for label, _ in boxes],
                         [Paragraph(value, total_value) for _, value in boxes]],
                        colWidths=[5 * cm] * 3, hAlign="RIGHT")
    total_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, brand),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, line),
        ("BACKGROUND", (0, 0), (-1, -1), soft),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    closing = [total_table]
    if totals["pending"]:
        closing += [Spacer(1, 4), Paragraph(
            f"{totals['pending']} item(ns) sem horário de fim ficaram fora do total.",
            ParagraphStyle("p", fontName="Helvetica-Oblique", fontSize=8.5, textColor=muted, alignment=2))]
    story.append(KeepTogether(closing))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
