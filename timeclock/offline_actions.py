"""Acoes feitas sem internet (Offline 2.0, etapa 3).

Cada acao da fila do aparelho chega em /me/offline/sincronizar/ com um client_ref unico
e e aplicada com AS MESMAS regras da tela online (reaproveitando formularios e funcoes
das proprias telas). O OfflineReceipt garante que reenviar nao duplica.

Tipos aceitos aqui (entrada/saida e item de producao continuam em offline.py):
  manual_punch    horario manual (so no proprio dia do toque, como na tela online)
  day_off         marcar/desmarcar folga ou feriado
  client_new      cliente novo (nome, valor/hora, WhatsApp)
  service_new     servico novo
  service_status  iniciar ou finalizar um servico
  shipment_draft  rascunho de romaneio
  report_draft    rascunho de relatorio de servico

Uma acao pode apontar para um cliente criado offline na mesma fila: "client_from_ref"
= client_ref do item client_new (resolvido pelo recibo dele).
"""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Contract, DayOff, OfflineReceipt, Punch
from .services import report_locks_day

MAX_AGE_DAYS = 7
FUTURE_TOLERANCE = timedelta(minutes=5)


class Rejected(Exception):
    """A acao nao pode ser aplicada; a mensagem vai para a pessoa na fila do aparelho."""


def _ref(item):
    try:
        return uuid.UUID(str(item.get("client_ref") or ""))
    except ValueError:
        raise Rejected("Identificador do registro inválido.")


def _occurred(item, now):
    occurred = parse_datetime(str(item.get("occurred_at") or ""))
    if occurred is None:
        raise Rejected("Horário do registro inválido.")
    if timezone.is_naive(occurred):
        occurred = timezone.make_aware(occurred)
    if occurred > now + FUTURE_TOLERANCE:
        raise Rejected("Horário no futuro: confira o relógio do celular.")
    if occurred < now - timedelta(days=MAX_AGE_DAYS):
        raise Rejected(f"Registro com mais de {MAX_AGE_DAYS} dias sem internet. Refaça com internet.")
    return occurred


def _day(value, message="Data inválida."):
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise Rejected(message)


def resolve_contract(user, item, *, active_only=True):
    """Cliente do proprio usuario: pelo id ou pelo cliente criado offline (client_from_ref)."""
    contract_id = item.get("contract_id")
    from_ref = item.get("client_from_ref")
    if from_ref and not contract_id:
        receipt = OfflineReceipt.objects.filter(client_ref=from_ref, owner=user, kind="client_new").first()
        if receipt is None:
            raise Rejected("O cliente novo deste registro ainda não foi salvo.")
        contract_id = receipt.object_id
    if not contract_id:
        raise Rejected("Selecione o cliente.")
    qs = Contract.objects.filter(id=contract_id, employee__user=user).select_related("company", "employee")
    if active_only:
        qs = qs.filter(is_active=True)
    contract = qs.first()
    if contract is None:
        raise Rejected("Cliente não encontrado ou inativo na sua conta.")
    return contract


# ---------- acoes ----------

