from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test email and print OK or the full error."

    def add_arguments(self, parser):
        parser.add_argument("to_email", help="Destination email address.")

    def handle(self, *args, **options):
        to_email = options["to_email"]

        try:
            send_mail(
                subject="HoraCerta - Teste de envio",
                message="Este e um e-mail de teste do HoraCerta.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,
            )
            self.stdout.write("OK")
        except Exception:
            import traceback

            self.stderr.write(traceback.format_exc())
