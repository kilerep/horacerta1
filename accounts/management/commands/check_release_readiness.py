from __future__ import annotations

from django.apps import apps
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core import checks
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState


CRITICAL_ASSETS = (
    "css/design_tokens.css",
    "css/ui_system.css",
    "css/public_landing_new.css",
    "js/theme_engine.js",
    "js/pwa-register.js",
    "pwa/icon-512.png",
    "pwa/apple-touch-icon-180.png",
    "pwa/favicon-32.png",
)


class Command(BaseCommand):
    help = (
        "Valida configuração Django, banco, migrations, arquivos estáticos de origem "
        "e, opcionalmente, os estáticos coletados antes de publicar o HoraCerta."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Alias do banco configurado no Django. Padrão: default.",
        )
        parser.add_argument(
            "--require-collected-static",
            action="store_true",
            help=(
                "Exige que os assets críticos existam em STATIC_ROOT e possam ser "
                "resolvidos pelo storage configurado. Use depois de collectstatic."
            ),
        )

    def handle(self, *args, **options):
        database_alias = options["database"]
        require_collected_static = options["require_collected_static"]
        failures: list[str] = []

        self.stdout.write("HoraCerta - verificação de prontidão da release")
        self.stdout.write("=" * 52)

        check_messages = checks.run_checks(include_deployment_checks=True)
        check_errors = [message for message in check_messages if message.level >= checks.ERROR]
        check_warnings = [
            message
            for message in check_messages
            if checks.WARNING <= message.level < checks.ERROR
        ]
        if check_errors:
            failures.append(
                "Configuração Django: "
                + "; ".join(f"{message.id or 'erro'}: {message.msg}" for message in check_errors)
            )
            self.stdout.write(self.style.ERROR("[FALHA] Configuração Django"))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Configuração Django"))
        if check_warnings:
            self.stdout.write(
                self.style.WARNING(
                    f"[AVISO] {len(check_warnings)} alerta(s) de segurança/deploy; revise com check --deploy."
                )
            )

        try:
            connection = connections[database_alias]
        except Exception as exc:
            failures.append(f"Configuração do banco ({database_alias}): {exc.__class__.__name__}")
            self.stdout.write(self.style.ERROR(f"[FALHA] Configuração do banco ({database_alias})"))
            connection = None

        database_ready = False
        if connection is not None:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except Exception as exc:  # pragma: no cover - depende do ambiente externo
                failures.append(f"Banco de dados ({database_alias}): {exc.__class__.__name__}")
                self.stdout.write(self.style.ERROR(f"[FALHA] Banco de dados ({database_alias})"))
            else:
                database_ready = True
                self.stdout.write(self.style.SUCCESS(f"[OK] Banco de dados ({database_alias})"))

        executor = None
        if database_ready:
            try:
                executor = MigrationExecutor(connection)
                leaf_nodes = executor.loader.graph.leaf_nodes()
                pending_plan = executor.migration_plan(leaf_nodes)
            except Exception as exc:  # pragma: no cover - depende do estado do banco
                failures.append(f"Leitura de migrations: {exc.__class__.__name__}")
                self.stdout.write(self.style.ERROR("[FALHA] Leitura do estado das migrations"))
            else:
                if pending_plan:
                    pending_labels = [migration.label for migration, _backwards in pending_plan]
                    failures.append("Migrations pendentes: " + ", ".join(pending_labels))
                    self.stdout.write(self.style.ERROR("[FALHA] Existem migrations pendentes"))
                    for label in pending_labels:
                        self.stdout.write(f"  - {label}")
                else:
                    self.stdout.write(self.style.SUCCESS("[OK] Nenhuma migration pendente"))

        if executor is not None:
            try:
                migration_changes = MigrationAutodetector(
                    executor.loader.project_state(),
                    ProjectState.from_apps(apps),
                ).changes(graph=executor.loader.graph)
            except Exception as exc:
                failures.append(f"Comparação modelos/migrations: {exc.__class__.__name__}")
                self.stdout.write(self.style.ERROR("[FALHA] Comparação entre modelos e migrations"))
            else:
                if migration_changes:
                    changed_apps = ", ".join(sorted(migration_changes))
                    failures.append(f"Modelos sem migration correspondente: {changed_apps}")
                    self.stdout.write(self.style.ERROR("[FALHA] Existem alterações de modelo sem migration"))
                    self.stdout.write(f"  - apps: {changed_apps}")
                else:
                    self.stdout.write(self.style.SUCCESS("[OK] Modelos e migrations estão consistentes"))

        missing_assets = [path for path in CRITICAL_ASSETS if not finders.find(path)]
        if missing_assets:
            failures.append("Assets de origem ausentes: " + ", ".join(missing_assets))
            self.stdout.write(self.style.ERROR("[FALHA] Arquivos estáticos críticos de origem"))
            for path in missing_assets:
                self.stdout.write(f"  - {path}")
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Arquivos estáticos críticos de origem"))

        if require_collected_static:
            collected_failures = []
            for path in CRITICAL_ASSETS:
                try:
                    if not staticfiles_storage.exists(path):
                        collected_failures.append(f"{path}: ausente em STATIC_ROOT")
                        continue
                    staticfiles_storage.url(path)
                except Exception as exc:
                    collected_failures.append(f"{path}: {exc.__class__.__name__}")

            if collected_failures:
                failures.append("Estáticos coletados inválidos: " + "; ".join(collected_failures))
                self.stdout.write(self.style.ERROR("[FALHA] Arquivos estáticos coletados/manifesto"))
                for failure in collected_failures:
                    self.stdout.write(f"  - {failure}")
            else:
                self.stdout.write(self.style.SUCCESS("[OK] Arquivos estáticos coletados e manifesto"))

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Release não está pronta para publicação."))
            for failure in failures:
                self.stdout.write(f"- {failure}")
            raise CommandError("Corrija as falhas antes de atualizar ou reiniciar o servidor.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Release pronta para a etapa de publicação."))