def _manual_punch(user, item, now):
    occurred = _occurred(item, now)
    launch_date = _day(item.get("date"), "Informe o dia do horário manual.")
    # mesma regra da tela: horario manual so no dia de hoje - aqui, o "hoje" do toque
    if launch_date != timezone.localtime(occurred).date():
        raise Rejected("O horário manual só pode ser lançado no próprio dia.")
    contract = resolve_contract(user, item)
    if report_locks_day(launch_date, contract=contract):
        raise Rejected("Esse dia já está em um relatório gerado.")
    times = []
    for raw in item.get("times") or []:
        try:
            parsed = datetime.strptime(str(raw).strip(), "%H:%M").time()
        except ValueError:
            raise Rejected(f"Horário inválido: {raw}.")
        if (parsed.hour, parsed.minute) not in times:
            times.append((parsed.hour, parsed.minute))
    if not times:
        raise Rejected("Informe pelo menos 1 horário.")
    tz = timezone.get_current_timezone()
    day_range = (timezone.make_aware(datetime.combine(launch_date, time.min), tz),
                 timezone.make_aware(datetime.combine(launch_date, time.max), tz))
    existing = {(t.hour, t.minute) for t in (timezone.localtime(ts, tz) for ts in
                Punch.objects.filter(contract=contract, timestamp__range=day_range).values_list("timestamp", flat=True))}
    clash = sorted(f"{h:02d}:{m:02d}" for h, m in times if (h, m) in existing)
    if clash:
        raise Rejected("Já existe horário para este cliente nesse dia: " + ", ".join(clash) + ".")
    note = str(item.get("note") or "").strip()[:1000]
    for hour, minute in sorted(times):
        Punch.objects.create(
            contract=contract,
            timestamp=timezone.make_aware(datetime.combine(launch_date, time(hour, minute)), tz),
            is_manual=True,
            note=note,
            validation_method=Punch.ValidationMethod.FREE_POLICY,
            confidence_status=Punch.ConfidenceStatus.FREE,
            qr_confirmation_status=Punch.QrConfirmationStatus.NOT_REQUIRED,
            audit_payload={"source": "OFFLINE_SYNC", "origin": "manual", "recorded_from": "offline_manual",
                           "client_ref": str(item.get("client_ref")), "occurred_at": occurred.isoformat(),
                           "synced_at": now.isoformat(), "user_id": str(user.id),
                           "local_date": launch_date.isoformat(), "local_time": f"{hour:02d}:{minute:02d}:00"},
        )
    return str(contract.id)


def _day_off(user, item, now):
    _occurred(item, now)
    day = _day(item.get("date"), "Escolha o dia da folga ou do feriado.")
    if item.get("remove"):
        DayOff.objects.filter(owner=user, date=day).delete()
        return ""
    kind = item.get("off_kind") if item.get("off_kind") in DayOff.Kind.values else DayOff.Kind.FOLGA
    off, _ = DayOff.objects.update_or_create(owner=user, date=day, defaults={
        "kind": kind, "note": str(item.get("note") or "").strip()[:80]})
    return str(off.id)


