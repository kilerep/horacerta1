from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode, urlparse
from xml.sax.saxutils import escape
import zipfile
from collections import defaultdict
import json
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from companies.models import Company, CompanySubscription, Employee, Feature, Plan
from companies.feature_flags import (
    get_company_feature_access,
    humanize_feature_reason,
    require_company_feature,
)
from timeclock.models import ActivityReportRequest, Contract, Punch
from timeclock.services import build_daily_summary, compute_day_total, filter_punches_by_period, format_hhmm
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
    CompanyContractForm,
    CompanyMEICreateForm,
    CompanyProfileForm,
    EmployeeSearchForm,
    LoginForm,
    MEIProfileForm,
    PeriodSearchForm,
    UnifiedSignupForm,
)

User = get_user_model()


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
    return ActivityReportRequest.objects.filter(company=company, is_answered=False).count()


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


def _subscription_status_badge(subscription, at_time=None):
    if not subscription:
        return {
            "label": "Sem assinatura ativa",
            "tone": "warn",
            "hint": "A empresa ainda nao possui plano atual definido.",
        }

    at = at_time or timezone.now()
    status = subscription.status
    is_access_active = subscription.is_access_active(at)

    if status == CompanySubscription.Status.TRIAL:
        tone = "pending" if is_access_active else "warn"
        hint = "Periodo de avaliacao em andamento." if is_access_active else "Trial encerrado."
    elif status == CompanySubscription.Status.ACTIVE:
        tone = "success" if is_access_active else "warn"
        hint = "Assinatura ativa e apta para uso." if is_access_active else "Assinatura ativa sem acesso no periodo atual."
    elif status == CompanySubscription.Status.PAST_DUE:
        tone = "warn"
        hint = "Pagamento pendente. A regularizacao pode ser necessaria."
    elif status == CompanySubscription.Status.CANCELED:
        tone = "warn"
        hint = "Assinatura cancelada."
    elif status == CompanySubscription.Status.EXPIRED:
        tone = "warn"
        hint = "Assinatura expirada."
    else:
        tone = "warn"
        hint = "Status de assinatura nao mapeado."

    return {
        "label": subscription.get_status_display(),
        "tone": tone,
        "hint": hint,
    }


