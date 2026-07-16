from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services"

    def ready(self):
        from . import signals  # noqa: F401
        from .professional_language import apply_professional_form_copy

        apply_professional_form_copy()
