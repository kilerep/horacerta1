"""Visual unico dos documentos impressos do HoraCerta (PDF e Excel).

Direcao: documento de papel, nao tela de app. Papel claro e quente, tinta grafite,
titulos com serifa, tabelas so com filetes finos (sem faixas coloridas) e um unico
acento terracota para marcar o que importa (total, topo da pagina). Nada de azul.

Usado pelos PDFs de relatorio de horas, relatorio de servico, resumo de horarios e
relatorio de producao, e pelo Excel da producao, para todos sairem iguais.
"""

from xml.sax.saxutils import escape

from django.utils import timezone

# Cores em hex sem "#", para servir ao reportlab (HexColor) e ao openpyxl.
INK = "1F1E1D"          # tinta principal
INK_SOFT = "3D3A35"     # texto de tabela
MUTED = "75716A"        # rotulos e notas
RULE = "E5E0D5"         # filete entre linhas
PAPER = "FAF8F3"        # zebra / fundo de destaque
ACCENT = "B5553A"       # terracota: total e barra do topo
ACCENT_SOFT = "F6E7E0"  # fundo do total
SAND = "F2E6D0"         # destino "guincho"
SAGE = "E2EADF"         # destino "implemento"
WARN_SOFT = "F8E1D8"    # item sem fim / pendente


def rl_color(hex_code):
    from reportlab.lib import colors

    return colors.HexColor("#" + hex_code)


def esc(value, default="-"):
    text = value if value not in (None, "") else default
    return escape(str(text))