def _client_new(user, item, now):
    from services.views import _create_casual_client_contract

    _occurred(item, now)
    name = str(item.get("name") or "").strip()[:120]
    if not name:
        raise Rejected("Informe o nome do cliente.")
    try:
        rate = Decimal(str(item.get("hourly_rate") or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise Rejected("Valor por hora inválido.")
    if rate < 0 or rate > Decimal("99999"):
        raise Rejected("Valor por hora inválido.")
    whatsapp = "".join(ch for ch in str(item.get("whatsapp") or "") if ch.isdigit())[:20]
    contract = _create_casual_client_contract(user, name=name, whatsapp=whatsapp)
    if rate:
        contract.hourly_rate = rate
        contract.save(update_fields=["hourly_rate"])
    return str(contract.id)


def _service_new(user, item, now):
    from services.forms import ServiceJobForm
    from services.models import ServiceJob
    from services.workflow import planned_status_for_service

    _occurred(item, now)
    data = QueryDict(mutable=True)
    if item.get("contract_id") or item.get("client_from_ref"):
        contract = resolve_contract(user, item)
        data.update({"client_mode": "registered", "contract": str(contract.id)})
    else:
        data.update({"client_mode": "casual", "manual_client_name": str(item.get("manual_client_name") or "")})
    data.update({
        "title": str(item.get("title") or ""),
        "category": str(item.get("category_id") or ""),
        "start_date": str(item.get("date") or ""),
        "planned_start_time": str(item.get("start") or ""),
        "service_street": str(item.get("location") or "")[:140],
        "billing_mode": ServiceJob.BillingMode.HOURLY if data.get("client_mode") == "registered" else ServiceJob.BillingMode.UNDEFINED,
        "description": str(item.get("description") or ""),
        "notes": str(item.get("notes") or ""),
    })
    form = ServiceJobForm(data, user=user)
    if not form.is_valid():
        raise Rejected("; ".join(str(e) for errs in form.errors.values() for e in errs) or "Dados do serviço inválidos.")
    job = form.save(status=ServiceJob.Status.DRAFT)
    status = planned_status_for_service(job, requested_status=ServiceJob.Status.PLANNED)
    if job.status != status:
        job.status = status
        job.save(update_fields=["status", "finished_at", "updated_at"])
    return str(job.id)


def _service_status(user, item, now):
    from services.models import ServiceJob

    _occurred(item, now)
    job = ServiceJob.objects.select_for_update().filter(id=item.get("job_id"), professional=user).first()
    if job is None:
        raise Rejected("Serviço não encontrado na sua conta.")
    action = item.get("action")
    base = item.get("base_status")
    target = {"start": ServiceJob.Status.IN_PROGRESS, "finish": ServiceJob.Status.FINISHED}.get(action)
    if target is None:
        raise Rejected("Ação inválida para este serviço.")
    if job.status == target:
        return str(job.id)  # ja feito (em outro aparelho ou reenvio): nada a mudar
    if base and job.status != base:
        raise Rejected(f"O serviço mudou em outro aparelho (agora: {job.get_status_display()}). Confira com internet.")
    if action == "start" and job.status not in (ServiceJob.Status.PLANNED, ServiceJob.Status.SENT, ServiceJob.Status.SCHEDULED):
        raise Rejected("Este serviço não pode ser iniciado agora.")
    if action == "finish":
        if job.status != ServiceJob.Status.IN_PROGRESS:
            raise Rejected("Inicie o serviço antes de finalizar.")
        if job.work_logs.filter(end_time__isnull=True).exists():
            raise Rejected("Encerre o período aberto do serviço antes de finalizar.")
    job.status = target
    job.save(update_fields=["status", "finished_at", "updated_at"])
    return str(job.id)


def _shipment_draft(user, item, now):
    from production.models import ShipmentNote
    from production.shipment_views import _read_form, _save_note

    _occurred(item, now)
    post = QueryDict(mutable=True)
    post.update({"destination_company": str(item.get("destination") or ""), "driver_name": str(item.get("driver") or ""),
                 "vehicle_plate": str(item.get("plate") or ""), "notes": str(item.get("notes") or "")})
    for row in (item.get("items") or [])[:200]:
        post.appendlist("item_order", str(row.get("order") or ""))
        post.appendlist("item_drawing", str(row.get("drawing") or ""))
        post.appendlist("item_quantity", str(row.get("quantity") or ""))
        post.appendlist("item_description", str(row.get("description") or ""))
    data, errors = _read_form(post)
    if errors:
        raise Rejected(" ".join(errors))
    note = _save_note(ShipmentNote(owner=user), data)
    return str(note.id)


def _report_draft(user, item, now):
    from writtenreports.models import WrittenReport
    from writtenreports.views import _read_form

    _occurred(item, now)
    post = QueryDict(mutable=True)
    for key in ("title", "client_name", "service_name", "date_from", "date_to",
                "objective", "activities", "observations", "conclusion"):
        post[key] = str(item.get(key) or "")
    report = WrittenReport(owner=user, kind=WrittenReport.Kind.SERVICE)
    errors = _read_form(type("R", (), {"POST": post})(), report)
    if errors:
        raise Rejected(" ".join(errors))
    report.save()
    return str(report.id)


HANDLERS = {
    "manual_punch": _manual_punch,
    "day_off": _day_off,
    "client_new": _client_new,
    "service_new": _service_new,
    "service_status": _service_status,
    "shipment_draft": _shipment_draft,
    "report_draft": _report_draft,
}


def apply_action(user, item, now):
    """Aplica uma acao da fila. Devolve o resultado no formato da sincronizacao."""
    handler = HANDLERS.get(item.get("kind"))
    if handler is None:
        return None
    try:
        ref = _ref(item)
        receipt = OfflineReceipt.objects.filter(client_ref=ref).first()
        if receipt is not None:
            if receipt.owner_id != user.id:
                return {"status": "erro", "motivo": "Registro de outra conta."}
            return {"status": "ok", "duplicado": True, "object_id": receipt.object_id}
        with transaction.atomic():
            object_id = handler(user, item, now) or ""
            OfflineReceipt.objects.create(client_ref=ref, owner=user, kind=item["kind"], object_id=object_id)
    except Rejected as rejected:
        return {"status": "erro", "motivo": str(rejected)}
    except IntegrityError:
        # mesmo client_ref chegou duas vezes ao mesmo tempo: o outro envio ja aplicou
        return {"status": "ok", "duplicado": True}
    return {"status": "ok", "object_id": object_id}
