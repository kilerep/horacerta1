from decimal import Decimal

from django import template

from services.service_playbooks import service_playbook_for


register = template.Library()


@register.filter
def brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@register.simple_tag
def service_playbook(slug):
    return service_playbook_for(slug)