def styles():
    """Estilos de paragrafo prontos (titulo serifado, corpo, celulas e rotulos)."""
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    ink, soft, muted = rl_color(INK), rl_color(INK_SOFT), rl_color(MUTED)
    return {
        "title": ParagraphStyle("hc_title", fontName="Times-Bold", fontSize=21, leading=25, textColor=ink, spaceAfter=2),
        "subtitle": ParagraphStyle("hc_sub", fontName="Helvetica", fontSize=9.5, leading=13, textColor=muted),
        "h2": ParagraphStyle("hc_h2", fontName="Times-Bold", fontSize=13, leading=16, textColor=ink,
                             spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("hc_body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=soft),
        "small": ParagraphStyle("hc_small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=muted),
        "cell": ParagraphStyle("hc_cell", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=soft,
                               alignment=TA_LEFT),
        "cell_right": ParagraphStyle("hc_cell_r", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=soft,
                                     alignment=TA_RIGHT),
        "head": ParagraphStyle("hc_head", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=muted),
        "head_right": ParagraphStyle("hc_head_r", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=muted,
                                     alignment=TA_RIGHT),
        "label": ParagraphStyle("hc_label", fontName="Helvetica", fontSize=7.6, leading=9.5, textColor=muted),
        "value": ParagraphStyle("hc_value", fontName="Helvetica-Bold", fontSize=10, leading=12.5, textColor=ink),
        "total_label": ParagraphStyle("hc_tl", fontName="Helvetica", fontSize=9, leading=12, textColor=soft,
                                      alignment=TA_RIGHT),
        "total_value": ParagraphStyle("hc_tv", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=ink,
                                      alignment=TA_RIGHT),
        "grand_label": ParagraphStyle("hc_gl", fontName="Times-Bold", fontSize=12.5, leading=15, textColor=ink,
                                      alignment=TA_RIGHT),
        "grand_value": ParagraphStyle("hc_gv", fontName="Times-Bold", fontSize=15, leading=18,
                                      textColor=rl_color(ACCENT), alignment=TA_RIGHT),
    }


def header_block(title, subtitle_lines):
    """Titulo serifado + linhas de contexto (quem, para quem, quando)."""
    from reportlab.platypus import Paragraph, Spacer

    st = styles()
    flow = [Paragraph(esc(title), st["title"])]
    for line in subtitle_lines:
        flow.append(Paragraph(line, st["subtitle"]))
    flow.append(Spacer(1, 12))
    return flow


def info_grid(pairs, width, columns=3):
    """Dados do documento em grade de rotulo/valor, sem caixa: filete fino embaixo de cada linha."""
    from reportlab.platypus import Paragraph, Table, TableStyle

    st = styles()
    cells = [[Paragraph(esc(label), st["label"]), Paragraph(esc(value), st["value"])] for label, value in pairs]
    rows = []
    for start in range(0, len(cells), columns):
        chunk = cells[start:start + columns]
        while len(chunk) < columns:
            chunk.append(["", ""])
        rows.append([[c[0], c[1]] for c in chunk])
    table = Table(rows, colWidths=[width / columns] * columns, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, rl_color(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def data_table(header, rows, col_widths, *, numeric_cols=(), empty_text="Nada registrado.", row_fills=None):
    """Tabela de dados: cabecalho em versalete cinza com filete de tinta, linhas separadas por filete
    fino e zebra de papel. Colunas numericas alinhadas a direita. row_fills: {indice_linha: hex}."""
    from reportlab.platypus import Paragraph, Table, TableStyle

    st = styles()
    head = [Paragraph(esc(h).upper(), st["head_right"] if i in numeric_cols else st["head"]) for i, h in enumerate(header)]
    body = []
    for row in rows:
        out = []
        for i, value in enumerate(row):
            if hasattr(value, "wrap"):  # ja e um Flowable (Paragraph)
                out.append(value)
            else:
                out.append(Paragraph(esc(value, default=""), st["cell_right"] if i in numeric_cols else st["cell"]))
        body.append(out)
    if not body:
        body.append([Paragraph(esc(empty_text), st["small"])] + [""] * (len(header) - 1))
    table = Table([head] + body, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, rl_color(INK)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, rl_color(RULE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFFFFF", "#" + PAPER]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 2), ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 6), ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]
    if not rows:
        style.append(("SPAN", (0, 1), (-1, 1)))
    for index, fill in (row_fills or {}).items():
        style.append(("BACKGROUND", (0, index + 1), (-1, index + 1), rl_color(fill)))
    table.setStyle(TableStyle(style))
    return table


def totals_block(lines, grand, width):
    """Totais alinhados a direita; a ultima linha (grand) em serifa com o acento terracota."""
    from reportlab.platypus import Paragraph, Table, TableStyle

    st = styles()
    rows = [[Paragraph(esc(label), st["total_label"]), Paragraph(esc(value), st["total_value"])] for label, value in lines]
    rows.append([Paragraph(esc(grand[0]), st["grand_label"]), Paragraph(esc(grand[1]), st["grand_value"])])
    table = Table(rows, colWidths=[width * 0.62, width * 0.38], hAlign="RIGHT")
    last = len(rows) - 1
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, last), (-1, last), 0.9, rl_color(INK)),
        ("BACKGROUND", (0, last), (-1, last), rl_color(ACCENT_SOFT)),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, last), (-1, last), 8), ("BOTTOMPADDING", (0, last), (-1, last), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def page_decorator(doc_label):
    """Barra terracota fina no topo, marca HoraCerta e numero da pagina no rodape."""
    emitted = timezone.localtime().strftime("%d/%m/%Y %H:%M")

    def draw(canvas, doc):
        from reportlab.lib.units import cm

        width, height = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(rl_color(ACCENT))
        canvas.rect(0, height - 0.18 * cm, width, 0.18 * cm, stroke=0, fill=1)
        canvas.setStrokeColor(rl_color(RULE))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 1.15 * cm, width - doc.rightMargin, 1.15 * cm)
        canvas.setFont("Times-Bold", 8.5)
        canvas.setFillColor(rl_color(INK))
        canvas.drawString(doc.leftMargin, 0.72 * cm, "HoraCerta")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(rl_color(MUTED))
        canvas.drawString(doc.leftMargin + 1.55 * cm, 0.72 * cm, f"{doc_label} · emitido em {emitted}")
        canvas.drawRightString(width - doc.rightMargin, 0.72 * cm, f"Página {doc.page}")
        canvas.restoreState()

    return draw
