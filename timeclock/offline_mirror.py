"""Copia dos dados do prestador para o modo sem internet (Offline 2.0, etapa 1).

O app baixa este pacote quando ha internet e guarda no aparelho CRIPTOGRAFADO
(static/js/offline_mirror.js). Sem internet, as telas offline leem dessa copia.

Regras de seguranca:
- so dados do proprio usuario logado (cada consulta filtra pelo dono);
- nunca links secretos (tokens de pagina publica, de romaneio ou de producao),
  arquivos, senhas ou dados de outras contas;
- resposta "no-store": nem o navegador nem proxies guardam o JSON em cache;
- janela limitada (meses recentes) para o pacote ficar pequeno.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

MIRROR_SCHEMA = 1
MIRROR_TTL_DAYS = 30
SERVICE_WINDOW_DAYS = 60
PRODUCTION_WINDOW_DAYS = 60
SHIPMENT_WINDOW_DAYS = 60
MAX_PUNCHES = 3000
MAX_JOBS = 300
MAX_ENTRIES = 2000
MAX_SHIPMENTS = 100


def _iso(value):
    return value.isoformat() if value else None


def _money(value):
    return str(value) if value is not None else None


def _month_start(day):
    return day.replace(day=1)


def build_mirror(user):
    from production.models import ProductionEntry, ProductionSheet, ShipmentNote
    from services.models import ServiceCategory, ServiceJob

    from .models import Contract, DayOff, Punch

    today = timezone.localdate()
    since_month = _month_start(_month_start(today) - timedelta(days=1))  # comeco do mes passado

    contracts = list(
        Contract.objects.filter(employee__user=user).select_related("company").order_by("company__name")
    )
    contract_ids = [c.id for c in contracts]

    punches = (
        Punch.objects.filter(contract_id__in=contract_ids, timestamp__date__gte=since_month)
        .order_by("timestamp")
        .values("id", "contract_id", "timestamp")[:MAX_PUNCHES]
    )
    days_off = DayOff.objects.filter(owner=user, date__gte=since_month).order_by("date")

    job_from = today - timedelta(days=SERVICE_WINDOW_DAYS)
    job_to = today + timedelta(days=SERVICE_WINDOW_DAYS)
    jobs = (
        ServiceJob.objects.filter(professional=user)
        .exclude(status=ServiceJob.Status.ARCHIVED)
        .filter(start_date__range=(job_from, job_to))
        .select_related("client", "category")
        .order_by("start_date", "planned_start_time")[:MAX_JOBS]
    )

    sheet_from = timezone.now() - timedelta(days=PRODUCTION_WINDOW_DAYS)
    sheets = list(
        ProductionSheet.objects.filter(owner=user)
        .filter(Q(status=ProductionSheet.Status.OPEN) | Q(updated_at__gte=sheet_from))
        .order_by("-created_at")
    )
    sheet_ids = [s.id for s in sheets]
    entries = (
        ProductionEntry.objects.filter(sheet_id__in=sheet_ids)
        .order_by("-work_date", "-created_at")[:MAX_ENTRIES]
    )

    shipments = (
        ShipmentNote.objects.filter(owner=user, created_at__gte=timezone.now() - timedelta(days=SHIPMENT_WINDOW_DAYS))
        .prefetch_related("items", "recipients")
        .order_by("-created_at")[:MAX_SHIPMENTS]
    )

    return {
        "schema": MIRROR_SCHEMA,
        "user_id": str(user.id),
        "generated_at": timezone.now().isoformat(),
        "ttl_days": MIRROR_TTL_DAYS,
        "today": today.isoformat(),
        "since": since_month.isoformat(),
        "categories": [
            {"id": str(c.id), "name": c.name}
            for c in ServiceCategory.objects.filter(is_active=True).order_by("sort_order", "name")
        ],
        "clients": [
            {
                "id": str(c.id),
                "name": c.company.name,
                "hourly_rate": _money(c.hourly_rate),
                "start_date": _iso(c.start_date),
                "end_date": _iso(c.end_date),
                "active": bool(c.is_active),
            }
            for c in contracts
        ],
        "punches": [
            {"id": str(p["id"]), "client_id": str(p["contract_id"]), "at": _iso(p["timestamp"])} for p in punches
        ],
        "days_off": [{"date": _iso(d.date), "kind": d.kind, "note": d.note} for d in days_off],
        "jobs": [
            {
                "id": str(j.id),
                "title": j.title,
                "client": j.client_display_name,
                "category": getattr(j.category, "name", ""),
                "status": j.status,
                "status_label": j.get_status_display(),
                "date": _iso(j.start_date),
                "start": j.planned_start_time.strftime("%H:%M") if j.planned_start_time else "",
                "end": j.planned_end_time.strftime("%H:%M") if j.planned_end_time else "",
                "location": j.service_location,
                "updated_at": _iso(j.updated_at),
            }
            for j in jobs
        ],
        "sheets": [
            {
                "id": str(s.id),
                "equipment": s.equipment,
                "company": s.company_name,
                "status": s.status,
                "updated_at": _iso(s.updated_at),
            }
            for s in sheets
        ],
        "entries": [
            {
                "id": str(e.id),
                "sheet_id": str(e.sheet_id),
                "date": _iso(e.work_date),
                "item_code": e.item_code,
                "production_order": e.production_order,
                "quantity": e.quantity,
                "destination": e.destination,
                "start": e.start_time.strftime("%H:%M") if e.start_time else "",
                "end": e.end_time.strftime("%H:%M") if e.end_time else "",
                "minutes": e.manual_minutes,
                "note": e.note,
            }
            for e in entries
        ],
        "shipments": [
            {
                "id": str(n.id),
                "number": n.number,
                "destination": n.destination_company,
                "status": n.status,
                "departed_at": _iso(n.departed_at),
                "items": [
                    {"production_order": i.production_order, "drawing": i.drawing_number,
                     "quantity": i.quantity, "description": i.description}
                    for i in n.items.all()
                ],
                "seen": sum(1 for r in n.recipients.all() if r.viewed_at),
                "authorized": sum(1 for r in n.recipients.all() if r.authorized_at),
                "recipients": len(n.recipients.all()),
            }
            for n in shipments
        ],
    }


@login_required
@require_GET
def offline_mirror_view(request):
    response = JsonResponse(build_mirror(request.user))
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    return response
