from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.db import transaction
from django.db.models import Count, F, Q

from companies.models import Employee
from timeclock.models import Contract


class Command(BaseCommand):
    help = (
        "Limpa dados invalidos e normaliza consistencia entre Employee e Contract. "
        "Use --apply para aplicar; sem --apply roda em modo simulacao."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica as alteracoes no banco. Sem este parametro, apenas simula.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        mode_label = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"[{mode_label}] Iniciando limpeza de dados..."))

        try:
            invalid_contracts_qs = Contract.objects.filter(Q(employee__isnull=True) | Q(company__isnull=True))
            invalid_employees_qs = Employee.objects.filter(Q(user__isnull=True) | Q(company__isnull=True))
            mismatched_contracts_qs = Contract.objects.exclude(company_id=F("employee__company_id"))
            invalid_contracts_count = invalid_contracts_qs.count()
            invalid_employees_count = invalid_employees_qs.count()
            mismatched_contracts_count = mismatched_contracts_qs.count()
        except (OperationalError, ProgrammingError) as exc:
            self.stdout.write(self.style.ERROR("Falha ao consultar tabelas/colunas esperadas."))
            self.stdout.write("Rode as migracoes antes da limpeza: python manage.py migrate")
            self.stdout.write(f"Detalhe tecnico: {exc}")
            return

        duplicate_pairs = (
            Contract.objects.filter(is_active=True)
            .values("company_id", "employee_id")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
        )
        duplicate_contracts_to_deactivate = []
        for pair in duplicate_pairs:
            contracts = list(
                Contract.objects.filter(
                    is_active=True,
                    company_id=pair["company_id"],
                    employee_id=pair["employee_id"],
                ).order_by("-created_at", "-id")
            )
            duplicate_contracts_to_deactivate.extend(contracts[1:])

        self.stdout.write(
            (
                f"Contratos invalidos (sem employee/company): {invalid_contracts_count}\n"
                f"Employees invalidos (sem user/company): {invalid_employees_count}\n"
                f"Contratos com company divergente do employee.company: {mismatched_contracts_count}\n"
                f"Contratos ativos duplicados (para desativar): {len(duplicate_contracts_to_deactivate)}"
            )
        )

        if not apply_changes:
            self.stdout.write(self.style.SUCCESS("DRY-RUN finalizado. Nada foi alterado."))
            self.stdout.write("Execute com --apply para aplicar as correcoes.")
            return

        with transaction.atomic():
            deleted_invalid_contracts = invalid_contracts_qs.delete()[0]
            deleted_invalid_employees = invalid_employees_qs.delete()[0]

            fixed_company = 0
            for contract in mismatched_contracts_qs.select_related("employee").iterator():
                contract.company_id = contract.employee.company_id
                contract.save(update_fields=["company"])
                fixed_company += 1

            deactivated_duplicates = 0
            for contract in duplicate_contracts_to_deactivate:
                if contract.is_active:
                    contract.is_active = False
                    contract.save(update_fields=["is_active"])
                    deactivated_duplicates += 1

        self.stdout.write(self.style.SUCCESS("Limpeza aplicada com sucesso."))
        self.stdout.write(
            (
                f"Registros removidos (Contract): {deleted_invalid_contracts}\n"
                f"Registros removidos (Employee): {deleted_invalid_employees}\n"
                f"Contratos corrigidos (company): {fixed_company}\n"
                f"Contratos desativados (duplicidade): {deactivated_duplicates}"
            )
        )
