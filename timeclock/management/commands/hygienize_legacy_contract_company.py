import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from companies.models import Employee
from timeclock.models import Contract


class Command(BaseCommand):
    help = (
        "Higieniza inconsistencias legadas entre Contract.company e Employee.company "
        "com modo seguro (dry-run por padrao)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica mudancas no banco. Sem este parametro, roda apenas simulacao.",
        )
        parser.add_argument(
            "--employee-id",
            action="append",
            dest="employee_ids",
            default=[],
            help="Filtra a execucao para um Employee especifico (UUID). Pode repetir o parametro.",
        )
        parser.add_argument(
            "--audit-file",
            type=str,
            default="",
            help="Caminho opcional para salvar o plano/resultado em JSON.",
        )
        parser.add_argument(
            "--show-samples",
            type=int,
            default=20,
            help="Quantidade maxima de registros para listar no console (padrao: 20).",
        )

    def _collect_plan(self, target_employee_ids):
        mismatch_qs = (
            Contract.objects.filter(
                employee__isnull=False,
                employee__user__isnull=False,
            )
            .exclude(company_id=F("employee__company_id"))
            .select_related("company", "employee", "employee__company", "employee__user")
            .order_by("employee_id", "-is_active", "-start_date", "-created_at")
        )
        if target_employee_ids:
            mismatch_qs = mismatch_qs.filter(employee_id__in=target_employee_ids)

        mismatch_contracts = list(mismatch_qs)
        if not mismatch_contracts:
            return {
                "mismatch_contracts": [],
                "fixable_employees": [],
                "blocked_employees": [],
            }

        mismatch_by_employee = {}
        for contract in mismatch_contracts:
            mismatch_by_employee.setdefault(contract.employee_id, []).append(contract)

        employees = (
            Employee.objects.filter(id__in=mismatch_by_employee.keys())
            .select_related("user", "company")
            .order_by("created_at", "id")
        )

        fixable = []
        blocked = []

        for employee in employees:
            contracts_qs = employee.contracts.all().order_by("-is_active", "-start_date", "-created_at")
            all_company_ids = set(contracts_qs.values_list("company_id", flat=True))
            active_company_ids = set(contracts_qs.filter(is_active=True).values_list("company_id", flat=True))
            employee_mismatch_contracts = mismatch_by_employee.get(employee.id, [])

            entry = {
                "employee_id": str(employee.id),
                "user_email": employee.user.email or employee.user.username,
                "employee_company_id": str(employee.company_id),
                "contract_companies_all": [str(company_id) for company_id in sorted(all_company_ids)],
                "contract_companies_active": [str(company_id) for company_id in sorted(active_company_ids)],
                "mismatch_contract_ids": [str(contract.id) for contract in employee_mismatch_contracts],
                "mismatch_count": len(employee_mismatch_contracts),
            }

            if len(all_company_ids) == 1:
                canonical_company_id = next(iter(all_company_ids))
                entry["canonical_company_id"] = str(canonical_company_id)
                entry["needs_employee_update"] = canonical_company_id != employee.company_id
                fixable.append(entry)
            else:
                entry["canonical_company_id"] = None
                entry["needs_employee_update"] = False
                entry["block_reason"] = (
                    "employee_com_multiplas_empresas_nos_contratos; "
                    "nao ha correcao automatica segura no modelo atual"
                )
                blocked.append(entry)

        return {
            "mismatch_contracts": mismatch_contracts,
            "fixable_employees": fixable,
            "blocked_employees": blocked,
        }

    def _write_audit_file(self, audit_path, payload):
        if not audit_path:
            return
        path = Path(audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Arquivo de auditoria salvo em: {path}"))

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        target_employee_ids = [value.strip() for value in (options.get("employee_ids") or []) if value.strip()]
        show_samples = max(1, int(options.get("show_samples") or 20))
        audit_file = (options.get("audit_file") or "").strip()

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"[{mode}] Iniciando higienizacao de inconsistencias legadas..."))

        plan = self._collect_plan(target_employee_ids)
        mismatch_contracts = plan["mismatch_contracts"]
        fixable_employees = plan["fixable_employees"]
        blocked_employees = plan["blocked_employees"]

        fixable_with_update = [item for item in fixable_employees if item["needs_employee_update"]]
        fixable_without_update = [item for item in fixable_employees if not item["needs_employee_update"]]

        self.stdout.write(
            "\n".join(
                [
                    f"Contratos inconsistentes encontrados: {len(mismatch_contracts)}",
                    f"Employees com correcao segura (update em Employee.company): {len(fixable_with_update)}",
                    f"Employees ja consistentes (sem update necessario): {len(fixable_without_update)}",
                    f"Employees bloqueados por ambiguidade (multiplas empresas): {len(blocked_employees)}",
                ]
            )
        )

        if fixable_with_update:
            self.stdout.write("\nAmostra de correcoes seguras:")
            for row in fixable_with_update[:show_samples]:
                self.stdout.write(
                    (
                        f"- employee={row['employee_id']} user={row['user_email']} "
                        f"company_atual={row['employee_company_id']} "
                        f"company_correta={row['canonical_company_id']} "
                        f"contratos_inconsistentes={row['mismatch_count']}"
                    )
                )

        if blocked_employees:
            self.stdout.write("\nAmostra de bloqueios (nao aplicados automaticamente):")
            for row in blocked_employees[:show_samples]:
                companies = ", ".join(row["contract_companies_all"]) or "-"
                self.stdout.write(
                    (
                        f"- employee={row['employee_id']} user={row['user_email']} "
                        f"companies_nos_contratos=[{companies}] "
                        f"mismatch_contracts={row['mismatch_contract_ids']}"
                    )
                )

        applied_updates = []

        if apply_changes and fixable_with_update:
            with transaction.atomic():
                for row in fixable_with_update:
                    employee = Employee.objects.select_for_update().get(id=row["employee_id"])
                    old_company_id = str(employee.company_id)
                    new_company_id = row["canonical_company_id"]
                    if old_company_id == new_company_id:
                        continue
                    employee.company_id = new_company_id
                    employee.save(update_fields=["company"])
                    applied_updates.append(
                        {
                            "employee_id": row["employee_id"],
                            "user_email": row["user_email"],
                            "old_company_id": old_company_id,
                            "new_company_id": new_company_id,
                            "reason": "single_company_across_contracts",
                        }
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Aplicacao concluida com sucesso. Employees atualizados: {len(applied_updates)}"
                )
            )
        elif apply_changes:
            self.stdout.write(self.style.WARNING("Nenhuma correcao segura disponivel para aplicar."))
        else:
            self.stdout.write(self.style.WARNING("Dry-run finalizado. Nenhuma alteracao aplicada."))

        audit_payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "mode": mode,
            "summary": {
                "mismatch_contracts_total": len(mismatch_contracts),
                "fixable_employees_with_update": len(fixable_with_update),
                "fixable_employees_without_update": len(fixable_without_update),
                "blocked_employees": len(blocked_employees),
                "applied_updates": len(applied_updates),
            },
            "fixable_employees": fixable_employees,
            "blocked_employees": blocked_employees,
            "applied_updates": applied_updates,
        }
        self._write_audit_file(audit_file, audit_payload)

