"""PDF e Excel da nota de envio, no mesmo visual dos relatorios (accounts/print_theme.py).

As duas saidas usam as mesmas linhas e o mesmo bloco de visto/autorizacao para nunca divergirem.
"""

from io import BytesIO

from django.utils import timezone
from django.utils.text import slugify

from accounts import print_theme as pt


def _when(value):
    return timezone.localtime(value).strftime("%d/%m/%Y às %H:%M") if value else ""


def stamp(recipient):
    if recipient.authorized_at:
        return f"Autorizado em {_when(recipient.authorized_at)}"
    if recipient.viewed_at:
        return f"Visto em {_when(recipient.viewed_at)} · aguardando autorização"
    return "Aguardando"


def check_code(note):
    return str(note.id)[:8].upper()


def info_pairs(note):
    pairs = [("Remetente", note.sender_name), ("Destino", note.destination_company), ("Saída", _when(note.departed_at))]
    if note.driver_name:
        pairs.append(("Motorista", note.driver_name))
    if note.vehicle_plate:
        pairs.append(("Placa", note.vehicle_plate))
    if note.replaces:
        pairs.append(("Substitui", f"Nota nº {note.replaces.number_label}"))
    return pairs


def item_rows(note):
    return [(i.production_order or "-", i.drawing_number, i.description or "", i.quantity) for i in note.items.all()]


def shipment_filename(note, ext):
    destination = slugify(note.destination_company)[:40] or "destino"
    return f"nota-envio-{note.number_label}-{destination}.{ext}"


def build_shipment_pdf(note):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    title = f"Nota de envio nº {note.number_label}"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.7 * cm, title=title, author="HoraCerta")
    width = A4[0] - doc.leftMargin - doc.rightMargin
    st = pt.styles()

    story = pt.header_block(title, [f"{pt.esc(note.destination_company)} · saída {pt.esc(_when(note.departed_at))}"])
    pairs = info_pairs(note)
    story.append(pt.info_grid(pairs, width, columns=3))
    story.append(Spacer(1, 10))
    rows = item_rows(note)
    story.append(pt.kpi_strip([
        ("Total de peças", str(note.total_quantity), True),
        ("Itens", str(len(rows)), False),
        ("Situação", note.situation[0], False),
    ], width))
    story.append(Spacer(1, 14))

    widths = [4.2 * cm, 4.6 * cm, 0, 2.0 * cm]
    widths[2] = width - sum(widths)
    story.append(pt.data_table(["Ordem de produção", "Desenho", "Descrição", "Qtd."],
                               [[a, b, c, str(d)] for a, b, c, d in rows],
                               widths, numeric_cols=(3,), empty_text="Nenhuma peça."))
    story.append(Spacer(1, 10))
    story.append(pt.totals_block([], ("Total de peças", str(note.total_quantity)), width * 0.34))
    if note.notes:
        story += [Spacer(1, 8), Paragraph(f"<b>Observação:</b> {pt.esc(note.notes)}", st["small"])]
    story.append(Spacer(1, 18))

    # Bloco de conferencia: um quadro por destinatario, com o carimbo e a linha de assinatura.
    boxes = []
    for r in note.recipients.all():
        boxes.append([
            Paragraph(f"<font size=8 color='#{pt.MUTED}'>{r.get_role_display().upper()}</font><br/>"
                      f"<b>{pt.esc(r.name)}</b><br/><font size=9>{pt.esc(stamp(r))}</font>", st["body"]),
        ])
    if boxes:
        table = Table([[b[0] for b in boxes]], colWidths=[width / len(boxes)] * len(boxes))
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, pt.rl_color(pt.RULE)),
            ("INNERGRID", (0, 0), (-1, -1), 0.6, pt.rl_color(pt.RULE)),
            ("BACKGROUND", (0, 0), (-1, -1), pt.rl_color(pt.PAPER)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 26),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -1), 0.8, pt.rl_color(pt.INK)),
        ]))
        sent = f"Nota registrada no HoraCerta em {_when(note.sent_at)}. " if note.sent_at else ""
        story.append(KeepTogether([
            table, Spacer(1, 6),
            Paragraph(f"{sent}Depois de enviada, não pode ser alterada. Código de conferência "
                      f"<b>{check_code(note)}</b>.", st["small"]),
        ]))

    decorate = pt.page_decorator(title)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


def build_shipment_xlsx(note):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = f"Nota {note.number_label}"
    ws.sheet_view.showGridLines = False
    columns = [("Ordem de produção", 22), ("Desenho", 24), ("Descrição", 40), ("Qtd.", 10)]
    for idx, (_title, width) in enumerate(columns, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
        ws.cell(row=1, column=idx).fill = PatternFill("solid", fgColor=pt.ACCENT)
    ws.row_dimensions[1].height = 5
    ws["A2"] = f"Nota de envio nº {note.number_label}"
    ws["A2"].font = Font(name="Georgia", size=18, bold=True, color=pt.INK)
    ws.merge_cells("A2:D2")
    ws.row_dimensions[2].height = 34

    hair = Border(bottom=Side(style="hair", color=pt.RULE))
    row = 3
    for label, value in info_pairs(note):
        ws.cell(row=row, column=1, value=label).font = Font(name="Arial", size=9, color=pt.MUTED)
        cell = ws.cell(row=row, column=2, value=value)
        cell.font = Font(name="Arial", size=11, bold=True, color=pt.INK)
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        for c in range(1, 5):
            ws.cell(row=row, column=c).border = hair
        row += 1

    row += 1
    for idx, (title, _width) in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=idx, value=title)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=pt.INK)
        cell.alignment = Alignment(horizontal="right" if title == "Qtd." else "left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 22
    thin = Border(bottom=Side(style="thin", color=pt.RULE))
    for n, values in enumerate(item_rows(note)):
        row += 1
        for idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=idx, value=value)
            cell.font = Font(name="Arial", size=10, bold=idx == 4, color=pt.INK_SOFT)
            cell.border = thin
            cell.alignment = Alignment(horizontal="right" if idx == 4 else "left", vertical="center", indent=1)
            if n % 2:
                cell.fill = PatternFill("solid", fgColor=pt.PAPER)

    row += 1
    ws.cell(row=row, column=3, value="Total de peças").font = Font(name="Georgia", size=12, bold=True, color=pt.INK)
    total = ws.cell(row=row, column=4, value=note.total_quantity)  # valor, nao formula: abre certo no celular
    total.font = Font(name="Georgia", size=14, bold=True, color=pt.ACCENT)
    total.alignment = Alignment(horizontal="right", indent=1)
    for c in (3, 4):
        ws.cell(row=row, column=c).fill = PatternFill("solid", fgColor=pt.ACCENT_SOFT)

    row += 2
    for r in note.recipients.all():
        ws.cell(row=row, column=1, value=r.get_role_display()).font = Font(name="Arial", size=9, color=pt.MUTED)
        ws.cell(row=row, column=2, value=r.name).font = Font(name="Arial", size=11, bold=True, color=pt.INK)
        ws.cell(row=row, column=3, value=stamp(r)).font = Font(name="Arial", size=10, color=pt.INK_SOFT)
        row += 1
    row += 1
    ws.cell(row=row, column=1, value=f"Código de conferência {check_code(note)}. Nota travada após o envio.").font = Font(
        name="Arial", size=9, italic=True, color=pt.MUTED)

    # Texto do usuario que comeca com = + - @ seria lido como formula ao abrir: grava sempre como texto.
    for line in ws.iter_rows():
        for cell in line:
            if cell.data_type == "f":
                cell.data_type = "s"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
