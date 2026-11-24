"""Romaneios de envio: telas do dono e link publico de cada pessoa que recebe a nota."""

from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ShipmentItem, ShipmentNote, ShipmentRecipient
from .shipment_exports import build_shipment_pdf, build_shipment_xlsx, delivery_term, shipment_filename

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Duas vagas por nota; o campo role so guarda a posicao (1 ou 2), nada de cargo na tela.
ROLES = {
    "1": ShipmentRecipient.Role.ENCARREGADO,
    "2": ShipmentRecipient.Role.SUPERVISOR,
}
MAX_QUANTITY = 999999
# Prefixo dos campos de cada destinatario no formulario.
RECIPIENT_FIELDS = (("boss", ShipmentRecipient.Role.ENCARREGADO), ("supervisor", ShipmentRecipient.Role.SUPERVISOR))


def _note_for(request, note_id):
    return get_object_or_404(ShipmentNote, id=note_id, owner=request.user)


def _digits(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())[:20]


def _read_form(post):
    """Le o formulario (campos simples + linhas de itens em listas paralelas). Devolve (dados, erros)."""
    data = {
        "destination_company": post.get("destination_company", "").strip()[:120],
        # O horario de carregamento e gravado no envio; o rascunho so guarda quando foi criado.
        "departed_at": timezone.now(),
        "driver_name": post.get("driver_name", "").strip()[:80],
        "vehicle_plate": post.get("vehicle_plate", "").strip().upper()[:10],
        "notes": post.get("notes", "").strip(),
        "recipients": {role: {"name": post.get(f"{prefix}_name", "").strip()[:80],
                              "whatsapp": _digits(post.get(f"{prefix}_whatsapp", ""))}
                       for prefix, role in RECIPIENT_FIELDS},
        "items": [],
    }
    errors = []
    columns = [post.getlist(name) for name in ("item_order", "item_drawing", "item_quantity", "item_description")]
    # de qual item da producao a linha veio (campo escondido); linha nova/digitada fica sem
    sources = post.getlist("item_source")
    sources += [""] * (len(columns[0]) - len(sources))
    for index, (order, drawing, quantity, description, source) in enumerate(zip(*columns, sources), start=1):
        order, drawing, quantity, description = (v.strip() for v in (order, drawing, quantity, description))
        if not (order or drawing or description):
            continue  # linha em branco
        try:
            qty = int(quantity)
        except ValueError:
            qty = 0
        if not drawing or not 1 <= qty <= MAX_QUANTITY:
            errors.append(f"Linha {index}: informe o nº do desenho e uma quantidade entre 1 e {MAX_QUANTITY}.")
        data["items"].append({"production_order": order[:40], "drawing_number": drawing[:60],
                              "quantity": min(max(qty, 1), MAX_QUANTITY), "description": description[:120],
                              "source_entry_id": (source or "").strip()})
    if not data["destination_company"]:
        errors.append("Informe a empresa de destino.")
    return data, errors


NOTE_FIELDS = ("destination_company", "driver_name", "vehicle_plate", "notes")


def _save_note(note, data):
    with transaction.atomic():
        is_new = note._state.adding
        if not is_new and not ShipmentNote.objects.select_for_update().filter(
                pk=note.pk, status=ShipmentNote.Status.DRAFT).exists():
            # Foi enviada enquanto o formulario estava aberto: nota travada nao muda.
            raise ValidationError("Este romaneio já foi enviado e está travado.")
        for field in NOTE_FIELDS:
            setattr(note, field, data[field])
        if is_new:
            note.save()
        else:  # nunca regrava status/numero/envio a partir de um objeto possivelmente antigo
            note.save(update_fields=[*NOTE_FIELDS, "updated_at"])
        note.items.all().delete()
        # so aceita vinculo com item de producao do proprio dono do romaneio
        from .models import ProductionEntry

        wanted = _valid_uuids([item.get("source_entry_id") for item in data["items"]])
        owned = {str(pk) for pk in ProductionEntry.objects.filter(id__in=wanted, sheet__owner=note.owner)
                 .values_list("id", flat=True)}
        ShipmentItem.objects.bulk_create(
            ShipmentItem(note=note, position=i, production_order=item["production_order"],
                         drawing_number=item["drawing_number"], quantity=item["quantity"],
                         description=item["description"],
                         source_entry_id=item.get("source_entry_id") if item.get("source_entry_id") in owned else None)
            for i, item in enumerate(data["items"])
        )
        for role, values in data["recipients"].items():
            if values["name"]:
                ShipmentRecipient.objects.update_or_create(note=note, role=role, defaults=values)
            else:  # nome apagado: essa pessoa nao recebe a nota
                ShipmentRecipient.objects.filter(note=note, role=role).delete()
    return note


