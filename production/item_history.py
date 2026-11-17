"""Historico de um item (codigo do desenho ou ordem de producao): cortes e romaneios enviados.

Usado pela busca da tela e pelo PDF que o prestador manda quando alguem pergunta "quando saiu o 8210-120?".
"""

from io import BytesIO

from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from accounts import print_theme as pt

from .models import ProductionEntry, ShipmentItem, ShipmentNote


def item_groups(user, query, exact=False):
    """Agrupa por codigo: cortes (relatorios de producao) e envios (so romaneios enviados)."""
    query = (query or "").strip()[:60]
    if len(query) < 2:
        return []
    if exact:
        cut_filter = Q(item_code__iexact=query)
        sent_filter = Q(drawing_number__iexact=query)
    else:
        cut_filter = Q(item_code__icontains=query) | Q(production_order__icontains=query)
        sent_filter = Q(drawing_number__icontains=query) | Q(production_order__icontains=query)
    entries = (ProductionEntry.objects.filter(sheet__owner=user).filter(cut_filter)
               .select_related("sheet").order_by("-work_date", "-created_at")[:300])
    shipped = (ShipmentItem.objects.filter(note__owner=user, note__status=ShipmentNote.Status.SENT).filter(sent_filter)
               .select_related("note").prefetch_related("note__recipients").order_by("-note__sent_at")[:300])
    by_code = {}
    for entry in entries:
        by_code.setdefault(entry.item_code or "Sem código", {"cuts": [], "sent": []})["cuts"].append(entry)
    for item in shipped:
        by_code.setdefault(item.drawing_number or "Sem código", {"cuts": [], "sent": []})["sent"].append(item)
    groups = []
    for code, group in by_code.items():
        cuts, sent = group["cuts"], group["sent"]
        groups.append({
            "code": code, "cuts": cuts, "sent": sent,
            "cut_pieces": sum(e.quantity or 0 for e in cuts),
            "sent_pieces": sum(i.quantity or 0 for i in sent),
            "romaneios": len({i.note_id for i in sent}),
            "first": min((e.work_date for e in cuts), default=None),
            "last": max((e.work_date for e in cuts), default=None),
        })
    # codigo identico ao digitado primeiro, depois os que tem mais cortes
    groups.sort(key=lambda g: (g["code"].lower() != query.lower(), -len(g["cuts"]), g["code"]))
    return groups


def history_filename(query):
    return f"historico-{slugify(query)[:50] or 'item'}.pdf"


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def build_item_history_pdf(user, query, groups):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    from writtenreports.data import sender_name

    title = f"Histórico do item {query}"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.7 * cm, title=title, author="HoraCerta")
    width = A4[0] - doc.leftMargin - doc.rightMargin
    st = pt.styles()
    now = timezone.localtime().strftime("%d/%m/%Y às %H:%M")
    story = pt.header_block(title, [f"{pt.esc(sender_name(user))} · gerado em {now}"])

    for group in groups:
        cuts, sent = group["cuts"], group["sent"]
        block = [Paragraph(f"<b>{pt.esc(group['code'])}</b>", st["subtitle"]), Spacer(1, 6)]
        kpis = [("Vezes cortado", str(len(cuts)), True), ("Peças cortadas", str(group["cut_pieces"]), False),
                ("Romaneios", str(group["romaneios"]), False), ("Peças enviadas", str(group["sent_pieces"]), False)]
        block.append(pt.kpi_strip(kpis, width))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 10))
        if cuts:
            story.append(Paragraph("Cortes", st["label"]))
            rows = [[e.work_date.strftime("%d/%m/%Y"), e.sheet.equipment, e.production_order or "-",
                     (f"{e.start_time:%H:%M}" + (f" às {e.end_time:%H:%M}" if e.end_time else "")) if e.start_time else "-",
                     str(e.quantity or "-")] for e in cuts]
            story.append(pt.data_table(["Data", "Máquina", "Ordem", "Horário", "Qtd."], rows,
                                       [2.6 * cm, width - 12.2 * cm, 3.2 * cm, 4.4 * cm, 2.0 * cm], numeric_cols=(4,)))
            story.append(Spacer(1, 10))
        story.append(Paragraph("Envios", st["label"]))
        if sent:
            rows = [[f"nº {i.note.number_label}", i.note.destination_company,
                     timezone.localtime(i.note.loaded_at).strftime("%d/%m/%Y %H:%M") if i.note.loaded_at else "-",
                     i.note.situation[0], str(i.quantity)] for i in sent]
            story.append(pt.data_table(["Romaneio", "Destino", "Carregado em", "Situação", "Qtd."], rows,
                                       [2.4 * cm, width - 13.4 * cm, 3.6 * cm, 5.4 * cm, 2.0 * cm], numeric_cols=(4,)))
        else:
            story.append(Paragraph("Ainda não saiu em nenhum romaneio enviado.", st["small"]))
        story.append(Spacer(1, 18))

    story.append(Paragraph(
        f"Gerado pelo HoraCerta a partir dos relatórios de produção e dos romaneios enviados. "
        f"{_plural(len(groups), 'item encontrado', 'itens encontrados')}.", st["small"]))
    decorate = pt.page_decorator(title)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
