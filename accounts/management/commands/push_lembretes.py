"""Lembretes no celular que dependem do horario (rodar pelo agendador do servidor).

    python manage.py push_lembretes --agenda   # 7h: "Hoje voce tem N servicos"
    python manage.py push_lembretes --saida    # 19h: entrada aberta sem saida registrada

So avisa quem ativou os avisos em Meu perfil. Sem as chaves VAPID nao faz nada.
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from accounts.models import PushSubscription, User
from accounts.push import push_enabled, send_push_to_user


def users_with_push():
    ids = PushSubscription.objects.values_list("user_id", flat=True).distinct()
    return User.objects.filter(id__in=ids, is_active=True)


def open_entries_today(user):
    """Clientes com numero impar de horarios hoje (entrou e ainda nao saiu)."""
    from timeclock.models import Punch

    today = timezone.localdate()
    counts = Counter(
        Punch.objects.filter(contract__employee__user=user, timestamp__date=today)
        .values_list("contract__company__name", flat=True)
    )
    return sorted(name or "cliente" for name, total in counts.items() if total % 2 == 1)


class Command(BaseCommand):
    help = "Envia lembretes no celular: agenda do dia (--agenda) ou saida aberta (--saida)."

    def add_arguments(self, parser):
        parser.add_argument("--agenda", action="store_true")
        parser.add_argument("--saida", action="store_true")

    def handle(self, *args, **options):
        if not push_enabled():
            self.stdout.write("Avisos no celular desligados (sem chaves VAPID).")
            return
        sent = 0
        for user in users_with_push():
            if options["agenda"]:
                from services.agenda import ensure_today_reminder

                # cria o aviso do dia (uma vez) e ele ja segue para o celular
                ensure_today_reminder(user)
            if options["saida"]:
                names = open_entries_today(user)
                if names:
                    sent += send_push_to_user(
                        user,
                        title="Você ainda está trabalhando?",
                        body=f"Sua entrada em {', '.join(names)} está aberta. Registre a saída quando terminar.",
                        url=reverse("employee_dashboard"),
                        tag="hc-saida-aberta",
                    )
        self.stdout.write(f"ok ({sent} avisos de saída)")
