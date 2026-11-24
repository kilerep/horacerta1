from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Lista os administradores (superusuarios) e onde eles entram. Nao mostra senhas."

    def handle(self, *args, **options):
        admins = User.objects.filter(is_superuser=True).order_by("date_joined")
        if not admins:
            self.stdout.write(
                "Nenhum administrador encontrado. Crie um com: manage.py createsuperuser"
            )
        for user in admins:
            last = user.last_login.strftime("%d/%m/%Y %H:%M") if user.last_login else "nunca entrou"
            status = "ativo" if user.is_active else "INATIVO"
            self.stdout.write(f"- usuario: {user.username} | e-mail: {user.email} | {status} | ultimo acesso: {last}")

        base = (settings.APP_BASE_URL or "https://SEU-DOMINIO").rstrip("/")
        self.stdout.write("")
        self.stdout.write(f"Entrar (mesmo login do sistema): {base}/login/")
        self.stdout.write(f"Painel interno: {base}/interno/")
        self.stdout.write(f"Diagnostico de e-mail: {base}/interno/email/")
        self.stdout.write(f"Funil: {base}/interno/funil/")
        self.stdout.write(f"Admin do Django: {base}/{__import__('os').getenv('ADMIN_URL_PATH', 'admin').strip('/')}/")
        self.stdout.write("")
        self.stdout.write("Para definir uma senha nova (voce digita, nada aparece na tela):")
        self.stdout.write("  sudo -u ubuntu venv/bin/python manage.py changepassword USUARIO")
