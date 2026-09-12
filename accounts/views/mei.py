# Split from the former monolithic accounts/views.py — see
# docs/EMPRESA_HORACERTA_ORGANIZACAO.md. Helpers/imports come from
# ._shared; this file only holds the views for its own audience.
from ._shared import *  # noqa: F401,F403


@login_required
def dashboard_employee(request):
    return redirect("employee_dashboard")


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
    service_today_count = ServiceJob.objects.filter(
        professional=request.user,
        start_date=today,
    ).exclude(status=ServiceJob.Status.ARCHIVED).count()
    new_service_requests_count = ServiceRequest.objects.filter(
        professional=request.user,
        status=ServiceRequest.Status.NEW,
    ).count()
    important_notifications_count = InternalNotification.objects.filter(
        recipient_user=request.user,
        audience=InternalNotification.Audience.MEI,
        is_read=False,
    ).count()

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
        "service_today_count": service_today_count,
        "new_service_requests_count": new_service_requests_count,
        "important_notifications_count": important_notifications_count,
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
    persistent_notifications = InternalNotification.objects.filter(
        recipient_user=request.user,
        audience=InternalNotification.Audience.MEI,
    ).select_related(
        "actor_user",
        "recipient_company",
    )
    persistent_cards = [_build_mei_persistent_notification_card(notification) for notification in persistent_notifications[:160]]
    dynamic_cards = _build_mei_dynamic_notifications(request.user)
    priority_order = {"high": 0, "new": 1, "normal": 2}
    attention_cards = sorted(
        [card for card in [*dynamic_cards, *persistent_cards] if card["priority"] in {"high", "new", "normal"}],
        key=lambda item: (
            priority_order.get(item["priority"], 3),
            -(timezone.localtime(item["created_at"]).timestamp() if item["created_at"] else 0),
        ),
    )[:5]
    all_cards = sorted(
        [*dynamic_cards, *persistent_cards],
        key=lambda item: (
            priority_order.get(item["priority"], 3),
            -(timezone.localtime(item["created_at"]).timestamp() if item["created_at"] else 0),
        ),
    )[:200]
    unread_count = sum(1 for card in persistent_cards if not card["is_read"])
    return render(
        request,
        "accounts/mei_notifications.html",
        {
            "attention_cards": attention_cards,
            "cards": all_cards,
            "unread_count": unread_count,
        },
    )


@login_required
@require_POST
def mei_notifications_bulk_action(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied
    action = (request.POST.get("action") or "").strip()
    if action == "read_all":
        now = timezone.now()
        updated = InternalNotification.objects.filter(
            recipient_user=request.user,
            audience=InternalNotification.Audience.MEI,
            is_read=False,
        ).update(is_read=True, read_at=now)
        if updated:
            messages.success(request, "Notificacoes marcadas como lidas.")
        else:
            messages.info(request, "Nao havia notificacoes novas.")
    else:
        messages.error(request, "Acao invalida para notificacoes.")
    return redirect("mei_notifications")


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
            "services_url": f"{reverse('service_job_list')}?contract={contract.id}",
            "service_requests_url": reverse("service_request_list"),
            "new_service_url": reverse("service_job_create"),
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
                _notify_service_report_created(report)
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
                # O relatorio precisa ter sido de fato compartilhado (link
                # gerado) antes de poder ser marcado como "Recebido" - sem essa
                # checagem, um relatorio ainda em Rascunho (nunca visto pelo
                # cliente) podia ser marcado como recebido, quebrando a logica
                # de confirmacao de recebimento. Bug da auditoria de 12/09/2026.
                if report.status == ServiceReport.Status.DRAFT:
                    messages.error(
                        request,
                        "Gere e compartilhe o link deste relatorio antes de marca-lo como recebido.",
                    )
                    event = "receive_invalid"
                else:
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
                report.ensure_conference_link()
                report.save()
                _notify_service_report_created(report)
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




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
