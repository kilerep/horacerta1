"""Sincronizacao do que o prestador registrou sem internet.

O app (static/js/offline_sync.js) guarda no aparelho cada toque feito offline, com o
horario real do toque e um identificador proprio (client_ref). Quando a conexao volta,
envia a fila para ca. Cada item e validado como se fosse feito na hora:

- o cliente (contrato) precisa ser do proprio usuario e estar ativo;
- o horario nao pode estar no futuro nem ter mais de OFFLINE_MAX_AGE_DAYS dias;
- o dia nao pode estar bloqueado por um relatorio ja gerado;
- o mesmo client_ref nunca vira dois registros (reenvio apos queda e seguro).

Itens aceitos ficam marcados no audit_payload com origem "offline" e o horario real.
"""

import json
import uuid
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .models import Contract, Punch
from .services import report_locks_day

OFFLINE_MAX_AGE_DAYS = 7
MAX_ITEMS_PER_SYNC = 200
FUTURE_TOLERANCE = timedelta(minutes=5)


def offline_profile(user):
    """Dados minimos que o app guarda no aparelho para funcionar sem internet."""
    contracts = (
        Contract.objects.filter(employee__user=user, is_active=True)
        .select_related("company")
        .order_by("company__name")
    )
    from production.models import ProductionSheet

    sheets = ProductionSheet.objects.filter(owner=user, status=ProductionSheet.Status.OPEN).order_by("-created_at")[:20]
    return {
        "user_id": str(user.id),
        "contracts": [{"id": str(c.id), "name": c.company.name} for c in contracts],
        "sheets": [{"id": str(s.id), "name": s.equipment} for s in sheets],
    }


def _accept_punch(user, item, now):
    ref = str(item.get("client_ref") or "").strip()
    try:
        uuid.UUID(ref)
    except ValueError:
        return {"status": "erro", "motivo": "Identificador do registro inválido."}

    existing = Punch.all_objects.filter(audit_payload__client_ref=ref).first()
    if existing is not None:
        if existing.contract.employee.user_id != user.id:
            return {"status": "erro", "motivo": "Registro de outra conta."}
        return {"status": "ok", "duplicado": True}

    occurred = parse_datetime(str(item.get("occurred_at") or ""))
    if occurred is None:
        return {"status": "erro", "motivo": "Horário inválido."}
    if timezone.is_naive(occurred):
        occurred = timezone.make_aware(occurred)
    if occurred > now + FUTURE_TOLERANCE:
        return {"status": "erro", "motivo": "Horário no futuro: confira o relógio do celular."}
    if occurred < now - timedelta(days=OFFLINE_MAX_AGE_DAYS):
        return {"status": "erro", "motivo": f"Registro com mais de {OFFLINE_MAX_AGE_DAYS} dias: lance pelo horário manual."}

    contract = (
        Contract.objects.filter(id=item.get("contract_id"), employee__user=user, is_active=True)
        .select_related("employee")
        .first()
    )
    if contract is None:
        return {"status": "erro", "motivo": "Cliente não encontrado ou inativo na sua conta."}

    local_day = timezone.localtime(occurred).date()
    if report_locks_day(local_day, contract=contract):
        return {"status": "erro", "motivo": "Esse dia já está em um relatório gerado."}

    Punch.objects.create(
        contract=contract,
        timestamp=occurred,
        validation_method=Punch.ValidationMethod.FREE_POLICY,
        confidence_status=Punch.ConfidenceStatus.FREE,
        qr_confirmation_status=Punch.QrConfirmationStatus.NOT_REQUIRED,
        audit_payload={
            "source": "OFFLINE_SYNC",
            "origin": "offline",
            "recorded_from": "offline_button",
            "client_ref": ref,
            "occurred_at": occurred.isoformat(),
            "synced_at": now.isoformat(),
            "user_id": str(user.id),
            "employee_id": str(contract.employee_id),
        },
    )
    return {"status": "ok"}


def _accept_production_entry(user, item):
    from production.forms import ProductionEntryForm
    from production.models import ProductionEntry, ProductionSheet

    ref = str(item.get("client_ref") or "").strip()
    try:
        uuid.UUID(ref)
    except ValueError:
        return {"status": "erro", "motivo": "Identificador do registro inválido."}
    if ProductionEntry.objects.filter(client_ref=ref).exists():
        return {"status": "ok", "duplicado": True}

    sheet = ProductionSheet.objects.filter(id=item.get("sheet_id"), owner=user).first()
    if sheet is None:
        return {"status": "erro", "motivo": "Relatório de produção não encontrado na sua conta."}
    if not sheet.is_open:
        return {"status": "erro", "motivo": "Esse relatório de produção está fechado."}

    data = item.get("fields") or {}
    form = ProductionEntryForm({key: str(data.get(key) or "") for key in
                                ("work_date", "item_code", "destination", "start_time", "end_time", "duration", "note")})
    if not form.is_valid():
        errors = "; ".join(str(e) for errs in form.errors.values() for e in errs)
        return {"status": "erro", "motivo": errors or "Dados do item inválidos."}
    entry = form.save(commit=False)
    entry.sheet = sheet
    entry.client_ref = ref
    entry.save()
    return {"status": "ok"}


@login_required
@require_POST
def offline_sync(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"erro": "Envio inválido."}, status=400)
    items = payload.get("items")
    if not isinstance(items, list):
        return JsonResponse({"erro": "Envio inválido."}, status=400)
    if len(items) > MAX_ITEMS_PER_SYNC:
        return JsonResponse({"erro": f"Envie no máximo {MAX_ITEMS_PER_SYNC} registros por vez."}, status=400)

    now = timezone.now()
    results = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"client_ref": None, "status": "erro", "motivo": "Item inválido."})
            continue
        kind = item.get("kind")
        if kind == "punch":
            outcome = _accept_punch(request.user, item, now)
        elif kind == "production_entry":
            outcome = _accept_production_entry(request.user, item)
        else:
            outcome = {"status": "erro", "motivo": "Tipo de registro desconhecido."}
        results.append({"client_ref": item.get("client_ref"), **outcome})
    return JsonResponse({"resultados": results, "perfil": offline_profile(request.user)})


@login_required
def offline_profile_view(request):
    response = JsonResponse(offline_profile(request.user))
    response["Cache-Control"] = "private, no-store"
    return response
