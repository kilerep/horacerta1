# Split from the former monolithic accounts/views.py — see
# docs/EMPRESA_HORACERTA_ORGANIZACAO.md. Helpers/imports come from
# ._shared; this file only holds the views for its own audience.
from ._shared import *  # noqa: F401,F403


def _email_diagnostics():
    """Configuracao efetiva de e-mail, sem expor a senha."""
    from django.conf import settings

    backend = settings.EMAIL_BACKEND
    user = settings.EMAIL_HOST_USER or ""
    masked_user = (user[:2] + "***" + user[user.find("@"):]) if "@" in user else ("(vazio)" if not user else user[:2] + "***")
    problems = []
    if backend.endswith("console.EmailBackend"):
        problems.append(
            "O sistema está no modo CONSOLE: os e-mails só são impressos no log do servidor e nunca saem. "
            "Defina USE_CONSOLE_EMAIL=False no .env do servidor."
        )
    else:
        if not settings.EMAIL_HOST_USER:
            problems.append("EMAIL_HOST_USER está vazio no .env do servidor.")
        if not settings.EMAIL_HOST_PASSWORD:
            problems.append("EMAIL_HOST_PASSWORD está vazio no .env do servidor.")
        if settings.DEFAULT_FROM_EMAIL.endswith(".local"):
            problems.append("DEFAULT_FROM_EMAIL está com valor de exemplo (.local).")
    return {
        "backend": backend.rsplit(".", 2)[-2] if "." in backend else backend,
        "host": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "use_tls": settings.EMAIL_USE_TLS,
        "use_ssl": settings.EMAIL_USE_SSL,
        "user_masked": masked_user,
        "password_set": bool(settings.EMAIL_HOST_PASSWORD),
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "app_base_url": settings.APP_BASE_URL or "(não definido)",
        "problems": problems,
    }


@internal_staff_required
def internal_email(request):
    """Diagnostico do envio de e-mail (recuperacao de senha) + envio de teste."""
    from django.core.mail import send_mail

    result = None
    if request.method == "POST":
        to_email = (request.POST.get("to_email") or request.user.email or "").strip()
        try:
            send_mail(
                subject="HoraCerta - Teste de envio",
                message="Este é um e-mail de teste do HoraCerta. Se você recebeu, o envio de e-mail está funcionando.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,
            )
            result = {"ok": True, "to": to_email, "error": ""}
        except Exception as exc:  # noqa: BLE001 - mostrar a causa real ao administrador
            result = {"ok": False, "to": to_email, "error": f"{type(exc).__name__}: {exc}"}
    return render(
        request,
        "accounts/internal_email.html",
        {"diag": _email_diagnostics(), "result": result, "default_to": request.user.email},
    )


@internal_staff_required
def internal_funnel(request):
    """Funil de ativacao e retencao dos prestadores (so metricas agregadas)."""
    from accounts.analytics import funnel_summary

    return render(request, "accounts/internal_funnel.html", {"funnel": funnel_summary(days=30)})


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




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
