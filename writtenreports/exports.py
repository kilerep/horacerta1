"""PDF do relatorio escrito, no mesmo visual dos outros documentos (accounts/print_theme.py)."""

from io import BytesIO

from django.utils.text import slugify

from accounts import print_theme as pt


def pdf_filename(report):
    client = slugify(report.client_name)[:40] or "cliente"
    return f"relatorio-{report.number_label.lower()}-{client}.pdf"


def build_pdf(report):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from .data import build_snapshot

    data = report.snapshot if report.is_locked else build_snapshot(report)
    kind = report.get_kind_display()
    title = f"{kind} nº {report.number_label}" if report.number else f"{kind} (rascunho)"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.7 * cm, title=title, author="HoraCerta")
    width = A4[0] - doc.leftMargin - doc.rightMargin
    st = pt.styles()

    story = pt.header_block(report.title, [pt.esc(title)])
    pairs = [("Prestador", data.get("sender", "")), ("Cliente", data.get("client", ""))]
    if report.kind == report.Kind.HOURS:
        pairs += [("Período", data.get("period", "")), ("Valor/hora", data.get("rate", "") or "-")]
    else:
        pairs += [("Serviço", data.get("service", "")), ("Categoria", data.get("category", "") or "-")]
    pairs.append(("Emitido em", data.get("issued", "") if report.is_locked else "Rascunho"))
    story.append(pt.info_grid(pairs, width, columns=3))
    story.append(Spacer(1, 14))

    for label, text in report.sections:
        story.append(Paragraph(f"<b>{pt.esc(label)}</b>", st["subtitle"]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(pt.esc(text).replace("\n", "<br/>"), st["body"]))
        story.append(Spacer(1, 12))

    if report.kind == report.Kind.HOURS:
        rows = [[r["date"], r["hours"] + (" (incompleto)" if r.get("incomplete") else "")] for r in data.get("rows", [])]
        story.append(pt.data_table(["Dia", "Horas"], rows, [width * 0.6, width * 0.4], numeric_cols=(1,),
                                   empty_text="Nenhuma hora registrada no período."))
        grand = ("Total", data.get("total_hours", "00:00"))
        lines = [("Valor estimado", data["total_value"])] if data.get("total_value") else []
    else:
        if data.get("logs"):
            story.append(pt.data_table(["Dia", "Horário", "O que foi feito"],
                                       [[l["date"], l["time"], l["description"]] for l in data["logs"]],
                                       [width * 0.2, width * 0.22, width * 0.58]))
            story.append(Spacer(1, 10))
        if data.get("items"):
            story.append(pt.data_table(["Item / material", "Qtd.", "Total"],
                                       [[i["name"], i["quantity"], i["total"]] for i in data["items"]],
                                       [width * 0.6, width * 0.15, width * 0.25], numeric_cols=(1, 2)))
        grand = ("Total do serviço", data.get("total_value", ""))
        lines = [("Horas trabalhadas", data.get("total_hours", ""))]
    story.append(Spacer(1, 10))
    story.append(pt.totals_block(lines, grand, width * 0.4))
    story.append(Spacer(1, 30))

    # duas linhas de assinatura separadas por uma coluna vazia no meio
    signature = Table([["", "", ""], [data.get("sender", ""), "", data.get("client", "")]],
                      colWidths=[width * 0.42, width * 0.16, width * 0.42], hAlign="CENTER", spaceBefore=0)
    signature.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (0, 1), 0.8, pt.rl_color(pt.INK)),
        ("LINEABOVE", (2, 1), (2, 1), 0.8, pt.rl_color(pt.INK)),
        ("TOPPADDING", (0, 0), (-1, 0), 18), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 1), (-1, 1), 9), ("TEXTCOLOR", (0, 1), (-1, 1), pt.rl_color(pt.MUTED)),
    ]))
    code = str(report.id)[:8].upper()
    story.append(KeepTogether([signature, Spacer(1, 10), Paragraph(
        f"Documento emitido pelo HoraCerta. Depois de emitido, não pode ser alterado. Código de conferência <b>{code}</b>.",
        st["small"])]))

    decorate = pt.page_decorator(title)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
