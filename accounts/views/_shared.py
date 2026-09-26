from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO
from urllib.parse import quote, urlencode, urlparse
from xml.sax.saxutils import escape
import zipfile
import csv
import re
from calendar import monthrange
from collections import defaultdict
import json
from uuid import UUID

from django.conf import settings

from accounts.analytics import (  # noqa: F401
    CLIENT_CREATED,
    REPORT_GENERATED,
    REPORT_PUBLIC_VIEWED,
    SIGNUP_COMPLETED,
    track,
)
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Q
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from companies.models import (
    Company,
    CompanyAttendancePolicy,
    CompanyAuthorizedLocation,
    CompanySubscription,
    Employee,
    EmployeeRelationshipAuditLog,
    InternalAdminActionLog,
)
from timeclock.models import (
    ActivityReportRequest,
    Contract,
    InternalNotification,
    Punch,
    PunchCorrectionLog,
    PunchCorrectionRequest,
    ServiceReport,
    WorkdayChangeLog,
)
from timeclock.notifications import (
    acknowledge_company_notification,
    create_internal_notification,
    notify_correction_request_created,
    notify_correction_request_status_changed,
    notify_punch_admin_action,
)
from timeclock.services import (
    add_punch_admin_note,
    build_daily_summary,
    cancel_punch,
    change_punch_time,
    compute_day_total,
    filter_punches_by_period,
    format_hhmm,
    report_locks_day,
    restore_punch,
)
from timeclock.state import (
    contract_is_operational,
    contract_operational_q,
    employee_lifecycle_summary,
    PROFESSIONAL_STATE_AGUARDANDO,
    PROFESSIONAL_STATE_ATIVO,
    PROFESSIONAL_STATE_CADASTRADO,
    PROFESSIONAL_STATE_INATIVO,
)
from services.models import ServiceJob, ServiceRequest

from ..forms import (
    CompanyAttendancePolicyForm,
    CompanyAuthorizedLocationForm,
    CompanyActivityReportRequestForm,
    CompanyContractForm,
    CompanyMEICreateForm,
    MEIClientForm,
    CompanyProfileForm,
    PunchCorrectionRequestForm,
    EmployeeSearchForm,
    LoginForm,
    ServiceReportCreateForm,
    MEIProfileForm,
    PeriodSearchForm,
    MEISignupForm,
    UnifiedSignupForm,
    UserThemeForm,
)
from ..mei_context import mei_contracts_for_user, resolve_mei_context
from ..permissions import can_access_internal_dashboard

User = get_user_model()
REVIEW_CONFIDENCE_STATUSES = {
    Punch.ConfidenceStatus.OUT_OF_RADIUS,
    Punch.ConfidenceStatus.NO_LOCATION,
    Punch.ConfidenceStatus.IMPRECISE,
}


class RenderAwarePasswordResetView(auth_views.PasswordResetView):
    """Use APP_BASE_URL when defined so reset links always use the public domain."""

    def form_valid(self, form):
        opts = {
            "use_https": self.request.is_secure(),
            "token_generator": self.token_generator,
            "from_email": self.from_email,
            "email_template_name": self.email_template_name,
            "subject_template_name": self.subject_template_name,
            "request": self.request,
            "html_email_template_name": self.html_email_template_name,
            "extra_email_context": self.extra_email_context,
        }

        app_base_url = (self.request.META.get("APP_BASE_URL") or "").strip()
        if not app_base_url:
            from django.conf import settings

            app_base_url = getattr(settings, "APP_BASE_URL", "").strip()

        if app_base_url:
            parsed = urlparse(app_base_url)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                opts["use_https"] = parsed.scheme == "https"
                opts["domain_override"] = parsed.netloc

        form.save(**opts)
        return super(auth_views.PasswordResetView, self).form_valid(form)


def _company_for_user(user):
    return Company.objects.filter(owner=user).first()


def _pending_reports_count_for_company(company):
    if not company:
        return 0
    return ActivityReportRequest.objects.filter(company=company, status=ActivityReportRequest.Status.PENDING).count()


def _contract_mei_label(contract):
    employee = getattr(contract, "employee", None)
    if not employee:
        return "MEI indisponivel"

    full_name = (getattr(employee, "full_name", "") or "").strip()
    if full_name:
        return full_name

    user = getattr(employee, "user", None)
    if user:
        email = (getattr(user, "email", "") or "").strip()
        if email:
            return email
        username = (getattr(user, "username", "") or "").strip()
        if username:
            return username

    return "MEI indisponivel"


def _count_inconsistency_days(punches):
    grouped = {}
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        key = (punch.contract_id, local_ts.date())
        grouped.setdefault(key, []).append(local_ts)

    total_inconsistent = 0
    for times in grouped.values():
        _seconds, is_incomplete = compute_day_total(times)
        if is_incomplete:
            total_inconsistent += 1
    return total_inconsistent


