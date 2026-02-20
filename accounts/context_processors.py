from companies.models import Company


def _build_display_name(user):
    base_name = (user.first_name or "").strip()
    if not base_name:
        email = (getattr(user, "email", "") or "").strip()
        if "@" in email:
            base_name = email.split("@", 1)[0]
        else:
            base_name = (getattr(user, "username", "") or "usuario").strip()

    first_token = base_name.split()[0] if base_name else "usuario"
    return first_token[:1].upper() + first_token[1:]


def header_profile_media(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    logo_url = ""
    photo_url = ""
    header_display_name = _build_display_name(request.user)
    header_company_name = "Empresa"
    header_mode = "mei"

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
        else:
            employee = getattr(request.user, "employee_profile", None)
            if employee and employee.profile_photo:
                photo_url = employee.profile_photo.url
    except Exception:
        # Fallback silencioso para nao quebrar layout se arquivo estiver ausente.
        pass

    return {
        "header_company_logo_url": logo_url,
        "header_profile_photo_url": photo_url,
        "header_display_name": header_display_name,
        "header_company_name": header_company_name,
        "header_mode": header_mode,
    }
