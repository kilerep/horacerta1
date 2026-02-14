def header_profile_media(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    logo_url = ""
    photo_url = ""

    try:
        if request.user.role == "EMPRESA":
            company = request.user.owned_companies.first()
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
    }
