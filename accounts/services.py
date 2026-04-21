from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from companies.models import Employee
from timeclock.models import Contract

User = get_user_model()


class MeiLinkError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MeiLinkResult:
    user: User
    employee: Employee
    contract: Contract | None
    user_created: bool
    linked_existing_user: bool
    employee_created: bool
    contract_created: bool


def _normalize_email(raw_email: str) -> str:
    return (raw_email or "").strip().lower()


def _is_contract_requested(contract_payload: dict) -> bool:
    notes = (contract_payload.get("notes") or "").strip()
    return any(
        [
            contract_payload.get("hourly_rate") is not None,
            contract_payload.get("start_date"),
            contract_payload.get("end_date"),
            contract_payload.get("contract_file"),
            notes,
        ]
    )


def find_user_by_email(email: str):
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return User.objects.filter(Q(email__iexact=normalized) | Q(username__iexact=normalized)).first()


def create_or_link_mei_by_email(
    *,
    company,
    full_name: str,
    mei_email: str,
    password: str | None = None,
    contract_payload: dict | None = None,
) -> MeiLinkResult:
    if not company:
        raise MeiLinkError("company_missing", "Empresa nao encontrada para criar MEI.")

    normalized_email = _normalize_email(mei_email)
    if not normalized_email:
        raise MeiLinkError("invalid_email", "Informe um email valido.")

    normalized_full_name = (full_name or "").strip()
    if not normalized_full_name:
        raise MeiLinkError("invalid_full_name", "Informe o nome completo do MEI.")

    contract_payload = contract_payload or {}

    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(Q(email__iexact=normalized_email) | Q(username__iexact=normalized_email))
            .first()
        )
        user_created = False
        linked_existing_user = False

        if user:
            if user.role != User.Role.FUNCIONARIO:
                raise MeiLinkError(
                    "email_role_conflict",
                    "Este email pertence a uma conta de empresa/admin. Use outro email do MEI.",
                )
            linked_existing_user = True
        else:
            if not password:
                raise MeiLinkError("password_required", "Defina a senha para criar a conta principal do MEI.")
            try:
                user = User.objects.create_user(
                    username=normalized_email,
                    email=normalized_email,
                    password=password,
                    role=User.Role.FUNCIONARIO,
                )
                user_created = True
            except IntegrityError:
                user = (
                    User.objects.select_for_update()
                    .filter(Q(email__iexact=normalized_email) | Q(username__iexact=normalized_email))
                    .first()
                )
                if not user:
                    raise
                if user.role != User.Role.FUNCIONARIO:
                    raise MeiLinkError(
                        "email_role_conflict",
                        "Este email pertence a uma conta de empresa/admin. Use outro email do MEI.",
                    )
                linked_existing_user = True

        if Employee.objects.filter(user=user, company=company).exists():
            raise MeiLinkError(
                "already_linked_company",
                "Este MEI ja possui vinculo com sua empresa. Use o gerenciamento de vinculos para continuar.",
            )

        employee = Employee.objects.create(
            user=user,
            company=company,
            full_name=normalized_full_name,
            is_active=True,
        )
        employee_created = True

        contract_created = False
        contract = None
        if _is_contract_requested(contract_payload):
            contract = Contract.objects.create(
                employee=employee,
                company=company,
                hourly_rate=contract_payload.get("hourly_rate"),
                start_date=contract_payload.get("start_date") or timezone.localdate(),
                end_date=contract_payload.get("end_date"),
                contract_file=contract_payload.get("contract_file"),
                notes=(contract_payload.get("notes") or "").strip(),
                is_active=True,
            )
            contract_created = True

        return MeiLinkResult(
            user=user,
            employee=employee,
            contract=contract,
            user_created=user_created,
            linked_existing_user=linked_existing_user,
            employee_created=employee_created,
            contract_created=contract_created,
        )