def _contracts_by_employee(company, employees):
    employee_ids = [employee.id for employee in employees]
    if not company or not employee_ids:
        return {}

    contract_list = list(
        Contract.objects.filter(
            company=company,
            employee_id__in=employee_ids,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .select_related("employee", "employee__user", "company")
        .order_by("-start_date", "-created_at")
    )
    by_employee = defaultdict(list)
    for contract in contract_list:
        by_employee[contract.employee_id].append(contract)
    return by_employee


def _redirect_for_role(user):
    if user.role == User.Role.EMPRESA:
        return redirect("dashboard_empresa")
    if user.role == User.Role.FUNCIONARIO:
        return redirect("employee_dashboard")
    return redirect("dashboard")


def _redirect_if_not_empresa(request):
    if request.user.role != User.Role.EMPRESA:
        return redirect("dashboard")
    return None


def _can_access_internal_dashboard(user):
    return can_access_internal_dashboard(user)


def internal_staff_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _can_access_internal_dashboard(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def _usage_status_for_company(punch_count, punch_count_last_30_days):
    if punch_count == 0:
        return {"label": "sem uso", "tone": "warn"}
    if punch_count_last_30_days >= 10:
        return {"label": "ativo", "tone": "success"}
    return {"label": "pouco uso", "tone": "pending"}


def _employee_status_for_backoffice(employee, active_contract_count=0):
    if not employee.is_active:
        if getattr(employee, "ended_at", None):
            return {"label": "encerrado", "tone": "warn", "key": "encerrado"}
        return {"label": "pendente", "tone": "pending", "key": "pendente"}
    if active_contract_count:
        return {"label": "ativo", "tone": "success", "key": "ativo"}
    return {"label": "inativo", "tone": "warn", "key": "inativo"}


def _company_usage_queryset(last_30_days_start):
    return Company.objects.annotate(
        employee_count=Count("employees", distinct=True),
        active_employee_count=Count("employees", filter=Q(employees__is_active=True), distinct=True),
        punch_count=Count("contracts__punches", filter=Q(contracts__punches__is_cancelled=False), distinct=True),
        punch_count_last_30_days=Count(
            "contracts__punches",
            filter=Q(contracts__punches__timestamp__gte=last_30_days_start, contracts__punches__is_cancelled=False),
            distinct=True,
        ),
        last_punch_at=Max("contracts__punches__timestamp", filter=Q(contracts__punches__is_cancelled=False)),
    )


def _build_company_usage_rows(companies):
    rows = []
    for company in companies:
        rows.append(
            {
                "company": company,
                "employee_count": company.employee_count,
                "active_employee_count": getattr(company, "active_employee_count", 0),
                "punch_count": company.punch_count,
                "punch_count_last_30_days": getattr(company, "punch_count_last_30_days", 0),
                "last_punch_at": company.last_punch_at,
                "status": _usage_status_for_company(company.punch_count, company.punch_count_last_30_days),
            }
        )
    return rows


def _punch_status_label(punch):
    if getattr(punch, "is_cancelled", False):
        return {"label": "cancelado", "tone": "warn"}
    return {"label": "ativo", "tone": "success"}


def _correction_request_status_tone(status):
    if status == PunchCorrectionRequest.Status.CORRECTED:
        return "success"
    if status == PunchCorrectionRequest.Status.REJECTED:
        return "warn"
    if status == PunchCorrectionRequest.Status.IN_REVIEW:
        return "pending"
    return ""


def _notification_tone(notification):
    if notification.company_acknowledged:
        return "success"
    if not notification.is_read:
        return "warn"
    return "neutral"


def _mark_notification_read(notification):
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])


def _company_ack_allowed(notification):
    return notification.notification_type in {
        InternalNotification.NotificationType.CORRECTION_REQUEST_CREATED,
        InternalNotification.NotificationType.CORRECTION_REQUEST_STATUS_CHANGED,
        InternalNotification.NotificationType.PUNCH_CORRECTED,
        InternalNotification.NotificationType.PUNCH_CANCELLED,
        InternalNotification.NotificationType.PUNCH_RESTORED,
        InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
    }


def _require_admin_reason(raw_reason):
    reason = (raw_reason or "").strip()
    if not reason:
        raise ValueError("Informe uma justificativa para registrar a auditoria.")
    return reason


AUDIT_ACTION_CHOICES = [
    ("time_changed", "Correcao de horario"),
    ("cancelled", "Cancelamento de registro"),
    ("restored", "Restauracao de registro"),
    ("admin_note_added", "Observacao administrativa"),
    ("relationship_ended", "Encerramento de contrato"),
    ("deactivate_company", "Desativacao de empresa"),
    ("activate_company", "Reativacao de empresa"),
    ("deactivate_user", "Desativacao de usuario"),
    ("activate_user", "Reativacao de usuario"),
    ("company_acknowledged", "Ciencia marcada pela empresa"),
    ("correction_request_status_changed", "Status de solicitacao alterado"),
]


def _audit_badge_tone(action_type):
    if action_type in {"time_changed", "restored", "activate_company", "activate_user", "company_acknowledged"}:
        return "success"
    if action_type in {"cancelled", "deactivate_company", "deactivate_user", "relationship_ended"}:
        return "warn"
    return "pending"


def _audit_action_label(action_type):
    return dict(AUDIT_ACTION_CHOICES).get(action_type, action_type)


def _audit_date_bounds(request):
    date_from = _parse_iso_date(request.GET.get("date_from"))
    date_to = _parse_iso_date(request.GET.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    start_dt = timezone.make_aware(datetime.combine(date_from, time.min)) if date_from else None
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max)) if date_to else None
    return date_from, date_to, start_dt, end_dt


def _apply_datetime_bounds(queryset, field_name, start_dt, end_dt):
    if start_dt:
        queryset = queryset.filter(**{f"{field_name}__gte": start_dt})
    if end_dt:
        queryset = queryset.filter(**{f"{field_name}__lte": end_dt})
    return queryset


