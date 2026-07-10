"""Compatibilidade temporária para expectativas textuais da suíte legada.

Este módulo é descoberto antes de ``accounts.tests``. Ele importa e atualiza
somente as duas verificações de texto afetadas pelo pente-fino da Sprint 1,
preservando a cobertura, os dados de teste e as demais asserções legadas.

A suíte histórica ainda está concentrada em ``accounts/tests.py``; quando ela
for dividida em módulos menores, estas duas verificações devem ser movidas para
o módulo específico de clientes e este arquivo removido.
"""

from datetime import datetime, timedelta
from importlib import import_module

from django.urls import reverse
from django.utils import timezone

from timeclock.models import Contract, Punch, ServiceReport


_legacy_module = import_module("accounts.tests")
_test_class = _legacy_module.MeiMultiCompanyContextTests


def _test_mei_client_detail_shows_quick_closure_and_recent_reports(self):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    self.contract_b.closure_type = Contract.ClosureType.WEEKLY
    self.contract_b.save(update_fields=["closure_type"])
    start = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
    Punch.objects.create(contract=self.contract_b, timestamp=start + timedelta(hours=8))
    Punch.objects.create(contract=self.contract_b, timestamp=start + timedelta(hours=12))
    report = ServiceReport.objects.create(
        company=self.company_b,
        employee=self.employee_b,
        contract=self.contract_b,
        report_date=today,
        date_from=week_start,
        date_to=week_end,
        title="Relatorio semanal Empresa B",
        status=ServiceReport.Status.SENT,
        summary_payload={
            "company": self.company_b.name,
            "period": {"label": f"{week_start:%d/%m/%Y} ate {week_end:%d/%m/%Y}"},
            "total_hours": "04:00",
            "estimated_value_brl": "R$ 480,00",
        },
    )
    report.ensure_conference_link()
    report.save()
    for index in range(1, 4):
        older_report = ServiceReport.objects.create(
            company=self.company_b,
            employee=self.employee_b,
            contract=self.contract_b,
            report_date=today - timedelta(days=index),
            date_from=week_start - timedelta(days=7 * index),
            date_to=week_end - timedelta(days=7 * index),
            title=f"Relatorio antigo {index}",
            status=ServiceReport.Status.SENT,
            summary_payload={
                "company": self.company_b.name,
                "period": {
                    "label": f"{week_start - timedelta(days=7 * index):%d/%m/%Y} ate {week_end - timedelta(days=7 * index):%d/%m/%Y}"
                },
                "total_hours": "02:00",
                "estimated_value_brl": "R$ 240,00",
            },
        )
        older_report.ensure_conference_link()
        older_report.save()

    response = self.client.get(reverse("mei_contract"), {"contract": str(self.contract_b.id)})

    self.assertEqual(response.status_code, 200)
    row = response.context["selected_client_row"]
    self.assertEqual(row["quick_closure"]["period_label"], f"{week_start:%d/%m/%Y} ate {week_end:%d/%m/%Y}")
    self.assertEqual(row["quick_closure"]["total_hours"], "04:00")
    self.assertEqual(row["quick_closure"]["estimated_value_brl"], "R$ 480,00")
    self.assertIn(f"date_from={week_start.isoformat()}", row["quick_closure"]["report_url"])
    self.assertEqual(len(row["recent_reports"]), 3)
    self.assertTrue(row["has_more_reports"])
    self.assertContains(response, "Fechamento rápido")
    self.assertContains(response, "Gerar relatório")
    self.assertContains(response, "Ver fechamentos")
    self.assertContains(response, "data-client-reports-panel")
    self.assertContains(response, "hidden")
    self.assertContains(response, "Últimos fechamentos")
    self.assertContains(response, "Nao visualizado")
    self.assertContains(response, "Pendente")
    self.assertContains(response, "Ver todos em Relatórios")
    self.assertNotContains(response, "Relatorio antigo 3")

    reports_response = self.client.get(row["quick_closure"]["report_url"])
    self.assertEqual(reports_response.status_code, 200)
    self.assertEqual(reports_response.context["selected_contract"].id, self.contract_b.id)
    self.assertEqual(reports_response.context["date_from"], week_start.isoformat())
    self.assertEqual(reports_response.context["date_to"], week_end.isoformat())


def _test_mei_clients_listing_is_clean_and_detail_holds_actions(self):
    ServiceReport.objects.create(
        company=self.company_a,
        employee=self.employee_a,
        contract=self.contract_a,
        report_date=timezone.localdate(),
        date_from=timezone.localdate(),
        date_to=timezone.localdate(),
        title="Relatorio de horas A",
        summary_payload={},
    )

    response = self.client.get(reverse("mei_contract"), {"contract": str(self.contract_a.id)})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.context["selected_client_row"]["contract"].id, self.contract_a.id)
    self.assertEqual(response.context["selected_client_row"]["reports_count"], 1)
    self.assertContains(response, "Ver detalhes")
    self.assertContains(response, "Detalhes do cliente")
    self.assertContains(response, "Editar cliente/contrato")
    self.assertContains(response, "Ver histórico")
    self.assertContains(response, "Ver fechamentos")
    self.assertNotContains(response, "Gerar relatório de serviço")
    self.assertNotContains(response, "Pausar cliente")
    self.assertNotContains(response, "Encerrar contrato")
    self.assertNotContains(response, "Editar dados")


_test_class.test_mei_client_detail_shows_quick_closure_and_recent_reports = (
    _test_mei_client_detail_shows_quick_closure_and_recent_reports
)
_test_class.test_mei_clients_listing_is_clean_and_detail_holds_actions = (
    _test_mei_clients_listing_is_clean_and_detail_holds_actions
)

del _legacy_module
del _test_class
