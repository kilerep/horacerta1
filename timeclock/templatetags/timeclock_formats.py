from datetime import datetime, time as time_obj

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def hhmm(value):
    if value in (None, ""):
        return ""

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%H:%M")

    if isinstance(value, time_obj):
        return value.strftime("%H:%M")

    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 5 and text[2] == ":":
            return text[:5]
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(text, fmt).strftime("%H:%M")
            except ValueError:
                continue
        return text

    return str(value)
