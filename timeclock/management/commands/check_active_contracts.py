from collections import defaultdict

from django.core.management.base import BaseCommand

from timeclock.models import Contract


class Command(BaseCommand):
    help = "Lista contratos ativos por empresa e destaca duplicidade de MEI ativo na mesma empresa."

    def handle(self, *args, **options):
        active_contracts = list(
            Contract.objects.filter(is_active=True)
            .select_related("company", "employee", "employee__user")
            .order_by("company__name", "employee__user__email", "-created_at")
        )

        if not active_contracts:
            self.stdout.write(self.style.WARNING("Nenhum contrato ativo encontrado."))
            return

        company_totals = defaultdict(int)
        company_meis = defaultdict(set)
        duplicates = defaultdict(list)

        for contract in active_contracts:
            company_totals[contract.company_id] += 1
            company_meis[contract.company_id].add(contract.employee_id)

            key = (contract.company_id, contract.employee_id)
            duplicates[key].append(contract.id)

            mei_name = contract.employee.full_name or contract.employee.user.email or contract.employee.user.username
            self.stdout.write(
                f"[{contract.company.name} | {str(contract.company_id)[:8]}] {mei_name} | contrato={contract.id} | ativo={contract.is_active}"
            )

        self.stdout.write("")
        self.stdout.write("Resumo por empresa:")
        for company_id, total_contracts in company_totals.items():
            sample_contract = next(c for c in active_contracts if c.company_id == company_id)
            self.stdout.write(
                f"- {sample_contract.company.name} ({str(company_id)[:8]}): contratos_ativos={total_contracts} | meis_ativos={len(company_meis[company_id])}"
            )

        duplicate_found = False
        for (company_id, employee_id), contract_ids in duplicates.items():
            if len(contract_ids) > 1:
                duplicate_found = True
                company_name = next(c.company.name for c in active_contracts if c.company_id == company_id)
                user_email = next(
                    c.employee.user.email
                    for c in active_contracts
                    if c.company_id == company_id and c.employee_id == employee_id
                )
                self.stdout.write(
                    self.style.ERROR(
                        f"DUPLICIDADE: empresa={company_name} mei={user_email} contratos_ativos={', '.join(str(cid) for cid in contract_ids)}"
                    )
                )

        if not duplicate_found:
            self.stdout.write(self.style.SUCCESS("OK: sem duplicidade de contrato ativo por MEI+empresa."))
