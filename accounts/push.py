"""Avisos no celular (notificacao push / Web Push).

Cada aviso importante do sininho pode tambem ir para o celular de quem ativou os avisos
em Meu perfil. Sem as chaves VAPID no .env o recurso fica desligado e nada e enviado.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def push_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def _webpush(**kwargs):
    from pywebpush import webpush

    return webpush(**kwargs)


def send_push_to_user(user, *, title, body="", url="/", tag="horacerta"):
    """Envia para todos os aparelhos do usuario. Devolve quantos receberam."""
    from accounts.models import PushSubscription

    if not push_enabled() or user is None:
        return 0
    payload = json.dumps({"title": title[:120], "body": body[:240], "tag": tag, "data": {"url": url or "/"}})
    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            _webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=6 * 3600,
                timeout=5,
            )
        except Exception as exc:  # aparelho saiu, desinstalou ou negou: remove; outros erros so registram
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                sub.delete()
            else:
                logger.warning("Falha ao enviar aviso push (%s): %s", status, exc)
            continue
        sent += 1
        PushSubscription.objects.filter(pk=sub.pk).update(last_success_at=timezone.now())
    return sent


def send_push_after_commit(user, **kwargs):
    """Envia so depois que o banco gravou (se a gravacao falhar, o celular nao recebe aviso falso)."""
    if not push_enabled() or user is None:
        return
    transaction.on_commit(lambda: send_push_to_user(user, **kwargs))
