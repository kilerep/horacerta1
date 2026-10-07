# Split from the former monolithic accounts/views.py — see
# docs/EMPRESA_HORACERTA_ORGANIZACAO.md. Helpers/imports come from
# ._shared; this file only holds the views for its own audience.
from ._shared import *  # noqa: F401,F403


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




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
