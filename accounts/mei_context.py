from __future__ import annotations

from dataclasses import dataclass

from timeclock.models import Contract
from timeclock.state import contract_operational_q

MEI_SELECTED_CONTRACT_SESSION_KEY = "hc_mei_selected_contract_id"


@dataclass(frozen=True)
class MeiContext:
    contracts: object
    selected_contract: Contract | None
    selected_employee: object | None
    selected_company: object | None
    requested_contract_id: str
    invalid_requested_contract: bool
    invalid_session_contract: bool


def mei_contracts_for_user(
    user,
    *,
    include_inactive_contracts: bool = False,
    operational_only: bool = False,
):
    qs = (
        Contract.objects.filter(
            employee__user=user,
            employee__user__is_active=True,
            employee__isnull=False,
            employee__user__isnull=False,
        )
        .select_related("company", "employee", "employee__user")
        .order_by("-start_date", "-created_at")
    )
    if not include_inactive_contracts:
        qs = qs.filter(is_active=True, employee__is_active=True)
    if operational_only:
        qs = qs.filter(contract_operational_q())
    return qs


def extract_requested_contract_id(request) -> str:
    return (
        request.GET.get("contract")
        or request.POST.get("contract")
        or request.POST.get("selected_contract")
        or ""
    ).strip()


def resolve_mei_context(
    request,
    *,
    include_inactive_contracts: bool = False,
    operational_only: bool = False,
    persist_selection: bool = True,
) -> MeiContext:
    contracts = mei_contracts_for_user(
        request.user,
        include_inactive_contracts=include_inactive_contracts,
        operational_only=operational_only,
    )
    requested_contract_id = extract_requested_contract_id(request)
    selected_contract = None
    invalid_requested_contract = False
    invalid_session_contract = False

    if requested_contract_id:
        selected_contract = contracts.filter(id=requested_contract_id).first()
        if selected_contract and persist_selection:
            request.session[MEI_SELECTED_CONTRACT_SESSION_KEY] = str(selected_contract.id)
            request.session.modified = True
        elif requested_contract_id:
            invalid_requested_contract = True

    if not selected_contract:
        session_contract_id = (request.session.get(MEI_SELECTED_CONTRACT_SESSION_KEY) or "").strip()
        if session_contract_id:
            selected_contract = contracts.filter(id=session_contract_id).first()
            if not selected_contract:
                invalid_session_contract = True
                if persist_selection:
                    request.session.pop(MEI_SELECTED_CONTRACT_SESSION_KEY, None)
                    request.session.modified = True

    if not selected_contract:
        selected_contract = contracts.first()
        if selected_contract and persist_selection:
            request.session[MEI_SELECTED_CONTRACT_SESSION_KEY] = str(selected_contract.id)
            request.session.modified = True
        elif persist_selection:
            request.session.pop(MEI_SELECTED_CONTRACT_SESSION_KEY, None)
            request.session.modified = True

    selected_employee = getattr(selected_contract, "employee", None) if selected_contract else None
    selected_company = getattr(selected_contract, "company", None) if selected_contract else None
    return MeiContext(
        contracts=contracts,
        selected_contract=selected_contract,
        selected_employee=selected_employee,
        selected_company=selected_company,
        requested_contract_id=requested_contract_id,
        invalid_requested_contract=invalid_requested_contract,
        invalid_session_contract=invalid_session_contract,
    )
