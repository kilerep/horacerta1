from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from accounts.models import User
from services.models import (
    ServiceCategory,
    ServiceItemCatalog,
    ServiceItemExpense,
    ServiceJob,
    ServiceRequest,
    ServiceRequestItem,
    ServiceWorkLog,
)
from timeclock.models import Contract, Punch


class LocalDemoScenariosCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_creates_idempotent_local_scenarios_for_core_flows(self):
        output = StringIO()
        arguments = (
            "seed_local_demo_scenarios",
            "--email",
            "zoe.cenarios@horacerta.test",
            "--password",
            "Teste@12345",
        )

        call_command(*arguments, stdout=output)
        call_command(*arguments, stdout=output)

        professional = User.objects.get(email="zoe.cenarios@horacerta.test")
        contract = Contract.objects.get(employee__user=professional, is_active=True)
        category = ServiceCategory.objects.get(slug="demo-local")
        catalog_item = ServiceItemCatalog.objects.get(
            professional=professional,
            internal_code="DEMO-MAT-001",
        )
        service_request = ServiceRequest.objects.get(
            professional=professional,
            title="Pedido demo - troca de tomada",
        )
        job = ServiceJob.objects.get(
            professional=professional,
            title="Serviço demo - instalação",
        )

        self.assertTrue(professional.check_password("Teste@12345"))
        self.assertEqual(catalog_item.category_id, category.id)
        self.assertEqual(service_request.contract_id, contract.id)
        self.assertEqual(ServiceRequestItem.objects.filter(service_request=service_request).count(), 1)
        self.assertEqual(job.contract_id, contract.id)
        self.assertEqual(job.status, ServiceJob.Status.IN_PROGRESS)
        self.assertEqual(ServiceWorkLog.objects.filter(service_job=job).count(), 1)
        self.assertEqual(ServiceItemExpense.objects.filter(service_job=job).count(), 1)
        self.assertEqual(Punch.objects.filter(contract=contract).count(), 3)
        self.assertIn("Cenários locais de demonstração prontos.", output.getvalue())

    @override_settings(DEBUG=False)
    def test_command_refuses_to_create_scenarios_outside_debug(self):
        with self.assertRaisesMessage(CommandError, "só funciona com DEBUG=True"):
            call_command("seed_local_demo_scenarios", "--password", "Teste@12345")