def _redirect_if_not_mei(request):
    if request.user.role != User.Role.FUNCIONARIO:
        return redirect("dashboard")
    return None


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
                        "action_label": "Revisar no cadastro MEI" if not latest_contract else "Editar vinculo",
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
        ).select_related("contract", "contract__employee", "contract__employee__user")

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
                "action_label": "Revisar no cadastro MEI" if not latest_contract else "Editar vinculo",
            }
        )

    contract_rows = []
    for contract in contracts_qs.order_by("-start_date", "-created_at", "employee__user__username")[:300]:
        mei_name = _contract_mei_label(contract)
        contract_rows.append({"contract": contract, "mei_name": mei_name})

    punch_rows = []
    for punch in punches_period_qs.order_by("-timestamp")[:120]:
        mei_name = _contract_mei_label(punch.contract)
        punch_rows.append({"punch": punch, "mei_name": mei_name})

    quick_links = [
        {
            "label": "Resumo operacional",
            "url": reverse("company_operational_summary"),
            "hint": "Visao por profissional no periodo",
        },
        {"label": "Gerenciar profissionais", "url": reverse("company_meis"), "hint": "Cadastro e status dos MEIs"},
        {"label": "Ver vinculos", "url": reverse("company_contracts"), "hint": "Lista, status e edicao"},
        {"label": "Abrir historico", "url": reverse("company_history"), "hint": "Conferencia por periodo"},
        {"label": "Relatorios", "url": reverse("company_reports"), "hint": "Resumo e exportacao"},
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
    create_mei_form = CompanyMEICreateForm()
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

    if request.method == "POST":
        action = (request.POST.get("action") or "create_mei").strip().lower()
        if action == "create_link":
            create_link_form = CompanyContractForm(
                request.POST,
                request.FILES,
                company=company,
                request=request,
                prefix="link",
            )
            if not company:
                create_link_form.add_error(None, "Empresa nao encontrada para criar vinculo.")
            elif create_link_form.is_valid():
                employee = create_link_form.cleaned_data.get("employee")
                if not employee or not Employee.objects.filter(id=employee.id, company=company).exists():
                    create_link_form.add_error("employee", "MEI invalido para esta empresa.")
                else:
                    contract = create_link_form.save(commit=False)
                    contract.company = company
                    contract.save()
                    return redirect(f"{reverse('company_meis')}?status=link_created&highlight_employee={employee.id}")
            create_mei_form = CompanyMEICreateForm()
        else:
            create_mei_form = CompanyMEICreateForm(request.POST, request.FILES)
            if not company:
                create_mei_form.add_error(None, "Empresa nao encontrada para criar MEI.")
            elif create_mei_form.is_valid():
                _employee, contract = create_mei_form.create_mei_and_optional_contract(company)
                status = "created_with_contract" if contract else "created_mei"
                return redirect(f"{reverse('company_meis')}?status={status}")
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
    employee_rows = []
    for employee in employees_list:
        employee_contracts = contracts_by_employee.get(employee.id, [])
        lifecycle = employee_lifecycle_summary(employee, employee_contracts)
        latest_contract = employee_contracts[0] if employee_contracts else None
        operational_count = sum(1 for contract in employee_contracts if contract_is_operational(contract))
        manage_contracts_url = (
            f"{reverse('company_contracts')}?edit={latest_contract.id}"
            if latest_contract
            else reverse("company_contracts")
        )
        setup_first_link_url = f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente"
        employee_rows.append(
            {
                "employee": employee,
                "state": lifecycle,
                "total_contracts": len(employee_contracts),
                "active_contracts": operational_count,
                "latest_contract": latest_contract,
                "profile_url": reverse("company_mei_profile", args=[employee.id]),
                "situation_url": reverse("company_mei_profile", args=[employee.id]),
                "manage_contracts_url": manage_contracts_url,
                "setup_first_link_url": setup_first_link_url,
                "action_url": setup_first_link_url if not latest_contract else manage_contracts_url,
                "action_label": "Configurar primeiro vinculo" if not latest_contract else "Gerenciar vinculos",
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
        "pending_reports_count": _pending_reports_count_for_company(company),
    }
    return render(request, "accounts/company_meis.html", context)


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
            status_label = "Aguardando vinculo"
            status_tone = "pending"
            status_hint = "Profissional cadastrado sem vinculo operacional. Use a tela de MEIs como fluxo principal."
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
    latest_contract = contracts[0] if contracts else None
    active_contracts = sum(1 for contract in contracts if contract_is_operational(contract))

    return render(
        request,
        "accounts/company_mei_profile.html",
        {
            "company": company,
            "employee": employee,
            "state": lifecycle,
            "contracts": contracts,
            "latest_contract": latest_contract,
            "active_contracts": active_contracts,
            "create_contract_url": f"{reverse('company_meis')}?link_for={employee.id}#vinculo-existente",
            "edit_contract_url": f"{reverse('company_contracts')}?edit={latest_contract.id}" if latest_contract else None,
            "history_url": f"{reverse('company_history')}?employee={employee.id}",
            "meis_url": reverse("company_meis"),
        },
    )


@login_required
def company_history(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    period_form = PeriodSearchForm(request.GET or None)
    employees = Employee.objects.filter(company=company).select_related("user").order_by("full_name") if company else Employee.objects.none()

    selected_employee = (request.GET.get("employee") or "").strip()
    page_raw = (request.GET.get("page") or "1").strip()

    contracts = (
        Contract.objects.filter(
            company=company,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        if company
        else Contract.objects.none()
    )
    punches = Punch.objects.filter(contract__in=contracts).select_related(
        "contract", "contract__employee", "contract__employee__user"
    )

    if selected_employee:
        punches = punches.filter(contract__employee_id=selected_employee)

    if period_form.is_valid():
        d1 = period_form.cleaned_data.get("date_from")
        d2 = period_form.cleaned_data.get("date_to")
        if d1:
            punches = punches.filter(timestamp__gte=timezone.make_aware(datetime.combine(d1, time.min)))
        if d2:
            punches = punches.filter(timestamp__lte=timezone.make_aware(datetime.combine(d2, time.max)))

    total_count = punches.count()
    page_size = 200
    try:
        page = max(1, int(page_raw))
    except ValueError:
        page = 1
    offset = (page - 1) * page_size
    punches_page = list(punches.order_by("-timestamp")[offset : offset + page_size])
    showing_count = len(punches_page)

    base_qs = {}
    if selected_employee:
        base_qs["employee"] = selected_employee
    if request.GET.get("date_from"):
        base_qs["date_from"] = request.GET.get("date_from")
    if request.GET.get("date_to"):
        base_qs["date_to"] = request.GET.get("date_to")

    prev_query = urlencode({**base_qs, "page": page - 1}) if page > 1 else ""
    next_query = urlencode({**base_qs, "page": page + 1}) if (offset + showing_count) < total_count else ""

    context = {
        "company": company,
        "period_form": period_form,
        "employees": employees,
        "selected_employee": selected_employee,
        "punches": punches_page,
        "total_count": total_count,
        "showing_count": showing_count,
        "page": page,
        "prev_query": prev_query,
        "next_query": next_query,
    }
    return render(request, "accounts/company_history.html", context)


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
            "status_label": "Sem registros no periodo",
            "status_kind": "empty",
            "details_url": (
                f"{reverse('company_history')}?employee={employee.id}&date_from={date_from.strftime('%Y-%m-%d')}"
                f"&date_to={date_to.strftime('%Y-%m-%d')}"
            ),
        }

    punches_by_employee_day = defaultdict(list)
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        employee_id = str(punch.contract.employee_id)
        punches_by_employee_day[(employee_id, local_ts.date())].append(local_ts)

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
        "employee_rows": employee_rows,
    }
    return render(request, "accounts/company_operational_summary.html", context)


@login_required
@require_company_feature("advanced_reports")
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
@require_company_feature("incident_center")
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

    plans = list(Plan.objects.filter(is_active=True).prefetch_related("plan_features__feature").order_by("tier"))
    current_plan_id = subscription.plan_id if subscription else None
    current_plan = subscription.plan if subscription else None

    features = list(Feature.objects.filter(is_active=True).order_by("category", "name"))

    enabled_codes_by_plan = {}
    enabled_features_by_plan = {}
    for plan in plans:
        enabled_features = [
            plan_feature.feature
            for plan_feature in plan.plan_features.all()
            if plan_feature.is_enabled and plan_feature.feature.is_active
        ]
        enabled_features_by_plan[plan.code] = enabled_features
        enabled_codes_by_plan[plan.code] = {feature.code for feature in enabled_features}

    plan_cards = []
    for plan in plans:
        plan_codes = enabled_codes_by_plan.get(plan.code, set())
        exclusive_count = 0
        for feature in features:
            if feature.code not in plan_codes:
                continue
            lower_tier_has = any(
                feature.code in enabled_codes_by_plan.get(lower_plan.code, set())
                for lower_plan in plans
                if lower_plan.tier < plan.tier
            )
            if not lower_tier_has:
                exclusive_count += 1
        plan_cards.append(
            {
                "plan": plan,
                "is_current": plan.id == current_plan_id,
                "feature_count": len(plan_codes),
                "exclusive_count": exclusive_count,
                "feature_preview": enabled_features_by_plan.get(plan.code, [])[:6],
            }
        )

    current_plan_tier = current_plan.tier if current_plan else 0
    suggested_upgrade = next((plan for plan in plans if plan.tier > current_plan_tier), None)

    def _first_plan_for_feature(feature_code):
        for plan in plans:
            if feature_code in enabled_codes_by_plan.get(plan.code, set()):
                return plan
        return None

    available_features = []
    blocked_features = []
    for feature in features:
        access = get_company_feature_access(
            company=company,
            feature_code=feature.code,
            user_role=None,
            at_time=now,
        )
        first_plan = _first_plan_for_feature(feature.code)
        item = {
            "feature": feature,
            "allowed": access.allowed,
            "reason": access.reason,
            "reason_label": humanize_feature_reason(access.reason),
            "audience_label": feature.get_required_role_display(),
            "available_from_plan": first_plan,
            "available_from_label": first_plan.name if first_plan else "Nao disponivel",
        }
        if access.allowed:
            available_features.append(item)
        else:
            blocked_features.append(item)

    comparison_rows = []
    for feature in features:
        comparison_rows.append(
            {
                "feature": feature,
                "plan_availability": [
                    {
                        "plan": plan,
                        "enabled": feature.code in enabled_codes_by_plan.get(plan.code, set()),
                    }
                    for plan in plans
                ],
            }
        )

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
        "plan_cards": plan_cards,
        "available_features": available_features,
        "blocked_features": blocked_features,
        "comparison_rows": comparison_rows,
        "comparison_plans": plans,
        "current_plan_name": subscription.plan.name if subscription else "Sem plano",
        "current_plan_code": subscription.plan.code if subscription else "",
        "current_plan_description": subscription.plan.description if subscription else "Sem assinatura ativa no momento.",
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
        "suggested_upgrade": suggested_upgrade,
    }
    return render(request, "accounts/company_plan.html", context)


@login_required
def company_settings(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    return render(request, "accounts/company_settings.html")


@login_required
def company_profile(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    if not company:
        return redirect("dashboard_empresa")

    if request.method == "POST":
        form = CompanyProfileForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            return redirect("company_profile")
    else:
        form = CompanyProfileForm(instance=company)

    return render(request, "accounts/company_profile.html", {"form": form, "company": company})


@login_required
def mei_panel(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    contracts = (
        Contract.objects.filter(employee__user=request.user, is_active=True)
        .select_related("company", "employee", "employee__user")
        .order_by("-created_at")
    )

    selected_contract = None
    selected_contract_id = request.GET.get("contract")

    if contracts.exists():
        selected_contract = contracts.filter(id=selected_contract_id).first() if selected_contract_id else contracts.first()
        if not selected_contract:
            selected_contract = contracts.first()

    current_period_label = _month_label_ptbr(timezone.localdate())
    total_hours_month = "00:00"
    accrued_value = Decimal("0.00")
    accrued_value_brl = "R$ 0,00"
    worked_days = 0
    complete_days = 0
    incomplete_days = 0
    recent_today_punches = []

    if selected_contract:
        today = timezone.localdate()
        month_start = today.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(month_start, time.min))
        end_dt = timezone.make_aware(datetime.combine(today, time.max))
        monthly_punches = list(
            Punch.objects.filter(contract=selected_contract, timestamp__range=(start_dt, end_dt)).order_by("timestamp")
        )
        month_rows, _max_cols = build_daily_summary(monthly_punches, min_punch_columns=4)
        total_seconds = sum(row["total_seconds"] for row in month_rows)
        total_hours_month = format_hhmm(total_seconds)
        worked_days = len(month_rows)
        complete_days = sum(1 for row in month_rows if not row["is_incomplete"])
        incomplete_days = sum(1 for row in month_rows if row["is_incomplete"])
        today_start = timezone.make_aware(datetime.combine(today, time.min))
        today_end = timezone.make_aware(datetime.combine(today, time.max))
        recent_today_punches = [
            timezone.localtime(p.timestamp).strftime("%H:%M")
            for p in Punch.objects.filter(contract=selected_contract, timestamp__range=(today_start, today_end))
            .order_by("-timestamp")[:6]
        ]

        hourly_rate = selected_contract.hourly_rate or Decimal("0")
        accrued_value = ((Decimal(total_seconds) / Decimal("3600")) * hourly_rate).quantize(Decimal("0.01"))
        brl = f"{accrued_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        accrued_value_brl = f"R$ {brl}"

    context = {
        "contracts": contracts,
        "contracts_count": contracts.count(),
        "selected_contract": selected_contract,
        "current_period_label": current_period_label,
        "total_hours_month": total_hours_month,
        "accrued_value_brl": accrued_value_brl,
        "worked_days": worked_days,
        "complete_days": complete_days,
        "incomplete_days": incomplete_days,
        "pending_days": incomplete_days,
        "recent_today_punches": recent_today_punches,
    }
    return render(request, "accounts/mei_panel.html", context)


@login_required
def mei_profile(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        active_contract = (
            Contract.objects.filter(employee__user=request.user)
            .select_related("company", "employee", "employee__user")
            .order_by("-created_at")
            .first()
        )
        if not active_contract:
            return redirect("mei_panel")
        employee = Employee.objects.create(
            user=request.user,
            company=active_contract.company,
            full_name=request.user.get_full_name() or request.user.username,
            is_active=True,
        )

    if request.method == "POST":
        form = MEIProfileForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            return redirect("mei_profile")
    else:
        form = MEIProfileForm(instance=employee)

    return render(request, "accounts/mei_profile.html", {"form": form, "employee": employee})


@login_required
def mei_history(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    contracts = Contract.objects.filter(employee__user=request.user, is_active=True).select_related("company", "employee", "employee__user")
    selected_contract = None
    punches = Punch.objects.none()
    selected_contract_id = request.GET.get("contract")
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    parsed_date_from = None
    parsed_date_to = None

    if contracts.exists():
        selected_contract = contracts.filter(id=selected_contract_id).first() if selected_contract_id else contracts.first()
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

    history_rows = sorted(history_rows, key=lambda row: row["date"], reverse=True)
    for row in history_rows:
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
    total_days_complete = sum(1 for row in history_rows if row["punches_count"] > 0 and not row["is_incomplete"])
    total_days_incomplete = sum(1 for row in history_rows if row["punches_count"] > 0 and row["is_incomplete"])

    if parsed_date_from and parsed_date_to:
        period_label = f"{parsed_date_from.strftime('%d/%m/%Y')} ate {parsed_date_to.strftime('%d/%m/%Y')}"
    else:
        period_label = "Periodo completo"

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
        "summary_total_days_complete": total_days_complete,
        "summary_total_days_incomplete": total_days_incomplete,
    }
    return render(request, "accounts/mei_history.html", context)


@login_required
def mei_export(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    contracts = Contract.objects.filter(employee__user=request.user, is_active=True).select_related("company", "employee", "employee__user")
    return render(request, "accounts/mei_export.html", {"contracts": contracts})


@login_required
def mei_contract(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    all_contracts = list(
        Contract.objects.filter(employee__user=request.user)
        .select_related("company", "employee", "employee__user")
        .order_by("-start_date", "-created_at")
    )
    active_contracts = [contract for contract in all_contracts if contract_is_operational(contract)]
    inactive_contracts = [contract for contract in all_contracts if contract not in active_contracts]
    selected_contract_id = (request.GET.get("contract") or "").strip()

    active_contract = None
    if active_contracts:
        if selected_contract_id:
            active_contract = next((c for c in active_contracts if str(c.id) == selected_contract_id), None)
        if not active_contract:
            active_contract = active_contracts[0]

    return render(
        request,
        "accounts/mei_contract.html",
        {
            "active_contract": active_contract,
            "active_contracts": active_contracts,
            "inactive_contracts": inactive_contracts,
            "all_contracts": all_contracts,
        },
    )


@login_required
def mei_reports(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    return render(request, "accounts/mei_reports.html")


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
        "description": "Plataforma de gestao de horas entre empresa e MEI.",
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

