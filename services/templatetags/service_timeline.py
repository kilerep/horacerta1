from django import template

from services.models import ServiceJob


register = template.Library()


TIMELINE_STEPS = (
    ("draft", "Rascunho"),
    ("planned", "Planejado"),
    ("in_progress", "Em execução"),
    ("finished", "Finalizado"),
    ("report_sent", "Relatório enviado"),
)


STATUS_STAGE = {
    ServiceJob.Status.DRAFT: 0,
    ServiceJob.Status.PLANNED: 1,
    ServiceJob.Status.SCHEDULED: 1,
    ServiceJob.Status.SENT: 1,
    ServiceJob.Status.IN_PROGRESS: 2,
    ServiceJob.Status.FINISHED: 3,
    ServiceJob.Status.REPORT_SENT: 4,
}


def build_service_timeline(status):
    """Return a stable visual sequence using the service status already persisted."""
    current_index = STATUS_STAGE.get(status)
    archived = status == ServiceJob.Status.ARCHIVED
    steps = []
    for index, (key, label) in enumerate(TIMELINE_STEPS):
        if archived:
            state = "upcoming"
        elif index < current_index:
            state = "complete"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        steps.append({"key": key, "label": label, "state": state})
    return steps, archived


@register.inclusion_tag("services/service_timeline.html")
def service_timeline(job):
    steps, archived = build_service_timeline(job.status)
    return {
        "timeline_steps": steps,
        "timeline_archived": archived,
        "timeline_status_label": job.get_status_display(),
    }
