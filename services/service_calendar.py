from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .models import ServiceJob


def _escape_ics(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _event_dates(job):
    if not job.start_date:
        return None

    end_date = job.end_date or job.start_date
    if not job.planned_start_time:
        return {
            "all_day": True,
            "start": job.start_date.strftime("%Y%m%d"),
            "end": (end_date + timedelta(days=1)).strftime("%Y%m%d"),
        }

    start_dt = datetime.combine(job.start_date, job.planned_start_time)
    if job.planned_end_time:
        end_dt = datetime.combine(end_date, job.planned_end_time)
    elif end_date > job.start_date:
        end_dt = datetime.combine(end_date, job.planned_start_time)
    else:
        end_dt = start_dt + timedelta(hours=1)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    return {
        "all_day": False,
        "start": start_dt.strftime("%Y%m%dT%H%M%S"),
        "end": end_dt.strftime("%Y%m%dT%H%M%S"),
    }


def build_service_calendar(job, detail_url):
    event_dates = _event_dates(job)
    if event_dates is None:
        return None

    location = job.full_service_address or job.service_location_summary or ""
    description_parts = [
        job.description or "Serviço registrado no HoraCerta.",
        f"Cliente: {job.client_display_name}",
        f"Status: {job.get_status_display()}",
        f"Detalhes internos: {detail_url}",
    ]
    if job.notes:
        description_parts.append(f"Observações: {job.notes}")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HoraCerta//Servicos//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:service-{job.id}@horacerta",
        f"DTSTAMP:{timezone.now().astimezone(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    ]

    if event_dates["all_day"]:
        lines.extend(
            [
                f"DTSTART;VALUE=DATE:{event_dates['start']}",
                f"DTEND;VALUE=DATE:{event_dates['end']}",
            ]
        )
    else:
        tzid = _escape_ics(getattr(settings, "TIME_ZONE", "America/Sao_Paulo"))
        lines.extend(
            [
                f"DTSTART;TZID={tzid}:{event_dates['start']}",
                f"DTEND;TZID={tzid}:{event_dates['end']}",
            ]
        )

    lines.extend(
        [
            f"SUMMARY:{_escape_ics(job.title)}",
            f"DESCRIPTION:{_escape_ics(chr(10).join(description_parts))}",
            f"LOCATION:{_escape_ics(location)}",
            f"URL:{_escape_ics(detail_url)}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )
    return "\r\n".join(lines) + "\r\n"


@login_required
def service_job_calendar_ics(request, job_id):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "category", "client", "contract"),
        id=job_id,
        professional=request.user,
    )
    detail_url = request.build_absolute_uri(reverse("service_job_detail", args=[job.id]))
    content = build_service_calendar(job, detail_url)
    if content is None:
        messages.error(request, "Informe a data prevista antes de adicionar o serviço ao calendário.")
        return redirect("service_job_detail", job_id=job.id)

    filename = slugify(job.title) or "servico"
    response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.ics"'
    response["Cache-Control"] = "private, no-store"
    return response
