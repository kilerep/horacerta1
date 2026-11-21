"""Agenda da semana dos servicos e o lembrete do dia (aviso no sininho e no Meu resumo)."""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import ServiceJob
from .workflow import status_label, status_tone

ACTIVE = (ServiceJob.Status.DRAFT, ServiceJob.Status.PLANNED, ServiceJob.Status.SENT,
          ServiceJob.Status.SCHEDULED, ServiceJob.Status.IN_PROGRESS)
WEEKDAYS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")


def _jobs(user):
    from .views import _service_jobs_for_user

    return _service_jobs_for_user(user).exclude(status=ServiceJob.Status.ARCHIVED)


def todays_jobs(user):
    """Servicos marcados para hoje que ainda pedem acao."""
    return list(_jobs(user).filter(start_date=timezone.localdate(), status__in=ACTIVE)
                .order_by("planned_start_time", "created_at"))


def ensure_today_reminder(user):
    """Cria (uma vez por dia) o aviso no sininho com os servicos de hoje. Devolve os servicos."""
    from timeclock.models import InternalNotification
    from timeclock.notifications import create_internal_notification

    jobs = todays_jobs(user)
    if not jobs:
        return jobs
    today = timezone.localdate()
    title = f"Hoje ({today:%d/%m}) você tem {len(jobs)} {'serviço' if len(jobs) == 1 else 'serviços'}"
    if not InternalNotification.objects.filter(recipient_user=user, title__startswith=f"Hoje ({today:%d/%m})").exists():
        names = ", ".join(f"{j.planned_start_time:%H:%M} {j.title}" if j.planned_start_time else j.title for j in jobs[:5])
        create_internal_notification(
            notification_type=InternalNotification.NotificationType.SERVICE_REMINDER,
            title=title, message=f"Agenda de hoje: {names}.", recipient_user=user,
            target_url=reverse("service_agenda"),
        )
    return jobs


def _week_start(raw):
    try:
        day = date.fromisoformat((raw or "").strip())
    except ValueError:
        day = timezone.localdate()
    return day - timedelta(days=day.weekday())


@login_required
def service_agenda(request):
    start = _week_start(request.GET.get("semana"))
    end = start + timedelta(days=6)
    today = timezone.localdate()
    ensure_today_reminder(request.user)
    jobs = list(_jobs(request.user).filter(start_date__range=(start, end))
                .order_by("start_date", "planned_start_time", "created_at"))
    for job in jobs:
        job.status_label = status_label(job)
        job.status_tone = status_tone(job)
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        days.append({"date": day, "weekday": WEEKDAYS[offset], "is_today": day == today,
                     "jobs": [j for j in jobs if j.start_date == day]})
    undated = _jobs(request.user).filter(start_date__isnull=True, status__in=ACTIVE).count()
    return render(request, "services/agenda.html", {
        "days": days, "start": start, "end": end, "total": len(jobs), "undated": undated,
        "prev": (start - timedelta(days=7)).isoformat(), "next": (start + timedelta(days=7)).isoformat(),
        "is_current_week": start <= today <= end,
    })
