"""Modo sem internet: o que foi registrado offline chega certo quando a conexao volta."""

import json
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from production.models import ProductionEntry, ProductionSheet
from timeclock.models import Contract, Punch, ServiceReport

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


@override_settings(**BASE)
class OfflineSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="off@horacerta.test", email="off@horacerta.test",
                                             password="Teste@12345", role=User.Role.FUNCIONARIO)
        company = Company.objects.create(owner=self.user, name="Condomínio Aurora")
        employee = Employee.objects.create(user=self.user, company=company, full_name="Rita", is_active=True)
        self.contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("60"),
                                                start_date=date(2026, 1, 1), is_active=True)
        self.client.force_login(self.user)
        self.url = reverse("offline_sync")

    def _send(self, *items):
        return self.client.post(self.url, json.dumps({"items": list(items)}), content_type="application/json")

    def _punch(self, minutes_ago=30, **extra):
        occurred = timezone.now() - timedelta(minutes=minutes_ago)
        item = {"kind": "punch", "client_ref": str(uuid.uuid4()), "contract_id": str(self.contract.id),
                "occurred_at": occurred.isoformat()}
        item.update(extra)
        return item, occurred

    def test_punch_keeps_the_real_time_of_the_tap(self):
        item, occurred = self._punch(minutes_ago=95)

        response = self._send(item)
        punch = Punch.objects.get(contract=self.contract)

        self.assertEqual(response.json()["resultados"][0]["status"], "ok")
        self.assertEqual(punch.timestamp.replace(microsecond=0), occurred.replace(microsecond=0))
        self.assertEqual(punch.audit_payload["origin"], "offline")
        self.assertEqual(punch.audit_payload["client_ref"], item["client_ref"])

    def test_resending_the_same_record_does_not_duplicate(self):
        item, _ = self._punch()

        self._send(item)
        second = self._send(item)

        self.assertEqual(Punch.objects.filter(contract=self.contract).count(), 1)
        self.assertTrue(second.json()["resultados"][0]["duplicado"])

    def test_rejects_future_old_and_foreign_records_with_reasons(self):
        other = User.objects.create_user(username="x@horacerta.test", email="x@horacerta.test", password="Teste@12345",
                                         role=User.Role.FUNCIONARIO)
        oc = Company.objects.create(owner=other, name="Outro")
        oe = Employee.objects.create(user=other, company=oc, full_name="X", is_active=True)
        foreign = Contract.objects.create(company=oc, employee=oe, hourly_rate=Decimal("1"), start_date=date(2026, 1, 1),
                                          is_active=True)
        future, _ = self._punch(minutes_ago=-60)
        old, _ = self._punch(minutes_ago=60 * 24 * 10)
        theirs, _ = self._punch(contract_id=str(foreign.id))
        bad_ref, _ = self._punch(client_ref="nao-e-uuid")

        results = self._send(future, old, theirs, bad_ref).json()["resultados"]

        self.assertEqual([r["status"] for r in results], ["erro"] * 4)
        self.assertIn("futuro", results[0]["motivo"])
        self.assertIn("mais de 7 dias", results[1]["motivo"])
        self.assertIn("Cliente não encontrado", results[2]["motivo"])
        self.assertFalse(Punch.objects.exists())

    def test_day_already_in_a_generated_report_is_refused(self):
        today = timezone.localdate()
        ServiceReport.objects.create(company=self.contract.company, employee=self.contract.employee,
                                     contract=self.contract, title="Fechado", date_from=today - timedelta(days=2),
                                     date_to=today, status=ServiceReport.Status.SENT)
        item, _ = self._punch()

        result = self._send(item).json()["resultados"][0]

        self.assertEqual(result["status"], "erro")
        self.assertIn("relatório gerado", result["motivo"])

    def test_production_entry_offline_goes_to_open_sheet_only(self):
        sheet = ProductionSheet.objects.create(owner=self.user, equipment="Chenlong")
        closed = ProductionSheet.objects.create(owner=self.user, equipment="Velha", status=ProductionSheet.Status.CLOSED)
        fields = {"work_date": timezone.localdate().isoformat(), "item_code": "0011-024", "destination": "IMPLEMENTO",
                  "start_time": "07:00", "end_time": "09:30"}
        ok = {"kind": "production_entry", "client_ref": str(uuid.uuid4()), "sheet_id": str(sheet.id), "fields": fields}
        refused = {"kind": "production_entry", "client_ref": str(uuid.uuid4()), "sheet_id": str(closed.id), "fields": fields}

        results = self._send(ok, refused, ok).json()["resultados"]

        self.assertEqual(results[0]["status"], "ok")
        self.assertIn("fechado", results[1]["motivo"])
        self.assertTrue(results[2]["duplicado"])
        entry = ProductionEntry.objects.get(sheet=sheet)
        self.assertEqual(entry.duration_label, "2:30")

    def test_profile_lists_only_my_active_clients_and_open_sheets(self):
        ProductionSheet.objects.create(owner=self.user, equipment="Chenlong")

        data = self.client.get(reverse("offline_profile")).json()

        self.assertEqual(data["user_id"], str(self.user.id))
        self.assertEqual(data["contracts"], [{"id": str(self.contract.id), "name": "Condomínio Aurora"}])
        self.assertEqual([s["name"] for s in data["sheets"]], ["Chenlong"])

    def test_requires_login_and_valid_payload(self):
        self.assertEqual(self.client.post(self.url, "x", content_type="application/json").status_code, 400)
        self.client.logout()
        self.assertEqual(self._send().status_code, 302)

    def test_offline_page_is_generic_and_embeds_the_queue_code(self):
        self.client.logout()
        html = self.client.get(reverse("offline")).content.decode()

        self.assertIn("window.HoraCertaOffline", html)
        self.assertIn("Registrar agora", html)
        self.assertNotIn("Condomínio Aurora", html)

    def test_logged_pages_load_the_offline_bridge(self):
        html = self.client.get(reverse("employee_dashboard")).content.decode()

        self.assertIn(f'data-user-id="{self.user.id}"', html)
        self.assertIn("js/offline_bridge.js", html)
        self.assertIn('id="hcPunchForm"', html)
