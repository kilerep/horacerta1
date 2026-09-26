from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, Employee
from timeclock.models import Contract, Punch, ServiceReport


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
)
class MeiOnboardingChecklistTests(TestCase):
    """"Modo de uso" para novos usuarios (item 2 do pedido do usuario):
    checklist de primeiros passos no Meu Resumo, baseado em dado real, que
    some sozinho assim que o prestador ja estiver usando o sistema.
    """

    def setUp(self):
        self.mei_user = User.objects.create_user(
            username="onboarding-mei@example.com",
            email="onboarding-mei@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )

    def _create_contract(self, hourly_rate=Decimal("0.00")):
        owner = User.objects.create_user(
            username=f"onboarding-cliente-{Company.objects.count()}@example.com",
            email=f"onboarding-cliente-{Company.objects.count()}@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        company = Company.objects.create(
            owner=owner,
            name="Cliente do onboarding",
            email=owner.email,
        )
        employee = Employee.objects.create(
            user=self.mei_user,
            company=company,
            full_name="Prestador do onboarding",
            is_active=True,
        )
        return Contract.objects.create(
            employee=employee,
            company=company,
            hourly_rate=hourly_rate,
            start_date=timezone.localdate(),
            is_active=True,
        )

    def test_brand_new_account_sees_all_steps_pending(self):
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primeiros passos")
        self.assertContains(response, "Cadastre seu primeiro cliente")
        self.assertContains(response, reverse("mei_client_create"))
        self.assertContains(response, "Defina o valor por hora do contrato")
        self.assertContains(response, "Registre seu primeiro horário")
        self.assertContains(response, "Gere seu primeiro relatório")

    def test_checklist_marks_steps_done_as_real_data_is_created(self):
        contract = self._create_contract(hourly_rate=Decimal("0.00"))
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertContains(response, "Primeiros passos")
        self.assertContains(response, "onboarding-step--done")
        self.assertContains(response, "✓")
        # O primeiro passo ja foi cumprido: o CTA de cadastro nao aparece mais,
        # mas o checklist continua visivel porque faltam os outros 3 passos.
        self.assertNotContains(response, "Adicionar cliente")

    def test_checklist_disappears_once_all_steps_are_completed(self):
        contract = self._create_contract(hourly_rate=Decimal("50.00"))
        Punch.objects.create(
            contract=contract,
            timestamp=timezone.make_aware(datetime.combine(timezone.localdate(), time(hour=9))),
        )
        ServiceReport.objects.create(
            company=contract.company,
            employee=contract.employee,
            contract=contract,
            report_date=timezone.localdate(),
            title="Relatorio de conclusao do onboarding",
            summary_payload={},
        )
        self.client.force_login(self.mei_user)

        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Primeiros passos")

    def test_another_providers_activity_never_completes_this_users_checklist(self):
        contract = self._create_contract(hourly_rate=Decimal("50.00"))

        other_mei_user = User.objects.create_user(
            username="outro-prestador-onboarding@example.com",
            email="outro-prestador-onboarding@example.com",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        other_owner = User.objects.create_user(
            username="outro-cliente-onboarding@example.com",
            email="outro-cliente-onboarding@example.com",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        other_company = Company.objects.create(
            owner=other_owner,
            name="Cliente de outro prestador",
            email=other_owner.email,
        )
        other_employee = Employee.objects.create(
            user=other_mei_user,
            company=other_company,
            full_name="Outro prestador",
            is_active=True,
        )
        other_contract = Contract.objects.create(
            employee=other_employee,
            company=other_company,
            hourly_rate=Decimal("80.00"),
            start_date=timezone.localdate(),
            is_active=True,
        )
        Punch.objects.create(
            contract=other_contract,
            timestamp=timezone.make_aware(datetime.combine(timezone.localdate(), time(hour=9))),
        )
        ServiceReport.objects.create(
            company=other_company,
            employee=other_employee,
            contract=other_contract,
            report_date=timezone.localdate(),
            title="Relatorio de outro prestador",
            summary_payload={},
        )

        self.client.force_login(self.mei_user)
        response = self.client.get(reverse("mei_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primeiros passos")
        self.assertContains(response, "Registre seu primeiro horário")
        self.assertContains(response, "Gere seu primeiro relatório")
        self.assertNotContains(response, "Cliente de outro prestador")
