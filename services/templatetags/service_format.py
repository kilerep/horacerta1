from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def brl(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