def _form_context(note=None, data=None, errors=None, owner=None):
    """Valores para o template: do POST com erro, da nota em edicao ou da ultima nota enviada."""
    if data is None:
        source = note
        if source is None:
            source = ShipmentNote.objects.filter(owner=owner, status=ShipmentNote.Status.SENT).order_by("-sent_at").first()
        recipients = {r.role: {"name": r.name, "whatsapp": r.whatsapp} for r in source.recipients.all()} if source else {}
        data = {
            "destination_company": source.destination_company if source else "",
            "driver_name": note.driver_name if note else "",
            "vehicle_plate": note.vehicle_plate if note else "",
            "notes": note.notes if note else "",
            "recipients": recipients,
            "items": [
                {"production_order": i.production_order, "drawing_number": i.drawing_number, "quantity": i.quantity,
                 "description": i.description, "source_entry_id": str(i.source_entry_id or ""),
                 "machine": i.source_entry.sheet.equipment if i.source_entry_id else ""}
                for i in note.items.select_related("source_entry__sheet")
            ] if note else [],
        }
    blank = {"production_order": "", "drawing_number": "", "quantity": "", "description": "", "source_entry_id": "", "machine": ""}
    rows = data["items"] + [blank] * max(3 - len(data["items"]), 1)
    empty = {"name": "", "whatsapp": ""}
    return {
        "note": note, "data": data, "errors": errors or [], "rows": rows,
        "boss": data["recipients"].get(ShipmentRecipient.Role.ENCARREGADO, empty),
        "supervisor": data["recipients"].get(ShipmentRecipient.Role.SUPERVISOR, empty),
    }


@login_required
def shipment_list(request):
    query = (request.GET.get("q") or "").strip()
    notes = ShipmentNote.objects.filter(owner=request.user).prefetch_related("items", "recipients")
    if query:
        digits = query.lstrip("0")
        match = (Q(destination_company__icontains=query) | Q(items__production_order__icontains=query)
                 | Q(items__drawing_number__icontains=query) | Q(items__description__icontains=query))
        if digits.isdigit():
            match |= Q(number=int(digits))
        notes = notes.filter(match).distinct()
    notes = list(notes)
    sent = [n for n in notes if n.is_locked]
    waiting = sum(1 for n in sent if any(not r.authorized_at for r in n.recipients.all()))
    return render(request, "production/shipment_list.html", {
        "drafts": [n for n in notes if not n.is_locked],
        "sent": sent,
        "waiting": waiting,
        "query": query,
    })


@login_required
def shipment_create(request):
    if request.method == "POST":
        data, errors = _read_form(request.POST)
        if not errors:
            note = _save_note(ShipmentNote(owner=request.user), data)
            messages.success(request, "Rascunho salvo. Confira e toque em Enviar romaneio.")
            return redirect("shipment_detail", note_id=note.id)
        return render(request, "production/shipment_form.html", _form_context(data=data, errors=errors))
    return render(request, "production/shipment_form.html", _form_context(owner=request.user))


@login_required
def shipment_edit(request, note_id):
    note = _note_for(request, note_id)
    if note.is_locked:
        messages.info(request, "Romaneio enviado fica travado. Para corrigir, crie um romaneio de correção.")
        return redirect("shipment_detail", note_id=note.id)
    if request.method == "POST":
        data, errors = _read_form(request.POST)
        if not errors:
            try:
                _save_note(note, data)
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, "Rascunho atualizado.")
            return redirect("shipment_detail", note_id=note.id)
        return render(request, "production/shipment_form.html", _form_context(note=note, data=data, errors=errors))
    return render(request, "production/shipment_form.html", _form_context(note=note))


@login_required
def shipment_detail(request, note_id):
    note = _note_for(request, note_id)
    recipients = list(note.recipients.all())
    return render(request, "production/shipment_detail.html", {
        "note": note, "items": note.grouped_items(), "recipients": recipients, "situation": note.situation,
        "recipients_count": len(recipients),
        "viewed_count": sum(1 for r in recipients if r.viewed_at),
        "authorized_count": sum(1 for r in recipients if r.authorized_at),
    })


