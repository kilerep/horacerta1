from django.test import SimpleTestCase

from .service_playbooks import service_playbook_for


class ServicePlaybookTests(SimpleTestCase):
    def test_event_playbook_uses_event_language(self):
        playbook = service_playbook_for("eventos-sonorizacao")

        self.assertEqual(playbook["document_title"], "Proposta técnica para evento")
        self.assertEqual(playbook["items_title"], "Composição técnica inclusa")
        self.assertIn("montagem/operação/desmontagem", playbook["client_focus"])
        self.assertTrue(any("check-in opcional" in item for item in playbook["checklist"]))

    def test_assistance_playbook_uses_technical_order_language(self):
        playbook = service_playbook_for("assistencia-tecnica")

        self.assertEqual(playbook["document_title"], "Ordem de serviço técnico")
        self.assertEqual(playbook["scope_title"], "Diagnóstico e serviço técnico")
        self.assertTrue(any("defeito informado" in item.lower() for item in playbook["checklist"]))

    def test_unknown_category_uses_default_playbook(self):
        playbook = service_playbook_for("categoria-desconhecida")

        self.assertEqual(playbook["document_title"], "Proposta técnica / Ordem de serviço")
        self.assertEqual(playbook["scope_title"], "Escopo combinado")
        self.assertGreaterEqual(len(playbook["checklist"]), 3)
        self.assertGreaterEqual(len(playbook["logistics"]), 3)
