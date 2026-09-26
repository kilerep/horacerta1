"""Instrumentacao minima de produto (funil de ativacao e retencao).

Uso nas views, no ponto em que a acao de negocio termina:

    track(user, "client_created")

Nunca quebra o fluxo do usuario: qualquer falha ao gravar o evento e ignorada
(so registrada em log). Propriedades fora da allowlist sao descartadas para
impedir que PII entre por engano.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

# Eventos que o produto emite. Manter curto e estavel.
SIGNUP_COMPLETED = "signup_completed"
CLIENT_CREATED = "client_created"
PUNCH_RECORDED = "punch_recorded"
REPORT_GENERATED = "report_generated"
REPORT_SHARE_CLICKED = "report_share_clicked"
REPORT_PUBLIC_VIEWED = "report_public_viewed"

ALLOWED_PROPERTIES = {"channel", "is_first", "kind"}


def track(user, event, **properties):
    """Registra um evento de produto para ``user`` (apos o commit da transacao)."""
    if user is None or not getattr(user, "pk", None):
        return
    clean = {key: value for key, value in properties.items() if key in ALLOWED_PROPERTIES}

    def _write():
        from .models import ProductEvent

        try:
            ProductEvent.objects.create(user_id=user.pk, event=event, properties=clean)
        except Exception:  # noqa: BLE001 - analytics jamais derruba a requisicao
            logger.exception("Falha ao gravar ProductEvent %s", event)

    transaction.on_commit(_write)