@login_required
@require_POST
def shipment_send(request, note_id):
    note = _note_for(request, note_id)
    try:
        note.send()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, f"Carregamento confirmado: romaneio nº {note.number_label} enviado e travado. "
                                  "Agora mande o link para cada um.")
    return redirect("shipment_detail", note_id=note.id)


@login_required
@require_POST
def shipment_delete(request, note_id):
    note = _note_for(request, note_id)
    if note.is_locked:
        messages.error(request, "Romaneio enviado não pode ser apagado: ele fica guardado como registro do envio.")
        return redirect("shipment_detail", note_id=note.id)
    note.delete()
    messages.success(request, "Rascunho apagado.")
    return redirect("shipment_list")


@login_required
@require_POST
def shipment_replace(request, note_id):
    original = _note_for(request, note_id)
    with transaction.atomic():
        copy = ShipmentNote.objects.create(
            owner=request.user, destination_company=original.destination_company, departed_at=original.departed_at,
            driver_name=original.driver_name,
            vehicle_plate=original.vehicle_plate, notes=original.notes, replaces=original,
        )
        ShipmentItem.objects.bulk_create(
            ShipmentItem(note=copy, position=i.position, production_order=i.production_order,
                         drawing_number=i.drawing_number, quantity=i.quantity, description=i.description)
            for i in original.items.all()
        )
        ShipmentRecipient.objects.bulk_create(
            ShipmentRecipient(note=copy, role=r.role, name=r.name, whatsapp=r.whatsapp) for r in original.recipients.all()
        )
    messages.success(request, f"Romaneio de correção criado a partir do nº {original.number_label}. Ajuste e envie.")
    return redirect("shipment_edit", note_id=copy.id)


def whatsapp_message(note, recipient, link):
    total = note.total_quantity
    pieces = "peça" if total == 1 else "peças"
    first_name = recipient.name.split()[0] if recipient.name else ""
    return (
        f"Olá{', ' + first_name if first_name else ''}! Segue o *romaneio de envio nº {note.number_label}*: "
        f"{total} {pieces} para {note.destination_company}, carga conferida e carregada em "
        f"{timezone.localtime(note.loaded_at or note.created_at):%d/%m às %H:%M}.\n"
        f"Confira e autorize por este link: {link}"
    )


@login_required
def shipment_whatsapp(request, note_id, role):
    note = _note_for(request, note_id)
    if role not in ROLES or not note.is_locked:
        raise Http404
    recipient = get_object_or_404(ShipmentRecipient, note=note, role=ROLES[role])
    link = request.build_absolute_uri(reverse("shipment_public", args=[recipient.token]))
    text = quote(whatsapp_message(note, recipient, link), safe="")
    digits = recipient.whatsapp
    if digits:
        number = digits if len(digits) > 11 else f"55{digits}"
        return redirect(f"https://wa.me/{number}?text={text}")
    return redirect(f"https://wa.me/?text={text}")


# ---- link publico (sem login): cada destinatario so enxerga a propria nota ----

def _recipient_for(token):
    recipient = get_object_or_404(ShipmentRecipient.objects.select_related("note", "note__owner"), token=token)
    if not recipient.note.is_locked:
        raise Http404
    return recipient


def _is_owner_preview(request, recipient):
    """Quem enviou a nota abrindo o link de outra pessoa: so mostra, nunca conta visto nem autoriza."""
    return request.user.is_authenticated and request.user.pk == recipient.note.owner_id


def _notify_owner(recipient, action):
    from timeclock.models import InternalNotification
    from timeclock.notifications import create_internal_notification

    note = recipient.note
    who = recipient.name or "Quem recebeu o link"
    create_internal_notification(
        notification_type=InternalNotification.NotificationType.SHIPMENT_NOTE,
        title=f"Romaneio nº {note.number_label} {action} por {who}",
        message=f"{who} {action} o romaneio de envio para {note.destination_company}.",
        recipient_user=note.owner,
        target_url=reverse("shipment_detail", args=[note.id]),
        push=True,
    )


