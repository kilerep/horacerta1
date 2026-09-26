from django.core.management.base import BaseCommand

from accounts.health import FAIL, OK, run_checks


class Command(BaseCommand):
    help = "Verifica a configuracao de producao (e-mail, URL publica, DEBUG, migracoes...). Sai com codigo 1 se houver falha."

    def handle(self, *args, **options):
        result = run_checks()
        icons = {OK: "[ok]  ", FAIL: "[FALHA]"}
        for check in result["checks"]:
            icon = icons.get(check["status"], "[aviso]")
            line = f"{icon} {check['label']}"
            if check["detail"]:
                line += f" - {check['detail']}"
            self.stdout.write(line)
        summary = result["summary"]
        self.stdout.write("")
        self.stdout.write(f"{summary['ok']} ok, {summary['warn']} aviso(s), {summary['fail']} falha(s)")
        if not result["healthy"]:
            raise SystemExit(1)
