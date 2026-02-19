import socket
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to validate SMTP/console configuration."

    def add_arguments(self, parser):
        parser.add_argument("to_email", help="Destination email address.")
        parser.add_argument(
            "--subject",
            default="HoraCerta - Teste de envio",
            help="Email subject.",
        )
        parser.add_argument(
            "--message",
            default="Este e um e-mail de teste do HoraCerta.",
            help="Email body.",
        )
        parser.add_argument(
            "--from-email",
            dest="from_email",
            default=settings.DEFAULT_FROM_EMAIL,
            help="Override sender email.",
        )

    def handle(self, *args, **options):
        to_email = options["to_email"]
        subject = options["subject"]
        message = options["message"]
        from_email = options["from_email"]

        self.stdout.write("Email backend: %s" % settings.EMAIL_BACKEND)
        self.stdout.write(
            "SMTP host=%s port=%s tls=%s ssl=%s user=%s"
            % (
                settings.EMAIL_HOST,
                settings.EMAIL_PORT,
                settings.EMAIL_USE_TLS,
                settings.EMAIL_USE_SSL,
                settings.EMAIL_HOST_USER or "(vazio)",
            )
        )

        try:
            delivered = send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
            )
        except SMTPException as exc:
            raise CommandError(f"SMTPException: {exc}") from exc
        except (socket.gaierror, TimeoutError, OSError) as exc:
            raise CommandError(f"Erro de conexao SMTP: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive for unknown backend errors
            raise CommandError(f"Falha inesperada no envio: {exc}") from exc

        if delivered != 1:
            raise CommandError(
                "send_mail concluiu sem excecao, mas o backend reportou %s envio(s)." % delivered
            )

        self.stdout.write(
            self.style.SUCCESS(f"Email de teste enviado com sucesso para {to_email}.")
        )