def shipment_public(request, token):
    recipient = _recipient_for(token)
    note = recipient.note
    recipients = list(note.recipients.all())
    authorized = sum(1 for r in recipients if r.authorized_at)
    response = render(request, "production/shipment_public.html", {
        "note": note, "recipient": recipient, "items": note.grouped_items(), "recipients": recipients,
        "recipients_count": len(recipients), "viewed_count": sum(1 for r in recipients if r.viewed_at),
        "authorized_count": authorized, "authorized_all": bool(recipients) and authorized == len(recipients),
        "owner_preview": _is_owner_preview(request, recipient),
        "delivery_term": delivery_term(note),
    })
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_POST
def shipment_public_seen(request, token):
    # Chamado pelo JavaScript da pagina: a previa de link do WhatsApp nao executa JS e nao conta como visto.
    recipient = _recipient_for(token)
    if not _is_owner_preview(request, recipient) and recipient.mark_viewed():
        _notify_owner(recipient, "visto")
    return HttpResponse(status=204)


@require_POST
def shipment_public_authorize(request, token):
    recipient = _recipient_for(token)
    if not _is_owner_preview(request, recipient) and recipient.authorize():
        _notify_owner(recipient, "autorizado")
    return redirect("shipment_public", token=token)


def _file(content, content_type, filename, inline=False):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def shipment_pdf(request, note_id):
    note = _note_for(request, note_id)
    return _file(build_shipment_pdf(note), "application/pdf", shipment_filename(note, "pdf"), inline=True)


@login_required
def shipment_xlsx(request, note_id):
    note = _note_for(request, note_id)
    return _file(build_shipment_xlsx(note), XLSX_TYPE, shipment_filename(note, "xlsx"))


def shipment_public_pdf(request, token):
    note = _recipient_for(token).note
    return _file(build_shipment_pdf(note), "application/pdf", shipment_filename(note, "pdf"), inline=True)


def shipment_public_xlsx(request, token):
    note = _recipient_for(token).note
    return _file(build_shipment_xlsx(note), XLSX_TYPE, shipment_filename(note, "xlsx"))


# ---- romaneio a partir dos itens do relatorio de producao ----

def _new_draft_like_last(owner):
    """Rascunho novo com destino e pessoas do ultimo romaneio enviado (quase sempre os mesmos)."""
    last = ShipmentNote.objects.filter(owner=owner, status=ShipmentNote.Status.SENT).order_by("-sent_at").first()
    draft = ShipmentNote.objects.create(owner=owner, destination_company=last.destination_company if last else "")
    if last:
        ShipmentRecipient.objects.bulk_create(
            ShipmentRecipient(note=draft, role=r.role, name=r.name, whatsapp=r.whatsapp) for r in last.recipients.all()
        )
    return draft


@login_required
@require_POST
def shipment_from_entries(request, sheet_id):
    from .models import ProductionEntry, ProductionSheet

    sheet = get_object_or_404(ProductionSheet, id=sheet_id, owner=request.user)
    wanted = [value for value in request.POST.getlist("entry") if value]
    by_id = {str(e.id): e for e in ProductionEntry.objects.filter(sheet=sheet, id__in=_valid_uuids(wanted))}
    entries = [by_id[value] for value in wanted if value in by_id]  # na ordem em que foram marcados
    if not entries:
        raise Http404
    with transaction.atomic():
        target = request.POST.get("target", "new")
        draft = None
        if target != "new":
            draft = ShipmentNote.objects.select_for_update().filter(
                id__in=_valid_uuids([target]), owner=request.user, status=ShipmentNote.Status.DRAFT).first()
        if draft is None:  # "novo" ou o rascunho escolhido ja foi enviado: comeca outro
            draft = _new_draft_like_last(request.user)
        start = draft.items.count()
        ShipmentItem.objects.bulk_create(
            ShipmentItem(
                note=draft, position=start + i, source_entry=e, production_order=e.production_order[:40],
                drawing_number=(e.item_code or "-")[:60],
                # o que falta enviar; item sem quantidade ou ja todo enviado entra com 1 e o dono ajusta
                quantity=min(max(e.remaining_quantity() or 1, 1), MAX_QUANTITY),
            )
            for i, e in enumerate(entries)
        )
        draft.save(update_fields=["updated_at"])  # vira o "romaneio em montagem" das proximas selecoes
    count = len(entries)
    messages.success(request, f"{count} {'item adicionado' if count == 1 else 'itens adicionados'} ao romaneio. "
                              "Ajuste as quantidades se só parte for no caminhão.")
    return redirect("shipment_edit", note_id=draft.id)


def _valid_uuids(values):
    import uuid

    valid = []
    for value in values:
        try:
            valid.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    return valid
