from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

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

    @override_settings(DEBUG=False)
    def test_command_refuses_to_create_demo_data_outside_debug(self):
        with self.assertRaisesMessage(CommandError, "só funciona com DEBUG=True"):
            call_command("create_local_demo_user", "--password", "Teste@12345")
