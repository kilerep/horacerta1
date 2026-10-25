"""Jornadas completas por persona, como um usuario real usaria o HoraCerta.

Cada teste e uma pessoa fazendo o trabalho dela do comeco ao fim, so pelas telas
(GET/POST no sistema), e conferindo o resultado em cada passo:

- Prestador fixo (horas por cliente): conta -> cliente -> registrar horario ->
  historico -> relatorio -> link -> cliente confere -> recebido -> PDF/Excel.
- Prestador de servico rapido (avulso): servico rapido -> item -> orcamento ->
  link publico -> iniciar/parar trabalho -> finalizar -> relatorio final -> PDF.
- Operador de producao: folha -> itens -> fechar -> Excel/PDF -> WhatsApp com link.
- Empresa cliente: entra e acompanha prestadores, registros, relatorios e avisos.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


class Journey(TestCase):
    def ok(self, response, *texts):
        self.assertLess(response.status_code, 400, getattr(response, "url", ""))
        for text in texts:
            self.assertContains(response, text)
        return response


@override_settings(**BASE)
class PrestadorFixoJourney(Journey):
    def test_dia_a_dia_ate_o_relatorio_conferido_e_recebido(self):
        from timeclock.models import Contract, Punch, ServiceReport

        # 1. cria a conta e cai no primeiro passo
        signup = self.client.post(reverse("signup_mei"), {
            "full_name": "Rita Técnica", "email": "rita@horacerta.test", "password1": "Uma-Senha-Forte-482",
            "password2": "Uma-Senha-Forte-482", "accept_terms": "on", "website": "",
        })
        self.assertEqual(signup.status_code, 302)
        user = User.objects.get(email="rita@horacerta.test")

        # 2. cadastra o cliente mensal
        today = timezone.localdate()
        self.client.post(reverse("mei_client_create"), {
            "name": "Condomínio Aurora", "hourly_rate": "60.00",
            "start_date": (today - timedelta(days=30)).isoformat(), "closure_type": "MONTHLY",
        })
        contract = Contract.objects.get(employee__user=user)
        self.ok(self.client.get(reverse("mei_contract")), "Condomínio Aurora")

        # 3. registra a entrada pela tela principal
        self.ok(self.client.get(reverse("employee_dashboard")), "Registrar horário")
        before = Punch.objects.filter(contract=contract).count()
        self.client.post(reverse("employee_dashboard"), {"action": "punch", "contract": str(contract.id)})
        self.assertEqual(Punch.objects.filter(contract=contract).count(), before + 1)

        # dias anteriores ja trabalhados (entrada e saida)
        for days_ago in (3, 2):
            start = timezone.make_aware(timezone.datetime.combine(today - timedelta(days=days_ago),
                                                                  timezone.datetime.min.time())) + timedelta(hours=8)
            Punch.objects.create(contract=contract, timestamp=start)
            Punch.objects.create(contract=contract, timestamp=start + timedelta(hours=4))

        # 4. confere historico e resumo
        self.ok(self.client.get(reverse("mei_history")), "08:00")
        self.ok(self.client.get(reverse("mei_panel")), "Meu resumo", "Condomínio Aurora")

        # 5. gera o relatorio do periodo
        self.client.post(reverse("mei_reports"), {
            "action": "create_report", "status": "DRAFT", "contract": str(contract.id),
            "date_from": (today - timedelta(days=7)).isoformat(), "date_to": (today - timedelta(days=1)).isoformat(),
            "title": "Horas da semana", "description": "",
        })
        report = ServiceReport.objects.get(contract=contract)
        self.assertEqual(report.summary_payload["total_hours"], "08:00")
        self.ok(self.client.get(reverse("mei_service_report_detail", args=[report.id])), "Horas da semana")

        # 6. manda pelo WhatsApp com o link de conferencia
        whatsapp = self.client.get(reverse("mei_service_report_whatsapp", args=[report.id]))
        self.assertTrue(whatsapp["Location"].startswith("https://wa.me/"))

        # 7. o cliente (sem login) abre, baixa PDF/Excel e confirma
        self.client.logout()
        public = reverse("public_service_report_conference", args=[report.conference_token])
        self.ok(self.client.get(public), "Relatório de horas")
        self.assertEqual(self.client.get(reverse("public_service_report_pdf", args=[report.conference_token]))["Content-Type"],
                         "application/pdf")
        self.ok(self.client.get(reverse("public_service_report_xlsx", args=[report.conference_token])))
        self.client.post(reverse("public_service_report_respond", args=[report.conference_token]), {"action": "confirm"})
        report.refresh_from_db()
        self.assertEqual(report.conference_final_status, ServiceReport.ConferenceStatus.REVIEWED)

        # 8. prestador marca como recebido
        self.client.force_login(user)
        self.client.post(reverse("mei_reports"), {"action": "set_payment_status", "report_id": str(report.id),
                                                  "payment_status": ServiceReport.PaymentStatus.PAID})
        report.refresh_from_db()
        self.assertEqual(report.payment_status, ServiceReport.PaymentStatus.PAID)
        self.ok(self.client.get(reverse("mei_reports")), "Horas da semana")


@override_settings(**BASE)
class ServicoRapidoJourney(Journey):
    def test_do_pedido_rapido_ao_relatorio_final(self):
        from services.models import ServiceItemExpense, ServiceJob

        user = User.objects.create_user(username="eli@horacerta.test", email="eli@horacerta.test",
                                        password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(user)

        # 1. servico rapido
        created = self.client.post(reverse("service_job_quick"), {
            "client_name": "Dona Maria", "client_whatsapp": "(11) 98888-7777",
            "title": "Trocar chuveiro", "price": "150,00", "start_date": timezone.localdate().isoformat(),
        })
        job = ServiceJob.objects.get(professional=user)
        self.assertRedirects(created, reverse("service_job_detail", args=[job.id]), fetch_redirect_response=False)
        self.ok(self.client.get(reverse("service_job_detail", args=[job.id])), "Trocar chuveiro", "Dona Maria")

        # 2. material previsto
        self.client.post(reverse("service_item_expense_create", args=[job.id]), {
            "type": ServiceItemExpense.ItemType.MATERIAL, "name": "Chuveiro 220V", "description": "",
            "unit": "UNIT", "quantity": "1.00", "unit_value": "89.90",
            "usage_status": ServiceItemExpense.UsageStatus.PLANNED, "receipt_note": "",
        })
        self.assertTrue(job.item_expenses.filter(name="Chuveiro 220V").exists())

        # 3. orcamento para o cliente e link publico
        self.client.post(reverse("service_job_preview_generate", args=[job.id]))
        job.refresh_from_db()
        self.assertIsNotNone(job.preview_generated_at)
        self.assertTrue(self.client.get(reverse("service_job_preview_whatsapp", args=[job.id]))["Location"].startswith("https://wa.me/"))
        self.client.logout()
        self.ok(self.client.get(reverse("public_service_job_preview", args=[job.public_token])), "Trocar chuveiro")
        self.client.force_login(user)

        # 4. executa: inicia e para o cronometro, usa o material
        self.client.post(reverse("service_clock_action", args=[job.id]), {"action": "start"})
        job.refresh_from_db()
        self.assertEqual(job.status, ServiceJob.Status.IN_PROGRESS)
        self.client.post(reverse("service_clock_action", args=[job.id]), {"action": "stop"})
        item = job.item_expenses.get(name="Chuveiro 220V")
        self.client.post(reverse("service_item_expense_update", args=[job.id, item.id]), {
            "type": item.type, "name": item.name, "description": "", "unit": "UNIT", "quantity": "1.00",
            "unit_value": "89.90", "usage_status": ServiceItemExpense.UsageStatus.USED, "receipt_note": "",
        })
        item.refresh_from_db()
        self.assertEqual(item.usage_status, ServiceItemExpense.UsageStatus.USED)

        # 5. finaliza, gera relatorio final, envia e o cliente abre o PDF
        self.client.post(reverse("service_job_status_action", args=[job.id]), {"action": "finish"})
        self.client.post(reverse("service_job_status_action", args=[job.id]), {"action": "generate_report"})
        job.refresh_from_db()
        self.assertEqual(job.status, ServiceJob.Status.REPORT_SENT)
        self.assertTrue(self.client.get(reverse("service_job_report_whatsapp", args=[job.id]))["Location"].startswith("https://wa.me/"))
        self.client.logout()
        self.ok(self.client.get(reverse("public_service_job_report", args=[job.public_token])), "Trocar chuveiro")
        pdf = self.client.get(reverse("public_service_job_report_pdf", args=[job.public_token]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")


@override_settings(**BASE)
class OperadorProducaoJourney(Journey):
    def test_folha_da_maquina_ate_o_envio(self):
        from production.models import ProductionSheet

        user = User.objects.create_user(username="op@horacerta.test", email="op@horacerta.test",
                                        password="Teste@12345", role=User.Role.FUNCIONARIO)
        self.client.force_login(user)
        self.client.post(reverse("production_sheet_create"), {
            "equipment": "Chenlong", "company_name": "Metalúrgica X", "operator_name": "Op",
            "supervisor_name": "Carlos", "supervisor_whatsapp": "(11) 98888-7777", "notes": "",
        })
        sheet = ProductionSheet.objects.get(owner=user)
        detail = reverse("production_sheet_detail", args=[sheet.id])
        self.client.post(detail, {"work_date": timezone.localdate().isoformat(), "item_code": "0011-024",
                                  "destination": "IMPLEMENTO", "start_time": "07:00", "end_time": "11:00"})
        self.client.post(detail, {"work_date": timezone.localdate().isoformat(), "destination": "GUINCHO", "duration": "1:30"})
        self.ok(self.client.get(detail), "<strong>5:30</strong>")
        self.client.post(reverse("production_sheet_status", args=[sheet.id]), {"action": "close"})
        sheet.refresh_from_db()
        self.assertFalse(sheet.is_open)
        self.assertEqual(self.client.get(reverse("production_sheet_pdf", args=[sheet.id]))["Content-Type"], "application/pdf")
        self.assertIn("spreadsheetml", self.client.get(reverse("production_sheet_xlsx", args=[sheet.id]))["Content-Type"])
        location = self.client.get(reverse("production_sheet_whatsapp", args=[sheet.id]))["Location"]
        self.assertTrue(location.startswith("https://wa.me/5511988887777?text="))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("production_public_pdf", args=[sheet.share_token])).status_code, 200)


@override_settings(**BASE)
class EmpresaJourney(Journey):
    @classmethod
    def setUpTestData(cls):
        from .fixtures import build_world

        cls.w = build_world()

    def test_empresa_acompanha_prestadores_registros_e_relatorios(self):
        self.client.force_login(self.w["company_user"])
        for name in ("dashboard_empresa", "company_today_center", "company_meis", "company_history",
                     "company_reports", "company_service_reports", "company_notifications", "company_settings"):
            with self.subTest(page=name):
                self.ok(self.client.get(reverse(name), follow=True))
        self.ok(self.client.get(reverse("company_mei_profile", args=[self.w["employee"].id]), follow=True))

    def test_empresa_nao_ve_area_do_prestador_nem_dados_de_outra_empresa(self):
        other = User.objects.create_user(username="outra@horacerta.test", email="outra@horacerta.test",
                                         password="Teste@12345", role=User.Role.EMPRESA)
        from companies.models import Company

        Company.objects.create(owner=other, name="Outra Empresa", email="outra@horacerta.test")
        self.client.force_login(other)

        self.assertIn(self.client.get(reverse("company_mei_profile", args=[self.w["employee"].id])).status_code, (302, 403, 404))
        services = self.client.get(reverse("service_job_list"))
        self.assertNotEqual(services.status_code, 200)
