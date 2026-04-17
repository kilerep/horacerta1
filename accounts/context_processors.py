from companies.models import Company
from companies.feature_flags import get_user_feature_access
from timeclock.models import ActivityReportRequest


def _build_display_name(user):
    # 1) Para funcionario/MEI, prioriza o nome salvo no perfil
    try:
        employee = getattr(user, "employee_profile", None)
        if employee and (employee.full_name or "").strip():
            return employee.full_name.strip()
    except Exception:
        pass

    # 2) Depois tenta nome + sobrenome do proprio user
    full_name = user.get_full_name().strip()
    if full_name:
        return full_name

    # 3) Depois tenta first_name sozinho
    first_name = (user.first_name or "").strip()
    if first_name:
        return first_name

    # 4) Fallback para email/username
    email = (getattr(user, "email", "") or "").strip()
    if "@" in email:
        return email.split("@", 1)[0]

    username = (getattr(user, "username", "") or "").strip()
    if username:
        return username

    return "Usuario"


def header_profile_media(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    logo_url = ""
    photo_url = ""
    header_display_name = _build_display_name(request.user)
    header_company_name = "Empresa"
    header_mode = "mei"
    pending_reports_count = 0
    header_feature_access = {}
    header_current_plan_code = ""
    header_current_plan_name = ""

    try:
        if request.user.role == "EMPRESA":
            header_mode = "company"
            company = request.user.owned_companies.first()
            if not company:
                company = Company.objects.filter(owner=request.user).first()
            if company and company.name:
                header_company_name = company.name
            if company and company.logo:
                logo_url = company.logo.url
            if company:
                pending_reports_count = ActivityReportRequest.objects.filter(
                    company=company,
                    is_answered=False,
                ).count()
            reports_access = get_user_feature_access(request.user, "advanced_reports")
            themes_access = get_user_feature_access(request.user, "custom_themes")
            incident_access = get_user_feature_access(request.user, "incident_center")
            header_feature_access["advanced_reports"] = reports_access.allowed
            header_feature_access["custom_themes"] = themes_access.allowed
            header_feature_access["incident_center"] = incident_access.allowed
            if reports_access.plan_code:
                header_current_plan_code = reports_access.plan_code
                header_current_plan_name = reports_access.plan_name or ""
        else:
            employee = getattr(request.user, "employee_profile", None)
            if employee and employee.profile_photo:
                photo_url = employee.profile_photo.url
            themes_access = get_user_feature_access(request.user, "custom_themes")
            header_feature_access["custom_themes"] = themes_access.allowed
            if themes_access.plan_code:
                header_current_plan_code = themes_access.plan_code
                header_current_plan_name = themes_access.plan_name or ""
    except Exception:
        # Fallback silencioso para nao quebrar layout se arquivo estiver ausente.
        pass

    return {
        "header_company_logo_url": logo_url,
        "header_profile_photo_url": photo_url,
        "header_display_name": header_display_name,
        "header_company_name": header_company_name,
        "header_mode": header_mode,
        "pending_reports_count": pending_reports_count,
        "header_feature_access": header_feature_access,
        "header_can_use_custom_themes": header_feature_access.get("custom_themes", False),
        "header_can_use_advanced_reports": header_feature_access.get("advanced_reports", False),
        "header_can_use_incident_center": header_feature_access.get("incident_center", False),
        "header_current_plan_code": header_current_plan_code,
        "header_current_plan_name": header_current_plan_name,
    }