def _audit_row(*, created_at, actor, action_type, company=None, employee=None, old_value="", new_value="", reason="", target_url=""):
    return {
        "created_at": created_at,
        "actor": actor,
        "action_type": action_type,
        "action_label": _audit_action_label(action_type),
        "tone": _audit_badge_tone(action_type),
        "company": company,
        "employee": employee,
        "old_value": old_value or "-",
        "new_value": new_value or "-",
        "reason": reason or "-",
        "target_url": target_url or "",
    }


def _log_internal_admin_action(*, admin_user, action, target_type, target_id, description=""):
    return InternalAdminActionLog.objects.create(
        admin_user=admin_user,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        description=(description or "").strip(),
    )


def _end_employee_company_relationship(*, employee, admin_user, reason):
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("Informe o motivo para encerrar o contrato.")
    now = timezone.now()
    today = timezone.localdate()
    with transaction.atomic():
        employee.is_active = False
        employee.ended_at = now
        employee.ended_by = admin_user
        employee.end_reason = clean_reason
        employee.save(update_fields=["is_active", "ended_at", "ended_by", "end_reason"])
        Contract.objects.filter(employee=employee, company=employee.company, is_active=True).update(
            is_active=False,
            end_date=today,
        )
        EmployeeRelationshipAuditLog.objects.create(
            admin_user=admin_user,
            employee=employee,
            company=employee.company,
            action_type=EmployeeRelationshipAuditLog.ActionType.RELATIONSHIP_ENDED,
            reason=clean_reason,
        )
        _log_internal_admin_action(
            admin_user=admin_user,
            action="relationship_ended",
            target_type="employee",
            target_id=employee.id,
            description=f"Contrato encerrado com {employee.company.name}. Motivo: {clean_reason}",
        )
        _log_internal_admin_action(
            admin_user=admin_user,
            action="relationship_ended",
            target_type="company",
            target_id=employee.company_id,
            description=f"Contrato encerrado com {employee.full_name}. Motivo: {clean_reason}",
        )


def _recent_30_day_summary_for_employee(employee):
    start = timezone.now() - timedelta(days=30)
    punches = list(
        Punch.objects.filter(contract__employee=employee, timestamp__gte=start)
        .select_related("contract", "contract__company")
        .order_by("timestamp")
    )
    grouped = defaultdict(list)
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        grouped[local_ts.date()].append(local_ts)

    total_seconds = 0
    incomplete_days = 0
    for day_punches in grouped.values():
        day_seconds, is_incomplete = compute_day_total(day_punches)
        total_seconds += day_seconds
        if is_incomplete:
            incomplete_days += 1

    return {
        "days_with_records": len(grouped),
        "punch_count": len(punches),
        "total_hours": format_hhmm(total_seconds),
        "incomplete_days": incomplete_days,
    }


def _subscription_status_badge(subscription, at_time=None):
    at = at_time or timezone.now()
    if not subscription:
        return {
            "label": "Suspenso",
            "tone": "warn",
            "hint": "Plano ainda não configurado para esta empresa.",
        }

    status = subscription.status
    is_access_active = subscription.is_access_active(at)
    trial_has_ended = bool(subscription.trial_ends_at and at > subscription.trial_ends_at)

    if status == CompanySubscription.Status.TRIAL:
        if trial_has_ended or not is_access_active:
            label = "Vencido"
            tone = "warn"
            hint = "Teste grátis encerrado."
        else:
            label = "Em teste"
            tone = "pending"
            hint = "Período de teste grátis ativo."
    elif status == CompanySubscription.Status.ACTIVE:
        if is_access_active:
            label = "Ativo"
            tone = "success"
            hint = "Plano ativo e apto para uso."
        else:
            label = "Vencido"
            tone = "warn"
            hint = "Plano vencido para o período atual."
    elif status == CompanySubscription.Status.PAST_DUE:
        label = "Suspenso"
        tone = "warn"
        hint = "Regularização comercial pendente."
    elif status == CompanySubscription.Status.CANCELED:
        label = "Cancelado"
        tone = "warn"
        hint = "Assinatura cancelada."
    elif status == CompanySubscription.Status.EXPIRED:
        label = "Vencido"
        tone = "warn"
        hint = "Plano vencido."
    else:
        label = "Status não mapeado"
        tone = "warn"
        hint = "Status de assinatura não mapeado."

    return {
        "label": label,
        "tone": tone,
        "hint": hint,
    }


def _commercial_plan_snapshot(subscription):
    return {
        "name": "HoraCerta Essencial",
        "monthly_price": "R$ 79,00",
        "active_provider_limit": 10,
        "description": (
            "Sua empresa possui acesso aos recursos essenciais para acompanhar prestadores, contratos, "
            "registros de horário, histórico, conferência, notificações e relatórios."
        ),
    }


def _redirect_if_not_mei(request):
    if request.user.role != User.Role.FUNCIONARIO:
        return redirect("dashboard")
    return None


def _employee_activation_summary(employee):
    user = getattr(employee, "user", None)
    if not getattr(employee, "is_active", True) or not getattr(user, "is_active", True):
        return {
            "key": "inactive",
            "label": "Inativo/desativado",
            "hint": "Acesso bloqueado para login e operacao do profissional.",
            "tone": "warn",
        }

    if user and user.last_login:
        last_login_local = timezone.localtime(user.last_login)
        return {
            "key": "active",
            "label": "Ativo",
            "hint": f"Acesso ativado. Ultimo login em {last_login_local.strftime('%d/%m/%Y %H:%M')}.",
            "tone": "success",
        }

    return {
        "key": "pending",
        "label": "Pendente de ativacao",
        "hint": "Aguardando primeiro acesso do profissional.",
        "tone": "pending",
    }


