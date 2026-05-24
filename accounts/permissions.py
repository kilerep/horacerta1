def can_access_internal_dashboard(user):
    return bool(user and user.is_authenticated and user.is_superuser)
