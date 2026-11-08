"""Notas de envio: telas do dono e link publico do encarregado/supervisor."""

from datetime import datetime
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

ROLES = {
    "encarregado": ShipmentRecipient.Role.ENCARREGADO,
    "supervisor": ShipmentRecipient.Role.SUPERVISOR,
}
# Prefixo dos campos de cada destinatario no formulario.
RECIPIENT_FIELDS = (("boss", ShipmentRecipient.Role.ENCARREGADO), ("supervisor", ShipmentRecipient.Role.SUPERVISOR))


def _note_for(request, note_id):
    return get_object_or_404(ShipmentNote, id=note_id, owner=request.user)


def _digits(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())[:20]


def _parse_departed(value):
    try:
        return timezone.make_aware(datetime.strptime(value, "%Y-%m-%dT%H:%M"))
    except (TypeError, ValueError):
        return None


def _read_form(post):
    """Le o formulario (campos simples + linhas de itens em listas paralelas). Devolve (dados, erros)."""
    data = {
        "destination_company": post.get("destination_company", "").strip()[:120],
        "departed_at_raw": post.get("departed_at", ""),
        "departed_at": _parse_departed(post.get("departed_at", "")),
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
    for index, (order, drawing, quantity, description) in enumerate(zip(*columns), start=1):
        order, drawing, quantity, description = (v.strip() for v in (order, drawing, quantity, description))
        if not (order or drawing or description):
            continue  # linha em branco
        try:
            qty = int(quantity)
        except ValueError:
            qty = 0
        if not drawing or qty < 1:
            errors.append(f"Linha {index}: informe o nº do desenho e uma quantidade maior que zero.")
        data["items"].append({"production_order": order[:40], "drawing_number": drawing[:60],
                              "quantity": max(qty, 1), "description": description[:120]})
    if not data["destination_company"]:
        errors.append("Informe a empresa de destino.")
    if data["departed_at"] is None:
        errors.append("Informe a data e a hora de saída.")
    return data, errors


def _save_note(note, data):
    with transaction.atomic():
        for field in ("destination_company", "departed_at", "driver_name", "vehicle_plate", "notes"):
            setattr(note, field, data[field])
        note.save()
        note.items.all().delete()
        ShipmentItem.objects.bulk_create(
            ShipmentItem(note=note, position=i, **item) for i, item in enumerate(data["items"])
        )
        for role, values in data["recipients"].items():
            ShipmentRecipient.objects.update_or_create(note=note, role=role, defaults=values)
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
            "departed_at_raw": timezone.localtime(note.departed_at if note else timezone.now()).strftime("%Y-%m-%dT%H:%M"),
            "driver_name": note.driver_name if note else "",
            "vehicle_plate": note.vehicle_plate if note else "",
            "notes": note.notes if note else "",
            "recipients": recipients,
            "items": list(note.items.values("production_order", "drawing_number", "quantity", "description")) if note else [],
        }
    blank = {"production_order": "", "drawing_number": "", "quantity": "", "description": ""}
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
    return render(request, "production/shipment_list.html", {
        "drafts": [n for n in notes if not n.is_locked],
        "sent": [n for n in notes if n.is_locked],
        "query": query,
    })


@login_required
def shipment_create(request):
    if request.method == "POST":
        data, errors = _read_form(request.POST)
        if not errors:
            note = _save_note(ShipmentNote(owner=request.user), data)
            messages.success(request, "Rascunho salvo. Confira e toque em Enviar nota.")
            return redirect("shipment_detail", note_id=note.id)
        return render(request, "production/shipment_form.html", _form_context(data=data, errors=errors))
    return render(request, "production/shipment_form.html", _form_context(owner=request.user))


@login_required
def shipment_edit(request, note_id):
    note = _note_for(request, note_id)
    if note.is_locked:
        messages.info(request, "Nota enviada fica travada. Para corrigir, crie uma nota de correção.")
        return redirect("shipment_detail", note_id=note.id)
    if request.method == "POST":
        data, errors = _read_form(request.POST)
        if not errors:
            _save_note(note, data)
            messages.success(request, "Rascunho atualizado.")
            return redirect("shipment_detail", note_id=note.id)
        return render(request, "production/shipment_form.html", _form_context(note=note, data=data, errors=errors))
    return render(request, "production/shipment_form.html", _form_context(note=note))


@login_required
def shipment_detail(request, note_id):
    note = _note_for(request, note_id)
    return render(request, "production/shipment_detail.html", {
        "note": note, "items": note.items.all(), "recipients": note.recipients.all(),
        "situation": note.situation,
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
        messages.success(request, f"Nota nº {note.number_label} enviada e travada. Agora mande o link para cada um.")
    return redirect("shipment_detail", note_id=note.id)


@login_required
@require_POST
def shipment_delete(request, note_id):
    note = _note_for(request, note_id)
    if note.is_locked:
        messages.error(request, "Nota enviada não pode ser apagada: ela é o seu comprovante.")
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
            owner=request.user, destination_company=original.destination_company, driver_name=original.driver_name,
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
    messages.success(request, f"Nota de correção criada a partir da nº {original.number_label}. Ajuste e envie.")
    return redirect("shipment_edit", note_id=copy.id)


def whatsapp_message(note, recipient, link):
    total = note.total_quantity
    pieces = "peça" if total == 1 else "peças"
    first_name = recipient.name.split()[0] if recipient.name else ""
    return (
        f"Olá{', ' + first_name if first_name else ''}! Segue a *nota de envio nº {note.number_label}*: "
        f"{total} {pieces} para {note.destination_company}, saída em "
        f"{timezone.localtime(note.departed_at):%d/%m às %H:%M}.\n"
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


def _notify_owner(recipient, action):
    from timeclock.models import InternalNotification
    from timeclock.notifications import create_internal_notification

    note = recipient.note
    who = recipient.name or recipient.get_role_display()
    create_internal_notification(
        notification_type=InternalNotification.NotificationType.SHIPMENT_NOTE,
        title=f"Nota nº {note.number_label} {action} por {who}",
        message=f"{recipient.get_role_display()} {who} {action} a nota de envio para {note.destination_company}.",
        recipient_user=note.owner,
        target_url=reverse("shipment_detail", args=[note.id]),
    )


def shipment_public(request, token):
    recipient = _recipient_for(token)
    note = recipient.note
    response = render(request, "production/shipment_public.html", {
        "note": note, "recipient": recipient, "items": note.items.all(), "recipients": note.recipients.all(),
    })
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_POST
def shipment_public_seen(request, token):
    # Chamado pelo JavaScript da pagina: a previa de link do WhatsApp nao executa JS e nao conta como visto.
    recipient = _recipient_for(token)
    if recipient.mark_viewed():
        _notify_owner(recipient, "vista")
    return HttpResponse(status=204)


@require_POST
def shipment_public_authorize(request, token):
    recipient = _recipient_for(token)
    if recipient.authorize():
        _notify_owner(recipient, "autorizada")
    return redirect("shipment_public", token=token)
