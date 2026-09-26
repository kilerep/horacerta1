from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract


class Command(BaseCommand):
    help = "Cria um prestador e um cliente de demonstração apenas no ambiente local."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo.prestador@horacerta.test")
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Este comando só funciona com DEBUG=True e nunca deve criar dados em produção.")

        email = (options["email"] or "").strip().lower()
        password = options["password"]
        if not email.endswith(".test"):
            raise CommandError("Use um e-mail local no domínio .test.")
        if len(password or "") < 8:
            raise CommandError("A senha temporária precisa ter pelo menos 8 caracteres.")

        with transaction.atomic():
            professional, _ = User.objects.get_or_create(
                email=email,
                defaults={"username": email, "role": User.Role.FUNCIONARIO, "is_active": True},
            )
            professional.username = email
            professional.role = User.Role.FUNCIONARIO
            professional.first_name = "Demo"
            professional.last_name = "Prestador"
            professional.is_active = True
            professional.set_password(password)
            professional.save()

            owner_email = "demo.cliente@horacerta.test"
            owner, _ = User.objects.get_or_create(
                email=owner_email,
                defaults={"username": owner_email, "role": User.Role.EMPRESA, "is_active": True},
            )
            owner.username = owner_email
            owner.role = User.Role.EMPRESA
            owner.is_active = True
            owner.set_password(password)
            owner.save()

            company, _ = Company.objects.get_or_create(
                owner=owner,
                name="Cliente Demonstração HoraCerta",
                defaults={"email": owner_email, "internal_note": "Dado local de demonstração."},
            )
            employee, _ = Employee.objects.get_or_create(
                user=professional,
                company=company,
                defaults={"full_name": "Demo Prestador", "is_active": True},
            )
            Contract.objects.get_or_create(
                employee=employee,
                company=company,
                defaults={"hourly_rate": "85.00", "is_active": True},
            )

        self.stdout.write(self.style.SUCCESS("Usuário local de demonstração pronto."))
        self.stdout.write(f"Prestador: {professional.email}")
        self.stdout.write(f"Empresa: {owner.email}")
