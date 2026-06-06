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
from django.views.decorators.http import require_GET, require_POST
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

from .forms import (
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
    UnifiedSignupForm,
    UserThemeForm,
)
from .mei_context import mei_contracts_for_user, resolve_mei_context
from .permissions import can_access_internal_dashboard

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


def _service_report_received_label(report):
    if report.payment_status == ServiceReport.PaymentStatus.PAID:
        if report.paid_at:
            return f"Recebido em {timezone.localtime(report.paid_at).strftime('%d/%m/%Y as %H:%M')}"
        return "Recebido"
    return "Pendente"


def _service_report_view_label(report):
    if report.conference_first_viewed_at:
        return f"Visualizado em {timezone.localtime(report.conference_first_viewed_at).strftime('%d/%m/%Y as %H:%M')}"
    return "Ainda nao visualizado"


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
    return ServiceReport.objects.filter(
        employee__user=user,
        date_from__lte=day,
        date_to__gte=day,
    ).exclude(status=ServiceReport.Status.CANCELED).exists()


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


def signup(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if request.method == "POST":
        form = UnifiedSignupForm(request.POST)
        if form.is_valid():
            pwd = form.cleaned_data["password1"]
            rh_email = form.cleaned_data["rh_email"]
            user = User.objects.create_user(
                username=rh_email,
                email=rh_email,
                password=pwd,
                role=User.Role.EMPRESA,
            )
            Company.objects.create(
                name=form.cleaned_data["company_name"],
                email=form.cleaned_data.get("company_email") or None,
                owner=user,
            )
            login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
            return _redirect_for_role(user)
    else:
        form = UnifiedSignupForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return _redirect_for_role(user)
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    return _redirect_for_role(request.user)


@internal_staff_required
def internal_dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    today_start = timezone.make_aware(datetime.combine(today, time.min), timezone.get_current_timezone())
    tomorrow_start = today_start + timedelta(days=1)
    last_7_days_start = now - timedelta(days=7)
    last_30_days_start = now - timedelta(days=30)

    total_users = User.objects.count()
    total_companies = Company.objects.count()
    total_employees = Employee.objects.count()
    total_active_employees = Employee.objects.filter(is_active=True).count()
    total_pending_employees = Employee.objects.filter(is_active=False).count()
    total_punches = Punch.objects.count()
    total_cancelled_punches = Punch.all_objects.filter(is_cancelled=True).count()
    total_open_correction_requests = PunchCorrectionRequest.objects.filter(status=PunchCorrectionRequest.Status.OPEN).count()
    total_notifications = InternalNotification.objects.filter(
        audience=InternalNotification.Audience.INTERNAL_ADMIN,
    ).count()
    total_unread_notifications = InternalNotification.objects.filter(
        audience=InternalNotification.Audience.INTERNAL_ADMIN,
        is_read=False,
    ).count()
    total_unacknowledged_company_notifications = InternalNotification.objects.filter(
        recipient_company__isnull=False,
        audience=InternalNotification.Audience.COMPANY,
        company_acknowledged=False,
        notification_type__in=[
            InternalNotification.NotificationType.CORRECTION_REQUEST_CREATED,
            InternalNotification.NotificationType.CORRECTION_REQUEST_STATUS_CHANGED,
            InternalNotification.NotificationType.PUNCH_CORRECTED,
            InternalNotification.NotificationType.PUNCH_CANCELLED,
            InternalNotification.NotificationType.PUNCH_RESTORED,
            InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
        ],
    ).count()
    total_punches_today = Punch.objects.filter(timestamp__gte=today_start, timestamp__lt=tomorrow_start).count()
    total_punches_last_7_days = Punch.objects.filter(timestamp__gte=last_7_days_start).count()
    total_punches_last_30_days = Punch.objects.filter(timestamp__gte=last_30_days_start).count()

    companies = _company_usage_queryset(last_30_days_start).order_by("-last_punch_at", "name")

    context = {
        "total_users": total_users,
        "total_companies": total_companies,
        "total_employees": total_employees,
        "total_active_employees": total_active_employees,
        "total_pending_employees": total_pending_employees,
        "total_punches": total_punches,
        "total_cancelled_punches": total_cancelled_punches,
        "total_open_correction_requests": total_open_correction_requests,
        "total_notifications": total_notifications,
        "total_unread_notifications": total_unread_notifications,
        "total_unacknowledged_company_notifications": total_unacknowledged_company_notifications,
        "total_punches_today": total_punches_today,
        "total_punches_last_7_days": total_punches_last_7_days,
        "total_punches_last_30_days": total_punches_last_30_days,
        "company_usage_rows": _build_company_usage_rows(companies),
        "generated_at": now,
    }
    return render(request, "accounts/internal_dashboard.html", context)


@internal_staff_required
def internal_companies(request):
    last_30_days_start = timezone.now() - timedelta(days=30)
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    companies = _company_usage_queryset(last_30_days_start)
    if q:
        companies = companies.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(cnpj__icontains=q))
    companies = companies.order_by("-last_punch_at", "name")

    rows = _build_company_usage_rows(companies)
    if status_filter:
        rows = [row for row in rows if row["status"]["label"] == status_filter]

    return render(
        request,
        "accounts/internal_companies.html",
        {
            "rows": rows,
            "q": q,
            "status_filter": status_filter,
        },
    )