def _safe_redirect_target(request, fallback_url):
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _parse_iso_date(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_year_month(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        return None
    return parsed.replace(day=1)


def _excel_col_name(index):
    name = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _build_xlsx_response(filename, headers, rows):
    def make_cell(col_idx, row_idx, value):
        ref = f"{_excel_col_name(col_idx)}{row_idx}"
        if isinstance(value, (int, float, Decimal)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        text = escape(str(value) if value is not None else "")
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    sheet_rows = []
    all_rows = [headers] + rows
    for r_idx, row in enumerate(all_rows, start=1):
        cells = "".join(make_cell(c_idx, r_idx, val) for c_idx, val in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{r_idx}">{cells}</row>')
    sheet_xml_rows = "".join(sheet_rows)

    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Relatorio" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/worksheets/sheet1.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{sheet_xml_rows}</sheetData>
</worksheet>""",
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buffer.seek(0)

    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _build_pdf_response(filename, lines):
    def esc(text):
        return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = ["BT", "/F1 11 Tf", "40 800 Td"]
    first = True
    for line in lines[:55]:
        if first:
            content_lines.append(f"({esc(line)}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({esc(line)}) Tj")
    content_lines.append("ET")
    stream_data = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n")
    objects.append(f"4 0 obj << /Length {len(stream_data)} >> stream\n".encode("ascii") + stream_data + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        pdf += f"{off:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode("ascii")

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _compute_report_metrics(punches):
    grouped = {}
    rates_by_contract = {}
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        key = (punch.contract_id, local_ts.date())
        grouped.setdefault(key, []).append(local_ts)
        rates_by_contract[punch.contract_id] = punch.contract.hourly_rate

    total_seconds = 0
    estimated_payment = Decimal("0")
    for (contract_id, _day), times in grouped.items():
        day_seconds, _is_incomplete = compute_day_total(times)
        hourly_rate = rates_by_contract.get(contract_id, Decimal("0"))
        total_seconds += day_seconds
        estimated_payment += (Decimal(day_seconds) / Decimal("3600")) * hourly_rate

    return {
        "total_punches": len(punches),
        "total_seconds": total_seconds,
        "total_hours_hhmm": format_hhmm(total_seconds),
        "estimated_payment": estimated_payment.quantize(Decimal("0.01")),
    }


def _is_pending_review_punch(punch):
    return (
        punch.confidence_status in REVIEW_CONFIDENCE_STATUSES
        or punch.qr_confirmation_status == Punch.QrConfirmationStatus.REQUIRED_MISSING
    )


def _compute_validation_quality_metrics(punches):
    total_punches = len(punches)
    validated_on_site = sum(1 for punch in punches if punch.confidence_status == Punch.ConfidenceStatus.ON_SITE)
    qr_confirmed = sum(1 for punch in punches if punch.qr_confirmation_status == Punch.QrConfirmationStatus.CONFIRMED)
    out_of_radius = sum(1 for punch in punches if punch.confidence_status == Punch.ConfidenceStatus.OUT_OF_RADIUS)
    no_location = sum(1 for punch in punches if punch.confidence_status == Punch.ConfidenceStatus.NO_LOCATION)
    pending_review = sum(1 for punch in punches if _is_pending_review_punch(punch))
    return {
        "total_punches": total_punches,
        "validated_on_site": validated_on_site,
        "qr_confirmed": qr_confirmed,
        "out_of_radius": out_of_radius,
        "no_location": no_location,
        "pending_review": pending_review,
    }


def _month_label_ptbr(date_obj):
    month_names = [
        "janeiro",
        "fevereiro",
        "marco",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    return f"{month_names[date_obj.month - 1].capitalize()} de {date_obj.year}"


def _format_brl(value):
    brl = f"{(value or Decimal('0')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {brl}"


def _contract_status_for_mei(contract):
    today = timezone.localdate()
    if contract_is_operational(contract, on_date=today):
        return {"label": "Ativo", "tone": "success"}
    if contract.is_active and contract.start_date and contract.start_date > today:
        return {"label": "Agendado", "tone": "pending"}
    if not contract.is_active:
        return {"label": "Pausado", "tone": "muted"}
    if contract.end_date and contract.end_date < today:
        return {"label": "Encerrado", "tone": "warn"}
    return {"label": "Inativo", "tone": "muted"}


def _build_service_report_payload(contract, date_from, date_to):
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    punches = list(
        Punch.objects.filter(contract=contract, timestamp__range=(start_dt, end_dt))
        .select_related("validated_location", "qr_confirmed_location")
        .order_by("timestamp")
    )
    punches_by_day = defaultdict(list)
    for punch in punches:
        punches_by_day[timezone.localtime(punch.timestamp, tz).date()].append(punch)

    days = []
    total_seconds = 0
    manual_count = 0
    located_count = 0
    incomplete_days = 0
    observations = []
    current_day = date_from
    while current_day <= date_to:
        day_punches = sorted(punches_by_day.get(current_day, []), key=lambda item: item.timestamp)
        local_datetimes = [timezone.localtime(item.timestamp, tz) for item in day_punches]
        day_seconds, is_incomplete = compute_day_total(local_datetimes)
        day_manual_count = sum(1 for item in day_punches if item.is_manual)
        day_location_count = sum(
            1
            for item in day_punches
            if item.geo_latitude is not None
            or item.geo_longitude is not None
            or item.validated_location_id
            or item.qr_confirmed_location_id
        )
        day_notes = [item.note for item in day_punches if (item.note or "").strip()]
        manual_count += day_manual_count
        located_count += day_location_count
        total_seconds += day_seconds
        if is_incomplete:
            incomplete_days += 1
        observations.extend(day_notes)
        days.append(
            {
                "date": current_day.isoformat(),
                "date_label": current_day.strftime("%d/%m/%Y"),
                "punch_times": [item.strftime("%H:%M") for item in local_datetimes],
                "total_hours": format_hhmm(day_seconds),
                "is_incomplete": is_incomplete,
                "manual_count": day_manual_count,
                "location_count": day_location_count,
                "notes": day_notes,
            }
        )
        current_day += timedelta(days=1)

    hourly_rate = contract.hourly_rate or Decimal("0")
    estimated_value = ((Decimal(total_seconds) / Decimal("3600")) * hourly_rate).quantize(Decimal("0.01"))
    return {
        "professional": contract.employee.full_name or contract.employee.user.email or contract.employee.user.username,
        "company": contract.company.name,
        "contract_id": str(contract.id),
        "employee_id": str(contract.employee_id),
        "company_id": str(contract.company_id),
        "period": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "label": f"{date_from:%d/%m/%Y} ate {date_to:%d/%m/%Y}",
        },
        "days": days,
        "total_hours": format_hhmm(total_seconds),
        "total_seconds": total_seconds,
        "hourly_rate": str(hourly_rate),
        "estimated_value": str(estimated_value),
        "estimated_value_brl": _format_brl(estimated_value),
        "manual_count": manual_count,
        "location_count": located_count,
        "incomplete_days": incomplete_days,
        "observations": observations,
    }


def _suggest_closure_period(contract, today=None):
    today = today or timezone.localdate()
    closure_type = getattr(contract, "closure_type", Contract.ClosureType.MONTHLY)
    if closure_type == Contract.ClosureType.WEEKLY:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif closure_type == Contract.ClosureType.BIWEEKLY:
        if today.day <= 15:
            start = today.replace(day=1)
            end = today.replace(day=15)
        else:
            last_day = monthrange(today.year, today.month)[1]
            start = today.replace(day=16)
            end = today.replace(day=last_day)
    else:
        start = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day)
    return start, end


def _compute_contract_period_totals(contract, date_from, date_to):
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    punches = list(Punch.objects.filter(contract=contract, timestamp__range=(start_dt, end_dt)).order_by("timestamp"))
    daily_rows, _max_cols = build_daily_summary(punches, min_punch_columns=4)
    total_seconds = sum(row["total_seconds"] for row in daily_rows)
    estimated_value = ((Decimal(total_seconds) / Decimal("3600")) * (contract.hourly_rate or Decimal("0"))).quantize(
        Decimal("0.01")
    )
    return {
        "total_seconds": total_seconds,
        "total_hours": format_hhmm(total_seconds),
        "estimated_value": estimated_value,
        "estimated_value_brl": _format_brl(estimated_value),
    }


def _service_report_period_display(report):
    payload = report.summary_payload or {}
    period_label = (payload.get("period") or {}).get("label")
    if period_label:
        return period_label
    start_label = report.date_from.strftime("%d/%m/%Y") if report.date_from else "-"
    end_label = report.date_to.strftime("%d/%m/%Y") if report.date_to else "-"
    return f"{start_label} ate {end_label}"


def _notification_card(
    *,
    title,
    message,
    category="Sistema",
    priority="normal",
    created_at=None,
    client_name="",
    action_label="",
    action_url="",
    is_read=True,
    notification=None,
    source="dynamic",
):
    return {
        "title": title,
        "message": message,
        "category": category,
        "priority": priority,
        "created_at": created_at,
        "client_name": client_name,
        "action_label": action_label,
        "action_url": action_url,
        "is_read": is_read,
        "notification": notification,
        "source": source,
    }


def _notification_category_for_title(title):
    title = (title or "").lower()
    if "relatorio" in title or "recebimento" in title or "periodo fechado" in title:
        return "Relatorios"
    if "fechamento" in title:
        return "Fechamentos"
    if "incompleto" in title or "valor/hora" in title:
        return "Pendencias"
    return "Sistema"


def _notification_action_label(title, target_url):
    title = (title or "").lower()
    if not target_url:
        return ""
    if "dia incompleto" in title:
        return "Revisar horario"
    if "valor/hora" in title:
        return "Editar cliente"
    if "fechamento" in title:
        return "Gerar relatorio"
    if "relatorio" in title or "periodo fechado" in title or "recebimento" in title:
        return "Ver relatorio"
    return "Abrir"


def _persistent_notification_exists(*, user, title, target_url):
    return InternalNotification.objects.filter(
        recipient_user=user,
        audience=InternalNotification.Audience.MEI,
        title=title,
        target_url=target_url or "",
    ).exists()


def _create_mei_report_notification(*, report, title, message, target_url):
    user = getattr(getattr(report, "employee", None), "user", None)
    if not user or _persistent_notification_exists(user=user, title=title, target_url=target_url):
        return None
    return create_internal_notification(
        recipient_user=user,
        audience=InternalNotification.Audience.MEI,
        notification_type=InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
        title=title,
        message=message,
        target_url=target_url,
    )


def _notify_service_report_created(report):
    if not report.pk:
        return None
    period_label = _service_report_period_display(report)
    company_name = getattr(getattr(report, "company", None), "name", "cliente")
    return _create_mei_report_notification(
        report=report,
        title="Periodo fechado",
        message=(
            f"O relatorio da {company_name} foi gerado. "
            f"Os dias de {period_label} foram bloqueados para preservar o fechamento."
        ),
        target_url=reverse("mei_service_report_detail", args=[report.id]),
    )


def _notify_service_report_viewed(report, viewed_at=None):
    if not report.pk:
        return None
    viewed_at = viewed_at or report.conference_first_viewed_at or timezone.now()
    company_name = getattr(getattr(report, "company", None), "name", "cliente")
    local_viewed_at = timezone.localtime(viewed_at).strftime("%d/%m/%Y %H:%M")
    return _create_mei_report_notification(
        report=report,
        title="Relatorio visualizado",
        message=f"O relatorio da {company_name} foi aberto pelo cliente em {local_viewed_at}.",
        target_url=reverse("mei_service_report_detail", args=[report.id]),
    )


def _build_mei_dynamic_notifications(user):
    today = timezone.localdate()
    recent_start = today - timedelta(days=6)
    recent_start_dt = timezone.make_aware(datetime.combine(recent_start, time.min))
    today_end_dt = timezone.make_aware(datetime.combine(today, time.max))
    contracts = list(
        mei_contracts_for_user(user, include_inactive_contracts=False)
        .select_related("company", "employee", "employee__user")
        .order_by("company__name")
    )
    contract_ids = [contract.id for contract in contracts]
    cards = []
    if contract_ids:
        punches = (
            Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(recent_start_dt, today_end_dt))
            .select_related("contract", "contract__company")
            .order_by("timestamp")
        )
        punches_by_contract_day = defaultdict(list)
        for punch in punches:
            punches_by_contract_day[(punch.contract_id, timezone.localtime(punch.timestamp).date())].append(punch)
        for contract in contracts:
            company_name = contract.company.name
            today_punches = punches_by_contract_day.get((contract.id, today), [])
            if today_punches and len(today_punches) % 2 == 1:
                cards.append(
                    _notification_card(
                        title="Dia incompleto",
                        message=(
                            f"Voce registrou {len(today_punches)} horarios hoje na {company_name}. "
                            "Confira antes de gerar relatorio."
                        ),
                        category="Pendencias",
                        priority="high",
                        created_at=timezone.now(),
                        client_name=company_name,
                        action_label="Revisar horario",
                        action_url=f"{reverse('mei_edit_today_punches')}?contract={contract.id}",
                    )
                )
                continue
            for offset in range(1, 7):
                day = today - timedelta(days=offset)
                day_punches = punches_by_contract_day.get((contract.id, day), [])
                if day_punches and len(day_punches) % 2 == 1:
                    cards.append(
                        _notification_card(
                            title="Dia incompleto",
                            message=(
                                f"Voce registrou {len(day_punches)} horarios em {day:%d/%m/%Y} na {company_name}. "
                                "Confira para evitar relatorio com erro."
                            ),
                            category="Pendencias",
                            priority="high",
                            client_name=company_name,
                            action_label="Revisar horario",
                            action_url=f"{reverse('mei_history')}?contract={contract.id}&date_from={day:%Y-%m-%d}&date_to={day:%Y-%m-%d}",
                        )
                    )
                    break

            if not contract.hourly_rate or contract.hourly_rate <= Decimal("0"):
                cards.append(
                    _notification_card(
                        title="Cliente sem valor/hora",
                        message=(
                            f"O cliente {company_name} esta sem valor/hora definido. "
                            "O valor estimado pode ficar zerado no relatorio."
                        ),
                        category="Pendencias",
                        priority="high",
                        client_name=company_name,
                        action_label="Editar cliente",
                        action_url=reverse("mei_client_edit", args=[contract.id]),
                    )
                )

            if contract.closure_type != Contract.ClosureType.CUSTOM:
                close_from, close_to = _suggest_closure_period(contract, today)
                days_until_close = (close_to - today).days
                closure_window_days = 6 if contract.closure_type == Contract.ClosureType.WEEKLY else 2
                if 0 <= days_until_close <= closure_window_days or today >= close_to:
                    query = urlencode(
                        {
                            "contract": str(contract.id),
                            "date_from": close_from.isoformat(),
                            "date_to": close_to.isoformat(),
                        }
                    )
                    cards.append(
                        _notification_card(
                            title="Fechamento proximo",
                            message=(
                                f"O fechamento da {company_name} esta no periodo de "
                                f"{close_from:%d/%m/%Y} ate {close_to:%d/%m/%Y}. "
                                "Voce ja pode revisar as horas e gerar o relatorio."
                            ),
                            category="Fechamentos",
                            priority="normal",
                            client_name=company_name,
                            action_label="Gerar relatorio",
                            action_url=f"{reverse('mei_reports')}?{query}",
                        )
                    )

    viewed_pending_reports = (
        ServiceReport.objects.filter(
            employee__user=user,
            conference_first_viewed_at__isnull=False,
            payment_status=ServiceReport.PaymentStatus.PENDING,
        )
        .select_related("company")
        .order_by("-conference_first_viewed_at")[:5]
    )
    for report in viewed_pending_reports:
        company_name = report.company.name
        cards.append(
            _notification_card(
                title="Recebimento pendente",
                message=(
                    f"O relatorio da {company_name} ja foi visualizado, "
                    "mas ainda esta como pendente no seu controle interno."
                ),
                category="Relatorios",
                priority="normal",
                created_at=report.conference_first_viewed_at,
                client_name=company_name,
                action_label="Ver relatorio",
                action_url=reverse("mei_service_report_detail", args=[report.id]),
            )
        )
    return cards


def _build_mei_persistent_notification_card(notification):
    category = _notification_category_for_title(notification.title)
    return _notification_card(
        title=notification.title,
        message=notification.message,
        category=category,
        priority="normal" if notification.is_read else "new",
        created_at=notification.created_at,
        client_name=getattr(notification.recipient_company, "name", ""),
        action_label=_notification_action_label(notification.title, notification.target_url),
        action_url=notification.target_url,
        is_read=notification.is_read,
        notification=notification,
        source="persistent",
    )


def _service_report_received_label(report):
    if report.payment_status == ServiceReport.PaymentStatus.PAID:
        if report.paid_at:
            return f"Recebido: {timezone.localtime(report.paid_at).strftime('%d/%m/%Y %H:%M')}"
        return "Recebido"
    return "Pendente"


def _service_report_view_label(report):
    if report.conference_first_viewed_at:
        return f"Visto: {timezone.localtime(report.conference_first_viewed_at).strftime('%d/%m/%Y %H:%M')}"
    return "Nao visualizado"


def _service_report_status_label(report):
    if report.status == ServiceReport.Status.PAID:
        return "Recebido"
    return report.get_status_display()


def _service_report_period_label(report):
    payload = report.summary_payload or {}
    period = payload.get("period") or {}
    label = (period.get("label") or "").strip()
    if label:
        return label.replace(" ate ", " até ")
    start_label = report.date_from.strftime("%d/%m/%Y") if report.date_from else "-"
    end_label = report.date_to.strftime("%d/%m/%Y") if report.date_to else "-"
    return f"{start_label} até {end_label}"


def _build_service_report_whatsapp_message(report, conference_url):
    payload = report.summary_payload or {}
    client_name = payload.get("company") or report.company.name
    total_hours = payload.get("total_hours") or "-"
    estimated_value = payload.get("estimated_value_brl") or "-"
    period_label = _service_report_period_label(report)
    return "\n".join(
        [
            "Olá, segue meu relatório de horas para conferência.",
            "",
            f"Cliente: {client_name}",
            f"Período: {period_label}",
            f"Total de horas: {total_hours}",
            f"Valor estimado: {estimated_value}",
            "",
            "Link para conferência:",
            conference_url,
        ]
    )


def _normalize_whatsapp_number(value):
    digits = re.sub(r"\D+", "", value or "")
    return digits


def _build_service_report_whatsapp_url(report, conference_url):
    message = _build_service_report_whatsapp_message(report, conference_url)
    encoded_message = quote(message, safe="")
    number = _normalize_whatsapp_number(getattr(report.company, "whatsapp", ""))
    if number:
        return f"https://wa.me/{number}?text={encoded_message}"
    return f"https://wa.me/?text={encoded_message}"


def _report_locks_day_for_user(user, day):
    # Mantido como fino wrapper de compatibilidade: a checagem em si agora
    # vive em timeclock.services.report_locks_day, unica fonte de verdade
    # tambem usada por timeclock.views.create_manual_punches (ver bug da
    # auditoria de 12/09/2026 sobre essa checagem estar faltando la).
    return report_locks_day(day, user=user)


def _today_bounds(day):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(day, time.min), tz),
        timezone.make_aware(datetime.combine(day, time.max), tz),
    )


def _request_ip_address(request):
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded_for or request.META.get("REMOTE_ADDR") or None


def _workday_log_snapshot(punches):
    items = []
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        items.append(
            {
                "punch_id": str(punch.id),
                "time": local_ts.strftime("%H:%M"),
                "contract_id": str(punch.contract_id),
                "company_id": str(punch.contract.company_id),
                "company": punch.contract.company.name,
                "is_cancelled": bool(punch.is_cancelled),
                "note": punch.note or "",
            }
        )
    active_items = [item for item in items if not item["is_cancelled"]]
    return {
        "times": [item["time"] for item in active_items],
        "items": active_items,
        "all_items": items,
    }


def _infer_workday_change_type(before_data, after_data):
    before_items = {item["punch_id"]: item for item in before_data.get("items", [])}
    after_items = {item["punch_id"]: item for item in after_data.get("items", [])}
    before_ids = set(before_items)
    after_ids = set(after_items)
    changes = set()
    if after_ids - before_ids:
        changes.add(WorkdayChangeLog.ChangeType.ADD)
    if before_ids - after_ids:
        changes.add(WorkdayChangeLog.ChangeType.REMOVE)
    for punch_id in before_ids & after_ids:
        before_item = before_items[punch_id]
        after_item = after_items[punch_id]
        if before_item.get("contract_id") != after_item.get("contract_id"):
            changes.add(WorkdayChangeLog.ChangeType.CLIENT_CHANGED)
        if before_item.get("time") != after_item.get("time") or before_item.get("note") != after_item.get("note"):
            changes.add(WorkdayChangeLog.ChangeType.EDIT)
    if len(changes) > 1:
        return WorkdayChangeLog.ChangeType.MIXED
    if changes:
        return next(iter(changes))
    return WorkdayChangeLog.ChangeType.EDIT


def _service_report_pdf_response(report):
    payload = report.summary_payload or {}
    def pdf_text(value, default="-"):
        text = str(value if value not in (None, "") else default)
        return escape(text)

    def filename_part(value):
        text = (str(value or "").strip().lower())
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-") or "relatorio"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title="HoraCerta - Relatorio de horas",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="MetaRight",
            parent=styles["Normal"],
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#4b5563"),
            fontSize=8,
            leading=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            parent=styles["Normal"],
            textColor=colors.HexColor("#4b5563"),
            fontSize=8,
            leading=10,
        )
    )
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].fontSize = 18
    styles["Title"].leading = 22
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 15

    professional_name = payload.get("professional") or report.employee.full_name
    client_name = payload.get("company") or report.company.name
    period_label = (payload.get("period") or {}).get("label")
    if not period_label:
        start_label = report.date_from.strftime("%d/%m/%Y") if report.date_from else "-"
        end_label = report.date_to.strftime("%d/%m/%Y") if report.date_to else "-"
        period_label = f"{start_label} a {end_label}"
    period_file_label = "periodo"
    if report.date_from and report.date_to:
        period_file_label = f"{report.date_from:%Y%m%d}-{report.date_to:%Y%m%d}"
    filename = f"horacerta_relatorio_{filename_part(client_name)}_{period_file_label}.pdf"
    emitted_at = timezone.localtime().strftime("%d/%m/%Y %H:%M")

    story = [
        Paragraph("HoraCerta - Relatorio de horas", styles["Title"]),
        Paragraph(f"Emitido em {emitted_at}", styles["MetaRight"]),
        Spacer(1, 10),
    ]

    summary_rows = [
        ["Profissional", professional_name],
        ["Cliente", client_name],
        ["Periodo", period_label],
        ["Total de horas", payload.get("total_hours") or "-"],
        ["Valor estimado", payload.get("estimated_value_brl") or "-"],
    ]
    summary_table = Table(summary_rows, colWidths=[4 * cm, 13 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2ff")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1f2937")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 14), Paragraph("Dias e horarios", styles["Heading2"])])

    day_rows = [["Dia", "Horarios", "Total", "Status", "Observacoes"]]
    for day in payload.get("days") or []:
        status_label = "Incompleto" if day.get("is_incomplete") else "OK"
        day_rows.append(
            [
                Paragraph(pdf_text(day.get("date_label")), styles["SmallMuted"]),
                Paragraph(pdf_text(", ".join(day.get("punch_times") or []) or "-"), styles["SmallMuted"]),
                Paragraph(pdf_text(day.get("total_hours")), styles["SmallMuted"]),
                Paragraph(pdf_text(status_label), styles["SmallMuted"]),
                Paragraph(pdf_text("; ".join(day.get("notes") or []) or "-"), styles["SmallMuted"]),
            ]
        )
    if len(day_rows) == 1:
        day_rows.append(["-", "Sem registros no periodo.", "-", "-", "-"])

    days_table = Table(day_rows, colWidths=[2.7 * cm, 5.4 * cm, 2.1 * cm, 2.3 * cm, 4.5 * cm], repeatRows=1)
    days_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([days_table, Spacer(1, 14), Paragraph("Observacoes", styles["Heading2"])])
    description = pdf_text(report.description or "Sem observacoes gerais.").replace("\n", "<br/>")
    story.append(Paragraph(description, styles["Normal"]))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _service_report_filename(report, extension):
    payload = report.summary_payload or {}

    def filename_part(value):
        text = (str(value or "").strip().lower())
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-") or "relatorio"

    client_name = payload.get("company") or report.company.name
    period_file_label = "periodo"
    if report.date_from and report.date_to:
        period_file_label = f"{report.date_from:%Y%m%d}-{report.date_to:%Y%m%d}"
    return f"horacerta_relatorio_{filename_part(client_name)}_{period_file_label}.{extension}"


def _service_report_xlsx_response(report):
    payload = report.summary_payload or {}
    period_label = (payload.get("period") or {}).get("label")
    if not period_label:
        start_label = report.date_from.strftime("%d/%m/%Y") if report.date_from else "-"
        end_label = report.date_to.strftime("%d/%m/%Y") if report.date_to else "-"
        period_label = f"{start_label} a {end_label}"

    summary_rows = [
        ["Profissional", payload.get("professional") or report.employee.full_name],
        ["Cliente", payload.get("company") or report.company.name],
        ["Periodo", period_label],
        ["Total de horas", payload.get("total_hours") or "-"],
        ["Valor estimado", payload.get("estimated_value_brl") or "-"],
        [],
        ["Dia", "Horarios", "Total", "Status", "Observacoes"],
    ]
    day_rows = []
    for day in payload.get("days") or []:
        punch_times = day.get("punch_times") or []
        if not punch_times:
            status_label = "Pendente"
        elif day.get("is_incomplete"):
            status_label = "Incompleto"
        else:
            status_label = "OK"
        day_rows.append(
            [
                day.get("date_label") or "-",
                ", ".join(punch_times) or "-",
                day.get("total_hours") or "-",
                status_label,
                "; ".join(day.get("notes") or []) or "-",
            ]
        )
    if not day_rows:
        day_rows.append(["-", "Sem registros no periodo.", "-", "-", "-"])

    filename = _service_report_filename(report, "xlsx")
    return _build_xlsx_response(filename, ["Campo", "Valor"], summary_rows + day_rows)




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
