"""Pedido 2026-11-15: o HoraCerta organiza horas e servicos; nada de recebimento/pagamento nas telas."""

from django.test import SimpleTestCase


class NoPaymentReceiptUITests(SimpleTestCase):
    def test_templates_have_no_payment_receipt_controls(self):
        from pathlib import Path

        from django.conf import settings

        base = Path(settings.BASE_DIR) / "templates"
        for rel in ("accounts/mei_reports.html", "accounts/mei_contract.html", "accounts/mei_panel.html",
                    "accounts/mei_service_report_detail.html", "public/_help_content.html"):
            text = (base / rel).read_text(encoding="utf-8")
            for word in ("set_payment_status", "Marcar pendente", "Recebimento pendente", "filter-receive",
                         "received_label", "marcado como recebido"):
                self.assertNotIn(word, text, f"{rel}: {word}")
