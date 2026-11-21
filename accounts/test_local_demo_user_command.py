from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company, Employee
from timeclock.models import Contract


class LocalDemoUserCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_creates_a_local_mei_workspace_and_is_idempotent(self):
        output = StringIO()

        call_command(
            "create_local_demo_user",
            "--email",
            "zoe.local@horacerta.test",
            "--password",
            "Teste@12345",
            stdout=output,
        )
        call_command(
            "create_local_demo_user",
            "--email",
            "zoe.local@horacerta.test",
            "--password",
            "Teste@12345",
            stdout=output,
        )

        professional = User.objects.get(email="zoe.local@horacerta.test")
        self.assertEqual(professional.role, User.Role.FUNCIONARIO)
        self.assertTrue(professional.check_password("Teste@12345"))
        self.assertEqual(Company.objects.filter(name="Cliente Demonstração HoraCerta").count(), 1)
        self.assertTrue(Employee.objects.filter(user=professional, is_active=True).exists())
        self.assertTrue(Contract.objects.filter(employee__user=professional, is_active=True).exists())
        self.assertIn("Usuário local de demonstração pronto.", output.getvalue())

    @override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
    def test_demo_user_reaches_the_core_mei_area(self):
        call_command(
            "create_local_demo_user",
            "--email",
            "demo.fluxo@horacerta.test",
            "--password",
            "Teste@12345",
            stdout=StringIO(),
        )
        professional = User.objects.get(email="demo.fluxo@horacerta.test")
        self.client.force_login(professional)

        for route_name in ("mei_panel", "mei_contract", "mei_history", "mei_reports"):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False)
    def test_command_refuses_to_create_demo_data_outside_debug(self):
        with self.assertRaisesMessage(CommandError, "só funciona com DEBUG=True"):
            call_command("create_local_demo_user", "--password", "Teste@12345")
