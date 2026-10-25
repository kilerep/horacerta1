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


@register.inclusion_tag("services/_services_nav.html", takes_context=True)
def services_nav(context, active):
    """Navegacao fixa da aba Servicos: Pedidos | Servicos | Mais (catalogo, propostas).

    Mostra no item "Pedidos" quantos pedidos ainda precisam de acao do prestador.
    """
    from services.models import ServiceRequest

    request = context.get("request")
    user = getattr(request, "user", None)
    open_requests = 0
    if user is not None and user.is_authenticated:
        open_requests = ServiceRequest.objects.filter(
            professional=user,
            status__in=[
                ServiceRequest.Status.NEW,
                ServiceRequest.Status.WAITING_INFO,
                ServiceRequest.Status.IN_REVIEW,
            ],
        ).count()
    return {"active": active, "open_requests": open_requests}
