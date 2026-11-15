"""Monta os dados que o relatorio escrito congela na emissao (horas do periodo ou dados do servico)."""

from decimal import Decimal

from django.utils import timezone


def brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def hhmm(seconds):
    minutes = int(seconds or 0) // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sender_name(user):
    """Nome de quem emite, como no topo do sistema: perfil > nome da conta > parte do e-mail antes do @."""
    from companies.models import Employee

    name = Employee.objects.filter(user=user).exclude(full_name="").values_list("full_name", flat=True).first()
    return (name or "").strip() or user.get_full_name().strip() or user.email.split("@")[0]


def hours_snapshot(report):
    from timeclock.models import Punch
    from timeclock.services import build_daily_summary

    contract = report.contract
    punches = Punch.objects.filter(
        contract=contract, timestamp__date__gte=report.date_from, timestamp__date__lte=report.date_to
    ).order_by("timestamp")
    rows, _cols = build_daily_summary(list(punches))
    rows = sorted(rows, key=lambda r: r["date"])
    total_seconds = sum(r["total_seconds"] or 0 for r in rows)
    rate = contract.hourly_rate or Decimal("0")
    value = (Decimal(total_seconds) / Decimal(3600) * rate).quantize(Decimal("0.01"))
    return {
        "client": contract.company.name,
        "rate": brl(rate) + "/h" if rate else "",
        "rows": [{"date": r["date"].strftime("%d/%m/%Y"), "hours": r["total_hours_hhmm"],
                  "incomplete": r["is_incomplete"]} for r in rows],
        "days": len(rows),
        "total_hours": hhmm(total_seconds),
        "total_value": brl(value) if rate else "",
    }


def service_snapshot(report):
    job = report.service_job
    logs = [{
        "date": log.work_date.strftime("%d/%m/%Y"),
        "time": f"{log.start_time:%H:%M}" + (f" às {log.end_time:%H:%M}" if log.end_time else ""),
        "description": log.description,
    } for log in job.work_logs.all().order_by("work_date", "start_time")]
    items = [{
        "name": item.name, "quantity": item.quantity_label, "total": brl(item.total_value),
    } for item in job.item_expenses.all().order_by("created_at")]
    return {
        "client": job.client_display_name,
        "service": job.title,
        "category": job.category.name if job.category else "",
        "logs": logs,
        "items": items,
        "total_hours": job.total_hours_label,
        "total_value": brl(job.estimated_total),
    }


def build_snapshot(report):
    data = hours_snapshot(report) if report.kind == report.Kind.HOURS else service_snapshot(report)
    data["sender"] = sender_name(report.owner)
    if report.kind == report.Kind.HOURS:
        data["period"] = f"{report.date_from:%d/%m/%Y} a {report.date_to:%d/%m/%Y}"
    data["issued"] = timezone.localtime().strftime("%d/%m/%Y às %H:%M")
    return data
