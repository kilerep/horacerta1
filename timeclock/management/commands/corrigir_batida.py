from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from timeclock.models import Punch
from timeclock.services import cancel_punch, change_punch_time, restore_punch


class Command(BaseCommand):
    help = "Corrige, cancela ou restaura uma batida de ponto com auditoria."

    def add_arguments(self, parser):
        parser.add_argument("--punch-id", required=True, help="ID da batida.")
        parser.add_argument("--novo-horario", help='Novo horario no formato "YYYY-MM-DD HH:MM".')
        parser.add_argument("--cancelar", action="store_true", help="Cancela a batida.")
        parser.add_argument("--restaurar", action="store_true", help="Restaura uma batida cancelada.")
        parser.add_argument("--motivo", required=True, help="Motivo obrigatorio para auditoria.")
        parser.add_argument("--admin-email", help="E-mail do admin responsavel. Usa o primeiro superuser se omitido.")
        parser.add_argument("--yes", action="store_true", help="Confirma a operacao sem prompt interativo.")

    def handle(self, *args, **options):
        actions = [bool(options["novo_horario"]), options["cancelar"], options["restaurar"]]
        if sum(actions) != 1:
            raise CommandError("Informe exatamente uma acao: --novo-horario, --cancelar ou --restaurar.")

        motivo = (options["motivo"] or "").strip()
        if not motivo:
            raise CommandError("Informe --motivo para registrar a auditoria.")

        try:
            punch = Punch.all_objects.select_related("contract", "contract__company", "contract__employee").get(id=options["punch_id"])
        except Punch.DoesNotExist as exc:
            raise CommandError("Registro de ponto nao encontrado.") from exc

        admin_user = self._resolve_admin_user(options["admin_email"])
        current_status = "cancelado" if punch.is_cancelled else "ativo"
        self.stdout.write("Dados atuais da batida:")
        self.stdout.write(f"ID: {punch.id}")
        self.stdout.write(f"Empresa: {punch.contract.company.name}")
        self.stdout.write(f"Funcionario: {punch.contract.employee.full_name}")
        self.stdout.write(f"Horario: {timezone.localtime(punch.timestamp):%Y-%m-%d %H:%M}")
        self.stdout.write(f"Status: {current_status}")
        self.stdout.write(f"Admin: {admin_user.email or admin_user.username}")

        if not options["yes"]:
            answer = input("Confirmar alteracao? [s/N] ").strip().lower()
            if answer not in {"s", "sim", "y", "yes"}:
                self.stdout.write(self.style.WARNING("Operacao cancelada."))
                return

        if options["novo_horario"]:
            new_datetime = self._parse_datetime(options["novo_horario"])
            change_punch_time(punch=punch, admin_user=admin_user, new_datetime=new_datetime, reason=motivo)
            punch.refresh_from_db()
            self.stdout.write(self.style.SUCCESS(f"Horario corrigido para {timezone.localtime(punch.timestamp):%Y-%m-%d %H:%M}."))
        elif options["cancelar"]:
            cancel_punch(punch=punch, admin_user=admin_user, reason=motivo)
            punch.refresh_from_db()
            self.stdout.write(self.style.SUCCESS("Batida cancelada com auditoria."))
        elif options["restaurar"]:
            restore_punch(punch=punch, admin_user=admin_user, reason=motivo)
            punch.refresh_from_db()
            self.stdout.write(self.style.SUCCESS("Batida restaurada com auditoria."))

        final_status = "cancelado" if punch.is_cancelled else "ativo"
        self.stdout.write(f"Resultado final: {timezone.localtime(punch.timestamp):%Y-%m-%d %H:%M} | {final_status}")

    def _resolve_admin_user(self, admin_email):
        User = get_user_model()
        if admin_email:
            user = User.objects.filter(email=admin_email).first()
            if not user:
                raise CommandError("Admin informado nao encontrado.")
            if not (user.is_staff or user.is_superuser):
                raise CommandError("Admin informado precisa ser staff ou superuser.")
            return user

        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            user = User.objects.filter(is_staff=True).order_by("id").first()
        if not user:
            raise CommandError("Nenhum usuario staff/superuser encontrado. Informe --admin-email.")
        return user

    def _parse_datetime(self, raw_value):
        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise CommandError('Use --novo-horario no formato "YYYY-MM-DD HH:MM".') from exc
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
