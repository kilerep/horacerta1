from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from services.models import (
    ServiceCategory,
    ServiceItemCatalog,
    ServiceItemExpense,
    ServiceItemUnit,
    ServiceJob,
    ServiceRequest,
    ServiceRequestItem,
    ServiceWorkLog,
)
from timeclock.models import Contract, Punch


class Command(BaseCommand):
    help = "Prepara cenários completos de demonstração local para validar horas, pedidos e serviços."

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

        call_command(
            "create_local_demo_user",
            "--email",
            email,
            "--password",
            password,
            stdout=self.stdout,
        )

        professional = User.objects.get(email=email)
        contract = (
            Contract.objects.filter(employee__user=professional, is_active=True)
            .select_related("company")
            .order_by("-created_at")
            .first()
        )
        if not contract:
            raise CommandError("Não foi possível resolver o contrato local de demonstração.")

        today = timezone.localdate()
        with transaction.atomic():
            category, _ = ServiceCategory.objects.get_or_create(
                slug="demo-local",
                defaults={
                    "name": "Demonstração local",
                    "description": "Categoria criada para validar o ambiente local do HoraCerta.",
                    "sort_order": 999,
                    "is_active": True,
                },
            )
            category.name = "Demonstração local"
            category.description = "Categoria criada para validar o ambiente local do HoraCerta."
            category.is_active = True
            category.save()

            catalog_item, _ = ServiceItemCatalog.objects.get_or_create(
                professional=professional,
                internal_code="DEMO-MAT-001",
                defaults={
                    "category": category,
                    "item_type": ServiceItemExpense.ItemType.MATERIAL,
                    "name": "Material de demonstração",
                    "description": "Item criado para testar busca por código interno.",
                    "unit": ServiceItemUnit.UNIT,
                    "estimated_unit_value": Decimal("18.50"),
                    "default_quantity": Decimal("2.00"),
                    "favorite": True,
                    "is_active": True,
                },
            )
            catalog_item.category = category
            catalog_item.item_type = ServiceItemExpense.ItemType.MATERIAL
            catalog_item.name = "Material de demonstração"
            catalog_item.description = "Item criado para testar busca por código interno."
            catalog_item.unit = ServiceItemUnit.UNIT
            catalog_item.estimated_unit_value = Decimal("18.50")
            catalog_item.default_quantity = Decimal("2.00")
            catalog_item.favorite = True
            catalog_item.is_active = True
            catalog_item.save()

            service_request, _ = ServiceRequest.objects.get_or_create(
                professional=professional,
                title="Pedido demo - troca de tomada",
                defaults={
                    "client": contract.company,
                    "contract": contract,
                    "client_name": contract.company.name,
                    "client_whatsapp": contract.company.whatsapp or contract.company.phone or "47999990000",
                    "client_email": contract.company.email,
                    "category": category,
                    "description": "Pedido local para testar itens rápidos e conversão em serviço.",
                    "status": ServiceRequest.Status.NEW,
                },
            )
            ServiceRequestItem.objects.get_or_create(
                service_request=service_request,
                name="Material de demonstração",
                defaults={
                    "quantity": Decimal("2.00"),
                    "note": "Item rápido do ambiente local.",
                    "estimated_unit_value": Decimal("18.50"),
                },
            )

            job, _ = ServiceJob.objects.get_or_create(
                professional=professional,
                title="Serviço demo - instalação",
                defaults={
                    "contract": contract,
                    "category": category,
                    "description": "Serviço local para validar execução, itens e relatório.",
                    "service_street": "Rua de Demonstração",
                    "service_number": "100",
                    "service_city": "Blumenau",
                    "service_state": "SC",
                    "start_date": today,
                    "planned_start_time": time(9, 0),
                    "planned_end_time": time(12, 0),
                    "status": ServiceJob.Status.IN_PROGRESS,
                    "billing_mode": ServiceJob.BillingMode.HOURLY,
                    "hourly_rate_snapshot": contract.hourly_rate,
                    "notes": "Dados exclusivamente locais de demonstração.",
                },
            )
            ServiceWorkLog.objects.get_or_create(
                service_job=job,
                work_date=today,
                start_time=time(9, 0),
                defaults={
                    "end_time": time(10, 30),
                    "description": "Período concluído para validação local.",
                },
            )
            ServiceItemExpense.objects.get_or_create(
                service_job=job,
                name="Material de demonstração",
                defaults={
                    "catalog_item": catalog_item,
                    "type": ServiceItemExpense.ItemType.MATERIAL,
                    "description": "Item previsto para validação local.",
                    "unit": ServiceItemUnit.UNIT,
                    "quantity": Decimal("2.00"),
                    "unit_value": Decimal("18.50"),
                    "usage_status": ServiceItemExpense.UsageStatus.PLANNED,
                },
            )

            completed_day = today - timedelta(days=1)
            for work_date, work_time, note in (
                (completed_day, time(8, 0), "Entrada local de demonstração."),
                (completed_day, time(12, 0), "Saída local de demonstração."),
                (today, time(8, 0), "Entrada local para validar dia incompleto."),
            ):
                Punch.all_objects.get_or_create(
                    contract=contract,
                    timestamp=timezone.make_aware(datetime.combine(work_date, work_time)),
                    defaults={"note": note, "is_manual": True},
                )

        self.stdout.write(self.style.SUCCESS("Cenários locais de demonstração prontos."))
        self.stdout.write(f"Prestador: {professional.email}")
        self.stdout.write("Incluídos: contrato, horários, catálogo, pedido, serviço, período e item previsto.")
