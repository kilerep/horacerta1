from django.db.models import Q
from django.utils import timezone

PROFESSIONAL_STATE_CADASTRADO = "CADASTRADO"
PROFESSIONAL_STATE_AGUARDANDO = "AGUARDANDO_CONTRATO"
PROFESSIONAL_STATE_ATIVO = "ATIVO"
PROFESSIONAL_STATE_INATIVO = "INATIVO"

PROFESSIONAL_STATE_META = {
    PROFESSIONAL_STATE_CADASTRADO: {
        "label": "Cadastrado",
        "hint": "Conta criada e aguardando criacao do primeiro contrato.",
        "tone": "neutral",
    },
    PROFESSIONAL_STATE_AGUARDANDO: {
        "label": "Aguardando contrato",
        "hint": "Cadastro concluido, aguardando vigencia de contrato ativo.",
        "tone": "pending",
    },
    PROFESSIONAL_STATE_ATIVO: {
        "label": "Ativo",
        "hint": "Contrato ativo e operacional para registrar horarios.",
        "tone": "success",
    },
    PROFESSIONAL_STATE_INATIVO: {
        "label": "Inativo",
        "hint": "Sem contrato operacional ativo no momento.",
        "tone": "warn",
    },
}


def contract_is_operational(contract, on_date=None):
    if not contract or not contract.is_active:
        return False
    ref_date = on_date or timezone.localdate()
    if contract.start_date and contract.start_date > ref_date:
        return False
    if contract.end_date and contract.end_date < ref_date:
        return False
    return True


def contract_operational_q(prefix=""):
    ref_date = timezone.localdate()
    p = f"{prefix}__" if prefix else ""
    return Q(**{f"{p}is_active": True}) & Q(**{f"{p}start_date__lte": ref_date}) & (
        Q(**{f"{p}end_date__isnull": True}) | Q(**{f"{p}end_date__gte": ref_date})
    )


def employee_lifecycle_state(employee, contracts, on_date=None):
    ref_date = on_date or timezone.localdate()
    contract_list = list(contracts or [])

    if not getattr(employee, "is_active", True):
        return PROFESSIONAL_STATE_INATIVO

    if not contract_list:
        return PROFESSIONAL_STATE_CADASTRADO

    if any(contract_is_operational(c, on_date=ref_date) for c in contract_list):
        return PROFESSIONAL_STATE_ATIVO

    has_future_active = any(
        c.is_active and c.start_date and c.start_date > ref_date
        for c in contract_list
    )
    if has_future_active:
        return PROFESSIONAL_STATE_AGUARDANDO

    return PROFESSIONAL_STATE_INATIVO


def employee_lifecycle_summary(employee, contracts, on_date=None):
    state = employee_lifecycle_state(employee, contracts, on_date=on_date)
    meta = PROFESSIONAL_STATE_META[state]
    return {
        "key": state,
        "label": meta["label"],
        "hint": meta["hint"],
        "tone": meta["tone"],
    }
