from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from companies.models import Company, Employee
from timeclock.models import Contract


User = get_user_model()


class Command(BaseCommand):
    help = "Cria dados MVP para MEI: Empresa Teste + contrato ativo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mei-email",
            required=True,
            help="Email do usuario MEI (role FUNCIONARIO).",
        )
        parser.add_argument(
            "--hourly-rate",
            default="30",
            help="Valor da hora do contrato (padrao: 30).",
        )

    def handle(self, *args, **options):
        mei_email = (options["mei_email"] or "").strip().lower()
        hourly_rate_raw = options["hourly_rate"]

        if not mei_email:
            raise CommandError("Informe --mei-email.")

        try:
            hourly_rate = Decimal(str(hourly_rate_raw))
        except Exception as exc:
            raise CommandError("--hourly-rate invalido.") from exc

        mei_user = User.objects.filter(email__iexact=mei_email).first()
        if not mei_user:
            raise CommandError(f"Usuario MEI nao encontrado: {mei_email}")

        if mei_user.role != User.Role.FUNCIONARIO:
            raise CommandError(f"Usuario informado nao e MEI/FUNCIONARIO: {mei_email}")

        owner_email = "empresa.teste@horacerta.local"
        owner_user, owner_created = User.objects.get_or_create(
            email=owner_email,
            defaults={
                "username": owner_email,
                "role": User.Role.EMPRESA,
            },
        )
        if owner_created:
            owner_user.set_unusable_password()
            owner_user.save(update_fields=["password"])

        company, company_created = Company.objects.get_or_create(
            owner=owner_user,
            name="Empresa Teste",
            defaults={"email": "contato@empresateste.local"},
        )

        employee, employee_created = Employee.objects.get_or_create(
            user=mei_user,
            defaults={
                "company": company,
                "full_name": mei_user.get_full_name() or mei_user.username,
                "is_active": True,
            },
        )
        if employee.company_id != company.id:
            employee.company = company
            employee.save(update_fields=["company"])

        contract, contract_created = Contract.objects.get_or_create(
            employee=employee,
            company=company,
            defaults={
                "hourly_rate": hourly_rate,
                "is_active": True,
            },
        )

        fields_to_update = []
        if contract.hourly_rate != hourly_rate:
            contract.hourly_rate = hourly_rate
            fields_to_update.append("hourly_rate")
        if not contract.is_active:
            contract.is_active = True
            fields_to_update.append("is_active")
        if fields_to_update:
            contract.save(update_fields=fields_to_update)

        self.stdout.write(self.style.SUCCESS("Seed MVP concluido."))
        self.stdout.write(f"MEI: {mei_user.email}")
        self.stdout.write(f"Empresa: {company.name} ({'criada' if company_created else 'reutilizada'})")
        self.stdout.write(f"Perfil Employee: {'criado' if employee_created else 'reutilizado'}")
        self.stdout.write(f"Contrato: {contract.id} ({'criado' if contract_created else 'reutilizado'})")
        self.stdout.write(f"Hourly rate: {contract.hourly_rate}")
