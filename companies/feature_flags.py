from __future__ import annotations

from typing import Optional

from django.utils import timezone

from .models import Company, company_has_feature


def company_has_plan_feature(company: Company, feature_code: str, user_role: Optional[str] = None, at_time=None) -> bool:
    return company_has_feature(
        company=company,
        feature_code=feature_code,
        user_role=user_role,
        at_time=at_time or timezone.now(),
    )


def user_has_feature(user, feature_code: str, at_time=None) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    role = getattr(user, "role", None)
    company = None

    if role == "EMPRESA":
        company = user.owned_companies.first()
    elif role == "FUNCIONARIO":
        employee = getattr(user, "employee_profile", None)
        company = getattr(employee, "company", None)

    if not company:
        return False

    return company_has_plan_feature(
        company=company,
        feature_code=feature_code,
        user_role=role,
        at_time=at_time,
    )
