from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Optional

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import Company, CompanyFeatureOverride, CompanySubscription, Feature, Plan, PlanFeature


@dataclass(frozen=True)
class FeatureAccessResult:
    feature_code: str
    allowed: bool
    reason: str
    user_role: str | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    has_subscription: bool = False
    override_mode: str | None = None


FEATURE_REASON_LABELS = {
    "allowed": "Recurso liberado.",
    "company_missing": "Empresa nao localizada para o usuario atual.",
    "feature_not_found": "Feature nao cadastrada ou inativa no sistema.",
    "role_not_allowed": "Seu perfil nao possui acesso a este recurso.",
    "subscription_missing": "A empresa ainda nao possui assinatura ativa.",
    "subscription_inactive": "A assinatura atual esta inativa ou vencida.",
    "feature_not_in_plan": "Seu plano atual nao inclui este recurso.",
    "override_forced_enable": "Recurso liberado manualmente para esta empresa.",
    "override_forced_disable": "Recurso bloqueado manualmente para esta empresa.",
    "user_not_authenticated": "E necessario autenticar para usar este recurso.",
}


def _company_from_user(user) -> Optional[Company]:
    if not getattr(user, "is_authenticated", False):
        return None
    role = getattr(user, "role", None)
    if role == "EMPRESA":
        return user.owned_companies.first()
    if role == "FUNCIONARIO":
        employee = getattr(user, "employee_profile", None)
        return getattr(employee, "company", None)
    return None


def get_company_feature_access(
    company: Company | None,
    feature_code: str,
    user_role: str | None = None,
    at_time=None,
) -> FeatureAccessResult:
    at = at_time or timezone.now()
    normalized_code = (feature_code or "").strip()
    if not company:
        return FeatureAccessResult(
            feature_code=normalized_code,
            allowed=False,
            reason="company_missing",
            user_role=user_role,
        )

    feature = Feature.objects.filter(code=normalized_code, is_active=True).first()
    if not feature:
        return FeatureAccessResult(
            feature_code=normalized_code,
            allowed=False,
            reason="feature_not_found",
            user_role=user_role,
        )

    if user_role and feature.required_role != Feature.RequiredRole.ANY and feature.required_role != user_role:
        return FeatureAccessResult(
            feature_code=feature.code,
            allowed=False,
            reason="role_not_allowed",
            user_role=user_role,
        )

    override = (
        CompanyFeatureOverride.objects.filter(
            company=company,
            feature=feature,
        )
        .order_by("-updated_at")
        .first()
    )
    if override and override.is_valid(at):
        override_allowed = override.mode == CompanyFeatureOverride.Mode.FORCE_ENABLE
        return FeatureAccessResult(
            feature_code=feature.code,
            allowed=override_allowed,
            reason="override_forced_enable" if override_allowed else "override_forced_disable",
            user_role=user_role,
            override_mode=override.mode,
        )

    subscription = (
        CompanySubscription.objects.filter(company=company, is_current=True)
        .select_related("plan")
        .first()
    )
    if not subscription:
        return FeatureAccessResult(
            feature_code=feature.code,
            allowed=False,
            reason="subscription_missing",
            user_role=user_role,
        )

    if not subscription.is_access_active(at):
        return FeatureAccessResult(
            feature_code=feature.code,
            allowed=False,
            reason="subscription_inactive",
            user_role=user_role,
            plan_code=subscription.plan.code,
            plan_name=subscription.plan.name,
            has_subscription=True,
        )

    is_enabled = PlanFeature.objects.filter(
        plan=subscription.plan,
        feature=feature,
        is_enabled=True,
    ).exists()

    return FeatureAccessResult(
        feature_code=feature.code,
        allowed=is_enabled,
        reason="allowed" if is_enabled else "feature_not_in_plan",
        user_role=user_role,
        plan_code=subscription.plan.code,
        plan_name=subscription.plan.name,
        has_subscription=True,
    )


def get_user_feature_access(user, feature_code: str, at_time=None) -> FeatureAccessResult:
    role = getattr(user, "role", None) if getattr(user, "is_authenticated", False) else None
    company = _company_from_user(user)
    if not getattr(user, "is_authenticated", False):
        return FeatureAccessResult(
            feature_code=feature_code,
            allowed=False,
            reason="user_not_authenticated",
            user_role=role,
        )
    return get_company_feature_access(
        company=company,
        feature_code=feature_code,
        user_role=role,
        at_time=at_time,
    )


def company_has_plan_feature(company: Company, feature_code: str, user_role: Optional[str] = None, at_time=None) -> bool:
    return get_company_feature_access(
        company=company,
        feature_code=feature_code,
        user_role=user_role,
        at_time=at_time,
    ).allowed


def user_has_feature(user, feature_code: str, at_time=None) -> bool:
    return get_user_feature_access(user=user, feature_code=feature_code, at_time=at_time).allowed


def humanize_feature_reason(reason: str) -> str:
    return FEATURE_REASON_LABELS.get(reason, "Acesso indisponivel para o recurso solicitado.")


def get_feature_minimum_plan(feature_code: str) -> Plan | None:
    normalized_code = (feature_code or "").strip()
    plan_feature = (
        PlanFeature.objects.filter(
            feature__code=normalized_code,
            feature__is_active=True,
            plan__is_active=True,
            is_enabled=True,
        )
        .select_related("plan")
        .order_by("plan__tier")
        .first()
    )
    return plan_feature.plan if plan_feature else None


def get_feature_required_plan_badge(feature_code: str) -> tuple[str, str, str]:
    """
    Returns a tuple: (label, tone, plan_name)
    tone values: premium | pro | business
    """
    plan = get_feature_minimum_plan(feature_code)
    if not plan:
        return ("Premium", "premium", "")

    plan_name = (plan.name or "").strip()
    plan_code = (plan.code or "").strip().lower()
    if "business" in plan_code:
        tone = "business"
    elif "pro" in plan_code:
        tone = "pro"
    else:
        tone = "premium"
    return (f"Plano {plan_name}" if plan_name else "Premium", tone, plan_name)


def require_company_feature(feature_code: str, *, template_name: str = "accounts/feature_locked.html"):
    """
    Decorator to guard view access by company subscription feature.
    Keeps role permission checks separate; role mismatch also denies here.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            access = get_user_feature_access(request.user, feature_code=feature_code)
            if access.allowed:
                request.feature_access = access
                return view_func(request, *args, **kwargs)

            feature = Feature.objects.filter(code=feature_code, is_active=True).first()
            required_plan = get_feature_minimum_plan(feature_code)
            required_plan_code = (required_plan.code if required_plan else "").strip()
            required_plan_name = (required_plan.name if required_plan else "").strip()
            required_plan_label, required_plan_tone, _required_plan_name = get_feature_required_plan_badge(feature_code)

            try:
                upgrade_url = reverse("company_plan")
            except Exception:
                upgrade_url = reverse("dashboard")

            return render(
                request,
                template_name,
                {
                    "feature_code": feature_code,
                    "feature_name": feature.name if feature else feature_code,
                    "feature_access": access,
                    "feature_blocked": True,
                    "feature_reason_label": humanize_feature_reason(access.reason),
                    "feature_required_plan_code": required_plan_code,
                    "feature_required_plan_name": required_plan_name,
                    "feature_required_plan_label": required_plan_label,
                    "feature_required_plan_tone": required_plan_tone,
                    "feature_upgrade_url": upgrade_url,
                },
                status=403,
            )

        return wrapped

    return decorator
