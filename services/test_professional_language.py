from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from accounts.models import User
from services.forms import ServiceJobForm, ServiceRequestForm


class ProfessionalLanguageTests(SimpleTestCase):
    def test_access_profiles_use_product_vocabulary(self):
        labels = dict(User.Role.choices)

        self.assertEqual(labels[User.Role.FUNCIONARIO], "Prestador de serviço")
        self.assertEqual(labels[User.Role.EMPRESA], "Empresa contratante")

    def test_service_form_uses_clear_professional_labels(self):
        fields = ServiceJobForm.base_fields

        self.assertEqual(fields["client_mode"].label, "Forma de cadastro do cliente")
        self.assertEqual(fields["service_number"].label, "Número")
        self.assertEqual(fields["service_reference"].label, "Ponto de referência")
        self.assertEqual(fields["title"].label, "Título do serviço")
        self.assertEqual(fields["description"].label, "Escopo do serviço")
        self.assertEqual(fields["billing_mode"].label, "Forma de cobrança")
        self.assertEqual(fields["fixed_labor_value"].label, "Valor fixo da mão de obra")
        self.assertEqual(fields["notes"].label, "Observações e condições do atendimento")

    def test_request_form_uses_clear_professional_labels(self):
        fields = ServiceRequestForm.base_fields

        self.assertEqual(fields["client_mode"].label, "Forma de cadastro do cliente")
        self.assertEqual(fields["title"].label, "Título do pedido")
        self.assertEqual(fields["description"].label, "Descrição do pedido")
        self.assertEqual(fields["urgency"].label, "Prioridade")
        self.assertEqual(fields["source"].label, "Origem do pedido")

    def test_critical_interface_files_do_not_contain_mojibake(self):
        paths = [
            Path(settings.BASE_DIR) / "accounts" / "models.py",
            Path(settings.BASE_DIR) / "services" / "forms.py",
            Path(settings.BASE_DIR) / "services" / "professional_language.py",
            Path(settings.BASE_DIR) / "templates" / "500.html",
            Path(settings.BASE_DIR) / "templates" / "public" / "landing.html",
        ]

        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path)):
                self.assertNotIn("Ã", text)
                self.assertNotIn("Â", text)
                self.assertNotIn("�", text)