@internal_staff_required
def internal_company_detail(request, company_id):
    last_30_days_start = timezone.now() - timedelta(days=30)
    company = get_object_or_404(_company_usage_queryset(last_30_days_start), id=company_id)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        description = (request.POST.get("description") or "").strip()
        if action == "activate_company":
            company.is_active = True
            company.save(update_fields=["is_active"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="activate_company",
                target_type="company",
                target_id=company.id,
                description=description or "Empresa ativada pelo Painel Interno.",
            )
            messages.success(request, "Empresa ativada.")
        elif action == "deactivate_company":
            company.is_active = False
            company.save(update_fields=["is_active"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="deactivate_company",
                target_type="company",
                target_id=company.id,
                description=description or "Empresa desativada pelo Painel Interno.",
            )
            messages.success(request, "Empresa desativada.")
        elif action == "save_company_note":
            company.internal_note = (request.POST.get("internal_note") or "").strip()
            company.save(update_fields=["internal_note"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="save_company_note",
                target_type="company",
                target_id=company.id,
                description=description or "Observacao interna da empresa atualizada.",
            )
            messages.success(request, "Observação interna salva.")
        elif action == "end_relationship":
            relationship_id = (request.POST.get("relationship_id") or "").strip()
            relationship = Employee.objects.select_related("company", "user").filter(id=relationship_id, company=company).first()
            if not relationship:
                messages.error(request, "Contrato invalido para este cliente.")
            elif not relationship.is_active and relationship.ended_at:
                messages.error(request, "Este contrato ja esta encerrado.")
            else:
                try:
                    _end_employee_company_relationship(
                        employee=relationship,
                        admin_user=request.user,
                        reason=description,
                    )
                    messages.success(request, "Contrato encerrado sem apagar login ou historico.")
                except ValueError as exc:
                    messages.error(request, str(exc))
        else:
            messages.error(request, "Ação administrativa inválida.")
        return redirect("internal_company_detail", company_id=company.id)

    company.status = _usage_status_for_company(company.punch_count, company.punch_count_last_30_days)
    employees = (
        Employee.objects.filter(company=company)
        .select_related("user", "company", "ended_by")
        .annotate(
            punch_count=Count("contracts__punches", filter=Q(contracts__punches__is_cancelled=False), distinct=True),
            last_punch_at=Max("contracts__punches__timestamp", filter=Q(contracts__punches__is_cancelled=False)),
            active_contract_count=Count("contracts", filter=Q(contracts__is_active=True), distinct=True),
        )
        .order_by("full_name")
    )
    employee_rows = [
        {
            "employee": employee,
            "status": _employee_status_for_backoffice(employee, employee.active_contract_count),
            "punch_count": employee.punch_count,
            "last_punch_at": employee.last_punch_at,
        }
        for employee in employees
    ]
    active_employee_rows = [row for row in employee_rows if row["employee"].is_active]
    ended_employee_rows = [row for row in employee_rows if not row["employee"].is_active and row["employee"].ended_at]
    inactive_employee_rows = [row for row in employee_rows if not row["employee"].is_active and not row["employee"].ended_at]
    recent_punches = (
        Punch.all_objects.filter(contract__company=company)
        .select_related("contract", "contract__employee", "contract__employee__user", "contract__company")
        .order_by("-timestamp")[:20]
    )
    contracts = (
        Contract.objects.filter(company=company)
        .select_related("employee", "employee__user", "company")
        .order_by("employee__full_name", "-start_date")
    )
    correction_requests = (
        PunchCorrectionRequest.objects.filter(company=company)
        .select_related("employee", "user", "punch")
        .order_by("-created_at")[:10]
    )
    admin_logs = InternalAdminActionLog.objects.filter(
        target_type="company",
        target_id=str(company.id),
    ).select_related("admin_user")[:10]

    return render(
        request,
        "accounts/internal_company_detail.html",
        {
            "company": company,
            "employee_rows": employee_rows,
            "active_employee_rows": active_employee_rows,
            "ended_employee_rows": ended_employee_rows,
            "inactive_employee_rows": inactive_employee_rows,
            "recent_punches": recent_punches,
            "contracts": contracts,
            "correction_requests": correction_requests,
            "admin_logs": admin_logs,
        },
    )


@internal_staff_required
def internal_employees(request):
    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    employees = (
        Employee.objects.select_related("user", "company")
        .annotate(
            punch_count=Count("contracts__punches", filter=Q(contracts__punches__is_cancelled=False), distinct=True),
            last_punch_at=Max("contracts__punches__timestamp", filter=Q(contracts__punches__is_cancelled=False)),
            active_contract_count=Count("contracts", filter=Q(contracts__is_active=True), distinct=True),
        )
        .order_by("full_name")
    )
    if q:
        employees = employees.filter(
            Q(full_name__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__username__icontains=q)
            | Q(document__icontains=q)
        )
    if company_id:
        employees = employees.filter(company_id=company_id)

    rows = []
    for employee in employees:
        status = _employee_status_for_backoffice(employee, employee.active_contract_count)
        if status_filter and status["key"] != status_filter:
            continue
        rows.append(
            {
                "employee": employee,
                "status": status,
                "punch_count": employee.punch_count,
                "last_punch_at": employee.last_punch_at,
            }
        )

    return render(
        request,
        "accounts/internal_employees.html",
        {
            "rows": rows,
            "companies": [
                {"company": company, "selected": str(company.id) == company_id}
                for company in Company.objects.order_by("name")
            ],
            "q": q,
            "company_id": company_id,
            "status_filter": status_filter,
        },
    )


@internal_staff_required
def internal_employee_detail(request, employee_id):
    employee = get_object_or_404(Employee.objects.select_related("user", "company"), id=employee_id)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        description = (request.POST.get("description") or "").strip()
        if action == "end_relationship":
            relationship_id = (request.POST.get("relationship_id") or "").strip()
            relationship = (
                Employee.objects.select_related("user", "company")
                .filter(id=relationship_id, user=employee.user)
                .first()
            )
            if not relationship:
                messages.error(request, "Contrato invalido para este prestador.")
            elif not relationship.is_active and relationship.ended_at:
                messages.error(request, "Este contrato ja esta encerrado.")
            else:
                try:
                    _end_employee_company_relationship(
                        employee=relationship,
                        admin_user=request.user,
                        reason=description,
                    )
                    messages.success(request, "Contrato encerrado sem apagar login ou historico.")
                except ValueError as exc:
                    messages.error(request, str(exc))
        elif action == "activate_user":
            employee.user.is_active = True
            employee.user.save(update_fields=["is_active"])
            employee.is_active = True
            employee.ended_at = None
            employee.ended_by = None
            employee.end_reason = ""
            employee.save(update_fields=["is_active", "ended_at", "ended_by", "end_reason"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="activate_user",
                target_type="employee",
                target_id=employee.id,
                description=description or "Usuario e perfil ativados pelo Painel Interno.",
            )
            messages.success(request, "Usuário ativado.")
        elif action == "deactivate_user":
            employee.user.is_active = False
            employee.user.save(update_fields=["is_active"])
            employee.is_active = False
            employee.save(update_fields=["is_active"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="deactivate_user",
                target_type="employee",
                target_id=employee.id,
                description=description or "Usuario e perfil desativados pelo Painel Interno.",
            )
            messages.success(request, "Usuário desativado.")
        elif action == "mark_pending":
            employee.is_active = False
            employee.save(update_fields=["is_active"])
            _log_internal_admin_action(
                admin_user=request.user,
                action="mark_employee_pending",
                target_type="employee",
                target_id=employee.id,
                description=description or "Perfil marcado como pendente de ativacao.",
            )
            messages.success(request, "Profissional marcado como pendente.")
        else:
            messages.error(request, "Ação administrativa inválida.")
        return redirect("internal_employee_detail", employee_id=employee.id)

    contracts = (
        Contract.objects.filter(employee=employee)
        .select_related("company", "employee", "employee__user")
        .order_by("-start_date", "-created_at")
    )
    related_relationships = (
        Employee.objects.filter(user=employee.user)
        .select_related("company", "user", "ended_by")
        .annotate(
            active_contract_count=Count("contracts", filter=Q(contracts__is_active=True), distinct=True),
            punch_count=Count("contracts__punches", distinct=True),
            last_punch_at=Max("contracts__punches__timestamp"),
        )
        .order_by("-is_active", "company__name")
    )
    relationship_rows = [
        {
            "employee": relationship,
            "status": _employee_status_for_backoffice(relationship, relationship.active_contract_count),
            "punch_count": relationship.punch_count,
            "last_punch_at": relationship.last_punch_at,
        }
        for relationship in related_relationships
    ]
    recent_punches = (
        Punch.all_objects.filter(contract__employee=employee)
        .select_related("contract", "contract__company", "contract__employee", "contract__employee__user")
        .order_by("-timestamp")[:30]
    )
    active_contract_count = contracts.filter(is_active=True).count()
    correction_requests = (
        PunchCorrectionRequest.objects.filter(employee=employee)
        .select_related("company", "punch")
        .order_by("-created_at")[:10]
    )
    admin_logs = InternalAdminActionLog.objects.filter(
        target_type="employee",
        target_id=str(employee.id),
    ).select_related("admin_user")[:10]

    return render(
        request,
        "accounts/internal_employee_detail.html",
        {
            "employee": employee,
            "status": _employee_status_for_backoffice(employee, active_contract_count),
            "contracts": contracts,
            "relationship_rows": relationship_rows,
            "recent_punches": recent_punches,
            "summary_30_days": _recent_30_day_summary_for_employee(employee),
            "correction_requests": correction_requests,
            "admin_logs": admin_logs,
        },
    )


@internal_staff_required
def internal_punches(request):
    company_id = (request.GET.get("company") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    punches = Punch.all_objects.select_related(
        "contract",
        "contract__company",
        "contract__employee",
        "contract__employee__user",
    ).order_by("-timestamp")

    if company_id:
        punches = punches.filter(contract__company_id=company_id)
    if employee_id:
        punches = punches.filter(contract__employee_id=employee_id)

    punches, date_from, date_to = filter_punches_by_period(
        punches,
        request.GET.get("date_from"),
        request.GET.get("date_to"),
    )
    if status_filter == "cancelado":
        punches = punches.filter(is_cancelled=True)
    elif status_filter == "ativo":
        punches = punches.filter(is_cancelled=False)

    return render(
        request,
        "accounts/internal_punches.html",
        {
            "punches": punches[:200],
            "companies": [
                {"company": company, "selected": str(company.id) == company_id}
                for company in Company.objects.order_by("name")
            ],
            "employees": [
                {"employee": employee, "selected": str(employee.id) == employee_id}
                for employee in Employee.objects.select_related("user", "company").order_by("full_name")
            ],
            "company_id": company_id,
            "employee_id": employee_id,
            "status_filter": status_filter,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@internal_staff_required
def internal_punch_detail(request, punch_id):
    punch = get_object_or_404(
        Punch.all_objects.select_related(
            "contract",
            "contract__company",
            "contract__employee",
            "contract__employee__user",
            "validated_location",
            "qr_confirmed_location",
        ),
        id=punch_id,
    )
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        try:
            if action == "change_time":
                raw_new_datetime = (request.POST.get("new_datetime") or "").strip()
                new_datetime = datetime.strptime(raw_new_datetime, "%Y-%m-%dT%H:%M")
                change_punch_time(punch=punch, admin_user=request.user, new_datetime=new_datetime, reason=reason)
                notify_punch_admin_action(
                    punch,
                    actor_user=request.user,
                    action_type=PunchCorrectionLog.ActionType.TIME_CHANGED,
                )
                messages.success(request, "Horario corrigido com auditoria registrada.")
            elif action == "cancel":
                cancel_punch(punch=punch, admin_user=request.user, reason=reason)
                notify_punch_admin_action(
                    punch,
                    actor_user=request.user,
                    action_type=PunchCorrectionLog.ActionType.CANCELLED,
                )
                messages.success(request, "Registro cancelado com auditoria registrada.")
            elif action == "restore":
                restore_punch(punch=punch, admin_user=request.user, reason=reason)
                notify_punch_admin_action(
                    punch,
                    actor_user=request.user,
                    action_type=PunchCorrectionLog.ActionType.RESTORED,
                )
                messages.success(request, "Registro restaurado com auditoria registrada.")
            elif action == "admin_note":
                add_punch_admin_note(
                    punch=punch,
                    admin_user=request.user,
                    note=request.POST.get("admin_note"),
                    reason=reason,
                )
                notify_punch_admin_action(
                    punch,
                    actor_user=request.user,
                    action_type=PunchCorrectionLog.ActionType.ADMIN_NOTE_ADDED,
                )
                messages.success(request, "Observacao administrativa salva com auditoria registrada.")
            else:
                messages.error(request, "Acao administrativa invalida.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("internal_punch_detail", punch_id=punch.id)

    correction_logs = PunchCorrectionLog.objects.filter(punch=punch).select_related("admin_user")
    return render(
        request,
        "accounts/internal_punch_detail.html",
        {
            "punch": punch,
            "punch_status": _punch_status_label(punch),
            "correction_logs": correction_logs,
        },
    )


@internal_staff_required
def internal_correction_requests(request):
    status = (request.GET.get("status") or "").strip()
    company_id = (request.GET.get("company") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    problem_type = (request.GET.get("problem_type") or "").strip()
    problem_date = (request.GET.get("problem_date") or "").strip()

    requests_qs = PunchCorrectionRequest.objects.select_related(
        "employee",
        "employee__user",
        "company",
        "contract",
        "punch",
        "resolved_by",
    )
    if status:
        requests_qs = requests_qs.filter(status=status)
    if company_id:
        requests_qs = requests_qs.filter(company_id=company_id)
    if employee_id:
        requests_qs = requests_qs.filter(employee_id=employee_id)
    if problem_type:
        requests_qs = requests_qs.filter(problem_type=problem_type)
    if problem_date:
        try:
            requests_qs = requests_qs.filter(problem_date=datetime.strptime(problem_date, "%Y-%m-%d").date())
        except ValueError:
            pass

    rows = [
        {
            "request": item,
            "status_tone": _correction_request_status_tone(item.status),
        }
        for item in requests_qs[:200]
    ]
    return render(
        request,
        "accounts/internal_correction_requests.html",
        {
            "rows": rows,
            "companies": [
                {"company": company, "selected": str(company.id) == company_id}
                for company in Company.objects.order_by("name")
            ],
            "employees": [
                {"employee": employee, "selected": str(employee.id) == employee_id}
                for employee in Employee.objects.select_related("company", "user").order_by("full_name")
            ],
            "status": status,
            "problem_type": problem_type,
            "problem_date": problem_date,
            "status_choices": PunchCorrectionRequest.Status.choices,
            "problem_type_choices": PunchCorrectionRequest.ProblemType.choices,
        },
    )


@internal_staff_required
def internal_correction_request_detail(request, request_id):
    correction_request = get_object_or_404(
        PunchCorrectionRequest.objects.select_related(
            "employee",
            "employee__user",
            "company",
            "contract",
            "punch",
            "resolved_by",
        ),
        id=request_id,
    )
    if request.method == "POST":
        new_status = (request.POST.get("status") or "").strip()
        response_text = (request.POST.get("admin_response") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        valid_statuses = {choice[0] for choice in PunchCorrectionRequest.Status.choices}
        if new_status not in valid_statuses:
            messages.error(request, "Status invalido para a solicitacao.")
        else:
            try:
                reason = _require_admin_reason(reason)
                old_status = correction_request.status
                old_response = correction_request.admin_response
                correction_request.status = new_status
                correction_request.admin_response = response_text
                if new_status in {PunchCorrectionRequest.Status.CORRECTED, PunchCorrectionRequest.Status.REJECTED}:
                    correction_request.resolved_by = request.user
                    correction_request.resolved_at = timezone.now()
                else:
                    correction_request.resolved_by = None
                    correction_request.resolved_at = None
                correction_request.save(
                    update_fields=["status", "admin_response", "resolved_by", "resolved_at", "updated_at"]
                )
                InternalAdminActionLog.objects.create(
                    admin_user=request.user,
                    action="correction_request_status_changed",
                    target_type="punch_correction_request",
                    target_id=str(correction_request.id),
                    description=(
                        f"Status: {old_status} -> {new_status}. "
                        f"Resposta anterior: {old_response or '-'}. "
                        f"Justificativa: {reason}"
                    ),
                )
                notify_correction_request_status_changed(
                    correction_request,
                    actor_user=request.user,
                    old_status=old_status,
                )
                messages.success(request, "Solicitacao atualizada com auditoria registrada.")
            except ValueError as exc:
                messages.error(request, str(exc))
        return redirect("internal_correction_request_detail", request_id=correction_request.id)

    day_start = timezone.make_aware(datetime.combine(correction_request.problem_date, time.min))
    day_end = timezone.make_aware(datetime.combine(correction_request.problem_date, time.max))
    day_punches = (
        Punch.all_objects.filter(
            contract__employee=correction_request.employee,
            timestamp__range=(day_start, day_end),
        )
        .select_related("contract", "contract__company")
        .order_by("timestamp")
    )
    records_url = (
        f"{reverse('internal_punches')}?employee={correction_request.employee_id}"
        f"&date_from={correction_request.problem_date:%Y-%m-%d}&date_to={correction_request.problem_date:%Y-%m-%d}"
    )
    return render(
        request,
        "accounts/internal_correction_request_detail.html",
        {
            "correction_request": correction_request,
            "status_tone": _correction_request_status_tone(correction_request.status),
            "day_punches": day_punches,
            "records_url": records_url,
            "status_choices": PunchCorrectionRequest.Status.choices,
        },
    )


@internal_staff_required
def internal_audit(request):
    company_id = (request.GET.get("company") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    action_filter = (request.GET.get("action_type") or "").strip()
    actor_id = (request.GET.get("actor") or "").strip()
    date_from, date_to, start_dt, end_dt = _audit_date_bounds(request)
    rows = []

    punch_action_values = {
        PunchCorrectionLog.ActionType.TIME_CHANGED,
        PunchCorrectionLog.ActionType.CANCELLED,
        PunchCorrectionLog.ActionType.RESTORED,
        PunchCorrectionLog.ActionType.ADMIN_NOTE_ADDED,
    }
    if not action_filter or action_filter in punch_action_values:
        punch_logs = PunchCorrectionLog.objects.select_related(
            "admin_user",
            "punch",
            "punch__contract",
            "punch__contract__company",
            "punch__contract__employee",
            "punch__contract__employee__user",
        )
        punch_logs = _apply_datetime_bounds(punch_logs, "created_at", start_dt, end_dt)
        if action_filter:
            punch_logs = punch_logs.filter(action_type=action_filter)
        if company_id:
            punch_logs = punch_logs.filter(punch__contract__company_id=company_id)
        if employee_id:
            punch_logs = punch_logs.filter(punch__contract__employee_id=employee_id)
        if actor_id:
            punch_logs = punch_logs.filter(admin_user_id=actor_id)
        for log in punch_logs[:300]:
            if log.action_type == PunchCorrectionLog.ActionType.TIME_CHANGED:
                old_value = timezone.localtime(log.old_datetime).strftime("%d/%m/%Y %H:%M") if log.old_datetime else ""
                new_value = timezone.localtime(log.new_datetime).strftime("%d/%m/%Y %H:%M") if log.new_datetime else ""
            elif log.action_type in {PunchCorrectionLog.ActionType.CANCELLED, PunchCorrectionLog.ActionType.RESTORED}:
                old_value = log.old_status
                new_value = log.new_status
            else:
                old_value = "-"
                new_value = "Observacao administrativa atualizada"
            rows.append(
                _audit_row(
                    created_at=log.created_at,
                    actor=log.admin_user,
                    action_type=log.action_type,
                    company=log.punch.contract.company,
                    employee=log.punch.contract.employee,
                    old_value=old_value,
                    new_value=new_value,
                    reason=log.reason,
                    target_url=reverse("internal_punch_detail", args=[log.punch_id]),
                )
            )

    if not action_filter or action_filter == "relationship_ended":
        relationship_logs = EmployeeRelationshipAuditLog.objects.select_related(
            "admin_user",
            "employee",
            "employee__user",
            "company",
        )
        relationship_logs = _apply_datetime_bounds(relationship_logs, "created_at", start_dt, end_dt)
        if company_id:
            relationship_logs = relationship_logs.filter(company_id=company_id)
        if employee_id:
            relationship_logs = relationship_logs.filter(employee_id=employee_id)
        if actor_id:
            relationship_logs = relationship_logs.filter(admin_user_id=actor_id)
        for log in relationship_logs[:300]:
            rows.append(
                _audit_row(
                    created_at=log.created_at,
                    actor=log.admin_user,
                    action_type=log.action_type,
                    company=log.company,
                    employee=log.employee,
                    old_value="Contrato ativo",
                    new_value="Contrato encerrado",
                    reason=log.reason,
                    target_url=reverse("internal_employee_detail", args=[log.employee_id]),
                )
            )

    admin_action_values = {
        "deactivate_company",
        "activate_company",
        "deactivate_user",
        "activate_user",
        "correction_request_status_changed",
    }
    if not action_filter or action_filter in admin_action_values:
        admin_logs = InternalAdminActionLog.objects.select_related("admin_user").filter(action__in=admin_action_values)
        admin_logs = _apply_datetime_bounds(admin_logs, "created_at", start_dt, end_dt)
        if action_filter:
            admin_logs = admin_logs.filter(action=action_filter)
        if actor_id:
            admin_logs = admin_logs.filter(admin_user_id=actor_id)
        if company_id:
            company_employee_ids = [str(item.id) for item in Employee.objects.filter(company_id=company_id).only("id")]
            company_correction_request_ids = [
                str(item.id) for item in PunchCorrectionRequest.objects.filter(company_id=company_id).only("id")
            ]
            admin_logs = admin_logs.filter(
                Q(target_type="company", target_id=str(company_id))
                | Q(target_type="employee", target_id__in=company_employee_ids)
                | Q(target_type="punch_correction_request", target_id__in=company_correction_request_ids)
            )
        if employee_id:
            employee_correction_request_ids = [
                str(item.id) for item in PunchCorrectionRequest.objects.filter(employee_id=employee_id).only("id")
            ]
            admin_logs = admin_logs.filter(
                Q(target_type="employee", target_id=str(employee_id))
                | Q(target_type="punch_correction_request", target_id__in=employee_correction_request_ids)
            )
        admin_logs = list(admin_logs[:300])
        company_targets = {
            log.target_id for log in admin_logs
            if log.target_type == "company"
        }
        employee_targets = {
            log.target_id for log in admin_logs
            if log.target_type == "employee"
        }
        correction_request_targets = {
            log.target_id for log in admin_logs
            if log.target_type == "punch_correction_request"
        }
        companies_by_id = {
            str(company.id): company
            for company in Company.objects.filter(id__in=company_targets)
        }
        employees_by_id = {
            str(employee.id): employee
            for employee in Employee.objects.select_related("company", "user").filter(id__in=employee_targets)
        }
        correction_requests_by_id = {
            str(item.id): item
            for item in PunchCorrectionRequest.objects.select_related("company", "employee", "employee__user").filter(
                id__in=correction_request_targets
            )
        }
        for log in admin_logs:
            company = companies_by_id.get(log.target_id) if log.target_type == "company" else None
            employee = employees_by_id.get(log.target_id) if log.target_type == "employee" else None
            correction_request = (
                correction_requests_by_id.get(log.target_id)
                if log.target_type == "punch_correction_request"
                else None
            )
            if correction_request:
                company = correction_request.company
                employee = correction_request.employee
            if employee and not company:
                company = employee.company
            if company_id and correction_request and str(company.id) != str(company_id):
                continue
            if employee_id and correction_request and str(employee.id) != str(employee_id):
                continue
            rows.append(
                _audit_row(
                    created_at=log.created_at,
                    actor=log.admin_user,
                    action_type=log.action,
                    company=company,
                    employee=employee,
                    old_value=(
                        "Status anterior"
                        if log.action == "correction_request_status_changed"
                        else "ativo" if log.action.startswith("deactivate") else "inativo"
                    ),
                    new_value=(
                        "Status atualizado"
                        if log.action == "correction_request_status_changed"
                        else "inativo" if log.action.startswith("deactivate") else "ativo"
                    ),
                    reason=log.description,
                    target_url=(
                        reverse("internal_correction_request_detail", args=[correction_request.id]) if correction_request
                        else reverse("internal_company_detail", args=[company.id]) if company and not employee
                        else reverse("internal_employee_detail", args=[employee.id]) if employee
                        else ""
                    ),
                )
            )

    if not action_filter or action_filter == "company_acknowledged":
        acknowledgements = InternalNotification.objects.filter(
            recipient_company__isnull=False,
            company_acknowledged=True,
            company_acknowledged_at__isnull=False,
        ).select_related("recipient_company", "company_acknowledged_by")
        acknowledgements = _apply_datetime_bounds(acknowledgements, "company_acknowledged_at", start_dt, end_dt)
        if company_id:
            acknowledgements = acknowledgements.filter(recipient_company_id=company_id)
        if employee_id:
            acknowledgements = acknowledgements.none()
        if actor_id:
            acknowledgements = acknowledgements.filter(company_acknowledged_by_id=actor_id)
        for notification in acknowledgements[:300]:
            rows.append(
                _audit_row(
                    created_at=notification.company_acknowledged_at,
                    actor=notification.company_acknowledged_by,
                    action_type="company_acknowledged",
                    company=notification.recipient_company,
                    old_value="Ciencia pendente",
                    new_value="Ciencia marcada",
                    reason=notification.title,
                    target_url=notification.target_url,
                )
            )

    rows.sort(key=lambda item: item["created_at"] or datetime.min.replace(tzinfo=timezone.get_current_timezone()), reverse=True)
    return render(
        request,
        "accounts/internal_audit.html",
        {
            "rows": rows[:500],
            "date_from": date_from,
            "date_to": date_to,
            "company_id": company_id,
            "employee_id": employee_id,
            "action_filter": action_filter,
            "actor_id": actor_id,
            "action_choices": AUDIT_ACTION_CHOICES,
            "companies": [
                {"company": company, "selected": str(company.id) == company_id}
                for company in Company.objects.order_by("name")
            ],
            "employees": [
                {"employee": employee, "selected": str(employee.id) == employee_id}
                for employee in Employee.objects.select_related("company", "user").order_by("full_name")
            ],
            "actors": [
                {"user": user, "selected": str(user.id) == actor_id}
                for user in User.objects.order_by("email", "username")
            ],
        },
    )


@internal_staff_required
def internal_workday_changes(request):
    company_id = (request.GET.get("company") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    change_type = (request.GET.get("change_type") or "").strip()
    date_from, date_to, start_dt, end_dt = _audit_date_bounds(request)

    logs_qs = WorkdayChangeLog.objects.select_related(
        "user",
        "employee",
        "employee__user",
        "company",
        "contract",
    ).order_by("-changed_at")
    logs_qs = _apply_datetime_bounds(logs_qs, "changed_at", start_dt, end_dt)
    if company_id:
        logs_qs = logs_qs.filter(company_id=company_id)
    if employee_id:
        logs_qs = logs_qs.filter(employee_id=employee_id)
    valid_change_types = {choice[0] for choice in WorkdayChangeLog.ChangeType.choices}
    if change_type in valid_change_types:
        logs_qs = logs_qs.filter(change_type=change_type)

    rows = []
    for log in logs_qs[:300]:
        before_times = ", ".join(log.before_data.get("times") or []) or "-"
        after_times = ", ".join(log.after_data.get("times") or []) or "-"
        rows.append(
            {
                "log": log,
                "before_times": before_times,
                "after_times": after_times,
            }
        )

    companies = [
        {"company": company, "selected": str(company.id) == company_id}
        for company in Company.objects.order_by("name")
    ]
    employees = [
        {"employee": employee, "selected": str(employee.id) == employee_id}
        for employee in Employee.objects.select_related("company", "user").order_by("full_name")
    ]

    return render(
        request,
        "accounts/internal_workday_changes.html",
        {
            "rows": rows,
            "companies": companies,
            "employees": employees,
            "change_type_choices": WorkdayChangeLog.ChangeType.choices,
            "change_type": change_type,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@internal_staff_required
def internal_notifications(request):
    type_filter = (request.GET.get("type") or "").strip()
    audience_filter = (request.GET.get("audience") or "").strip()
    company_id = (request.GET.get("company") or "").strip()
    user_id = (request.GET.get("user") or "").strip()
    read_filter = (request.GET.get("read") or "").strip()
    ack_filter = (request.GET.get("ack") or "").strip()

    notifications = InternalNotification.objects.select_related(
        "recipient_user",
        "recipient_company",
        "actor_user",
        "company_acknowledged_by",
    )
    if not audience_filter:
        notifications = notifications.filter(audience=InternalNotification.Audience.INTERNAL_ADMIN)
    if type_filter:
        notifications = notifications.filter(notification_type=type_filter)
    if audience_filter:
        notifications = notifications.filter(audience=audience_filter)
    if company_id:
        notifications = notifications.filter(recipient_company_id=company_id)
    if user_id:
        notifications = notifications.filter(recipient_user_id=user_id)
    notifications, date_from, date_to = filter_punches_by_period(
        notifications,
        request.GET.get("date_from"),
        request.GET.get("date_to"),
        field_name="created_at",
    )
    if read_filter == "unread":
        notifications = notifications.filter(is_read=False)
    elif read_filter == "read":
        notifications = notifications.filter(is_read=True)
    if ack_filter == "acknowledged":
        notifications = notifications.filter(company_acknowledged=True)
    elif ack_filter == "pending":
        notifications = notifications.filter(recipient_company__isnull=False, company_acknowledged=False)

    return render(
        request,
        "accounts/internal_notifications.html",
        {
            "rows": [
                {"notification": notification, "tone": _notification_tone(notification)}
                for notification in notifications[:300]
            ],
            "type_filter": type_filter,
            "audience_filter": audience_filter,
            "company_id": company_id,
            "user_id": user_id,
            "read_filter": read_filter,
            "ack_filter": ack_filter,
            "date_from": date_from,
            "date_to": date_to,
            "notification_type_choices": InternalNotification.NotificationType.choices,
            "notification_audience_choices": InternalNotification.Audience.choices,
            "companies": [
                {"company": company, "selected": str(company.id) == company_id}
                for company in Company.objects.order_by("name")
            ],
            "users": [
                {"user": user, "selected": str(user.id) == user_id}
                for user in User.objects.order_by("email", "username")
            ],
        },
    )


@login_required
def dashboard_employee(request):
    return redirect("employee_dashboard")


@login_required
def dashboard_empresa(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    employee_search_form = EmployeeSearchForm(request.GET or None)
    period_form = PeriodSearchForm(request.GET or None)

    employees_qs = Employee.objects.none()
    contracts_qs = Contract.objects.none()
    punches_period_qs = Punch.objects.none()

    total_registered_professionals = 0
    total_active_professionals = 0
    total_pending_contract = 0
    total_inactive_professionals = 0
    total_active_contracts = 0
    total_punches_period = 0
    total_hours_period = "00:00"
    inconsistency_days_period = 0
    date_from = ""
    date_to = ""
    pending_professionals = []
    state_counters = {
        PROFESSIONAL_STATE_CADASTRADO: 0,
        PROFESSIONAL_STATE_AGUARDANDO: 0,
        PROFESSIONAL_STATE_ATIVO: 0,
        PROFESSIONAL_STATE_INATIVO: 0,
    }

    if company:
        employees_base_qs = Employee.objects.filter(company=company).select_related("user")
        contracts_base_qs = Contract.objects.filter(
            company=company,
            employee__isnull=False,
            employee__user__isnull=False,
        ).select_related(
            "employee",
            "employee__user",
            "company",
        )
        operational_contracts_base_qs = contracts_base_qs.filter(contract_operational_q())

        q = ""
        if employee_search_form.is_valid():
            q = (employee_search_form.cleaned_data.get("q") or "").strip()

        if q:
            employees_qs = employees_base_qs.filter(
                Q(full_name__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__username__icontains=q)
            )
            contracts_qs = operational_contracts_base_qs.filter(
                Q(employee__user__email__icontains=q)
                | Q(employee__user__username__icontains=q)
                | Q(employee__full_name__icontains=q)
            )
        else:
            employees_qs = employees_base_qs
            contracts_qs = operational_contracts_base_qs

        all_employees = list(employees_base_qs.order_by("full_name")[:500])
        contracts_by_employee_all = _contracts_by_employee(company, all_employees)
        for employee in all_employees:
            summary = employee_lifecycle_summary(employee, contracts_by_employee_all.get(employee.id, []))
            state_counters[summary["key"]] += 1
            if summary["key"] != PROFESSIONAL_STATE_ATIVO and len(pending_professionals) < 8:
                employee_contracts = contracts_by_employee_all.get(employee.id, [])
                latest_contract = employee_contracts[0] if employee_contracts else None
                pending_professionals.append(
                    {
                        "employee": employee,
                        "state": summary,
                        "latest_contract": latest_contract,
                        "action_url": (
                            f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente"
                            if not latest_contract
                            else f"{reverse('company_contracts')}?edit={latest_contract.id}"
                        ),
                        "action_label": "Revisar no cadastro MEI" if not latest_contract else "Editar contrato",
                    }
                )

        today = timezone.localdate()
        first_day = today.replace(day=1)
        start_date = first_day
        end_date = today

        if period_form.is_valid():
            start_date = period_form.cleaned_data.get("date_from") or first_day
            end_date = period_form.cleaned_data.get("date_to") or today
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max))
        punches_period_qs = Punch.objects.filter(
            contract__in=contracts_qs,
            timestamp__range=(start_dt, end_dt),
        ).select_related("contract", "contract__employee", "contract__employee__user", "validated_location")

        total_registered_professionals = len(all_employees)
        total_active_professionals = state_counters[PROFESSIONAL_STATE_ATIVO]
        total_pending_contract = state_counters[PROFESSIONAL_STATE_CADASTRADO] + state_counters[PROFESSIONAL_STATE_AGUARDANDO]
        total_inactive_professionals = state_counters[PROFESSIONAL_STATE_INATIVO]
        total_active_contracts = operational_contracts_base_qs.count()
        total_punches_period = punches_period_qs.count()
        period_punches = list(punches_period_qs)
        period_daily_rows, _period_columns = build_daily_summary(period_punches, min_punch_columns=4)
        period_total_seconds = sum(row["total_seconds"] for row in period_daily_rows)
        total_hours_period = format_hhmm(period_total_seconds)
        inconsistency_days_period = _count_inconsistency_days(period_punches)
        date_from = start_date.strftime("%Y-%m-%d")
        date_to = end_date.strftime("%Y-%m-%d")

    period_result = {
        "date_from": date_from,
        "date_to": date_to,
        "total_punches": total_punches_period,
        "total_hours": total_hours_period,
    }
    employees_list = list(employees_qs.order_by("full_name")[:300])
    contracts_by_employee = _contracts_by_employee(company, employees_list)
    employee_rows = []
    for employee in employees_list:
        employee_contracts = contracts_by_employee.get(employee.id, [])
        latest_contract = employee_contracts[0] if employee_contracts else None
        action_url = (
            f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente"
            if not latest_contract
            else f"{reverse('company_contracts')}?edit={latest_contract.id}"
        )
        employee_rows.append(
            {
                "employee": employee,
                "active_contracts": sum(1 for c in employee_contracts if contract_is_operational(c)),
                "total_contracts": len(employee_contracts),
                "state": employee_lifecycle_summary(employee, employee_contracts),
                "profile_url": reverse("company_mei_profile", args=[employee.id]),
                "action_url": action_url,
                "action_label": "Revisar no cadastro MEI" if not latest_contract else "Editar contrato",
            }
        )

    contract_rows = []
    for contract in contracts_qs.order_by("-start_date", "-created_at", "employee__user__username")[:300]:
        mei_name = _contract_mei_label(contract)
        contract_rows.append({"contract": contract, "mei_name": mei_name})

    punch_rows = []
    for punch in punches_period_qs.order_by("-timestamp")[:120]:
        mei_name = _contract_mei_label(punch.contract)
        distance_value = "-"
        if punch.distance_to_location_m is not None:
            try:
                distance_value = f"{float(punch.distance_to_location_m):.1f} m"
            except (TypeError, ValueError):
                distance_value = "-"
        punch_rows.append(
            {
                "punch": punch,
                "mei_name": mei_name,
                "confidence_label": punch.get_confidence_status_display(),
                "confidence_tone": punch.confidence_tone,
                "qr_label": punch.get_qr_confirmation_status_display(),
                "qr_tone": punch.qr_tone,
                "validation_method_label": punch.get_validation_method_display(),
                "validated_location_name": punch.validated_location.name if punch.validated_location else "-",
                "distance_label": distance_value,
            }
        )

    quick_links = [
        {
            "label": "Resumo operacional",
            "url": reverse("company_operational_summary"),
            "hint": "Visão por profissional no período",
        },
        {"label": "Hoje", "url": reverse("company_today_center"), "hint": "Acompanhamento diário"},
        {
            "label": "Revisão de registros",
            "url": reverse("company_records_review_center"),
            "hint": "Selo de confiança e auditoria",
        },
        {"label": "Prestadores", "url": reverse("company_meis"), "hint": "Cadastro, contratos e status"},
        {"label": "Registros", "url": reverse("company_history"), "hint": "Histórico, conferência e pendências"},
        {"label": "Relatórios", "url": reverse("company_reports"), "hint": "Fechamento e exportações"},
        {"label": "Atividades", "url": reverse("company_service_reports"), "hint": "Relatórios enviados pelos prestadores"},
    ]

    context = {
        "company": company,
        "employees": employee_rows,
        "contracts": contract_rows,
        "employee_search_form": employee_search_form,
        "period_form": period_form,
        "period_result": period_result,
        "total_registered_professionals": total_registered_professionals,
        "total_active_professionals": total_active_professionals,
        "total_pending_contract": total_pending_contract,
        "total_inactive_professionals": total_inactive_professionals,
        "state_counters": state_counters,
        "total_active_contracts": total_active_contracts,
        "total_punches_period": total_punches_period,
        "total_hours_period": total_hours_period,
        "inconsistency_days_period": inconsistency_days_period,
        "punches_period": punch_rows,
        "pending_professionals": pending_professionals,
        "quick_links": quick_links,
        "pending_reports_count": _pending_reports_count_for_company(company),
    }
    return render(request, "accounts/dashboard_empresa.html", context)


@login_required
def company_meis(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    form = EmployeeSearchForm(request.GET or None)
    create_mei_form = CompanyMEICreateForm(company=company)
    link_for_id = (request.GET.get("link_for") or "").strip()
    link_for_employee = None
    if company and link_for_id:
        link_for_employee = Employee.objects.filter(
            id=link_for_id,
            company=company,
            user__role=User.Role.FUNCIONARIO,
        ).first()

    link_initial = {}
    if link_for_employee:
        link_initial["employee"] = link_for_employee
    create_link_form = CompanyContractForm(company=company, request=request, prefix="link", initial=link_initial)
    tab_filter = (request.GET.get("tab") or "").strip().lower()
    legacy_activation_filter = (request.GET.get("activation") or "").strip().lower()
    if not tab_filter and legacy_activation_filter:
        tab_filter = {
            "all": "todos",
            "active": "ativos",
            "pending": "pendentes",
            "inactive": "encerrados",
        }.get(legacy_activation_filter, "todos")
    if tab_filter not in {"todos", "ativos", "pendentes", "encerrados"}:
        tab_filter = "todos"
    activation_link = request.build_absolute_uri(reverse("password_reset"))

    if request.method == "POST":
        action = (request.POST.get("action") or "create_mei").strip().lower()
        if action == "end_contract":
            contract_id = (request.POST.get("contract_id") or "").strip()
            contract = (
                Contract.objects.select_related("employee", "employee__user", "company")
                .filter(
                    id=contract_id,
                    company=company,
                    employee__company=company,
                    employee__user__role=User.Role.FUNCIONARIO,
                )
                .first()
            )
            if not contract:
                return redirect(f"{reverse('company_meis')}?status=invalid_contract")
            if contract.is_active:
                contract.is_active = False
                contract.end_date = timezone.localdate()
                contract.save(update_fields=["is_active", "end_date"])
            redirect_target = _safe_redirect_target(
                request,
                f"{reverse('company_meis')}?tab=encerrados&status=contract_ended&highlight_employee={contract.employee_id}",
            )
            return redirect(redirect_target)
        if action in {"deactivate_access", "reactivate_access"}:
            employee_id = (request.POST.get("employee_id") or "").strip()
            employee = (
                Employee.objects.select_related("user")
                .filter(
                    id=employee_id,
                    company=company,
                    user__role=User.Role.FUNCIONARIO,
                )
                .first()
            )
            if not employee:
                return redirect(f"{reverse('company_meis')}?status=invalid_employee")

            should_activate = action == "reactivate_access"
            if should_activate and employee.ended_at:
                return redirect(f"{reverse('company_meis')}?status=relationship_ended&highlight_employee={employee.id}")
            if employee.is_active != should_activate:
                employee.is_active = should_activate
                employee.save(update_fields=["is_active"])

            if employee.user and employee.user.is_active != should_activate:
                employee.user.is_active = should_activate
                employee.user.save(update_fields=["is_active"])

            status_key = "access_reactivated" if should_activate else "access_deactivated"
            redirect_target = _safe_redirect_target(
                request,
                f"{reverse('company_meis')}?status={status_key}&highlight_employee={employee.id}",
            )
            return redirect(redirect_target)
        if action == "create_link":
            create_link_form = CompanyContractForm(
                request.POST,
                request.FILES,
                company=company,
                request=request,
                prefix="link",
            )
            if not company:
                create_link_form.add_error(None, "Cliente nao encontrado para criar contrato.")
            elif create_link_form.is_valid():
                employee = create_link_form.cleaned_data.get("employee")
                if not employee or not Employee.objects.filter(id=employee.id, company=company).exists():
                    create_link_form.add_error("employee", "MEI invalido para esta empresa.")
                else:
                    contract = create_link_form.save(commit=False)
                    contract.company = company
                    contract.save()
                    return redirect(f"{reverse('company_meis')}?status=link_created&highlight_employee={employee.id}")
            create_mei_form = CompanyMEICreateForm(company=company)
        else:
            create_mei_form = CompanyMEICreateForm(request.POST, request.FILES, company=company)
            if not company:
                create_mei_form.add_error(None, "Empresa nao encontrada para criar MEI.")
            elif create_mei_form.is_valid():
                employee, contract, link_result = create_mei_form.create_or_link_mei_and_optional_contract(company)
                if link_result:
                    if link_result.user_created:
                        status = "created_with_contract" if contract else "created_mei"
                    else:
                        status = "linked_existing_with_contract" if contract else "linked_existing"
                    return redirect(f"{reverse('company_meis')}?status={status}&highlight_employee={employee.id}")
            create_link_form = CompanyContractForm(company=company, request=request, prefix="link", initial=link_initial)

    if company:
        qs = Employee.objects.filter(company=company).select_related("user")
    else:
        qs = Employee.objects.none()

    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(user__email__icontains=q) | Q(user__username__icontains=q))

    employees_list = list(qs.order_by("full_name")[:300])
    contracts_by_employee = _contracts_by_employee(company, employees_list)
    employee_ids = [employee.id for employee in employees_list]
    latest_punch_by_employee = {}
    if employee_ids:
        latest_punches = (
            Punch.all_objects.filter(contract__company=company, contract__employee_id__in=employee_ids)
            .select_related("contract", "contract__employee")
            .order_by("contract__employee_id", "-timestamp")
        )
        for punch in latest_punches:
            latest_punch_by_employee.setdefault(punch.contract.employee_id, punch)

    def _contract_status_for_row(current_contract, latest_contract, operational_count):
        if current_contract:
            return {
                "key": "active",
                "label": "Contrato ativo",
                "hint": f"Contrato vigente desde {current_contract.start_date:%d/%m/%Y}.",
                "tone": "success",
            }
        if latest_contract:
            if latest_contract.end_date and latest_contract.end_date < timezone.localdate():
                label = "Vínculo encerrado"
                hint = f"Encerrado em {latest_contract.end_date:%d/%m/%Y}."
                key = "ended"
            elif not latest_contract.is_active:
                label = "Vínculo encerrado"
                hint = "Contrato inativo. Histórico preservado para consulta."
                key = "ended"
            else:
                label = "Contrato pendente"
                hint = "Contrato cadastrado, mas ainda sem vigência operacional."
                key = "pending"
            return {"key": key, "label": label, "hint": hint, "tone": "warn" if key == "ended" else "pending"}
        return {
            "key": "missing",
            "label": "Sem contrato",
            "hint": "Configure um contrato para liberar o registro de ponto.",
            "tone": "pending",
        }

    def _prestador_tab_key(employee, activation, current_contract, latest_contract, contract_status):
        if getattr(employee, "ended_at", None) or contract_status["key"] == "ended":
            return "encerrados"
        if activation["key"] == "pending" or contract_status["key"] in {"missing", "pending"}:
            return "pendentes"
        if activation["key"] == "inactive":
            return "pendentes"
        if current_contract:
            return "ativos"
        return "pendentes"

    employee_rows = []
    tab_counts = {"todos": 0, "ativos": 0, "pendentes": 0, "encerrados": 0}
    for employee in employees_list:
        employee_contracts = contracts_by_employee.get(employee.id, [])
        lifecycle = employee_lifecycle_summary(employee, employee_contracts)
        activation = _employee_activation_summary(employee)
        latest_contract = employee_contracts[0] if employee_contracts else None
        current_contract = next((contract for contract in employee_contracts if contract_is_operational(contract)), None)
        operational_count = sum(1 for contract in employee_contracts if contract_is_operational(contract))
        contract_status = _contract_status_for_row(current_contract, latest_contract, operational_count)
        row_tab_key = _prestador_tab_key(employee, activation, current_contract, latest_contract, contract_status)
        tab_counts["todos"] += 1
        tab_counts[row_tab_key] += 1
        if tab_filter != "todos" and row_tab_key != tab_filter:
            continue
        display_contract = current_contract or latest_contract
        latest_punch = latest_punch_by_employee.get(employee.id)
        manage_contracts_url = (
            f"{reverse('company_contracts')}?edit={latest_contract.id}"
            if latest_contract
            else reverse("company_contracts")
        )
        setup_first_link_url = f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente"
        activation_copy_text = (
            "Ative seu acesso no HoraCerta em "
            f"{activation_link} usando o email {employee.user.email or employee.user.username}."
        )
        activation_mailto_url = (
            "mailto:"
            f"{quote(employee.user.email or employee.user.username)}"
            "?subject=Ativacao%20do%20acesso%20HoraCerta"
            f"&body={quote(activation_copy_text)}"
        )
        employee_rows.append(
            {
                "employee": employee,
                "state": lifecycle,
                "activation": activation,
                "tab_key": row_tab_key,
                "contract_status": contract_status,
                "total_contracts": len(employee_contracts),
                "active_contracts": operational_count,
                "latest_contract": latest_contract,
                "current_contract": current_contract,
                "display_contract": display_contract,
                "latest_punch": latest_punch,
                "profile_url": reverse("company_mei_profile", args=[employee.id]),
                "situation_url": reverse("company_mei_profile", args=[employee.id]),
                "manage_contracts_url": manage_contracts_url,
                "setup_first_link_url": setup_first_link_url,
                "action_url": setup_first_link_url if not latest_contract else manage_contracts_url,
                "action_label": "Configurar primeiro contrato" if not latest_contract else "Gerenciar contratos",
                "activation_link": activation_link,
                "activation_copy_text": activation_copy_text,
                "activation_mailto_url": activation_mailto_url,
            }
        )

    context = {
        "company": company,
        "employees": employee_rows,
        "employee_search_form": form,
        "create_mei_form": create_mei_form,
        "create_link_form": create_link_form,
        "link_for_employee": link_for_employee,
        "highlight_employee_id": (request.GET.get("highlight_employee") or "").strip(),
        "show_flow_notice": (request.GET.get("flow") or "").strip() == "principal",
        "tab_filter": tab_filter,
        "tab_counts": tab_counts,
        "activation_link": activation_link,
        "pending_reports_count": _pending_reports_count_for_company(company),
    }
    return render(request, "accounts/company_meis.html", context)


@login_required
@require_GET
def company_mei_email_status(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return JsonResponse({"ok": False, "status": "forbidden"}, status=403)

    company = _company_for_user(request.user)
    raw_email = (request.GET.get("email") or "").strip().lower()
    if not raw_email:
        return JsonResponse({"ok": False, "status": "invalid_email", "message": "Informe um email valido."}, status=400)

    user = User.objects.filter(Q(email__iexact=raw_email) | Q(username__iexact=raw_email)).first()
    if not user:
        return JsonResponse(
            {
                "ok": True,
                "status": "new",
                "message": "Novo email: sera criada a conta principal do MEI com senha.",
            }
        )

    if user.role != User.Role.FUNCIONARIO:
        return JsonResponse(
            {
                "ok": True,
                "status": "conflict",
                "message": "Este email pertence a uma conta de empresa/admin. Use outro email do MEI.",
            }
        )

    if company and Employee.objects.filter(user=user, company=company).exists():
        return JsonResponse(
            {
                "ok": True,
                "status": "already_linked",
                "message": "Este MEI ja possui contrato com este cliente. Use o gerenciamento de contratos.",
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "status": "existing",
            "message": (
                "Este profissional ja possui conta no HoraCerta. "
                "Sera criado apenas um novo contrato com este cliente."
            ),
        }
    )


@login_required
def company_contracts(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    contracts_qs_all = (
        Contract.objects.filter(company=company).select_related("employee", "employee__user", "company")
        if company
        else Contract.objects.none()
    )
    contracts_qs = contracts_qs_all.filter(employee__isnull=False, employee__user__isnull=False)

    edit_contract = None
    edit_form = None
    invalid_edit_contract = False
    edit_id = (request.GET.get("edit") or "").strip()
    create_for_id = (request.GET.get("create_for") or "").strip()

    if create_for_id and not edit_id:
        return redirect(f"{reverse('company_meis')}?flow=principal")

    if edit_id and company:
        edit_contract = contracts_qs.filter(id=edit_id).first()
        invalid_edit_contract = edit_contract is None

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "create":
            return redirect(f"{reverse('company_meis')}?flow=principal")
        if action == "update":
            contract_id = (request.POST.get("contract_id") or "").strip()
            instance = contracts_qs.filter(id=contract_id).first() if contract_id and company else None
            if not instance:
                invalid_edit_contract = True
            else:
                edit_form = CompanyContractForm(request.POST, request.FILES, instance=instance, company=company, request=request)
                if edit_form.is_valid():
                    employee = edit_form.cleaned_data.get("employee")
                    if not employee or not Employee.objects.filter(id=employee.id, company=company).exists():
                        edit_form.add_error("employee", "MEI invalido para esta empresa.")
                        edit_contract = instance
                    else:
                        contract = edit_form.save(commit=False)
                        contract.company = company
                        contract.save()
                        return redirect(f"{reverse('company_contracts')}?status=updated")
                edit_contract = instance
        else:
            return redirect(f"{reverse('company_contracts')}?flow=only_edit")

    if request.method != "POST" and edit_contract:
        edit_form = CompanyContractForm(instance=edit_contract, company=company, request=request)

    employees = list(
        Employee.objects.filter(company=company, user__role=User.Role.FUNCIONARIO)
        .select_related("user")
        .order_by("full_name")[:400]
    ) if company else []
    contracts_by_employee = _contracts_by_employee(company, employees)
    pending_without_contracts = []
    for employee in employees:
        employee_contracts = contracts_by_employee.get(employee.id, [])
        latest_contract = employee_contracts[0] if employee_contracts else None
        has_contract = latest_contract is not None
        needs_contract = not has_contract

        if needs_contract:
            status_label = "Aguardando contrato"
            status_tone = "pending"
            status_hint = "Profissional cadastrado sem contrato operacional. Use a tela de MEIs como fluxo principal."
            action_url = f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente"
            pending_without_contracts.append(
                {
                    "employee": employee,
                    "state": {
                        "label": status_label,
                        "hint": status_hint,
                        "tone": status_tone,
                    },
                    "action_url": action_url,
                }
            )

    contract_rows = []
    for contract in contracts_qs.order_by("-start_date", "-created_at"):
        employee = getattr(contract, "employee", None)
        employee_user = getattr(employee, "user", None) if employee else None
        if not employee or not employee_user:
            continue
        if company and employee.company_id != company.id:
            continue

        is_operational = contract_is_operational(contract)
        if is_operational:
            status_label = "Ativo operacional"
            status_tone = "success"
        elif not contract.is_active:
            status_label = "Inativo"
            status_tone = "warn"
        elif contract.start_date and contract.start_date > timezone.localdate():
            status_label = "Aguardando inicio"
            status_tone = "pending"
        elif contract.end_date and contract.end_date < timezone.localdate():
            status_label = "Encerrado"
            status_tone = "warn"
        else:
            status_label = "Ativo sem vigencia operacional"
            status_tone = "pending"

        contract_rows.append(
            {
                "contract": contract,
                "employee": employee,
                "status_label": status_label,
                "status_tone": status_tone,
                "is_operational": is_operational,
                "profile_url": reverse("company_mei_profile", args=[employee.id]),
                "edit_url": f"{reverse('company_contracts')}?edit={contract.id}",
            }
        )

    inconsistent_filters = contracts_qs_all.filter(employee__isnull=True) | contracts_qs_all.filter(employee__user__isnull=True)
    if company:
        inconsistent_filters = inconsistent_filters | contracts_qs_all.exclude(employee__company_id=company.id)
    inconsistent_contracts_count = inconsistent_filters.distinct().count()

    return render(
        request,
        "accounts/company_contracts.html",
        {
            "company": company,
            "contracts": contract_rows,
            "edit_form": edit_form,
            "edit_contract": edit_contract,
            "invalid_edit_contract": invalid_edit_contract,
            "pending_without_contracts": pending_without_contracts[:12],
            "inconsistent_contracts_count": inconsistent_contracts_count,
            "show_creation_redirect_notice": (request.GET.get("flow") or "").strip() == "principal",
            "show_only_edit_notice": (request.GET.get("flow") or "").strip() == "only_edit",
        },
    )


@login_required
def company_mei_profile(request, employee_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    employee = get_object_or_404(
        Employee.objects.select_related("user"),
        id=employee_id,
        company=company,
        user__role=User.Role.FUNCIONARIO,
    )
    contracts = list(
        Contract.objects.filter(
            company=company,
            employee=employee,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .select_related("employee", "employee__user", "company")
        .order_by("-start_date", "-created_at")
    )
    lifecycle = employee_lifecycle_summary(employee, contracts)
    activation = _employee_activation_summary(employee)
    latest_contract = contracts[0] if contracts else None
    active_contracts = sum(1 for contract in contracts if contract_is_operational(contract))

    return render(
        request,
        "accounts/company_mei_profile.html",
        {
            "company": company,
            "employee": employee,
            "state": lifecycle,
            "activation": activation,
            "contracts": contracts,
            "latest_contract": latest_contract,
            "active_contracts": active_contracts,
            "create_contract_url": f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente",
            "edit_contract_url": f"{reverse('company_contracts')}?edit={latest_contract.id}" if latest_contract else None,
            "history_url": f"{reverse('company_history')}?employee={employee.id}",
            "closure_url": f"{reverse('company_mei_closure', args=[employee.id])}",
            "meis_url": reverse("company_meis"),
            "activation_link": request.build_absolute_uri(reverse("password_reset")),
        },
    )


@login_required
def company_mei_closure(request, employee_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    employee = get_object_or_404(
        Employee.objects.select_related("user"),
        id=employee_id,
        company=company,
        user__role=User.Role.FUNCIONARIO,
    )

    period_form = PeriodSearchForm(request.GET or None)
    today = timezone.localdate()
    first_day = today.replace(day=1)
    date_from = first_day
    date_to = today
    if period_form.is_valid():
        date_from = period_form.cleaned_data.get("date_from") or first_day
        date_to = period_form.cleaned_data.get("date_to") or today
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    contracts = list(
        Contract.objects.filter(
            company=company,
            employee=employee,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .select_related("company", "employee", "employee__user")
        .order_by("-start_date", "-created_at")
    )
    current_contract = next((item for item in contracts if contract_is_operational(item)), contracts[0] if contracts else None)

    start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max))

    punches = list(
        Punch.objects.filter(contract__in=contracts, timestamp__range=(start_dt, end_dt))
        .select_related("contract", "contract__company", "contract__employee", "contract__employee__user")
        .order_by("timestamp")
    )
    grouped_rows, _max_cols = build_daily_summary(punches, min_punch_columns=4)
    rows_by_date = {row["date"]: row for row in grouped_rows}
    daily_rows = []
    current_day = date_from
    while current_day <= date_to:
        existing = rows_by_date.get(current_day)
        if existing:
            row = existing
            punches_label = " - ".join(row["punch_times"]) if row["punch_times"] else "-"
            if row["is_incomplete"]:
                status_label = "Incompleto"
                status_tone = "warn"
            else:
                status_label = "Completo"
                status_tone = "ok"
        else:
            row = {
                "date": current_day,
                "punches_count": 0,
                "punch_times": [],
                "total_seconds": 0,
                "total_hours_hhmm": "00:00",
                "is_incomplete": False,
            }
            punches_label = "-"
            status_label = "Sem registros"
            status_tone = "empty"
        row["punches_label"] = punches_label
        row["status_label"] = status_label
        row["status_tone"] = status_tone
        daily_rows.append(row)
        current_day += timedelta(days=1)
    daily_rows = sorted(daily_rows, key=lambda item: item["date"], reverse=True)

    days_with_records = sum(1 for row in daily_rows if row["punches_count"] > 0)
    total_punches = sum(row["punches_count"] for row in daily_rows)
    total_seconds = sum(row["total_seconds"] for row in daily_rows)
    total_hours_hhmm = format_hhmm(total_seconds)
    complete_days = sum(1 for row in daily_rows if row["punches_count"] > 0 and not row["is_incomplete"])
    incomplete_days = sum(1 for row in daily_rows if row["punches_count"] > 0 and row["is_incomplete"])
    quality_metrics = _compute_validation_quality_metrics(punches)

    service_reports = list(
        ServiceReport.objects.filter(
            company=company,
            employee=employee,
            report_date__gte=date_from,
            report_date__lte=date_to,
        )
        .select_related("contract", "company")
        .order_by("-report_date", "-created_at")[:200]
    )

    rates_by_day = {}
    for punch in punches:
        day_key = timezone.localtime(punch.timestamp).date()
        rates_by_day.setdefault(day_key, {})[punch.contract_id] = punch.contract.hourly_rate or Decimal("0")

    estimated_value = Decimal("0.00")
    for row in grouped_rows:
        day_rates = rates_by_day.get(row["date"], {})
        if day_rates:
            # Reaproveita a logica simples: usa taxa media dos contratos registrados no dia.
            avg_rate = sum(day_rates.values(), Decimal("0")) / Decimal(len(day_rates))
            estimated_value += (Decimal(row["total_seconds"]) / Decimal("3600")) * avg_rate

    current_hourly_rate = current_contract.hourly_rate if current_contract else None
    if estimated_value == Decimal("0.00") and current_hourly_rate and total_seconds > 0:
        estimated_value = (Decimal(total_seconds) / Decimal("3600")) * (current_hourly_rate or Decimal("0"))
    estimated_value = estimated_value.quantize(Decimal("0.01"))

    def _as_brl(value):
        brl = f"{(value or Decimal('0')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {brl}"

    period_label = f"{date_from.strftime('%d/%m/%Y')} ate {date_to.strftime('%d/%m/%Y')}"
    export_kind = (request.GET.get("export") or "").strip().lower()
    if export_kind == "pdf":
        employee_name = employee.full_name or employee.user.email or employee.user.username
        lines = [
            "HoraCerta - Fechamento individual do profissional",
            f"Empresa: {company.name if company else '-'}",
            f"Profissional: {employee_name}",
            f"Periodo: {period_label}",
            f"Dias com registro: {days_with_records}",
            f"Total de horarios: {total_punches}",
            f"Total de horas: {total_hours_hhmm}",
            f"Dias completos: {complete_days}",
            f"Dias incompletos: {incomplete_days}",
            f"Valor/hora atual: {_as_brl(current_hourly_rate) if current_hourly_rate else '-'}",
            f"Valor acumulado no periodo: {_as_brl(estimated_value)}",
            "",
            "Qualidade de validacao:",
            f"Registros no local: {quality_metrics['validated_on_site']}",
            f"Registros com QR confirmado: {quality_metrics['qr_confirmed']}",
            f"Registros fora do raio: {quality_metrics['out_of_radius']}",
            f"Registros sem localizacao: {quality_metrics['no_location']}",
            f"Registros pendentes de revisao: {quality_metrics['pending_review']}",
            "",
            "Conferencia diaria (maximo 35 linhas):",
        ]
        for row in daily_rows[:35]:
            lines.append(
                f"{row['date'].strftime('%d/%m/%Y')} | qtd={row['punches_count']} | {row['punches_label']} | total={row['total_hours_hhmm']} | {row['status_label']}"
            )
        if service_reports:
            lines.append("")
            lines.append("Relatorios no periodo (maximo 10 linhas):")
            for report in service_reports[:10]:
                lines.append(f"{report.report_date.strftime('%d/%m/%Y')} | {report.title}")
        return _build_pdf_response("horacerta_fechamento_individual.pdf", lines)

    context = {
        "company": company,
        "employee": employee,
        "period_form": period_form,
        "period_label": period_label,
        "date_from_value": date_from.strftime("%Y-%m-%d"),
        "date_to_value": date_to.strftime("%Y-%m-%d"),
        "current_contract": current_contract,
        "days_with_records": days_with_records,
        "total_punches": total_punches,
        "total_hours_hhmm": total_hours_hhmm,
        "complete_days": complete_days,
        "incomplete_days": incomplete_days,
        "quality_validated_on_site": quality_metrics["validated_on_site"],
        "quality_qr_confirmed": quality_metrics["qr_confirmed"],
        "quality_out_of_radius": quality_metrics["out_of_radius"],
        "quality_no_location": quality_metrics["no_location"],
        "quality_pending_review": quality_metrics["pending_review"],
        "current_hourly_rate": current_hourly_rate,
        "current_hourly_rate_brl": _as_brl(current_hourly_rate) if current_hourly_rate else "-",
        "estimated_value": estimated_value,
        "estimated_value_brl": _as_brl(estimated_value),
        "daily_rows": daily_rows,
        "service_reports": service_reports,
        "history_url": f"{reverse('company_history')}?employee={employee.id}&date_from={date_from.strftime('%Y-%m-%d')}&date_to={date_to.strftime('%Y-%m-%d')}",
        "profile_url": reverse("company_mei_profile", args=[employee.id]),
    }
    return render(request, "accounts/company_mei_closure.html", context)


@login_required
def company_history(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    period_form = PeriodSearchForm(request.GET or None)
    employees = Employee.objects.filter(company=company).select_related("user").order_by("full_name") if company else Employee.objects.none()

    selected_employee = (request.GET.get("employee") or "").strip()

    today = timezone.localdate()
    first_day = today.replace(day=1)
    date_from = first_day
    date_to = today
    if period_form.is_valid():
        date_from = period_form.cleaned_data.get("date_from") or first_day
        date_to = period_form.cleaned_data.get("date_to") or today
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    selected_employee_obj = employees.filter(id=selected_employee).first() if selected_employee else None
    month_start = _parse_year_month(request.GET.get("month")) or today.replace(day=1)
    month_first_weekday, month_days_count = monthrange(month_start.year, month_start.month)
    month_end = month_start.replace(day=month_days_count)
    selected_day = _parse_iso_date(request.GET.get("selected_day"))
    if selected_day and (selected_day < month_start or selected_day > month_end):
        selected_day = None

    contracts_qs = Contract.objects.none()
    punches_qs = Punch.objects.none()
    history_rows = []
    summary_days_with_records = 0
    summary_total_punches = 0
    summary_total_seconds = 0
    summary_total_hours = "00:00"
    summary_incomplete_days = 0
    period_label = f"{date_from.strftime('%d/%m/%Y')} ate {date_to.strftime('%d/%m/%Y')}"
    calendar_weeks = []
    calendar_day_detail = None
    calendar_month_label = month_start.strftime("%m/%Y")
    weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    next_month_start = (month_end + timedelta(days=1)).replace(day=1)

    def build_history_query(extra_params):
        query = {}
        if selected_employee:
            query["employee"] = selected_employee
        period_from_value = (request.GET.get("date_from") or "").strip()
        period_to_value = (request.GET.get("date_to") or "").strip()
        if period_from_value:
            query["date_from"] = period_from_value
        if period_to_value:
            query["date_to"] = period_to_value
        query.update(extra_params)
        return urlencode(query)

    if selected_employee_obj and company:
        contracts_qs = Contract.objects.filter(
            company=company,
            employee=selected_employee_obj,
            employee__isnull=False,
            employee__user__isnull=False,
        ).select_related("employee", "employee__user", "company")

        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        end_dt = timezone.make_aware(datetime.combine(date_to, time.max))
        punches_qs = Punch.objects.filter(contract__in=contracts_qs, timestamp__range=(start_dt, end_dt)).select_related(
            "contract", "contract__employee", "contract__employee__user"
        )

        grouped_rows, _max_punches = build_daily_summary(list(punches_qs.order_by("timestamp")), min_punch_columns=4)
        history_rows = sorted(grouped_rows, key=lambda row: row["date"], reverse=True)
        for row in history_rows:
            row["punches_label"] = " - ".join(row["punch_times"]) if row["punch_times"] else "-"
            row["status_label"] = "Incompleto" if row["is_incomplete"] else "Completo"
            row["status_tone"] = "warn" if row["is_incomplete"] else "ok"

        summary_days_with_records = len(history_rows)
        summary_total_punches = sum(row["punches_count"] for row in history_rows)
        summary_total_seconds = sum(row["total_seconds"] for row in history_rows)
        summary_total_hours = format_hhmm(summary_total_seconds)
        summary_incomplete_days = sum(1 for row in history_rows if row["is_incomplete"])

        calendar_start_dt = timezone.make_aware(datetime.combine(month_start, time.min))
        calendar_end_dt = timezone.make_aware(datetime.combine(month_end, time.max))
        calendar_punches_qs = Punch.objects.filter(
            contract__in=contracts_qs,
            timestamp__range=(calendar_start_dt, calendar_end_dt),
        ).select_related("contract", "contract__employee", "contract__employee__user")
        calendar_grouped_rows, _calendar_cols = build_daily_summary(list(calendar_punches_qs.order_by("timestamp")), min_punch_columns=4)
        calendar_by_day = {row["date"]: row for row in calendar_grouped_rows}

        calendar_cells = [None] * month_first_weekday
        for day_number in range(1, month_days_count + 1):
            day_date = month_start.replace(day=day_number)
            day_row = calendar_by_day.get(day_date)
            if day_row:
                status_key = "incomplete" if day_row["is_incomplete"] else "complete"
                status_label = "Incompleto" if day_row["is_incomplete"] else "Completo"
                punches_label = " - ".join(day_row["punch_times"]) if day_row["punch_times"] else "-"
                punches_count = day_row["punches_count"]
                total_hours_hhmm = day_row["total_hours_hhmm"]
            else:
                status_key = "empty"
                status_label = "Sem registros"
                punches_label = "-"
                punches_count = 0
                total_hours_hhmm = "00:00"

            day_query = build_history_query(
                {
                    "month": month_start.strftime("%Y-%m"),
                    "selected_day": day_date.strftime("%Y-%m-%d"),
                }
            )
            cell = {
                "date": day_date,
                "day_number": day_number,
                "status_key": status_key,
                "status_label": status_label,
                "punches_label": punches_label,
                "punches_count": punches_count,
                "total_hours_hhmm": total_hours_hhmm,
                "query": day_query,
                "is_selected": bool(selected_day and selected_day == day_date),
            }
            calendar_cells.append(cell)

            if selected_day and selected_day == day_date:
                calendar_day_detail = cell

        while len(calendar_cells) % 7 != 0:
            calendar_cells.append(None)
        calendar_weeks = [calendar_cells[index : index + 7] for index in range(0, len(calendar_cells), 7)]

    export_kind = (request.GET.get("export") or "").strip().lower()
    if export_kind in {"csv", "xlsx", "pdf"} and selected_employee_obj:
        export_rows = []
        for row in history_rows:
            export_rows.append(
                [
                    row["date"].strftime("%d/%m/%Y"),
                    row["punches_count"],
                    row["punches_label"],
                    row["total_hours_hhmm"],
                    row["status_label"],
                ]
            )

        headers = ["Data", "Quantidade de horarios", "Horarios registrados", "Total do dia", "Status do dia"]
        employee_name = selected_employee_obj.full_name or selected_employee_obj.user.email or selected_employee_obj.user.username
        if export_kind == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="horacerta_historico_profissional.csv"'
            writer = csv.writer(response)
            writer.writerow([f"Empresa: {company.name if company else '-'}"])
            writer.writerow([f"Profissional: {employee_name}"])
            writer.writerow([f"Periodo: {period_label}"])
            writer.writerow([])
            writer.writerow(headers)
            for line in export_rows:
                writer.writerow(line)
            return response

        if export_kind == "xlsx":
            return _build_xlsx_response("horacerta_historico_profissional.xlsx", headers, export_rows)

        if export_kind == "pdf":
            lines = [
                "HoraCerta - Historico do profissional",
                f"Empresa: {company.name if company else '-'}",
                f"Profissional: {employee_name}",
                f"Periodo: {period_label}",
                f"Dias com registro: {summary_days_with_records}",
                f"Total de horarios: {summary_total_punches}",
                f"Total de horas: {summary_total_hours}",
                f"Dias incompletos: {summary_incomplete_days}",
                "",
                "Tabela de conferencia (maximo 45 linhas no PDF):",
            ]
            for row in history_rows[:45]:
                lines.append(
                    f"{row['date'].strftime('%d/%m/%Y')} | qtd={row['punches_count']} | {row['punches_label']} | total={row['total_hours_hhmm']} | {row['status_label']}"
                )
            return _build_pdf_response("horacerta_historico_profissional.pdf", lines)

    context = {
        "company": company,
        "period_form": period_form,
        "employees": employees,
        "selected_employee": selected_employee,
        "selected_employee_obj": selected_employee_obj,
        "history_rows": history_rows,
        "period_label": period_label,
        "summary_days_with_records": summary_days_with_records,
        "summary_total_punches": summary_total_punches,
        "summary_total_hours": summary_total_hours,
        "summary_incomplete_days": summary_incomplete_days,
        "summary_total_seconds": summary_total_seconds,
        "calendar_month_label": calendar_month_label,
        "calendar_month_iso": month_start.strftime("%Y-%m"),
        "calendar_weekday_labels": weekday_labels,
        "calendar_weeks": calendar_weeks,
        "calendar_day_detail": calendar_day_detail,
        "calendar_prev_query": build_history_query({"month": prev_month_start.strftime("%Y-%m")}),
        "calendar_next_query": build_history_query({"month": next_month_start.strftime("%Y-%m")}),
        "calendar_current_query": build_history_query({"month": today.replace(day=1).strftime("%Y-%m")}),
    }
    return render(request, "accounts/company_history.html", context)


@login_required
def company_today_center(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    today = timezone.localdate()
    now_local = timezone.localtime()
    today_start_dt = timezone.make_aware(datetime.combine(today, time.min))
    today_end_dt = timezone.make_aware(datetime.combine(today, time.max))

    operational_contracts_qs = (
        Contract.objects.filter(
            company=company,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .filter(contract_operational_q())
        .select_related("employee", "employee__user", "company")
        if company
        else Contract.objects.none()
    )
    operational_contracts = list(operational_contracts_qs.order_by("employee__full_name"))

    operational_by_employee = {}
    for contract in operational_contracts:
        operational_by_employee.setdefault(contract.employee_id, contract)

    today_punches = list(
        Punch.objects.filter(contract__in=operational_contracts_qs, timestamp__range=(today_start_dt, today_end_dt))
        .select_related("contract", "contract__employee", "contract__employee__user")
        .order_by("timestamp")
    )

    times_by_employee = defaultdict(list)
    for punch in today_punches:
        local_ts = timezone.localtime(punch.timestamp)
        times_by_employee[punch.contract.employee_id].append(local_ts)

    no_records_rows = []
    in_progress_rows = []
    finished_rows = []
    incomplete_rows = []
    status_rows = []

    for employee_id, contract in operational_by_employee.items():
        employee = contract.employee
        day_times = sorted(times_by_employee.get(employee_id, []))
        punches_count = len(day_times)
        total_seconds, is_incomplete = compute_day_total(day_times)
        total_hours_hhmm = format_hhmm(total_seconds)
        punches_label = " - ".join(ts.strftime("%H:%M") for ts in day_times) if day_times else "-"

        if punches_count == 0:
            status_key = "no_records"
            status_label = "Sem registros hoje"
            status_tone = "neutral"
        elif is_incomplete and now_local.hour >= 20:
            status_key = "incomplete"
            status_label = "Dia incompleto"
            status_tone = "warn"
        elif is_incomplete:
            status_key = "in_progress"
            status_label = "Jornada em andamento"
            status_tone = "progress"
        else:
            status_key = "finished"
            status_label = "Dia finalizado"
            status_tone = "ok"

        row = {
            "employee": employee,
            "contract": contract,
            "status_key": status_key,
            "status_label": status_label,
            "status_tone": status_tone,
            "punches_count": punches_count,
            "punches_label": punches_label,
            "total_hours_hhmm": total_hours_hhmm,
            "history_url": (
                f"{reverse('company_history')}?employee={employee.id}&date_from={today.strftime('%Y-%m-%d')}"
                f"&date_to={today.strftime('%Y-%m-%d')}"
            ),
            "profile_url": reverse("company_mei_profile", args=[employee.id]),
        }
        status_rows.append(row)
        if status_key == "no_records":
            no_records_rows.append(row)
        elif status_key == "in_progress":
            in_progress_rows.append(row)
        elif status_key == "finished":
            finished_rows.append(row)
        elif status_key == "incomplete":
            incomplete_rows.append(row)

    reports_today_qs = (
        ServiceReport.objects.filter(company=company, created_at__range=(today_start_dt, today_end_dt))
        .select_related("employee", "employee__user", "contract")
        .order_by("-created_at")
        if company
        else ServiceReport.objects.none()
    )
    reports_today = list(reports_today_qs[:12])

    context = {
        "company": company,
        "today": today,
        "total_professionals_with_records_today": sum(1 for row in status_rows if row["punches_count"] > 0),
        "total_punches_today": len(today_punches),
        "journeys_in_progress_count": len(in_progress_rows),
        "incomplete_days_count": len(incomplete_rows),
        "service_reports_today_count": reports_today_qs.count(),
        "no_records_rows": no_records_rows[:30],
        "in_progress_rows": in_progress_rows[:30],
        "finished_rows": finished_rows[:30],
        "incomplete_rows": incomplete_rows[:30],
        "reports_today": reports_today,
    }
    return render(request, "accounts/company_today_center.html", context)


@login_required
def company_operational_summary(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    period_form = PeriodSearchForm(request.GET or None)
    employees_qs = (
        Employee.objects.filter(company=company).select_related("user").order_by("full_name")
        if company
        else Employee.objects.none()
    )

    selected_employee = (request.GET.get("employee") or "").strip()
    selected_scope = (request.GET.get("scope") or "company").strip().lower()
    if selected_scope not in {"company"}:
        selected_scope = "company"

    today = timezone.localdate()
    first_day = today.replace(day=1)
    date_from = first_day
    date_to = today
    if period_form.is_valid():
        date_from = period_form.cleaned_data.get("date_from") or first_day
        date_to = period_form.cleaned_data.get("date_to") or today
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    filtered_employees_qs = employees_qs
    if selected_employee:
        filtered_employees_qs = filtered_employees_qs.filter(id=selected_employee)

    employees = list(filtered_employees_qs)
    contracts_qs = (
        Contract.objects.filter(
            company=company,
            employee__in=employees,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .filter(contract_operational_q())
        .select_related("employee", "employee__user", "company")
        if company and employees
        else Contract.objects.none()
    )

    start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max))
    punches = list(
        Punch.objects.filter(contract__in=contracts_qs, timestamp__range=(start_dt, end_dt))
        .select_related("contract", "contract__employee", "contract__employee__user")
        .order_by("timestamp")
    )

    rows_by_employee = {}
    for employee in employees:
        rows_by_employee[str(employee.id)] = {
            "employee": employee,
            "days_with_records": 0,
            "total_punches": 0,
            "total_seconds": 0,
            "total_hours_hhmm": "00:00",
            "incomplete_days": 0,
            "validated_on_site": 0,
            "qr_confirmed": 0,
            "out_of_radius": 0,
            "no_location": 0,
            "pending_review": 0,
            "status_label": "Sem registros no periodo",
            "status_kind": "empty",
            "details_url": (
                f"{reverse('company_history')}?employee={employee.id}&date_from={date_from.strftime('%Y-%m-%d')}"
                f"&date_to={date_to.strftime('%Y-%m-%d')}"
            ),
        }

    punches_by_employee_day = defaultdict(list)
    punches_by_employee = defaultdict(list)
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        employee_id = str(punch.contract.employee_id)
        punches_by_employee_day[(employee_id, local_ts.date())].append(local_ts)
        punches_by_employee[employee_id].append(punch)

    for (employee_id, _day), times in punches_by_employee_day.items():
        row = rows_by_employee.get(employee_id)
        if not row:
            continue
        ordered_times = sorted(times)
        total_seconds, is_incomplete = compute_day_total(ordered_times)
        row["days_with_records"] += 1
        row["total_punches"] += len(ordered_times)
        row["total_seconds"] += total_seconds
        if is_incomplete:
            row["incomplete_days"] += 1

    employee_rows = list(rows_by_employee.values())
    for row in employee_rows:
        row["total_hours_hhmm"] = format_hhmm(row["total_seconds"])
        quality_metrics = _compute_validation_quality_metrics(punches_by_employee.get(str(row["employee"].id), []))
        row["validated_on_site"] = quality_metrics["validated_on_site"]
        row["qr_confirmed"] = quality_metrics["qr_confirmed"]
        row["out_of_radius"] = quality_metrics["out_of_radius"]
        row["no_location"] = quality_metrics["no_location"]
        row["pending_review"] = quality_metrics["pending_review"]
        if row["total_punches"] == 0:
            row["status_label"] = "Sem registros no periodo"
            row["status_kind"] = "empty"
        elif row["incomplete_days"] > 0:
            row["status_label"] = f"Atencao: {row['incomplete_days']} dia(s) incompleto(s)"
            row["status_kind"] = "warn"
        else:
            row["status_label"] = "Operacao regular no periodo"
            row["status_kind"] = "ok"

    employee_rows.sort(
        key=lambda item: (
            -item["days_with_records"],
            -item["incomplete_days"],
            item["employee"].full_name.lower(),
        )
    )

    summary_professionals_with_records = sum(1 for row in employee_rows if row["days_with_records"] > 0)
    summary_total_punches = sum(row["total_punches"] for row in employee_rows)
    summary_total_seconds = sum(row["total_seconds"] for row in employee_rows)
    summary_total_incomplete_days = sum(row["incomplete_days"] for row in employee_rows)
    summary_quality = _compute_validation_quality_metrics(punches)

    export_kind = (request.GET.get("export") or "").strip().lower()
    if export_kind in {"csv", "xlsx", "pdf"}:
        export_rows = []
        for row in employee_rows:
            export_rows.append(
                [
                    row["employee"].full_name or row["employee"].user.email or row["employee"].user.username,
                    row["days_with_records"],
                    row["total_punches"],
                    row["total_hours_hhmm"],
                    row["incomplete_days"],
                    row["validated_on_site"],
                    row["qr_confirmed"],
                    row["out_of_radius"],
                    row["no_location"],
                    row["pending_review"],
                    row["status_label"],
                ]
            )
        headers = [
            "Profissional",
            "Dias com registro",
            "Total de horarios",
            "Total de horas",
            "Dias incompletos",
            "Validados no local",
            "QR confirmado",
            "Fora do raio",
            "Sem localizacao",
            "Pendentes de revisao",
            "Status",
        ]
        period_label = f"{date_from.strftime('%d/%m/%Y')} ate {date_to.strftime('%d/%m/%Y')}"
        if export_kind == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="horacerta_resumo_operacional.csv"'
            writer = csv.writer(response)
            writer.writerow([f"Empresa: {company.name if company else '-'}"])
            writer.writerow([f"Periodo: {period_label}"])
            writer.writerow([f"Profissionais com registro: {summary_professionals_with_records}"])
            writer.writerow([f"Total de horarios: {summary_total_punches}"])
            writer.writerow([f"Total de horas: {format_hhmm(summary_total_seconds)}"])
            writer.writerow([f"Dias incompletos: {summary_total_incomplete_days}"])
            writer.writerow([f"Validados no local: {summary_quality['validated_on_site']}"])
            writer.writerow([f"QR confirmado: {summary_quality['qr_confirmed']}"])
            writer.writerow([f"Fora do raio: {summary_quality['out_of_radius']}"])
            writer.writerow([f"Sem localizacao: {summary_quality['no_location']}"])
            writer.writerow([f"Pendentes de revisao: {summary_quality['pending_review']}"])
            writer.writerow([])
            writer.writerow(headers)
            for line in export_rows:
                writer.writerow(line)
            return response
        if export_kind == "xlsx":
            return _build_xlsx_response("horacerta_resumo_operacional.xlsx", headers, export_rows)
        lines = [
            "HoraCerta - Resumo operacional da empresa",
            f"Empresa: {company.name if company else '-'}",
            f"Periodo: {period_label}",
            f"Profissionais com registro: {summary_professionals_with_records}",
            f"Total de horarios: {summary_total_punches}",
            f"Total de horas: {format_hhmm(summary_total_seconds)}",
            f"Dias incompletos: {summary_total_incomplete_days}",
            "",
            "Qualidade de validacao consolidada:",
            f"Registros no local: {summary_quality['validated_on_site']}",
            f"Registros com QR confirmado: {summary_quality['qr_confirmed']}",
            f"Registros fora do raio: {summary_quality['out_of_radius']}",
            f"Registros sem localizacao: {summary_quality['no_location']}",
            f"Registros pendentes de revisao: {summary_quality['pending_review']}",
            "",
            "Resumo por profissional (maximo 40 linhas):",
        ]
        for row in employee_rows[:40]:
            lines.append(
                f"{row['employee'].full_name or row['employee'].user.email or row['employee'].user.username} | "
                f"qtd={row['total_punches']} | horas={row['total_hours_hhmm']} | "
                f"local={row['validated_on_site']} | qr={row['qr_confirmed']} | "
                f"fora={row['out_of_radius']} | sem_geo={row['no_location']} | pendente={row['pending_review']}"
            )
        return _build_pdf_response("horacerta_resumo_operacional.pdf", lines)

    context = {
        "company": company,
        "period_form": period_form,
        "employees": employees_qs,
        "selected_employee": selected_employee,
        "selected_scope": selected_scope,
        "selected_scope_label": "Empresa atual",
        "period_label": f"{date_from.strftime('%d/%m/%Y')} ate {date_to.strftime('%d/%m/%Y')}",
        "period_from": date_from.strftime("%Y-%m-%d"),
        "period_to": date_to.strftime("%Y-%m-%d"),
        "summary_professionals_with_records": summary_professionals_with_records,
        "summary_total_punches": summary_total_punches,
        "summary_total_hours": format_hhmm(summary_total_seconds),
        "summary_total_incomplete_days": summary_total_incomplete_days,
        "summary_quality_validated_on_site": summary_quality["validated_on_site"],
        "summary_quality_qr_confirmed": summary_quality["qr_confirmed"],
        "summary_quality_out_of_radius": summary_quality["out_of_radius"],
        "summary_quality_no_location": summary_quality["no_location"],
        "summary_quality_pending_review": summary_quality["pending_review"],
        "employee_rows": employee_rows,
    }
    return render(request, "accounts/company_operational_summary.html", context)


@login_required
def company_reports(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    employees = Employee.objects.filter(company=company).select_related("user").order_by("full_name") if company else Employee.objects.none()
    contracts = (
        Contract.objects.filter(
            company=company,
            employee__isnull=False,
            employee__user__isnull=False,
        ).select_related("employee", "employee__user")
        if company
        else Contract.objects.none()
    )

    selected_employee = (request.GET.get("employee") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    export_kind = (request.GET.get("export") or "").strip().lower()

    punches_qs = Punch.objects.filter(contract__in=contracts).select_related(
        "contract", "contract__employee", "contract__employee__user"
    )

    if selected_employee:
        punches_qs = punches_qs.filter(contract__employee_id=selected_employee)

    date_from = None
    date_to = None
    try:
        if date_from_raw:
            date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
        if date_to_raw:
            date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
    except ValueError:
        date_from = None
        date_to = None

    if date_from:
        punches_qs = punches_qs.filter(timestamp__gte=timezone.make_aware(datetime.combine(date_from, time.min)))
    if date_to:
        punches_qs = punches_qs.filter(timestamp__lte=timezone.make_aware(datetime.combine(date_to, time.max)))

    punches = list(punches_qs.order_by("-timestamp")[:5000])
    metrics = _compute_report_metrics(punches)
    daily_report_rows = []

    punches_by_contract = {}
    for punch in punches:
        punches_by_contract.setdefault(punch.contract_id, []).append(punch)

    for contract_punches in punches_by_contract.values():
        if not contract_punches:
            continue
        contract_punches_sorted = sorted(contract_punches, key=lambda item: item.timestamp)
        contract = contract_punches_sorted[0].contract
        mei_name = _contract_mei_label(contract)
        daily_rows, _max_cols = build_daily_summary(contract_punches_sorted, min_punch_columns=4)
        for row in daily_rows:
            daily_report_rows.append(
                {
                    "date": row["date"],
                    "company_name": contract.company.name,
                    "mei_name": mei_name,
                    "contract_label": f"{contract.company.name} - R$ {contract.hourly_rate}/h",
                    "status": row["status"],
                    "total_hours_hhmm": row["total_hours_hhmm"],
                    "punches_label": " | ".join(row["punch_times"]) if row["punch_times"] else "-",
                }
            )

    daily_report_rows.sort(
        key=lambda item: (
            item["date"],
            item["company_name"].lower(),
            item["mei_name"].lower(),
        ),
        reverse=True,
    )

    if request.method == "POST" and request.POST.get("action") == "request_activity_report":
        employee_id = (request.POST.get("employee") or "").strip()
        message = (request.POST.get("message") or "").strip()
        req_from = (request.POST.get("req_date_from") or "").strip()
        req_to = (request.POST.get("req_date_to") or "").strip()

        employee_obj = get_object_or_404(Employee, id=employee_id, company=company, user__role=User.Role.FUNCIONARIO)
        if not employees.filter(id=employee_obj.id).exists():
            return redirect("company_reports")

        req_date_from = None
        req_date_to = None
        try:
            if req_from:
                req_date_from = datetime.strptime(req_from, "%Y-%m-%d").date()
            if req_to:
                req_date_to = datetime.strptime(req_to, "%Y-%m-%d").date()
        except ValueError:
            req_date_from = None
            req_date_to = None

        ActivityReportRequest.objects.create(
            company=company,
            employee=employee_obj,
            requested_by=request.user,
            date_from=req_date_from,
            date_to=req_date_to,
            message=message,
        )
        query_parts = ["event=request_sent"]
        if selected_employee:
            query_parts.append(f"employee={selected_employee}")
        if date_from_raw:
            query_parts.append(f"date_from={date_from_raw}")
        if date_to_raw:
            query_parts.append(f"date_to={date_to_raw}")
        return redirect(f"{reverse('company_reports')}?{'&'.join(query_parts)}")

    if export_kind == "xlsx":
        headers = ["MEI", "Data", "Hora", "Valor/h"]
        rows = []
        for punch in punches:
            mei_name = _contract_mei_label(punch.contract)
            local_ts = timezone.localtime(punch.timestamp)
            rows.append(
                [
                    mei_name,
                    local_ts.strftime("%d/%m/%Y"),
                    local_ts.strftime("%H:%M"),
                    float(punch.contract.hourly_rate),
                ]
            )
        rows.append([])
        rows.append(["Total punches", metrics["total_punches"], "Total hours", metrics["total_hours_hhmm"]])
        rows.append(["Estimated payment", float(metrics["estimated_payment"]), "", ""])
        return _build_xlsx_response("horacerta_relatorio.xlsx", headers, rows)

    if export_kind == "pdf":
        employee_name = "Todos"
        if selected_employee:
            emp_obj = employees.filter(id=selected_employee).first()
            if emp_obj:
                employee_name = emp_obj.full_name

        lines = [
            "HoraCerta - Relatorio de servico",
            f"Empresa: {company.name if company else '-'}",
            f"MEI: {employee_name}",
            f"Periodo: {date_from_raw or '-'} ate {date_to_raw or '-'}",
            "",
            f"Total de horas: {metrics['total_hours_hhmm']}",
            f"Total de horários: {metrics['total_punches']}",
            f"Pagamento estimado: R$ {metrics['estimated_payment']}",
            "",
            "registros de horario (ultimos 25):",
        ]
        for punch in punches[:25]:
            mei_name = _contract_mei_label(punch.contract)
            local_ts = timezone.localtime(punch.timestamp)
            lines.append(f"{local_ts:%d/%m/%Y %H:%M} | {mei_name}")
        return _build_pdf_response("horacerta_relatorio.pdf", lines)

    requests_qs = ActivityReportRequest.objects.filter(company=company).select_related("employee", "employee__user")
    if selected_employee:
        requests_qs = requests_qs.filter(employee_id=selected_employee)

    context = {
        "company": company,
        "employees": employees,
        "selected_employee": selected_employee,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "total_hours": metrics["total_hours_hhmm"],
        "total_punches": metrics["total_punches"],
        "estimated_payment": metrics["estimated_payment"],
        "punches": punches[:300],
        "daily_report_rows": daily_report_rows[:500],
        "requests": requests_qs.order_by("-requested_at")[:200],
    }
    return render(request, "accounts/company_reports.html", context)


@login_required
def company_incident_center(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    employee_search_form = EmployeeSearchForm(request.GET or None)
    period_form = PeriodSearchForm(request.GET or None)
    status_filter = (request.GET.get("status") or "all").strip().lower()
    if status_filter not in {"all", "pending", "reviewed"}:
        status_filter = "all"

    type_filter = (request.GET.get("type") or "all").strip().lower()
    if type_filter not in {"all", "incomplete", "request"}:
        type_filter = "all"

    selected_employee = (request.GET.get("employee") or "").strip()

    employees_qs = Employee.objects.filter(company=company).select_related("user").order_by("full_name")
    search_query = ""
    if employee_search_form.is_valid():
        search_query = (employee_search_form.cleaned_data.get("q") or "").strip()
    if search_query:
        employees_qs = employees_qs.filter(
            Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__username__icontains=search_query)
        )
    if selected_employee:
        try:
            selected_employee = str(UUID(selected_employee))
            employees_qs = employees_qs.filter(id=selected_employee)
        except (ValueError, TypeError):
            selected_employee = ""

    today = timezone.localdate()
    period_start = today.replace(day=1)
    period_end = today
    if period_form.is_valid():
        period_start = period_form.cleaned_data.get("date_from") or period_start
        period_end = period_form.cleaned_data.get("date_to") or period_end
    if period_start > period_end:
        period_start, period_end = period_end, period_start

    period_start_dt = timezone.make_aware(datetime.combine(period_start, time.min))
    period_end_dt = timezone.make_aware(datetime.combine(period_end, time.max))

    employees = list(employees_qs[:300])
    employee_ids = [employee.id for employee in employees]
    contracts = list(
        Contract.objects.filter(
            company=company,
            employee_id__in=employee_ids,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .select_related("employee", "employee__user")
        .order_by("-start_date", "-created_at")
    )
    contract_ids = [contract.id for contract in contracts]

    punches = list(
        Punch.objects.filter(
            contract_id__in=contract_ids,
            timestamp__range=(period_start_dt, period_end_dt),
        )
        .select_related("contract", "contract__employee", "contract__employee__user")
        .order_by("-timestamp")
    )

    punches_by_employee = defaultdict(list)
    for punch in punches:
        employee = getattr(punch.contract, "employee", None)
        if employee:
            punches_by_employee[employee.id].append(punch)

    pending_requests_qs = ActivityReportRequest.objects.filter(
        company=company,
        is_answered=False,
        employee_id__in=employee_ids,
        requested_at__lte=period_end_dt,
    ).select_related("employee", "employee__user")
    pending_requests = list(pending_requests_qs.order_by("-requested_at"))
    answered_requests_qs = ActivityReportRequest.objects.filter(
        company=company,
        is_answered=True,
        employee_id__in=employee_ids,
        responded_at__isnull=False,
    ).select_related("employee")
    answered_requests = list(answered_requests_qs)

    answered_ranges_by_employee = defaultdict(list)
    for req in answered_requests:
        if req.date_from and req.date_to:
            range_start = req.date_from if req.date_from <= req.date_to else req.date_to
            range_end = req.date_to if req.date_to >= req.date_from else req.date_from
            answered_ranges_by_employee[req.employee_id].append((range_start, range_end))
        elif req.date_from:
            answered_ranges_by_employee[req.employee_id].append((req.date_from, req.date_from))
        elif req.date_to:
            answered_ranges_by_employee[req.employee_id].append((req.date_to, req.date_to))

    def _is_reviewed(employee_id, day_value):
        ranges = answered_ranges_by_employee.get(employee_id, [])
        for range_start, range_end in ranges:
            if range_start <= day_value <= range_end:
                return True
        return False

    pending_items = []
    unique_incomplete_days = 0
    service_request_items = 0
    unique_employee_ids = set()

    for employee in employees:
        employee_punches = punches_by_employee.get(employee.id, [])
        daily_rows, _max_cols = build_daily_summary(employee_punches, min_punch_columns=4)

        for row in daily_rows:
            has_incomplete = row["is_incomplete"]
            if not has_incomplete:
                continue

            pending_type = "incomplete"
            type_label = "Registro incompleto"
            type_tone = "danger"

            is_reviewed = _is_reviewed(employee.id, row["date"])
            status_key = "reviewed" if is_reviewed else "pending"
            status_label = "Revisado" if is_reviewed else "Pendente"
            status_tone = "success" if is_reviewed else "warn"

            matches_status = status_filter == "all" or status_filter == status_key
            matches_type = type_filter == "all" or type_filter == pending_type
            if not (matches_status and matches_type):
                continue

            unique_employee_ids.add(employee.id)
            if has_incomplete:
                unique_incomplete_days += 1

            pending_items.append(
                {
                    "employee": employee,
                    "date": row["date"],
                    "type_key": pending_type,
                    "type_label": type_label,
                    "type_tone": type_tone,
                    "status_key": status_key,
                    "status_label": status_label,
                    "status_tone": status_tone,
                    "notes_summary": "",
                    "punches_count": row["punches_count"],
                    "total_hours_hhmm": row["total_hours_hhmm"],
                    "history_url": f"{reverse('company_history')}?employee={employee.id}&date_from={row['date']}&date_to={row['date']}",
                    "profile_url": reverse("company_mei_profile", args=[employee.id]),
                }
            )

    for req in pending_requests:
        request_day = timezone.localtime(req.requested_at).date()
        if request_day < period_start or request_day > period_end:
            continue
        if type_filter not in {"all", "request"}:
            continue
        if status_filter not in {"all", "pending"}:
            continue

        unique_employee_ids.add(req.employee_id)
        service_request_items += 1
        pending_items.append(
            {
                "employee": req.employee,
                "date": request_day,
                "type_key": "request",
                "type_label": "Solicitacao pendente",
                "type_tone": "warn",
                "status_key": "pending",
                "status_label": "Pendente",
                "status_tone": "warn",
                "notes_summary": (req.message or "").strip(),
                "punches_count": "-",
                "total_hours_hhmm": "-",
                "history_url": f"{reverse('company_history')}?employee={req.employee_id}&date_from={request_day}&date_to={request_day}",
                "profile_url": reverse("company_mei_profile", args=[req.employee_id]),
            }
        )

    pending_items.sort(
        key=lambda item: (
            item["date"],
            1 if item["status_key"] == "pending" else 0,
            1 if item["type_key"] == "incomplete" else 0,
            item["employee"].full_name.lower(),
        ),
        reverse=True,
    )

    context = {
        "company": company,
        "employee_search_form": employee_search_form,
        "period_form": period_form,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "selected_employee": selected_employee,
        "employee_options": employees,
        "period_start": period_start.strftime("%Y-%m-%d"),
        "period_end": period_end.strftime("%Y-%m-%d"),
        "pending_items": pending_items[:700],
        "summary_total_pending": len(pending_items),
        "summary_incomplete_days": unique_incomplete_days,
        "summary_service_requests": service_request_items,
        "summary_people_with_occurrence": len(unique_employee_ids),
    }
    return render(request, "accounts/company_incident_center.html", context)


@login_required
def company_docs(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    return render(request, "accounts/company_docs.html")


@login_required
def company_plan(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    now = timezone.now()
    subscription = company.current_subscription()
    status_badge = _subscription_status_badge(subscription, at_time=now)
    current_plan = subscription.plan if subscription else None
    commercial_plan = _commercial_plan_snapshot(subscription)
    active_provider_count = (
        Contract.objects.filter(company=company, is_active=True, employee__is_active=True, employee__user__is_active=True)
        .values("employee_id")
        .distinct()
        .count()
    )
    provider_limit = commercial_plan["active_provider_limit"]
    provider_usage_percent = min(100, round((active_provider_count / provider_limit) * 100)) if provider_limit else 0
    limit_reached = bool(provider_limit and active_provider_count >= provider_limit)
    is_trial_active = bool(
        subscription
        and subscription.status == CompanySubscription.Status.TRIAL
        and not (subscription.trial_ends_at and now > subscription.trial_ends_at)
        and subscription.is_access_active(now)
    )

    included_benefits = [
        "Acompanhamento diário dos registros de horário.",
        "Gestão de prestadores, contratos e status operacional.",
        "Histórico de registros para consulta e conferência.",
        "Relatórios por período para apoio ao fechamento.",
        "Documentos e anexos vinculados à operação.",
        "Notificações para empresa e prestadores.",
        "Registro de problemas de horário pelo prestador.",
        "Correções administrativas com auditoria interna.",
        "Prestadores com vínculo ativo contam no limite do plano.",
    ]

    date_format = "%d/%m/%Y"

    def _fmt_dt(value):
        if not value:
            return "-"
        return timezone.localtime(value).strftime(date_format)

    context = {
        "company": company,
        "subscription": subscription,
        "subscription_status_badge": status_badge,
        "current_plan": current_plan,
        "current_plan_name": commercial_plan["name"],
        "current_plan_code": subscription.plan.code if subscription else "",
        "current_plan_description": commercial_plan["description"],
        "monthly_price_label": commercial_plan["monthly_price"],
        "active_provider_limit": provider_limit,
        "active_provider_count": active_provider_count,
        "provider_usage_percent": provider_usage_percent,
        "limit_reached": limit_reached,
        "is_trial_active": is_trial_active,
        "included_benefits": included_benefits,
        "starts_at_label": _fmt_dt(subscription.starts_at) if subscription else "-",
        "period_start_label": _fmt_dt(subscription.current_period_start) if subscription else "-",
        "period_end_label": _fmt_dt(subscription.current_period_end) if subscription else "-",
        "renewal_or_end_label": (
            _fmt_dt(subscription.current_period_end or subscription.ends_at)
            if subscription
            else "-"
        ),
        "expires_at_label": _fmt_dt(subscription.ends_at) if subscription else "-",
        "trial_end_label": _fmt_dt(subscription.trial_ends_at) if subscription else "-",
        "support_message": "Para ampliar o limite de prestadores ativos, entre em contato com o suporte.",
        "trial_message": (
            "Durante o período de teste, os recursos essenciais ficam disponíveis para cadastro de prestadores, "
            "registro de horários, histórico, conferência e relatórios."
        ),
    }
    return render(request, "accounts/company_plan.html", context)


@login_required
def company_settings(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    return render(request, "accounts/company_settings.html")


@login_required
def company_attendance_reliability(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    policy, _created = CompanyAttendancePolicy.objects.get_or_create(company=company)
    locations_qs = CompanyAuthorizedLocation.objects.filter(company=company).order_by("-is_active", "name", "-updated_at")
    locations = list(locations_qs[:400])

    editing_location = None
    edit_id = (request.GET.get("edit") or "").strip()
    if edit_id:
        editing_location = CompanyAuthorizedLocation.objects.filter(id=edit_id, company=company).first()

    policy_form = CompanyAttendancePolicyForm(instance=policy, company=company)
    if editing_location:
        location_form = CompanyAuthorizedLocationForm(instance=editing_location)
    else:
        location_form = CompanyAuthorizedLocationForm(initial={"allowed_radius_m": policy.default_allowed_radius_m})
    active_locations_count = sum(1 for item in locations if item.is_active)
    inactive_locations_count = len(locations) - active_locations_count

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "save_policy":
            policy_form = CompanyAttendancePolicyForm(request.POST, instance=policy, company=company)
            if policy_form.is_valid():
                policy_obj = policy_form.save(commit=False)
                policy_obj.company = company
                policy_obj.updated_by = request.user
                policy_obj.save()
                return redirect(f"{reverse('company_attendance_reliability')}?event=policy_saved")
        elif action == "save_location":
            location_id = (request.POST.get("location_id") or "").strip()
            location_obj = None
            if location_id:
                location_obj = CompanyAuthorizedLocation.objects.filter(id=location_id, company=company).first()
                if location_obj is None:
                    location_form = CompanyAuthorizedLocationForm(
                        request.POST,
                        instance=CompanyAuthorizedLocation(company=company),
                    )
                    location_form.add_error(None, "Local informado nao pertence a sua empresa.")
                    editing_location = None
                    return render(
                        request,
                        "accounts/company_attendance_reliability.html",
                        {
                            "company": company,
                            "policy": policy,
                            "policy_form": policy_form,
                            "location_form": location_form,
                            "locations": locations,
                            "editing_location": editing_location,
                            "active_locations_count": active_locations_count,
                            "inactive_locations_count": inactive_locations_count,
                        },
                        status=400,
                    )
            if location_obj is None:
                location_obj = CompanyAuthorizedLocation(company=company)
            location_form = CompanyAuthorizedLocationForm(request.POST, instance=location_obj)
            if location_form.is_valid():
                saved = location_form.save(commit=False)
                saved.company = company
                saved.save()
                if location_obj:
                    return redirect(f"{reverse('company_attendance_reliability')}?event=location_updated")
                return redirect(f"{reverse('company_attendance_reliability')}?event=location_created")
            editing_location = location_obj
        elif action == "toggle_location":
            location_id = (request.POST.get("location_id") or "").strip()
            location_obj = get_object_or_404(CompanyAuthorizedLocation, id=location_id, company=company)
            location_obj.is_active = not location_obj.is_active
            location_obj.save(update_fields=["is_active", "updated_at"])
            return redirect(f"{reverse('company_attendance_reliability')}?event=location_toggled")
        elif action == "rotate_qr_token":
            location_id = (request.POST.get("location_id") or "").strip()
            location_obj = get_object_or_404(CompanyAuthorizedLocation, id=location_id, company=company)
            location_obj.rotate_qr_token()
            return redirect(f"{reverse('company_attendance_reliability')}?event=qr_rotated")

    return render(
        request,
        "accounts/company_attendance_reliability.html",
        {
            "company": company,
            "policy": policy,
            "policy_form": policy_form,
            "location_form": location_form,
            "locations": locations,
            "editing_location": editing_location,
            "active_locations_count": active_locations_count,
            "inactive_locations_count": inactive_locations_count,
        },
    )


@login_required
def company_location_qr_panel(request, location_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    location = get_object_or_404(
        CompanyAuthorizedLocation,
        id=location_id,
        company=company,
    )
    scan_url = request.build_absolute_uri(reverse("qr_presence_checkin", args=[location.qr_token]))
    qr_image_url = f"https://quickchart.io/qr?size=320&text={quote(scan_url, safe='')}"

    return render(
        request,
        "accounts/company_location_qr_panel.html",
        {
            "company": company,
            "location": location,
            "scan_url": scan_url,
            "qr_image_url": qr_image_url,
            "back_url": reverse("company_attendance_reliability"),
        },
    )


@login_required
def company_records_review_center(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    period_form = PeriodSearchForm(request.GET or None)
    employees = (
        Employee.objects.filter(company=company, user__role=User.Role.FUNCIONARIO, user__isnull=False)
        .select_related("user")
        .order_by("full_name")
    )
    locations = CompanyAuthorizedLocation.objects.filter(company=company).order_by("name")

    today = timezone.localdate()
    first_day = today.replace(day=1)
    date_from = first_day
    date_to = today
    if period_form.is_valid():
        date_from = period_form.cleaned_data.get("date_from") or first_day
        date_to = period_form.cleaned_data.get("date_to") or today
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    selected_employee = (request.GET.get("employee") or "").strip()
    selected_status = (request.GET.get("status") or "").strip().upper()
    selected_location = (request.GET.get("location") or "").strip()

    start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
    end_dt = timezone.make_aware(datetime.combine(date_to, time.max))

    review_statuses = {
        Punch.ConfidenceStatus.OUT_OF_RADIUS,
        Punch.ConfidenceStatus.NO_LOCATION,
        Punch.ConfidenceStatus.IMPRECISE,
    }
    allowed_statuses = {choice[0] for choice in Punch.ConfidenceStatus.choices}
    if selected_status not in allowed_statuses:
        selected_status = "REVIEW"

    punches_qs = (
        Punch.objects.filter(contract__company=company, timestamp__range=(start_dt, end_dt))
        .select_related(
            "contract",
            "contract__company",
            "contract__employee",
            "contract__employee__user",
            "validated_location",
        )
        .order_by("-timestamp")
    )
    if selected_employee:
        punches_qs = punches_qs.filter(contract__employee_id=selected_employee)
    if selected_location:
        punches_qs = punches_qs.filter(validated_location_id=selected_location)
    if selected_status == "REVIEW":
        punches_qs = punches_qs.filter(
            Q(confidence_status__in=review_statuses)
            | Q(qr_confirmation_status=Punch.QrConfirmationStatus.REQUIRED_MISSING)
        )
    elif selected_status:
        punches_qs = punches_qs.filter(confidence_status=selected_status)

    rows = []
    for punch in punches_qs[:600]:
        rows.append(
            {
                "punch": punch,
                "employee_name": _contract_mei_label(punch.contract),
                "expected_location": punch.validated_location.name if punch.validated_location else "-",
                "distance_label": (
                    f"{float(punch.distance_to_location_m):.1f} m"
                    if punch.distance_to_location_m is not None
                    else "-"
                ),
                "accuracy_label": (
                    f"{float(punch.geo_accuracy_m):.1f} m"
                    if punch.geo_accuracy_m is not None
                    else "-"
                ),
                "confidence_label": punch.get_confidence_status_display(),
                "confidence_tone": punch.confidence_tone,
                "qr_label": punch.get_qr_confirmation_status_display(),
                "qr_tone": punch.qr_tone,
                "detail_url": f"{reverse('company_record_review_detail', args=[punch.id])}?from={urlencode(request.GET)}",
            }
        )

    status_choices = [("REVIEW", "Pendentes de revisao")] + list(Punch.ConfidenceStatus.choices)
    summary_total = len(rows)
    summary_out_of_radius = sum(1 for item in rows if item["punch"].confidence_status == Punch.ConfidenceStatus.OUT_OF_RADIUS)
    summary_no_location = sum(1 for item in rows if item["punch"].confidence_status == Punch.ConfidenceStatus.NO_LOCATION)
    summary_imprecise = sum(1 for item in rows if item["punch"].confidence_status == Punch.ConfidenceStatus.IMPRECISE)
    summary_qr_missing = sum(
        1 for item in rows if item["punch"].qr_confirmation_status == Punch.QrConfirmationStatus.REQUIRED_MISSING
    )

    return render(
        request,
        "accounts/company_records_review_center.html",
        {
            "company": company,
            "period_form": period_form,
            "employees": employees,
            "locations": locations,
            "status_choices": status_choices,
            "selected_employee": selected_employee,
            "selected_status": selected_status,
            "selected_location": selected_location,
            "date_from_value": date_from.strftime("%Y-%m-%d"),
            "date_to_value": date_to.strftime("%Y-%m-%d"),
            "rows": rows,
            "summary_total": summary_total,
            "summary_out_of_radius": summary_out_of_radius,
            "summary_no_location": summary_no_location,
            "summary_imprecise": summary_imprecise,
            "summary_qr_missing": summary_qr_missing,
        },
    )


@login_required
def company_record_review_detail(request, punch_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    punch = get_object_or_404(
        Punch.objects.select_related(
            "contract",
            "contract__company",
            "contract__employee",
            "contract__employee__user",
            "validated_location",
        ),
        id=punch_id,
        contract__company=company,
    )
    back_query = (request.GET.get("from") or "").strip()
    if back_query:
        back_url = f"{reverse('company_records_review_center')}?{back_query}"
    else:
        back_url = reverse("company_records_review_center")

    return render(
        request,
        "accounts/company_record_review_detail.html",
        {
            "company": company,
            "punch": punch,
            "employee_name": _contract_mei_label(punch.contract),
            "distance_label": (
                f"{float(punch.distance_to_location_m):.1f} m" if punch.distance_to_location_m is not None else "-"
            ),
            "accuracy_label": (f"{float(punch.geo_accuracy_m):.1f} m" if punch.geo_accuracy_m is not None else "-"),
            "audit_source": (punch.audit_payload or {}).get("source", "-"),
            "audit_recorded_from": (punch.audit_payload or {}).get("recorded_from", "-"),
            "audit_geolocation_collected": bool((punch.audit_payload or {}).get("geolocation_collected")),
            "audit_qr_required_for_punch": bool((punch.audit_payload or {}).get("qr_required_for_punch")),
            "audit_qr_requirement_reason": (punch.audit_payload or {}).get("qr_requirement_reason", "-"),
            "audit_policy_mode": ((punch.audit_payload or {}).get("policy") or {}).get("policy_mode", "-"),
            "back_url": back_url,
        },
    )


@login_required
def company_notifications(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    notifications = InternalNotification.objects.filter(
        recipient_company=company,
        audience=InternalNotification.Audience.COMPANY,
    ).select_related(
        "actor_user",
        "company_acknowledged_by",
    )
    return render(
        request,
        "accounts/company_notifications.html",
        {
            "company": company,
            "rows": [
                {
                    "notification": notification,
                    "tone": _notification_tone(notification),
                    "can_acknowledge": _company_ack_allowed(notification),
                }
                for notification in notifications[:200]
            ],
        },
    )


@login_required
@require_POST
def company_notification_action(request, notification_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    notification = get_object_or_404(
        InternalNotification.objects.select_related("recipient_company"),
        id=notification_id,
        recipient_company=company,
        audience=InternalNotification.Audience.COMPANY,
    )
    action = (request.POST.get("action") or "").strip()
    if action == "read":
        _mark_notification_read(notification)
        messages.success(request, "Notificacao marcada como lida.")
    elif action == "acknowledge" and _company_ack_allowed(notification):
        acknowledge_company_notification(notification, actor_user=request.user)
        messages.success(request, "Ciencia registrada para a empresa.")
    else:
        messages.error(request, "Acao invalida para esta notificacao.")
    return redirect("company_notifications")


@login_required
def company_correction_requests(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    requests_qs = PunchCorrectionRequest.objects.filter(company=company).select_related(
        "employee",
        "employee__user",
        "contract",
        "punch",
        "resolved_by",
    )
    return render(
        request,
        "accounts/company_correction_requests.html",
        {
            "company": company,
            "rows": [
                {
                    "request": item,
                    "status_tone": _correction_request_status_tone(item.status),
                }
                for item in requests_qs[:200]
            ],
        },
    )


@login_required
def company_correction_request_detail(request, request_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    correction_request = get_object_or_404(
        PunchCorrectionRequest.objects.select_related(
            "employee",
            "employee__user",
            "company",
            "contract",
            "punch",
            "resolved_by",
        ),
        id=request_id,
        company=company,
    )
    day_start = timezone.make_aware(datetime.combine(correction_request.problem_date, time.min))
    day_end = timezone.make_aware(datetime.combine(correction_request.problem_date, time.max))
    day_punches = (
        Punch.all_objects.filter(
            contract__employee=correction_request.employee,
            contract__company=company,
            timestamp__range=(day_start, day_end),
        )
        .select_related("contract", "contract__company", "contract__employee")
        .order_by("timestamp")
    )
    return render(
        request,
        "accounts/company_correction_request_detail.html",
        {
            "company": company,
            "correction_request": correction_request,
            "status_tone": _correction_request_status_tone(correction_request.status),
            "day_punches": day_punches,
        },
    )


@login_required
def company_service_reports(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    employees = (
        Employee.objects.filter(company=company, user__role=User.Role.FUNCIONARIO)
        .select_related("user")
        .order_by("full_name")
        if company
        else Employee.objects.none()
    )

    selected_employee = (request.GET.get("employee") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    date_from = _parse_iso_date(date_from_raw)
    date_to = _parse_iso_date(date_to_raw)
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
        date_from_raw, date_to_raw = date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d")

    request_form = CompanyActivityReportRequestForm(company=company)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "create_request":
            request_form = CompanyActivityReportRequestForm(request.POST, company=company)
            if request_form.is_valid():
                request_form.save(requested_by=request.user)
                return redirect(f"{reverse('company_service_reports')}?event=request_created")
        elif action == "mark_reviewed":
            request_id = (request.POST.get("request_id") or "").strip()
            req = ActivityReportRequest.objects.filter(id=request_id, company=company).first()
            if (
                req
                and req.response_report_id
                and req.status in {ActivityReportRequest.Status.RESPONDED, ActivityReportRequest.Status.REVIEWED}
            ):
                req.status = ActivityReportRequest.Status.REVIEWED
                req.reviewed_by = request.user
                req.save(update_fields=["status", "reviewed_by", "responded_at", "reviewed_at", "is_answered"])
                return redirect(f"{reverse('company_service_reports')}?event=request_reviewed")

    reports_qs = (
        ServiceReport.objects.filter(company=company).select_related("employee", "employee__user", "contract", "company")
        if company
        else ServiceReport.objects.none()
    )
    if selected_employee:
        reports_qs = reports_qs.filter(employee_id=selected_employee)
    if date_from:
        reports_qs = reports_qs.filter(report_date__gte=date_from)
    if date_to:
        reports_qs = reports_qs.filter(report_date__lte=date_to)

    reports = list(reports_qs.order_by("-report_date", "-created_at")[:500])
    total_reports = len(reports)
    unique_professionals = len({str(item.employee_id) for item in reports})
    latest_submission = reports[0].created_at if reports else None
    requests_qs = ActivityReportRequest.objects.filter(company=company).select_related(
        "employee",
        "employee__user",
        "contract",
        "response_report",
        "reviewed_by",
    )
    if selected_employee:
        requests_qs = requests_qs.filter(employee_id=selected_employee)
    if date_from:
        requests_qs = requests_qs.filter(Q(date_from__gte=date_from) | Q(date_to__gte=date_from) | Q(requested_at__date__gte=date_from))
    if date_to:
        requests_qs = requests_qs.filter(Q(date_from__lte=date_to) | Q(date_to__lte=date_to) | Q(requested_at__date__lte=date_to))
    requests = list(requests_qs.order_by("-requested_at")[:300])
    pending_requests_count = sum(1 for item in requests if item.status == ActivityReportRequest.Status.PENDING)

    context = {
        "company": company,
        "employees": employees,
        "request_form": request_form,
        "reports": reports,
        "requests": requests,
        "selected_employee": selected_employee,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "total_reports": total_reports,
        "unique_professionals": unique_professionals,
        "latest_submission": latest_submission,
        "pending_requests_count": pending_requests_count,
    }
    return render(request, "accounts/company_service_reports.html", context)


@login_required
def company_service_report_detail(request, report_id):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    report = get_object_or_404(
        ServiceReport.objects.select_related("employee", "employee__user", "contract", "company"),
        id=report_id,
        company=company,
    )
    return render(
        request,
        "accounts/company_service_report_detail.html",
        {
            "company": company,
            "report": report,
            "reports_url": reverse("company_service_reports"),
        },
    )


@login_required
def company_profile(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    theme_form = UserThemeForm(instance=request.user)
    if request.method == "POST" and (request.POST.get("action") or "") == "save_theme":
        form = CompanyProfileForm(instance=company)
        theme_form = UserThemeForm(request.POST, instance=request.user)
        if theme_form.is_valid():
            theme_form.save()
            messages.success(request, "Tema atualizado com sucesso.")
            return redirect("company_profile")
    elif request.method == "POST":
        form = CompanyProfileForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            return redirect("company_profile")
    else:
        form = CompanyProfileForm(instance=company)

    return render(request, "accounts/company_profile.html", {"form": form, "theme_form": theme_form, "company": company})


@login_required
def mei_panel(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    mei_context = resolve_mei_context(request, include_inactive_contracts=True)
    selected_contract = mei_context.selected_contract
    contracts = list(mei_context.contracts)
    active_contracts = [contract for contract in contracts if contract_is_operational(contract)]

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(datetime.combine(month_start, time.min))
    month_end_dt = timezone.make_aware(datetime.combine(today, time.max))
    contract_ids = [contract.id for contract in contracts]
    monthly_punches_by_contract = defaultdict(list)

    if contract_ids:
        monthly_punches = (
            Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(month_start_dt, month_end_dt))
            .select_related("contract", "contract__company")
            .order_by("timestamp")
        )
        for punch in monthly_punches:
            monthly_punches_by_contract[punch.contract_id].append(punch)

    client_summaries = []
    total_today_seconds = 0
    total_week_seconds = 0
    total_month_seconds = 0
    total_estimated_value = Decimal("0.00")
    incomplete_days = 0
    incomplete_alerts = []
    paused_contracts = []
    missing_rate_contracts = []

    for contract in contracts:
        month_rows, _max_cols = build_daily_summary(monthly_punches_by_contract.get(contract.id, []), min_punch_columns=4)
        month_seconds = sum(row["total_seconds"] for row in month_rows)
        week_seconds = sum(row["total_seconds"] for row in month_rows if row["date"] >= week_start)
        today_seconds = sum(row["total_seconds"] for row in month_rows if row["date"] == today)
        client_incomplete_days = [row for row in month_rows if row["is_incomplete"]]
        hourly_rate = contract.hourly_rate or Decimal("0")
        estimated_value = ((Decimal(month_seconds) / Decimal("3600")) * hourly_rate).quantize(Decimal("0.01"))
        status = _contract_status_for_mei(contract)

        total_today_seconds += today_seconds
        total_week_seconds += week_seconds
        total_month_seconds += month_seconds
        total_estimated_value += estimated_value
        incomplete_days += len(client_incomplete_days)

        if client_incomplete_days:
            incomplete_alerts.append(
                {
                    "contract": contract,
                    "count": len(client_incomplete_days),
                    "latest_date": client_incomplete_days[0]["date"],
                }
            )
        if status["label"] != "Ativo":
            paused_contracts.append({"contract": contract, "status": status})
        if hourly_rate <= Decimal("0"):
            missing_rate_contracts.append(contract)

        client_summaries.append(
            {
                "contract": contract,
                "status": status,
                "total_hours_month": format_hhmm(month_seconds),
                "hourly_rate": hourly_rate,
                "estimated_value_brl": _format_brl(estimated_value),
            }
        )

    pending_report_requests_qs = ActivityReportRequest.objects.filter(
        employee__user=request.user,
        status=ActivityReportRequest.Status.PENDING,
    ).select_related("company", "contract")
    pending_reports_count = pending_report_requests_qs.count()
    pending_report_requests = list(pending_report_requests_qs[:20])

    context = {
        "contracts": contracts,
        "selected_contract": selected_contract,
        "contracts_count": len(contracts),
        "active_clients_count": len(active_contracts),
        "current_period_label": _month_label_ptbr(today),
        "week_period_label": f"{week_start:%d/%m} a {today:%d/%m}",
        "total_hours_today": format_hhmm(total_today_seconds),
        "total_hours_week": format_hhmm(total_week_seconds),
        "total_hours_month": format_hhmm(total_month_seconds),
        "estimated_value_month_brl": _format_brl(total_estimated_value.quantize(Decimal("0.01"))),
        "incomplete_days": incomplete_days,
        "pending_days": incomplete_days,
        "pending_reports_count": pending_reports_count,
        "pending_report_requests": pending_report_requests,
        "client_summaries": client_summaries,
        "incomplete_alerts": incomplete_alerts,
        "paused_contracts": paused_contracts,
        "missing_rate_contracts": missing_rate_contracts,
        "context_warning": (
            "O vinculo selecionado anteriormente nao esta mais disponivel. Exibindo o vinculo atual."
            if (mei_context.invalid_requested_contract or mei_context.invalid_session_contract)
            else ""
        ),
    }
    return render(request, "accounts/mei_panel.html", context)


@login_required
def mei_profile(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    mei_context = resolve_mei_context(request, include_inactive_contracts=True)
    contracts = mei_context.contracts
    selected_contract = mei_context.selected_contract
    employee = mei_context.selected_employee
    if not employee:
        employee = (
            Employee.objects.filter(user=request.user)
            .select_related("company")
            .order_by("-is_active", "-created_at")
            .first()
        )
        if not employee:
            return redirect("mei_panel")

    theme_form = UserThemeForm(instance=request.user)

    if request.method == "POST" and (request.POST.get("action") or "") == "save_theme":
        theme_form = UserThemeForm(request.POST, instance=request.user)
        form = MEIProfileForm(instance=employee)
        if theme_form.is_valid():
            theme_form.save()
            messages.success(request, "Tema atualizado com sucesso.")
            redirect_url = reverse("mei_profile")
            if selected_contract:
                redirect_url = f"{redirect_url}?contract={selected_contract.id}"
            return redirect(redirect_url)
    elif request.method == "POST":
        form = MEIProfileForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            redirect_url = reverse("mei_profile")
            if selected_contract:
                redirect_url = f"{redirect_url}?contract={selected_contract.id}"
            return redirect(redirect_url)
    else:
        form = MEIProfileForm(instance=employee)

    return render(
        request,
        "accounts/mei_profile.html",
        {
            "form": form,
            "theme_form": theme_form,
            "employee": employee,
            "contracts": contracts,
            "selected_contract": selected_contract,
        },
    )


@login_required
def mei_history(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    mei_context = resolve_mei_context(request)
    contracts = mei_context.contracts
    selected_contract = mei_context.selected_contract
    punches = Punch.objects.none()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    parsed_date_from = None
    parsed_date_to = None

    if selected_contract:
        if not date_from_raw and not date_to_raw:
            today = timezone.localdate()
            date_from_raw = today.replace(day=1).strftime("%Y-%m-%d")
            date_to_raw = today.strftime("%Y-%m-%d")
        base_punches = Punch.objects.filter(contract=selected_contract).order_by("timestamp")
        punches, parsed_date_from, parsed_date_to = filter_punches_by_period(base_punches, date_from_raw, date_to_raw)

    grouped_rows, max_punches = build_daily_summary(list(punches), min_punch_columns=4)
    rows_by_date = {row["date"]: row for row in grouped_rows}
    history_rows = []

    if parsed_date_from and parsed_date_to:
        current_day = parsed_date_from
        while current_day <= parsed_date_to:
            existing = rows_by_date.get(current_day)
            if existing:
                history_rows.append(existing)
            else:
                history_rows.append(
                    {
                        "date": current_day,
                        "punches_count": 0,
                        "punch_times": [],
                        "punch_columns": ["-"] * max_punches,
                        "total_seconds": 0,
                        "total_hours_hhmm": "00:00",
                        "status": "SEM REGISTROS",
                        "is_incomplete": False,
                    }
                )
            current_day += timedelta(days=1)
    else:
        history_rows = grouped_rows

    hourly_rate = getattr(selected_contract, "hourly_rate", None) or Decimal("0")
    history_rows = sorted(history_rows, key=lambda row: row["date"], reverse=True)
    for row in history_rows:
        estimated_value = ((Decimal(row["total_seconds"]) / Decimal("3600")) * hourly_rate).quantize(Decimal("0.01"))
        row["estimated_value"] = estimated_value
        row["estimated_value_brl"] = _format_brl(estimated_value)
        if row["punches_count"] == 0:
            row["status_label"] = "Sem registros"
            row["status_kind"] = "empty"
        elif row["is_incomplete"]:
            row["status_label"] = "Incompleto"
            row["status_kind"] = "incomplete"
        else:
            row["status_label"] = "Completo"
            row["status_kind"] = "complete"
        row["punch_times_label"] = " - ".join(row["punch_times"]) if row["punch_times"] else "-"

    total_days_with_records = sum(1 for row in history_rows if row["punches_count"] > 0)
    total_punches = sum(row["punches_count"] for row in history_rows)
    total_seconds = sum(row["total_seconds"] for row in history_rows)
    total_hours_period = format_hhmm(total_seconds)
    total_estimated_value = sum((row["estimated_value"] for row in history_rows), Decimal("0.00"))
    total_days_complete = sum(1 for row in history_rows if row["punches_count"] > 0 and not row["is_incomplete"])
    total_days_incomplete = sum(1 for row in history_rows if row["punches_count"] > 0 and row["is_incomplete"])

    if parsed_date_from and parsed_date_to:
        period_label = f"{parsed_date_from.strftime('%d/%m/%Y')} até {parsed_date_to.strftime('%d/%m/%Y')}"
    else:
        period_label = "Período completo"

    context = {
        "contracts": contracts,
        "selected_contract": selected_contract,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "period_label": period_label,
        "history_rows": history_rows,
        "history_punch_columns": range(1, max_punches + 1),
        "summary_total_days_with_records": total_days_with_records,
        "summary_total_punches": total_punches,
        "summary_total_hours": total_hours_period,
        "summary_estimated_value_brl": _format_brl(total_estimated_value.quantize(Decimal("0.01"))),
        "summary_total_days_complete": total_days_complete,
        "summary_total_days_incomplete": total_days_incomplete,
    }
    return render(request, "accounts/mei_history.html", context)


@login_required
def mei_edit_today_punches(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    contracts = list(mei_contracts_for_user(request.user, include_inactive_contracts=False))
    if not contracts:
        messages.error(request, "Cadastre um cliente ativo antes de editar os horarios de hoje.")
        return redirect("mei_panel")

    today = timezone.localdate()
    is_locked = _report_locks_day_for_user(request.user, today)
    start_dt, end_dt = _today_bounds(today)
    contract_ids = [contract.id for contract in contracts]
    today_punches_qs = (
        Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(start_dt, end_dt))
        .select_related("contract", "contract__company")
        .order_by("timestamp", "created_at")
    )
    today_punches = list(today_punches_qs)

    selected_contract_id = (request.POST.get("contract") or request.GET.get("contract") or "").strip()
    selected_contract = next((item for item in contracts if str(item.id) == selected_contract_id), None)
    if not selected_contract and today_punches:
        selected_contract = next((item for item in contracts if item.id == today_punches[0].contract_id), None)
    if not selected_contract:
        selected_contract = contracts[0]

    errors = []
    note_value = ""

    if request.method == "POST":
        if is_locked:
            messages.error(request, "Este dia esta bloqueado porque ja foi incluido em um relatorio gerado.")
            return redirect("mei_edit_today_punches")

        posted_contract = next((item for item in contracts if str(item.id) == selected_contract_id), None)
        if not posted_contract:
            errors.append("Selecione um cliente/contrato ativo da sua conta.")
        else:
            selected_contract = posted_contract

        existing_ids = request.POST.getlist("existing_punch_id")
        existing_times = request.POST.getlist("existing_time")
        remove_ids = set(request.POST.getlist("remove_punch"))
        new_times = [(value or "").strip() for value in request.POST.getlist("new_time") if (value or "").strip()]
        note_value = (request.POST.get("day_note") or "").strip()[:1000]

        today_punches_by_id = {str(punch.id): punch for punch in today_punches}
        if len(existing_ids) != len(existing_times):
            errors.append("Nao foi possivel validar os horarios enviados.")

        parsed_existing = []
        for punch_id, raw_time in zip(existing_ids, existing_times):
            punch = today_punches_by_id.get(punch_id)
            if not punch:
                errors.append("Um dos horarios enviados nao pertence ao dia atual da sua conta.")
                continue
            if punch_id in remove_ids:
                continue
            try:
                parsed_time = datetime.strptime((raw_time or "").strip(), "%H:%M").time()
            except ValueError:
                errors.append("Informe horarios existentes no formato HH:MM.")
                continue
            parsed_existing.append((punch, parsed_time))

        parsed_new = []
        for raw_time in new_times:
            try:
                parsed_new.append(datetime.strptime(raw_time, "%H:%M").time())
            except ValueError:
                errors.append("Informe horarios adicionados no formato HH:MM.")

        final_times = [item[1] for item in parsed_existing] + parsed_new
        if not final_times:
            errors.append("Mantenha pelo menos um horario no dia atual.")

        sorted_times = sorted(final_times)
        for idx in range(0, len(sorted_times) - 1, 2):
            if sorted_times[idx] >= sorted_times[idx + 1]:
                errors.append("A entrada deve ser menor que a saida em cada par de horarios.")
                break

        if not errors:
            tz = timezone.get_current_timezone()
            before_data = _workday_log_snapshot(today_punches)
            with transaction.atomic():
                for punch_id in remove_ids:
                    punch = today_punches_by_id.get(punch_id)
                    if punch and not punch.is_cancelled:
                        punch.is_cancelled = True
                        punch.cancelled_at = timezone.now()
                        punch.cancelled_by = request.user
                        punch.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])

                for punch, parsed_time in parsed_existing:
                    punch.timestamp = timezone.make_aware(datetime.combine(today, parsed_time), tz)
                    punch.contract = selected_contract
                    if note_value:
                        punch.note = note_value
                    update_fields = ["timestamp", "contract"]
                    if note_value:
                        update_fields.append("note")
                    punch.save(update_fields=update_fields)

                for parsed_time in parsed_new:
                    Punch.objects.create(
                        contract=selected_contract,
                        timestamp=timezone.make_aware(datetime.combine(today, parsed_time), tz),
                        note=note_value,
                        is_manual=True,
                        validation_method=Punch.ValidationMethod.FREE_POLICY,
                        confidence_status=Punch.ConfidenceStatus.FREE,
                        qr_confirmation_status=Punch.QrConfirmationStatus.NOT_REQUIRED,
                        audit_payload={"origin": "today_edit"},
                    )

                updated_punches = list(
                    Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(start_dt, end_dt))
                    .select_related("contract", "contract__company")
                    .order_by("timestamp", "created_at")
                )
                after_data = _workday_log_snapshot(updated_punches)
                if before_data != after_data:
                    WorkdayChangeLog.objects.create(
                        user=request.user,
                        employee=selected_contract.employee,
                        company=selected_contract.company,
                        contract=selected_contract,
                        edited_date=today,
                        before_data=before_data,
                        after_data=after_data,
                        change_type=_infer_workday_change_type(before_data, after_data),
                        ip_address=_request_ip_address(request),
                        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
                        note=note_value,
                    )

            messages.success(request, "Horarios de hoje atualizados com sucesso.")
            return redirect("mei_history")

    today_punches = list(
        Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(start_dt, end_dt))
        .select_related("contract", "contract__company")
        .order_by("timestamp", "created_at")
    )
    local_datetimes = [timezone.localtime(punch.timestamp) for punch in today_punches]
    total_seconds, is_incomplete = compute_day_total(local_datetimes)
    active_note = note_value or next((punch.note for punch in today_punches if (punch.note or "").strip()), "")

    return render(
        request,
        "accounts/mei_edit_today_punches.html",
        {
            "contracts": contracts,
            "selected_contract": selected_contract,
            "today": today,
            "today_punches": today_punches,
            "total_hours": format_hhmm(total_seconds),
            "is_incomplete": is_incomplete,
            "is_locked": is_locked,
            "lock_message": "Este dia esta bloqueado porque ja foi incluido em um relatorio gerado.",
            "errors": errors,
            "day_note": active_note,
        },
    )


@login_required
def mei_punch_correction_request(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    mei_context = resolve_mei_context(request, include_inactive_contracts=True)
    employee = mei_context.selected_employee
    if not employee:
        return render(
            request,
            "accounts/mei_punch_correction_request.html",
            {"form": None, "no_employee": True},
        )

    initial = {"problem_date": timezone.localdate()}
    if mei_context.selected_contract:
        initial["contract"] = mei_context.selected_contract
    form = PunchCorrectionRequestForm(
        request.POST or None,
        employee=employee,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        correction_request = form.save()
        notify_correction_request_created(correction_request)
        return redirect(f"{reverse('employee_dashboard')}?event=correction_request_sent")

    return render(
        request,
        "accounts/mei_punch_correction_request.html",
        {
            "form": form,
            "employee": employee,
        },
    )


@login_required
def mei_notifications(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    notifications = InternalNotification.objects.filter(
        recipient_user=request.user,
        audience=InternalNotification.Audience.MEI,
    ).select_related(
        "actor_user",
        "recipient_company",
    )
    return render(
        request,
        "accounts/mei_notifications.html",
        {
            "rows": [
                {"notification": notification, "tone": _notification_tone(notification)}
                for notification in notifications[:200]
            ],
        },
    )


@login_required
@require_POST
def mei_notification_action(request, notification_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    notification = get_object_or_404(
        InternalNotification,
        id=notification_id,
        recipient_user=request.user,
        audience=InternalNotification.Audience.MEI,
    )
    action = (request.POST.get("action") or "").strip()
    if action == "read":
        _mark_notification_read(notification)
        messages.success(request, "Notificacao marcada como lida.")
    else:
        messages.error(request, "Acao invalida para esta notificacao.")
    return redirect("mei_notifications")


@login_required
def mei_export(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    return redirect("mei_reports")


@login_required
def mei_contract(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    all_contracts = list(mei_contracts_for_user(request.user, include_inactive_contracts=True))
    active_contracts = [contract for contract in all_contracts if contract_is_operational(contract)]
    inactive_contracts = [contract for contract in all_contracts if contract not in active_contracts]
    selected_contract_id = (request.GET.get("contract") or "").strip()

    active_contract = None
    if all_contracts:
        if selected_contract_id:
            active_contract = next((c for c in all_contracts if str(c.id) == selected_contract_id), None)
        if not active_contract:
            active_contract = active_contracts[0] if active_contracts else all_contracts[0]

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "set_payment_status":
            report_id = (request.POST.get("report_id") or "").strip()
            payment_status = (request.POST.get("payment_status") or "").strip()
            report = get_object_or_404(
                ServiceReport.objects.select_related("contract"),
                id=report_id,
                employee__user=request.user,
            )
            if payment_status == ServiceReport.PaymentStatus.PAID:
                report.payment_status = ServiceReport.PaymentStatus.PAID
                report.paid_at = timezone.now()
                report.paid_note = ""
                report.save(update_fields=["payment_status", "paid_at", "paid_note", "updated_at"])
                event = "report_received"
            elif payment_status == ServiceReport.PaymentStatus.PENDING:
                report.payment_status = ServiceReport.PaymentStatus.PENDING
                report.paid_at = None
                report.paid_note = ""
                report.save(update_fields=["payment_status", "paid_at", "paid_note", "updated_at"])
                event = "report_receive_pending"
            else:
                messages.error(request, "Status de recebimento invalido.")
                event = "receive_invalid"
            return redirect(f"{reverse('mei_contract')}?contract={report.contract_id}&event={event}")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(datetime.combine(month_start, time.min))
    month_end_dt = timezone.make_aware(datetime.combine(today, time.max))
    contract_ids = [contract.id for contract in all_contracts]
    monthly_punches_by_contract = defaultdict(list)
    last_punch_by_contract = {}

    if contract_ids:
        monthly_punches = (
            Punch.objects.filter(contract_id__in=contract_ids, timestamp__range=(month_start_dt, month_end_dt))
            .select_related("contract", "contract__company")
            .order_by("timestamp")
        )
        for punch in monthly_punches:
            monthly_punches_by_contract[punch.contract_id].append(punch)

        recent_punches = (
            Punch.objects.filter(contract_id__in=contract_ids)
            .select_related("contract", "contract__company")
            .order_by("-timestamp")[:500]
        )
        for punch in recent_punches:
            last_punch_by_contract.setdefault(punch.contract_id, punch)

    client_rows = []
    selected_client_row = None
    total_month_seconds = 0
    total_estimated_value = Decimal("0.00")
    report_counts_by_contract = {}
    if contract_ids:
        report_counts_by_contract = dict(
            ServiceReport.objects.filter(contract_id__in=contract_ids)
            .values_list("contract_id")
            .annotate(total=Count("id"))
        )

    for contract in all_contracts:
        month_rows, _max_cols = build_daily_summary(monthly_punches_by_contract.get(contract.id, []), min_punch_columns=4)
        month_seconds = sum(row["total_seconds"] for row in month_rows)
        estimated_value = ((Decimal(month_seconds) / Decimal("3600")) * (contract.hourly_rate or Decimal("0"))).quantize(
            Decimal("0.01")
        )
        quick_date_from = None
        quick_date_to = None
        quick_metrics = None
        quick_period_label = "Definir manualmente em Relatorios"
        if contract.closure_type != Contract.ClosureType.CUSTOM:
            quick_date_from, quick_date_to = _suggest_closure_period(contract, today)
            quick_metrics = _compute_contract_period_totals(contract, quick_date_from, quick_date_to)
            quick_period_label = f"{quick_date_from:%d/%m/%Y} ate {quick_date_to:%d/%m/%Y}"
        quick_query = {"contract": str(contract.id)}
        if quick_date_from and quick_date_to:
            quick_query["date_from"] = quick_date_from.isoformat()
            quick_query["date_to"] = quick_date_to.isoformat()
        quick_report_url = f"{reverse('mei_reports')}?{urlencode(quick_query)}"
        recent_reports = []
        recent_reports_qs = ServiceReport.objects.filter(contract=contract, employee__user=request.user).order_by(
            "-report_date", "-created_at"
        )
        recent_reports_sample = list(recent_reports_qs[:4])
        for report in recent_reports_sample[:3]:
            conference_url = ""
            whatsapp_url = ""
            if report.conference_is_accessible:
                conference_url = request.build_absolute_uri(reverse("public_service_report_conference", args=[report.conference_token]))
                whatsapp_url = reverse("mei_service_report_whatsapp", args=[report.id])
            recent_reports.append(
                {
                    "report": report,
                    "period_label": _service_report_period_display(report),
                    "status_label": _service_report_status_label(report),
                    "view_label": _service_report_view_label(report),
                    "view_tone": "success" if report.conference_first_viewed_at else "pending",
                    "received_label": _service_report_received_label(report),
                    "received_tone": "success" if report.payment_status == ServiceReport.PaymentStatus.PAID else "pending",
                    "conference_url": conference_url,
                    "whatsapp_url": whatsapp_url,
                    "pdf_url": reverse("mei_service_report_pdf", args=[report.id]),
                    "detail_url": reverse("mei_service_report_detail", args=[report.id]),
                }
            )
        total_month_seconds += month_seconds
        total_estimated_value += estimated_value
        last_punch = last_punch_by_contract.get(contract.id)
        row = {
            "contract": contract,
            "status": _contract_status_for_mei(contract),
            "total_hours_month": format_hhmm(month_seconds),
            "estimated_value": estimated_value,
            "estimated_value_brl": _format_brl(estimated_value),
            "last_punch": last_punch,
            "last_punch_label": timezone.localtime(last_punch.timestamp).strftime("%d/%m/%Y %H:%M")
            if last_punch
            else "Sem registros",
            "reports_count": report_counts_by_contract.get(contract.id, 0),
            "quick_closure": {
                "period_label": quick_period_label,
                "total_hours": quick_metrics["total_hours"] if quick_metrics else "-",
                "estimated_value_brl": quick_metrics["estimated_value_brl"] if quick_metrics else "-",
                "report_url": quick_report_url,
                "is_custom": contract.closure_type == Contract.ClosureType.CUSTOM,
            },
            "recent_reports": recent_reports,
            "has_more_reports": len(recent_reports_sample) > 3,
            "details_url": f"{reverse('mei_contract')}?contract={contract.id}",
            "history_url": f"{reverse('mei_history')}?contract={contract.id}",
            "report_url": f"{reverse('mei_reports')}?contract={contract.id}",
            "reports_all_url": f"{reverse('mei_reports')}?contract={contract.id}",
            "service_report_url": reverse("mei_service_report_prepare", args=[contract.id]),
            "edit_url": reverse("mei_client_edit", args=[contract.id]),
        }
        client_rows.append(row)
        if active_contract and contract.id == active_contract.id:
            selected_client_row = row

    return render(
        request,
        "accounts/mei_contract.html",
        {
            "active_contract": active_contract,
            "active_contracts": active_contracts,
            "inactive_contracts": inactive_contracts,
            "all_contracts": all_contracts,
            "client_rows": client_rows,
            "selected_client_row": selected_client_row,
            "active_clients_count": len(active_contracts),
            "inactive_clients_count": len(inactive_contracts),
            "current_period_label": _month_label_ptbr(today),
            "total_hours_month": format_hhmm(total_month_seconds),
            "total_estimated_value_brl": _format_brl(total_estimated_value.quantize(Decimal("0.01"))),
        },
    )


@login_required
def mei_service_report_prepare(request, contract_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    contract = get_object_or_404(
        mei_contracts_for_user(request.user, include_inactive_contracts=True),
        id=contract_id,
    )
    today = timezone.localdate()
    return render(
        request,
        "accounts/mei_service_report_prepare.html",
        {
            "contract": contract,
            "date_from": today.replace(day=1),
            "date_to": today,
            "issued_at": today,
        },
    )


@login_required
def mei_client_create(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    if request.method == "POST":
        form = MEIClientForm(request.POST, user=request.user)
        if form.is_valid():
            contract = form.save()
            messages.success(request, "Cliente cadastrado com sucesso.")
            return redirect(f"{reverse('mei_contract')}?contract={contract.id}")
        messages.error(request, "Revise os campos destacados antes de salvar.")
    else:
        form = MEIClientForm(user=request.user, initial={"start_date": timezone.localdate()})

    return render(
        request,
        "accounts/mei_client_form.html",
        {
            "form": form,
            "mode": "create",
            "title": "Adicionar cliente",
        },
    )


@login_required
def mei_client_edit(request, contract_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    contract = get_object_or_404(
        mei_contracts_for_user(request.user, include_inactive_contracts=True),
        id=contract_id,
    )

    if request.method == "POST":
        form = MEIClientForm(request.POST, user=request.user, instance=contract)
        if form.is_valid():
            contract = form.save()
            messages.success(request, "Cliente atualizado com sucesso.")
            return redirect(f"{reverse('mei_contract')}?contract={contract.id}")
        messages.error(request, "Revise os campos destacados antes de salvar.")
    else:
        form = MEIClientForm(user=request.user, instance=contract)

    return render(
        request,
        "accounts/mei_client_form.html",
        {
            "form": form,
            "mode": "edit",
            "contract": contract,
            "title": "Editar cliente",
        },
    )


@login_required
def mei_reports(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    contracts = mei_contracts_for_user(request.user, include_inactive_contracts=True)
    contracts_list = list(contracts)
    if not contracts_list:
        return redirect("mei_panel")

    selected_contract_id = (request.GET.get("contract") or request.POST.get("selected_contract") or "").strip()
    selected_contract = None
    if selected_contract_id and selected_contract_id != "all":
        selected_contract = next((item for item in contracts_list if str(item.id) == selected_contract_id), None)
    form_contract = selected_contract or contracts_list[0]

    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    view_filter = (request.GET.get("view") or "all").strip()
    receive_filter = (request.GET.get("receive") or "all").strip()

    reports_qs = (
        ServiceReport.objects.filter(employee__user=request.user)
        .select_related("company", "contract", "employee", "employee__user")
        .order_by("-report_date", "-created_at")
    )
    requests_qs = (
        ActivityReportRequest.objects.filter(employee__user=request.user)
        .select_related("company", "contract", "requested_by", "response_report")
        .order_by("-requested_at")
    )
    if selected_contract:
        reports_qs = reports_qs.filter(contract=selected_contract)
        requests_qs = requests_qs.filter(
            Q(contract=selected_contract)
            | Q(contract__isnull=True, company=selected_contract.company)
        )
    if search_query:
        search_filter = (
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(company__name__icontains=search_query)
        )
        for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                searched_date = datetime.strptime(search_query, date_format).date()
            except ValueError:
                continue
            search_filter |= Q(date_from__lte=searched_date, date_to__gte=searched_date)
            break
        reports_qs = reports_qs.filter(search_filter)
    date_from = None
    date_to = None
    if date_from_raw:
        try:
            date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
        except ValueError:
            date_from = None
    if date_to_raw:
        try:
            date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
        except ValueError:
            date_to = None
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    if date_from:
        reports_qs = reports_qs.filter(date_to__gte=date_from)
    if date_to:
        reports_qs = reports_qs.filter(date_from__lte=date_to)
    valid_statuses = {choice[0] for choice in ServiceReport.Status.choices}
    if status_filter in valid_statuses:
        reports_qs = reports_qs.filter(status=status_filter)
    if view_filter == "viewed":
        reports_qs = reports_qs.filter(conference_first_viewed_at__isnull=False)
    elif view_filter == "unviewed":
        reports_qs = reports_qs.filter(conference_first_viewed_at__isnull=True)
    else:
        view_filter = "all"
    if receive_filter == "received":
        reports_qs = reports_qs.filter(payment_status=ServiceReport.PaymentStatus.PAID)
    elif receive_filter == "pending":
        reports_qs = reports_qs.filter(payment_status=ServiceReport.PaymentStatus.PENDING)
    else:
        receive_filter = "all"

    pending_requests = [item for item in requests_qs[:300] if item.status == ActivityReportRequest.Status.PENDING]
    responded_requests = [item for item in requests_qs[:300] if item.status != ActivityReportRequest.Status.PENDING]
    form_initial = {"contract": form_contract}
    if date_from:
        form_initial["date_from"] = date_from
    if date_to:
        form_initial["date_to"] = date_to
    report_form = ServiceReportCreateForm(user=request.user, initial=form_initial)
    report_form.fields["contract"].initial = form_contract

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "create_report":
            report_form = ServiceReportCreateForm(request.POST, user=request.user)
            if report_form.is_valid():
                report = report_form.save(commit=False)
                report.summary_payload = _build_service_report_payload(
                    report.contract,
                    report.date_from,
                    report.date_to,
                )
                report.ensure_conference_link()
                report.save()
                redirect_url = f"{reverse('mei_reports')}?event=report_created"
                if not report.summary_payload.get("total_seconds"):
                    redirect_url = f"{reverse('mei_reports')}?event=report_created_empty"
                redirect_url = f"{redirect_url}&contract={report.contract.id}"
                return redirect(redirect_url)
        elif action == "generate_conference_link":
            report_id = (request.POST.get("report_id") or "").strip()
            report = get_object_or_404(
                ServiceReport.objects.select_related("contract"),
                id=report_id,
                employee__user=request.user,
            )
            report.ensure_conference_link()
            report.save(
                update_fields=[
                    "conference_token",
                    "conference_link_created_at",
                    "conference_first_viewed_at",
                    "conference_reviewed_at",
                    "conference_comment",
                    "conference_revoked_at",
                    "conference_expires_at",
                    "conference_final_status",
                    "status",
                    "updated_at",
                ]
            )
            redirect_url = f"{reverse('mei_reports')}?event=link_created&contract={report.contract_id}"
            return redirect(redirect_url)
        elif action == "set_payment_status":
            report_id = (request.POST.get("report_id") or "").strip()
            payment_status = (request.POST.get("payment_status") or "").strip()
            report = get_object_or_404(
                ServiceReport.objects.select_related("contract"),
                id=report_id,
                employee__user=request.user,
            )
            if payment_status == ServiceReport.PaymentStatus.PAID:
                report.payment_status = ServiceReport.PaymentStatus.PAID
                report.paid_at = timezone.now()
                report.paid_note = (request.POST.get("paid_note") or "").strip()[:1000]
                report.save(update_fields=["payment_status", "paid_at", "paid_note", "updated_at"])
                event = "report_received"
            elif payment_status == ServiceReport.PaymentStatus.PENDING:
                report.payment_status = ServiceReport.PaymentStatus.PENDING
                report.paid_at = None
                report.paid_note = (request.POST.get("paid_note") or "").strip()[:1000]
                report.save(update_fields=["payment_status", "paid_at", "paid_note", "updated_at"])
                event = "report_receive_pending"
            else:
                messages.error(request, "Status de recebimento invalido.")
                event = "receive_invalid"
            redirect_url = f"{reverse('mei_reports')}?event={event}&contract={report.contract_id}"
            return redirect(redirect_url)

    reports = list(reports_qs[:300])
    report_rows = []
    for report in reports:
        conference_url = ""
        whatsapp_url = ""
        if report.conference_is_accessible:
            conference_url = request.build_absolute_uri(reverse("public_service_report_conference", args=[report.conference_token]))
            whatsapp_url = reverse("mei_service_report_whatsapp", args=[report.id])
        report_rows.append(
            {
                "report": report,
                "conference_url": conference_url,
                "whatsapp_url": whatsapp_url,
                "pdf_url": reverse("mei_service_report_pdf", args=[report.id]),
                "detail_url": reverse("mei_service_report_detail", args=[report.id]),
                "period_label": _service_report_period_display(report),
                "status_label": _service_report_status_label(report),
                "view_label": _service_report_view_label(report),
                "view_tone": "success" if report.conference_first_viewed_at else "pending",
                "received_label": _service_report_received_label(report),
                "received_tone": "success" if report.payment_status == ServiceReport.PaymentStatus.PAID else "pending",
            }
        )
    csv_query = {}
    if selected_contract:
        csv_query["contract"] = str(selected_contract.id)
    if date_from_raw:
        csv_query["date_from"] = date_from_raw
    if date_to_raw:
        csv_query["date_to"] = date_to_raw
    csv_url = reverse("export_csv")
    if csv_query:
        csv_url = f"{csv_url}?{urlencode(csv_query)}"
    return render(
        request,
        "accounts/mei_reports.html",
        {
            "contracts": contracts_list,
            "selected_contract": selected_contract,
            "report_form": report_form,
            "reports": reports,
            "report_rows": report_rows,
            "pending_requests": pending_requests,
            "responded_requests": responded_requests,
            "status_filter": status_filter,
            "search_query": search_query,
            "view_filter": view_filter,
            "receive_filter": receive_filter,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "status_choices": [
                (value, "Recebido" if value == ServiceReport.Status.PAID else label)
                for value, label in ServiceReport.Status.choices
            ],
            "csv_url": csv_url,
        },
    )


@login_required
@require_GET
def mei_service_report_whatsapp(request, report_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        id=report_id,
        employee__user=request.user,
    )
    if not report.conference_is_accessible:
        messages.error(request, "Gere um link ativo antes de enviar pelo WhatsApp.")
        return redirect("mei_service_report_detail", report_id=report.id)

    if not report.whatsapp_sent_attempted_at:
        report.whatsapp_sent_attempted_at = timezone.now()
        report.save(update_fields=["whatsapp_sent_attempted_at", "updated_at"])

    conference_url = request.build_absolute_uri(reverse("public_service_report_conference", args=[report.conference_token]))
    return redirect(_build_service_report_whatsapp_url(report, conference_url))


@login_required
def mei_service_report_detail(request, report_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        id=report_id,
        employee__user=request.user,
    )
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "generate_conference_link":
            expires_at = None
            expires_at_raw = (request.POST.get("conference_expires_at") or "").strip()
            if expires_at_raw:
                try:
                    expires_at = datetime.strptime(expires_at_raw, "%Y-%m-%dT%H:%M")
                    expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
                except ValueError:
                    messages.error(request, "Informe uma data de expiracao valida.")
                    return redirect("mei_service_report_detail", report_id=report.id)
                if expires_at <= timezone.now():
                    messages.error(request, "A expiracao precisa ser uma data futura.")
                    return redirect("mei_service_report_detail", report_id=report.id)
            report.ensure_conference_link(expires_at=expires_at)
            report.save(
                update_fields=[
                    "conference_token",
                    "conference_link_created_at",
                    "conference_first_viewed_at",
                    "conference_reviewed_at",
                    "conference_comment",
                    "conference_revoked_at",
                    "conference_expires_at",
                    "conference_final_status",
                    "status",
                    "updated_at",
                ]
            )
            messages.success(request, "Link de conferencia gerado.")
            return redirect("mei_service_report_detail", report_id=report.id)
        if action == "revoke_conference_link":
            if report.conference_token and not report.conference_revoked_at:
                report.revoke_conference_link()
                report.save(update_fields=["conference_revoked_at", "conference_final_status", "updated_at"])
                messages.success(request, "Link de conferencia revogado.")
            else:
                messages.info(request, "Este relatorio nao possui link ativo para revogar.")
            return redirect("mei_service_report_detail", report_id=report.id)
        messages.error(request, "Acao invalida para este relatorio.")
        return redirect("mei_service_report_detail", report_id=report.id)

    selected_contract = getattr(report, "contract", None)
    reports_url = reverse("mei_reports")
    if selected_contract:
        reports_url = f"{reports_url}?contract={selected_contract.id}"
    conference_url = ""
    if report.conference_is_accessible:
        conference_url = request.build_absolute_uri(reverse("public_service_report_conference", args=[report.conference_token]))
    whatsapp_message = _build_service_report_whatsapp_message(report, conference_url) if conference_url else ""
    whatsapp_url = reverse("mei_service_report_whatsapp", args=[report.id]) if conference_url else ""
    return render(
        request,
        "accounts/mei_service_report_detail.html",
        {
            "employee": report.employee,
            "report": report,
            "payload": report.summary_payload or {},
            "reports_url": reports_url,
            "conference_url": conference_url,
            "whatsapp_message": whatsapp_message if conference_url else "",
            "whatsapp_url": whatsapp_url,
            "pdf_url": reverse("mei_service_report_pdf", args=[report.id]),
            "status_label": _service_report_status_label(report),
        },
    )


@login_required
def mei_service_report_pdf(request, report_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        id=report_id,
        employee__user=request.user,
    )
    return _service_report_pdf_response(report)


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


@require_GET
def public_service_report_conference(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
    )
    now = timezone.now()
    unavailable_reason = ""
    if report.conference_revoked_at:
        unavailable_reason = "Este link de conferencia foi revogado pelo profissional."
    elif report.conference_is_expired:
        unavailable_reason = "Este link de conferencia expirou."
        if report.conference_final_status != ServiceReport.ConferenceStatus.EXPIRED:
            report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
            report.save(update_fields=["conference_final_status", "updated_at"])

    if unavailable_reason:
        return render(
            request,
            "public/service_report_conference.html",
            {
                "report": None,
                "payload": {},
                "unavailable_reason": unavailable_reason,
            },
            status=410,
        )

    update_fields = []
    if not report.conference_first_viewed_at:
        report.conference_first_viewed_at = now
        update_fields.append("conference_first_viewed_at")
    if report.conference_final_status == ServiceReport.ConferenceStatus.PENDING:
        report.conference_final_status = ServiceReport.ConferenceStatus.VIEWED
        update_fields.append("conference_final_status")
    if report.status == ServiceReport.Status.SENT:
        report.status = ServiceReport.Status.VIEWED
        update_fields.append("status")
    if update_fields:
        update_fields.append("updated_at")
        report.save(update_fields=update_fields)

    public_pdf_url = reverse("public_service_report_pdf", args=[report.conference_token])
    public_xlsx_url = reverse("public_service_report_xlsx", args=[report.conference_token])
    return render(
        request,
        "public/service_report_conference.html",
        {
            "report": report,
            "payload": report.summary_payload or {},
            "conference_url": request.build_absolute_uri(),
            "pdf_url": public_pdf_url,
            "xlsx_url": public_xlsx_url,
        },
    )


@require_GET
def public_service_report_pdf(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
        conference_revoked_at__isnull=True,
    )
    if report.conference_is_expired:
        report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
        report.save(update_fields=["conference_final_status", "updated_at"])
        raise PermissionDenied("Link de conferencia expirado.")
    if not report.conference_first_viewed_at:
        report.conference_first_viewed_at = timezone.now()
        report.save(update_fields=["conference_first_viewed_at", "updated_at"])
    return _service_report_pdf_response(report)


@require_GET
def public_service_report_xlsx(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
        conference_revoked_at__isnull=True,
    )
    if report.conference_is_expired:
        report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
        report.save(update_fields=["conference_final_status", "updated_at"])
        raise PermissionDenied("Link de conferencia expirado.")
    if not report.conference_first_viewed_at:
        report.conference_first_viewed_at = timezone.now()
        report.save(update_fields=["conference_first_viewed_at", "updated_at"])
    return _service_report_xlsx_response(report)


@login_required
def mei_service_report_request_detail(request, request_id):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    report_request = get_object_or_404(
        ActivityReportRequest.objects.select_related(
            "company",
            "contract",
            "employee",
            "employee__user",
            "requested_by",
            "response_report",
        ),
        id=request_id,
        employee__user=request.user,
    )
    employee = report_request.employee

    can_respond = report_request.status == ActivityReportRequest.Status.PENDING
    initial = {
        "date_from": report_request.date_from or timezone.localdate().replace(day=1),
        "date_to": report_request.date_to or timezone.localdate(),
        "title": report_request.subject[:120] if report_request.subject else "",
        "status": ServiceReport.Status.SENT,
    }
    if report_request.contract_id:
        initial["contract"] = report_request.contract_id

    report_form = ServiceReportCreateForm(employee=employee, initial=initial)
    if report_request.contract_id:
        report_form.fields["contract"].queryset = (
            Contract.objects.filter(
                id=report_request.contract_id,
                employee=employee,
                company=report_request.company,
            )
            .select_related("company")
            .order_by("-start_date", "-created_at")
        )

    if request.method == "POST" and (request.POST.get("action") or "").strip().lower() == "respond_request" and can_respond:
        report_form = ServiceReportCreateForm(request.POST, employee=employee)
        if report_request.contract_id:
            report_form.fields["contract"].queryset = (
                Contract.objects.filter(
                    id=report_request.contract_id,
                    employee=employee,
                    company=report_request.company,
                )
                .select_related("company")
                .order_by("-start_date", "-created_at")
            )
        if report_form.is_valid():
            with transaction.atomic():
                report = report_form.save(commit=False)
                report.summary_payload = _build_service_report_payload(
                    report.contract,
                    report.date_from,
                    report.date_to,
                )
                report.save()
                report_request.response_report = report
                report_request.response_text = report.description
                report_request.status = ActivityReportRequest.Status.RESPONDED
                report_request.save(
                    update_fields=[
                        "response_report",
                        "response_text",
                        "status",
                        "responded_at",
                        "reviewed_at",
                        "reviewed_by",
                        "is_answered",
                    ]
                )
            redirect_url = f"{reverse('mei_service_report_request_detail', args=[report_request.id])}?event=request_answered"
            if report_request.contract_id:
                redirect_url = f"{redirect_url}&contract={report_request.contract_id}"
            return redirect(redirect_url)

    reports_url = reverse("mei_reports")
    if report_request.contract_id:
        reports_url = f"{reports_url}?contract={report_request.contract_id}"

    return render(
        request,
        "accounts/mei_service_report_request_detail.html",
        {
            "employee": employee,
            "report_request": report_request,
            "report_form": report_form,
            "can_respond": can_respond,
            "reports_url": reports_url,
        },
    )


def terms_view(request):
    return render(request, "public/terms.html")


def help_view(request):
    return render(request, "public/help.html")


def privacy_view(request):
    return render(request, "public/privacy.html")


def _public_base_url(request):
    app_base_url = (settings.APP_BASE_URL or "").rstrip("/")
    return app_base_url or f"{request.scheme}://{request.get_host()}"


def _public_page_context(request, path="/"):
    base_url = _public_base_url(request)
    canonical_url = f"{base_url}{path}"
    og_image_url = f"{base_url}{static('img/public/prints/painel-profissional-mobile.png.jpg')}"
    return {
        "canonical_url": canonical_url,
        "og_url": canonical_url,
        "og_image_url": og_image_url,
    }


def landing_view(request):
    if request.user.is_authenticated:
        return redirect("employee_dashboard")
    context = _public_page_context(request, "/")
    return render(request, "public/landing.html", context)


def evaluation_view(request):
    context = _public_page_context(request, "/avaliacao/")
    return render(request, "public/evaluation.html", context)


def evaluation_next_step_view(request):
    context = _public_page_context(request, "/avaliacao/proximo-passo/")
    return render(request, "public/evaluation_next_step.html", context)


@require_GET
def pwa_manifest(request):
    manifest = {
        "id": "/",
        "name": "HoraCerta - Gestao de Horas",
        "short_name": "HoraCerta",
        "description": "Controle de horas, clientes e relatorios para profissionais e MEIs.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": "#0b1220",
        "background_color": "#0b1220",
        "categories": ["business", "productivity"],
        "lang": "pt-BR",
        "icons": [
            {
                "src": static("pwa/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("pwa/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("pwa/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    response = HttpResponse(
        json.dumps(manifest, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@require_GET
def pwa_service_worker(request):
    sw_path = settings.BASE_DIR / "static" / "js" / "sw.js"
    source = sw_path.read_text(encoding="utf-8")
    response = HttpResponse(source, content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    return response

