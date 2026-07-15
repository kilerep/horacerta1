from __future__ import annotations

from django.contrib.staticfiles import finders
from django.core import checks
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor


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
        "Valida configuracao Django, banco, migrations pendentes e arquivos estaticos "
        "criticos antes de publicar ou reiniciar o HoraCerta."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Alias do banco configurado no Django. Padrao: default.",
        )

    def handle(self, *args, **options):
        database_alias = options["database"]
        failures: list[str] = []

        self.stdout.write("HoraCerta - verificacao de prontidao da release")
        self.stdout.write("=" * 52)

        check_messages = checks.run_checks()
        check_errors = [message for message in check_messages if message.level >= checks.ERROR]
        if check_errors:
            failures.append(
                "Configuracao Django: "
                + "; ".join(f"{message.id or 'erro'}: {message.msg}" for message in check_errors)
            )
            self.stdout.write(self.style.ERROR("[FALHA] Configuracao Django"))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Configuracao Django"))

        connection = connections[database_alias]
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:  # pragma: no cover - depende do ambiente externo
            failures.append(f"Banco de dados ({database_alias}): {exc.__class__.__name__}")
            self.stdout.write(self.style.ERROR(f"[FALHA] Banco de dados ({database_alias})"))
        else:
            self.stdout.write(self.style.SUCCESS(f"[OK] Banco de dados ({database_alias})"))

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

        missing_assets = [path for path in CRITICAL_ASSETS if not finders.find(path)]
        if missing_assets:
            failures.append("Assets ausentes: " + ", ".join(missing_assets))
            self.stdout.write(self.style.ERROR("[FALHA] Arquivos estaticos criticos"))
            for path in missing_assets:
                self.stdout.write(f"  - {path}")
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Arquivos estaticos criticos"))

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Release nao esta pronta para publicacao."))
            for failure in failures:
                self.stdout.write(f"- {failure}")
            raise CommandError("Corrija as falhas antes de atualizar ou reiniciar o servidor.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Release pronta para a etapa de publicacao."))
