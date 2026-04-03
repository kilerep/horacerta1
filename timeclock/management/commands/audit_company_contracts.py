from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from timeclock.models import Contract


class Command(BaseCommand):
    help = (
        "Audita contratos da empresa e identifica registros invalidos "
        "(sem employee, sem employee.user ou company divergente)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica alteracoes no banco. Sem este parametro, apenas lista.",
        )
        parser.add_argument(
            "--delete-invalid",
            action="store_true",
            help="Ao usar --apply, remove contratos sem employee ou sem employee.user.",
        )
        parser.add_argument(
            "--fix-company-mismatch",
            action="store_true",
            help="Ao usar --apply, corrige company do contrato para employee.company quando divergente.",
        )

    def _ids(self, queryset):
        return list(queryset.values_list("id", flat=True))

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        delete_invalid = bool(options.get("delete_invalid"))
        fix_company_mismatch = bool(options.get("fix_company_mismatch"))

        missing_employee_qs = Contract.objects.filter(employee__isnull=True).order_by("created_at")
        missing_employee_user_qs = Contract.objects.filter(
            employee__isnull=False,
            employee__user__isnull=True,
        ).order_by("created_at")
        mismatch_company_qs = Contract.objects.filter(
            employee__isnull=False,
            employee__user__isnull=False,
        ).exclude(company_id=F("employee__company_id")).order_by("created_at")

        missing_employee_ids = self._ids(missing_employee_qs)
        missing_employee_user_ids = self._ids(missing_employee_user_qs)
        mismatch_company_ids = self._ids(mismatch_company_qs)

        self.stdout.write("Auditoria de contratos:")
        self.stdout.write(f"- sem employee: {len(missing_employee_ids)}")
        self.stdout.write(f"- sem employee.user: {len(missing_employee_user_ids)}")
        self.stdout.write(f"- company divergente de employee.company: {len(mismatch_company_ids)}")

        if missing_employee_ids:
            self.stdout.write(f"  ids sem employee: {missing_employee_ids}")
        if missing_employee_user_ids:
            self.stdout.write(f"  ids sem employee.user: {missing_employee_user_ids}")
        if mismatch_company_ids:
            self.stdout.write(f"  ids com company divergente: {mismatch_company_ids}")

        if not apply_changes:
            self.stdout.write(self.style.WARNING("DRY-RUN: nada foi alterado."))
            self.stdout.write(
                "Para aplicar, rode com --apply e escolha --delete-invalid e/ou --fix-company-mismatch."
            )
            return

        if not delete_invalid and not fix_company_mismatch:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhuma acao selecionada. Use --delete-invalid e/ou --fix-company-mismatch junto com --apply."
                )
            )
            return

        with transaction.atomic():
            deleted_invalid_count = 0
            fixed_mismatch_count = 0

            if delete_invalid:
                invalid_ids = missing_employee_ids + missing_employee_user_ids
                if invalid_ids:
                    deleted_invalid_count, _ = Contract.objects.filter(id__in=invalid_ids).delete()

            if fix_company_mismatch:
                for contract in mismatch_company_qs.select_related("employee").iterator():
                    contract.company_id = contract.employee.company_id
                    contract.save(update_fields=["company"])
                    fixed_mismatch_count += 1

        self.stdout.write(self.style.SUCCESS("Aplicacao concluida."))
        self.stdout.write(f"- contratos removidos: {deleted_invalid_count}")
        self.stdout.write(f"- contratos corrigidos (company): {fixed_mismatch_count}")
