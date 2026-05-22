from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import InternalNotification, PunchCorrectionLog


def create_internal_notification(
    *,
    notification_type,
    title,
    message,
    actor_user=None,
    recipient_user=None,
    recipient_company=None,
    target_url="",
):
    if not recipient_user and not recipient_company:
        return None
    return InternalNotification.objects.create(
        recipient_user=recipient_user,
        recipient_company=recipient_company,
        actor_user=actor_user,
        notification_type=notification_type,
        title=title,
        message=message,
        target_url=target_url or "",
    )


def notify_internal_staff(*, notification_type, title, message, actor_user=None, target_url=""):
    User = get_user_model()
    staff_users = User.objects.filter(is_active=True).filter(is_staff=True) | User.objects.filter(
        is_active=True,
        is_superuser=True,
    )
    for user in staff_users.distinct():
        create_internal_notification(
            recipient_user=user,
            actor_user=actor_user,
            notification_type=notification_type,
            title=title,
            message=message,
            target_url=target_url,
        )


def _company_history_url(punch):
    day = timezone.localtime(punch.timestamp).date()
    return (
        f"{reverse('company_history')}?employee={punch.contract.employee_id}"
        f"&date_from={day:%Y-%m-%d}&date_to={day:%Y-%m-%d}"
    )


def _mei_history_url(punch):
    day = timezone.localtime(punch.timestamp).date()
    return f"{reverse('mei_history')}?date_from={day:%Y-%m-%d}&date_to={day:%Y-%m-%d}"


def notify_correction_request_created(correction_request):
    target_url = reverse("internal_correction_request_detail", args=[correction_request.id])
    employee_name = correction_request.employee.full_name
    company_name = correction_request.company.name
    problem_date = correction_request.problem_date.strftime("%d/%m/%Y")
    title = "Solicitacao de correcao de horario"
    message = f"{employee_name} reportou um problema em {problem_date} para {company_name}."
    create_internal_notification(
        recipient_company=correction_request.company,
        actor_user=correction_request.user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_CREATED,
        title=title,
        message=message,
        target_url=reverse("company_notifications"),
    )
    create_internal_notification(
        recipient_user=correction_request.user,
        actor_user=correction_request.user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_CREATED,
        title="Solicitacao enviada",
        message=f"Sua solicitacao sobre {problem_date} foi registrada para analise interna.",
        target_url=reverse("mei_notifications"),
    )
    notify_internal_staff(
        actor_user=correction_request.user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_CREATED,
        title=title,
        message=message,
        target_url=target_url,
    )


def notify_correction_request_status_changed(correction_request, *, actor_user, old_status):
    if old_status == correction_request.status:
        return
    status_label = correction_request.get_status_display()
    problem_date = correction_request.problem_date.strftime("%d/%m/%Y")
    title = "Solicitacao de correcao atualizada"
    message = f"A solicitacao de {problem_date} foi atualizada para {status_label}."
    create_internal_notification(
        recipient_user=correction_request.user,
        actor_user=actor_user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_STATUS_CHANGED,
        title=title,
        message=message,
        target_url=reverse("mei_notifications"),
    )
    create_internal_notification(
        recipient_company=correction_request.company,
        actor_user=actor_user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_STATUS_CHANGED,
        title=title,
        message=f"{correction_request.employee.full_name}: {message}",
        target_url=reverse("company_notifications"),
    )
    notify_internal_staff(
        actor_user=actor_user,
        notification_type=InternalNotification.NotificationType.CORRECTION_REQUEST_STATUS_CHANGED,
        title=title,
        message=f"{correction_request.employee.full_name}: {message}",
        target_url=reverse("internal_correction_request_detail", args=[correction_request.id]),
    )


def notify_punch_admin_action(punch, *, actor_user, action_type):
    type_map = {
        PunchCorrectionLog.ActionType.TIME_CHANGED: (
            InternalNotification.NotificationType.PUNCH_CORRECTED,
            "Horario corrigido",
            "Um horario foi corrigido pelo Painel Interno.",
        ),
        PunchCorrectionLog.ActionType.CANCELLED: (
            InternalNotification.NotificationType.PUNCH_CANCELLED,
            "Registro cancelado",
            "Um registro de ponto foi cancelado pelo Painel Interno.",
        ),
        PunchCorrectionLog.ActionType.RESTORED: (
            InternalNotification.NotificationType.PUNCH_RESTORED,
            "Registro restaurado",
            "Um registro de ponto foi restaurado pelo Painel Interno.",
        ),
        PunchCorrectionLog.ActionType.ADMIN_NOTE_ADDED: (
            InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
            "Observacao administrativa adicionada",
            "Uma observacao administrativa foi adicionada ao registro.",
        ),
    }
    notification_type, title, base_message = type_map[action_type]
    local_time = timezone.localtime(punch.timestamp).strftime("%d/%m/%Y %H:%M")
    message = f"{base_message} Horario relacionado: {local_time}."
    employee_user = punch.contract.employee.user
    create_internal_notification(
        recipient_user=employee_user,
        actor_user=actor_user,
        notification_type=notification_type,
        title=title,
        message=message,
        target_url=_mei_history_url(punch),
    )
    create_internal_notification(
        recipient_company=punch.contract.company,
        actor_user=actor_user,
        notification_type=notification_type,
        title=title,
        message=f"{punch.contract.employee.full_name}: {message}",
        target_url=_company_history_url(punch),
    )
    notify_internal_staff(
        actor_user=actor_user,
        notification_type=notification_type,
        title=title,
        message=f"{punch.contract.employee.full_name} / {punch.contract.company.name}: {message}",
        target_url=reverse("internal_punch_detail", args=[punch.id]),
    )


def acknowledge_company_notification(notification, *, actor_user):
    now = timezone.now()
    notification.company_acknowledged = True
    notification.company_acknowledged_at = now
    notification.company_acknowledged_by = actor_user
    notification.is_read = True
    notification.read_at = notification.read_at or now
    notification.save(
        update_fields=[
            "company_acknowledged",
            "company_acknowledged_at",
            "company_acknowledged_by",
            "is_read",
            "read_at",
        ]
    )
    return notify_internal_staff(
        actor_user=actor_user,
        notification_type=InternalNotification.NotificationType.COMPANY_ACKNOWLEDGED,
        title="Empresa marcou ciencia",
        message=(
            f"{actor_user.get_full_name() or actor_user.email or actor_user.username} "
            f"marcou ciencia: {notification.title}."
        ),
        target_url=reverse("internal_notifications"),
    )
