from dataclasses import dataclass

from django.urls import reverse

from .models import ServiceJob


@dataclass(frozen=True)
class ServiceAction:
    key: str
    label: str
    method: str = "get"
    url_name: str = ""
    post_action: str = ""
    anchor: str = ""
    external: bool = False

    def resolve_url(self, service):
        if self.anchor:
            return self.anchor
        if self.url_name:
            return reverse(self.url_name, args=[service.id])
        return reverse("service_job_detail", args=[service.id])


def has_minimum_service_data(service):
    has_client = bool(service.client_id or service.contract_id or service.manual_client_name)
    has_address = bool(service.service_location_summary or service.full_service_address)
    return bool(
        has_client
        and service.description
        and service.category_id
        and has_address
        and service.start_date
    )


def normalize_service_status(service):
    if service.status == ServiceJob.Status.SCHEDULED:
        return ServiceJob.Status.PLANNED
    return service.status


def status_label(service):
    labels = {
        ServiceJob.Status.DRAFT: "Rascunho",
        ServiceJob.Status.PLANNED: "Planejado",
        ServiceJob.Status.SENT: "Prévia enviada",
        ServiceJob.Status.SCHEDULED: "Planejado",
        ServiceJob.Status.IN_PROGRESS: "Em execução",
        ServiceJob.Status.FINISHED: "Finalizado",
        ServiceJob.Status.REPORT_SENT: "Relatório enviado",
        ServiceJob.Status.ARCHIVED: "Arquivado",
    }
    return labels.get(service.status, service.get_status_display())


def status_tone(service):
    status = normalize_service_status(service)
    if status == ServiceJob.Status.DRAFT:
        return "draft"
    if status in (ServiceJob.Status.PLANNED, ServiceJob.Status.SENT):
        return "planned"
    if status == ServiceJob.Status.IN_PROGRESS:
        return "progress"
    if status == ServiceJob.Status.FINISHED:
        return "finished"
    if status == ServiceJob.Status.REPORT_SENT:
        return "report"
    if status == ServiceJob.Status.ARCHIVED:
        return "archived"
    return "neutral"


def planned_status_for_service(service, *, requested_status=None):
    if requested_status == ServiceJob.Status.DRAFT:
        return ServiceJob.Status.DRAFT
    if service.status in (
        ServiceJob.Status.IN_PROGRESS,
        ServiceJob.Status.FINISHED,
        ServiceJob.Status.REPORT_SENT,
        ServiceJob.Status.ARCHIVED,
    ):
        return service.status
    if service.status == ServiceJob.Status.SENT:
        return ServiceJob.Status.SENT
    return ServiceJob.Status.PLANNED if has_minimum_service_data(service) else ServiceJob.Status.DRAFT


def get_next_service_action(service, *, open_work_log=None):
    if open_work_log is None:
        open_work_log = service.work_logs.filter(end_time__isnull=True).first()
    status = normalize_service_status(service)

    if status == ServiceJob.Status.DRAFT:
        primary = ServiceAction("complete", "Completar dados", "get", "service_job_update")
        secondary = [
            ServiceAction("edit", "Editar", "get", "service_job_update"),
            ServiceAction("archive", "Arquivar", "post", "service_job_status_action", "archive"),
        ]
    elif status == ServiceJob.Status.PLANNED:
        primary = ServiceAction("start", "Iniciar trabalho", "post", "service_clock_action", "start")
        secondary = [
            ServiceAction("manual_period", "Adicionar período manual", "get", anchor="#manual-period"),
            ServiceAction("send_preview", "Enviar prévia", "get", "service_job_preview_whatsapp", external=True),
            ServiceAction("add_item", "Adicionar item", "get", anchor="#items"),
            ServiceAction("quote", "Pedir cotação", "get", anchor="#quote"),
        ]
    elif status == ServiceJob.Status.SENT:
        primary = ServiceAction("start", "Iniciar trabalho", "post", "service_clock_action", "start")
        secondary = [
            ServiceAction("manual_period", "Adicionar período manual", "get", anchor="#manual-period"),
            ServiceAction("update_preview", "Atualizar prévia", "post", "service_job_preview_generate"),
            ServiceAction("quote", "Pedir cotação", "get", anchor="#quote"),
        ]
    elif status == ServiceJob.Status.IN_PROGRESS:
        if open_work_log:
            primary = ServiceAction("stop", "Encerrar período", "post", "service_clock_action", "stop")
        else:
            primary = ServiceAction("start", "Iniciar novo período", "post", "service_clock_action", "start")
        secondary = [
            ServiceAction("manual_period", "Adicionar período manual", "get", anchor="#manual-period"),
            ServiceAction("add_item", "Adicionar item", "get", anchor="#items"),
            ServiceAction("finish", "Finalizar serviço", "post", "service_job_status_action", "finish"),
        ]
    elif status == ServiceJob.Status.FINISHED:
        primary = ServiceAction("generate_report", "Gerar relatório", "post", "service_job_status_action", "generate_report")
        secondary = [
            ServiceAction("reopen", "Reabrir serviço", "post", "service_job_status_action", "reopen"),
            ServiceAction("summary", "Ver resumo", "get", anchor="#report"),
        ]
    elif status == ServiceJob.Status.REPORT_SENT:
        primary = ServiceAction("view_report", "Ver relatório", "get", "service_job_public_report_redirect", external=True)
        secondary = [
            ServiceAction("pdf", "PDF", "get", "service_job_report_pdf"),
            ServiceAction("whatsapp", "Enviar WhatsApp", "get", "service_job_report_whatsapp", external=True),
            ServiceAction("archive", "Arquivar", "post", "service_job_status_action", "archive"),
        ]
    elif status == ServiceJob.Status.ARCHIVED:
        primary = ServiceAction("restore", "Restaurar serviço", "post", "service_job_status_action", "restore")
        secondary = [ServiceAction("details", "Ver detalhes", "get", anchor="#details")]
    else:
        primary = ServiceAction("details", "Ver detalhes", "get", anchor="#details")
        secondary = []

    return {
        "status": status,
        "status_label": status_label(service),
        "status_tone": status_tone(service),
        "primary": primary,
        "secondary": secondary,
    }
