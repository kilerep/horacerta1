from datetime import datetime, time
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode, urlparse
from xml.sax.saxutils import escape
import zipfile

from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import ActivityReportRequest, Contract, Punch
from timeclock.services import build_daily_summary, compute_day_total, filter_punches_by_period, format_hhmm

from .forms import (
    CompanyContractForm,
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
            acc_type = form.cleaned_data["account_type"]
            pwd = form.cleaned_data["password1"]

            if acc_type == "EMPRESA":
                rh_email = form.cleaned_data["rh_email"].strip().lower()
                user = User.objects.create_user(
                    username=rh_email,
                    email=rh_email,
                    password=pwd,
                    role=User.Role.EMPRESA,
                )
                Company.objects.create(
                    name=form.cleaned_data["company_name"].strip(),
                    email=form.cleaned_data.get("company_email") or None,
                    owner=user,
                )
                login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
                return _redirect_for_role(user)

            mei_email = form.cleaned_data["mei_email"].strip().lower()
            full_name = form.cleaned_data["full_name"].strip()
            user = User.objects.create_user(
                username=mei_email,
                email=mei_email,
                password=pwd,
                role=User.Role.FUNCIONARIO,
            )
            Employee.objects.create(
                user=user,
                full_name=full_name,
                is_active=True,
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

    total_employees = 0
    total_active_contracts = 0
    total_punches_period = 0
    total_hours_period = "00:00"
    date_from = ""
    date_to = ""

    if company:
        contracts_base_qs = Contract.objects.filter(company=company).select_related(
            "employee_user",
            "employee_user__employee_profile",
        )
        active_contracts_base_qs = contracts_base_qs.filter(is_active=True)
        active_user_ids_qs = active_contracts_base_qs.values_list("employee_user_id", flat=True).distinct()
        employees_base_qs = Employee.objects.filter(user_id__in=active_user_ids_qs).select_related("user")

        q = ""
        if employee_search_form.is_valid():
            q = (employee_search_form.cleaned_data.get("q") or "").strip()

        if q:
            employees_qs = employees_base_qs.filter(
                Q(full_name__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__username__icontains=q)
            )
            contracts_qs = active_contracts_base_qs.filter(
                Q(employee_user__email__icontains=q)
                | Q(employee_user__username__icontains=q)
                | Q(employee_user__employee_profile__full_name__icontains=q)
            )
        else:
            employees_qs = employees_base_qs
            contracts_qs = active_contracts_base_qs

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
            contract__in=active_contracts_base_qs,
            timestamp__range=(start_dt, end_dt),
        ).select_related("contract", "contract__employee_user")

        total_employees = active_contracts_base_qs.values("employee_user_id").distinct().count()
        total_active_contracts = active_contracts_base_qs.count()
        total_punches_period = punches_period_qs.count()
        period_daily_rows, _period_columns = build_daily_summary(list(punches_period_qs), min_punch_columns=4)
        period_total_seconds = sum(row["total_seconds"] for row in period_daily_rows)
        total_hours_period = format_hhmm(period_total_seconds)
        date_from = start_date.strftime("%Y-%m-%d")
        date_to = end_date.strftime("%Y-%m-%d")

    period_result = {
        "date_from": date_from,
        "date_to": date_to,
        "total_punches": total_punches_period,
        "total_hours": total_hours_period,
    }

    active_contracts_by_user = {
        row["employee_user_id"]: row["count"]
        for row in contracts_qs.values("employee_user_id").annotate(count=Count("id"))
    }

    employee_rows = [
        {
            "employee": employee,
            "active_contracts": active_contracts_by_user.get(employee.user_id, 0),
        }
        for employee in employees_qs.order_by("full_name")[:200]
    ]

    contract_rows = []
    for contract in contracts_qs.order_by("-start_date", "-created_at", "employee_user__username")[:300]:
        profile = getattr(contract.employee_user, "employee_profile", None)
        mei_name = getattr(profile, "full_name", "") or contract.employee_user.email or contract.employee_user.username
        contract_rows.append({"contract": contract, "mei_name": mei_name})

    punch_rows = []
    for punch in punches_period_qs.order_by("-timestamp")[:120]:
        profile = getattr(punch.contract.employee_user, "employee_profile", None)
        mei_name = getattr(profile, "full_name", "") or punch.contract.employee_user.email or punch.contract.employee_user.username
        punch_rows.append({"punch": punch, "mei_name": mei_name})

    context = {
        "company": company,
        "employees": employee_rows,
        "contracts": contract_rows,
        "employee_search_form": employee_search_form,
        "period_form": period_form,
        "period_result": period_result,
        "total_employees": total_employees,
        "total_active_contracts": total_active_contracts,
        "total_punches_period": total_punches_period,
        "total_hours_period": total_hours_period,
        "punches_period": punch_rows,
        "relatorios_pendentes": 2,
    }
    return render(request, "accounts/dashboard_empresa.html", context)


@login_required
def company_meis(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    form = EmployeeSearchForm(request.GET or None)
    qs = Employee.objects.filter(companies=company).select_related("user").distinct() if company else Employee.objects.none()
    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(user__email__icontains=q) | Q(user__username__icontains=q))
    return render(request, "accounts/company_meis.html", {"company": company, "employees": qs.order_by("full_name")[:300], "employee_search_form": form})


@login_required
def company_contracts(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    contracts = (
        Contract.objects.filter(company=company).select_related("employee_user", "employee_user__employee_profile")
        if company
        else Contract.objects.none()
    )

    edit_contract = None
    edit_id = (request.GET.get("edit") or "").strip()
    if edit_id and company:
        edit_contract = get_object_or_404(Contract, id=edit_id, company=company)

    if request.method == "POST":
        contract_id = (request.POST.get("contract_id") or "").strip()
        instance = None
        if contract_id and company:
            instance = get_object_or_404(Contract, id=contract_id, company=company)

        form = CompanyContractForm(request.POST, request.FILES, instance=instance, company=company)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.company = company
            contract.save()
            return redirect("company_contracts")
        edit_contract = instance
    else:
        form = CompanyContractForm(instance=edit_contract, company=company)

    return render(
        request,
        "accounts/company_contracts.html",
        {
            "company": company,
            "contracts": contracts.order_by("-is_active", "-start_date", "employee_user__username")[:400],
            "form": form,
            "edit_contract": edit_contract,
        },
    )


@login_required
def company_history(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied

    company = _company_for_user(request.user)
    period_form = PeriodSearchForm(request.GET or None)
    employees = Employee.objects.filter(companies=company).select_related("user").distinct().order_by("full_name") if company else Employee.objects.none()

    selected_employee = (request.GET.get("employee") or "").strip()
    page_raw = (request.GET.get("page") or "1").strip()

    contracts = Contract.objects.filter(company=company) if company else Contract.objects.none()
    punches = Punch.objects.filter(contract__in=contracts).select_related(
        "contract", "contract__employee_user", "contract__employee_user__employee_profile"
    )

    if selected_employee:
        punches = punches.filter(contract__employee_user_id=selected_employee)

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
def company_reports(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    company = _company_for_user(request.user)
    employees = Employee.objects.filter(companies=company).select_related("user").distinct().order_by("full_name") if company else Employee.objects.none()
    contracts = Contract.objects.filter(company=company).select_related("employee_user", "employee_user__employee_profile") if company else Contract.objects.none()

    selected_employee = (request.GET.get("employee") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    export_kind = (request.GET.get("export") or "").strip().lower()

    punches_qs = Punch.objects.filter(contract__in=contracts).select_related(
        "contract", "contract__employee_user", "contract__employee_user__employee_profile"
    )

    if selected_employee:
        punches_qs = punches_qs.filter(contract__employee_user_id=selected_employee)

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
        mei_name = (
            getattr(getattr(contract.employee_user, "employee_profile", None), "full_name", "")
            or contract.employee_user.email
            or contract.employee_user.username
        )
        daily_rows, _max_cols = build_daily_summary(contract_punches_sorted, min_punch_columns=4)
        for row in daily_rows:
            note_text = (row.get("notes_summary") or "").strip()
            daily_report_rows.append(
                {
                    "date": row["date"],
                    "company_name": contract.company.name,
                    "mei_name": mei_name,
                    "contract_label": f"{contract.company.name} - R$ {contract.hourly_rate}/h",
                    "status": row["status"],
                    "total_hours_hhmm": row["total_hours_hhmm"],
                    "punches_label": " | ".join(row["punch_times"]) if row["punch_times"] else "-",
                    "note": note_text,
                    "has_note": bool(note_text),
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
        employee_user_id = (request.POST.get("employee_user") or "").strip()
        message = (request.POST.get("message") or "").strip()
        req_from = (request.POST.get("req_date_from") or "").strip()
        req_to = (request.POST.get("req_date_to") or "").strip()

        employee_obj = get_object_or_404(User, id=employee_user_id, role=User.Role.FUNCIONARIO)
        if not employees.filter(user=employee_obj).exists():
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
            employee_user=employee_obj,
            requested_by=request.user,
            date_from=req_date_from,
            date_to=req_date_to,
            message=message,
        )
        return redirect("company_reports")

    if export_kind == "xlsx":
        headers = ["MEI", "Data", "Hora", "Valor/h", "Observacao"]
        rows = []
        for punch in punches:
            mei_name = getattr(getattr(punch.contract.employee_user, "employee_profile", None), "full_name", "") or punch.contract.employee_user.email
            local_ts = timezone.localtime(punch.timestamp)
            rows.append(
                [
                    mei_name,
                    local_ts.strftime("%d/%m/%Y"),
                    local_ts.strftime("%H:%M"),
                    float(punch.contract.hourly_rate),
                    punch.note or "",
                ]
            )
        rows.append([])
        rows.append(["Total punches", metrics["total_punches"], "Total hours", metrics["total_hours_hhmm"], "Estimated payment"])
        rows.append(["", "", "", "", float(metrics["estimated_payment"])])
        return _build_xlsx_response("horacerta_relatorio.xlsx", headers, rows)

    if export_kind == "pdf":
        employee_name = "Todos"
        if selected_employee:
            emp_obj = employees.filter(user_id=selected_employee).first()
            if emp_obj:
                employee_name = emp_obj.full_name

        lines = [
            "HoraCerta - Relatorio de horários",
            f"Empresa: {company.name if company else '-'}",
            f"MEI: {employee_name}",
            f"Periodo: {date_from_raw or '-'} ate {date_to_raw or '-'}",
            "",
            f"Total de horas: {metrics['total_hours_hhmm']}",
            f"Total de horários: {metrics['total_punches']}",
            f"Pagamento estimado: R$ {metrics['estimated_payment']}",
            "",
            "horários (ultimas 25):",
        ]
        for punch in punches[:25]:
            mei_name = getattr(getattr(punch.contract.employee_user, "employee_profile", None), "full_name", "") or punch.contract.employee_user.email
            local_ts = timezone.localtime(punch.timestamp)
            lines.append(f"{local_ts:%d/%m/%Y %H:%M} | {mei_name} | {punch.note or '-'}")
        return _build_pdf_response("horacerta_relatorio.pdf", lines)

    requests_qs = ActivityReportRequest.objects.filter(company=company).select_related("employee_user", "employee_user__employee_profile")
    if selected_employee:
        requests_qs = requests_qs.filter(employee_user_id=selected_employee)

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
def company_docs(request):
    denied = _redirect_if_not_empresa(request)
    if denied:
        return denied
    return render(request, "accounts/company_docs.html")


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
        Contract.objects.filter(employee_user=request.user, is_active=True)
        .select_related("company")
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
        employee = Employee.objects.create(
            user=request.user,
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
    contracts = Contract.objects.filter(employee_user=request.user, is_active=True).select_related("company")
    selected_contract = None
    punches = Punch.objects.none()
    selected_contract_id = request.GET.get("contract")
    date_from_raw = request.GET.get("date_from") or ""
    date_to_raw = request.GET.get("date_to") or ""

    if contracts.exists():
        selected_contract = contracts.filter(id=selected_contract_id).first() if selected_contract_id else contracts.first()
        if selected_contract:
            base_punches = Punch.objects.filter(contract=selected_contract).order_by("timestamp")
            punches, _, _ = filter_punches_by_period(base_punches, date_from_raw, date_to_raw)

    grouped_rows, max_punches = build_daily_summary(punches, min_punch_columns=4)
    month_names_pt = [
        "Janeiro",
        "Fevereiro",
        "Marco",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    history_month_groups = []
    for row in grouped_rows:
        row_date = row["date"]
        month_key = (row_date.year, row_date.month)
        if not history_month_groups or history_month_groups[-1]["key"] != month_key:
            history_month_groups.append(
                {
                    "key": month_key,
                    "label": f"{month_names_pt[row_date.month - 1]} {row_date.year}",
                    "items": [],
                }
            )
        history_month_groups[-1]["items"].append(row)

    context = {
        "contracts": contracts,
        "selected_contract": selected_contract,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "history_days": grouped_rows,
        "history_month_groups": history_month_groups,
        "history_punch_columns": range(1, max_punches + 1),
    }
    return render(request, "accounts/mei_history.html", context)


@login_required
def mei_export(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    contracts = Contract.objects.filter(employee_user=request.user, is_active=True).select_related("company")
    return render(request, "accounts/mei_export.html", {"contracts": contracts})


@login_required
def mei_contract(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    active_contracts = list(
        Contract.objects.filter(employee_user=request.user, is_active=True)
        .select_related("company")
        .order_by("-created_at")
    )
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
        },
    )


@login_required
def mei_reports(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    return render(request, "accounts/mei_reports.html")


def terms_view(request):
    return render(request, "accounts/terms.html")


def help_view(request):
    return render(request, "accounts/help.html")
