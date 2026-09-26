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


# ---------------------------------------------------------------------------
# Leitura (painel interno do funil). So agregados - nunca dados pessoais.
# ---------------------------------------------------------------------------

FUNNEL_STEPS = (
    (SIGNUP_COMPLETED, "Criaram conta"),
    (CLIENT_CREATED, "Cadastraram um cliente"),
    (PUNCH_RECORDED, "Registraram um horário"),
    (REPORT_GENERATED, "Geraram um relatório"),
    (REPORT_SHARE_CLICKED, "Clicaram em compartilhar"),
    (REPORT_PUBLIC_VIEWED, "Cliente abriu o relatório"),
)

# Acoes de produto que contam como "uso de verdade" (login nao conta).
ACTIVE_EVENTS = (PUNCH_RECORDED, REPORT_GENERATED)


def funnel_summary(*, days=30, now=None):
    """Resumo do funil: usuarios DISTINTOS por etapa, onde travaram e retencao.

    Conta pessoas, nao eventos (15 horarios de uma pessoa valem 1).
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import ProductEvent

    now = now or timezone.now()
    since = now - timedelta(days=days)

    events = ProductEvent.objects.filter(occurred_at__gte=since)
    steps = []
    first_count = None
    for key, label in FUNNEL_STEPS:
        count = events.filter(event=key).values("user_id").distinct().count()
        if first_count is None:
            first_count = count
        steps.append(
            {
                "event": key,
                "label": label,
                "users": count,
                "percent_of_signups": round(100 * count / first_count) if first_count else None,
            }
        )

    # Onde travaram: cadastraram ha mais de 24h e nao passaram da etapa seguinte.
    cutoff = now - timedelta(hours=24)
    signup_users = set(
        ProductEvent.objects.filter(event=SIGNUP_COMPLETED, occurred_at__gte=since, occurred_at__lt=cutoff)
        .values_list("user_id", flat=True)
        .distinct()
    )

    def users_with(event):
        return set(ProductEvent.objects.filter(event=event).values_list("user_id", flat=True).distinct())

    with_client = users_with(CLIENT_CREATED)
    with_punch = users_with(PUNCH_RECORDED)
    with_report = users_with(REPORT_GENERATED)
    with_view = users_with(REPORT_PUBLIC_VIEWED)
    stuck = [
        {"label": "Cadastro → sem cliente", "users": len(signup_users - with_client)},
        {"label": "Cliente → sem horário", "users": len((signup_users & with_client) - with_punch)},
        {"label": "Horário → sem relatório", "users": len((signup_users & with_punch) - with_report)},
        {"label": "Relatório → nunca visualizado", "users": len((signup_users & with_report) - with_view)},
    ]

    # Retencao: quem cadastrou ha 14+ dias e agiu na semana 1 E na semana 2.
    retention_cutoff = now - timedelta(days=14)
    cohort = list(
        ProductEvent.objects.filter(event=SIGNUP_COMPLETED, occurred_at__lt=retention_cutoff).values_list(
            "user_id", "occurred_at"
        )
    )
    active_week1 = returned_week2 = 0
    for user_id, signup_at in cohort:
        week1_end = signup_at + timedelta(days=7)
        week2_end = signup_at + timedelta(days=14)
        actions = ProductEvent.objects.filter(
            user_id=user_id, event__in=ACTIVE_EVENTS, occurred_at__gte=signup_at, occurred_at__lt=week2_end
        ).values_list("occurred_at", flat=True)
        in_week1 = any(at < week1_end for at in actions)
        in_week2 = any(at >= week1_end for at in actions)
        if in_week1:
            active_week1 += 1
            if in_week2:
                returned_week2 += 1

    return {
        "days": days,
        "steps": steps,
        "stuck": stuck,
        "retention": {
            "cohort": len(cohort),
            "active_week1": active_week1,
            "returned_week2": returned_week2,
            "percent": round(100 * returned_week2 / active_week1) if active_week1 else None,
        },
    }
