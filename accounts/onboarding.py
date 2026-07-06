from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.mei_context import mei_contracts_for_user
from accounts.models import User
from timeclock.models import Punch, ServiceReport


@login_required
def mei_onboarding(request):
    """Show a derived, non-destructive start checklist for MEI/prestador users."""
    if request.user.role != User.Role.FUNCIONARIO:
        return redirect("dashboard")

    contracts = list(mei_contracts_for_user(request.user))
    missing_rate_contracts = [
        contract for contract in contracts if (contract.hourly_rate or Decimal("0.00")) <= Decimal("0.00")
    ]
    has_hour_records = Punch.objects.filter(contract__employee__user=request.user).exists()
    has_reports = ServiceReport.objects.filter(employee__user=request.user).exists()

    steps = [
        {
            "number": 1,
            "title": "Cadastre um cliente",
            "description": "Crie o cliente e o contrato que será usado para organizar horas e relatórios.",
            "is_complete": bool(contracts),
            "action_label": "Adicionar cliente",
            "action_url": "mei_client_create",
        },
        {
            "number": 2,
            "title": "Defina o valor por hora",
            "description": "O valor por hora permite acompanhar a estimativa do período antes do fechamento.",
            "is_complete": bool(contracts) and not missing_rate_contracts,
            "action_label": "Definir valor/hora",
            "action_url": "mei_client_edit",
            "contract_id": missing_rate_contracts[0].id if missing_rate_contracts else None,
            "blocked": not contracts,
        },
        {
            "number": 3,
            "title": "Registre sua primeira jornada",
            "description": "Registre os horários no cliente correto para alimentar o histórico e o resumo.",
            "is_complete": has_hour_records,
            "action_label": "Registrar horário",
            "action_url": "employee_dashboard",
        },
        {
            "number": 4,
            "title": "Revise e gere o primeiro relatório",
            "description": "Antes de fechar, confira cliente, período, horas e valor. O fechamento bloqueia o período para alterações do prestador.",
            "is_complete": has_reports,
            "action_label": "Abrir relatórios",
            "action_url": "mei_reports",
            "blocked": not has_hour_records,
        },
    ]
    completed_steps = sum(1 for step in steps if step["is_complete"])

    return render(
        request,
        "accounts/mei_onboarding.html",
        {
            "steps": steps,
            "completed_steps": completed_steps,
            "total_steps": len(steps),
            "has_contracts": bool(contracts),
            "has_hour_records": has_hour_records,
        },
    )
