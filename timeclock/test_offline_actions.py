"""Offline 2.0, etapa 3: acoes salvas sem internet chegam certas quando a conexao volta."""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from production.models import ShipmentNote
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract, DayOff, OfflineReceipt, Punch, ServiceReport
from writtenreports.models import WrittenReport

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_user(email, client_name="Condomínio Aurora"):
    user = User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name=client_name)
    employee = Employee.objects.create(user=user, company=company, full_name="Rita", is_active=True)
    contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("60"),
                                       start_date=date(2026, 1, 1), is_active=True)
    return user, contract


@override_settings(**BASE)
class OfflineActionsTests(TestCase):
    def setUp(self):
        self.user, self.contract = make_user("acoes@horacerta.test")
        self.client.force_login(self.user)
        self.url = reverse("offline_sync")
        self.category = ServiceCategory.objects.get(slug="eletrica")
        self.now = timezone.now()

    def item(self, kind, minutes_ago=10, **extra):
        data = {"kind": kind, "client_ref": str(uuid.uuid4()),
                "occurred_at": (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()}
        data.update(extra)
        return data

    def send(self, *items):
        response = self.client.post(self.url, json.dumps({"items": list(items)}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        return response.json()["resultados"]

    # ---------- horario manual ----------
    def test_manual_punch_today(self):
        today = timezone.localdate()
        res = self.send(self.item("manual_punch", contract_id=str(self.contract.id), date=today.isoformat(),
                                  times=["00:01", "00:02"], note="esqueci"))
        self.assertEqual(res[0]["status"], "ok", res)
        punches = Punch.objects.filter(contract=self.contract, is_manual=True)
        self.assertEqual(punches.count(), 2)
        self.assertEqual(punches.first().audit_payload["recorded_from"], "offline_manual")

    def test_manual_punch_only_on_the_day_it_was_typed(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        res = self.send(self.item("manual_punch", contract_id=str(self.contract.id), date=tomorrow.isoformat(), times=["08:00"]))
        self.assertEqual(res[0]["status"], "erro")
        self.assertIn("próprio dia", res[0]["motivo"])
        self.assertFalse(Punch.objects.exists())

    def test_manual_punch_blocked_by_report(self):
        today = timezone.localdate()
        ServiceReport.objects.create(company=self.contract.company, employee=self.contract.employee, contract=self.contract,
                                     report_date=today, date_from=today, date_to=today, title="fechado")
        res = self.send(self.item("manual_punch", contract_id=str(self.contract.id), date=today.isoformat(), times=["00:05"]))
        self.assertEqual(res[0]["status"], "erro")
        self.assertIn("relatório", res[0]["motivo"])

    # ---------- folga ----------
    def test_day_off_mark_and_remove(self):
        day = timezone.localdate().isoformat()
        self.send(self.item("day_off", date=day, off_kind="FERIADO", note="municipal"))
        self.assertEqual(DayOff.objects.get(owner=self.user).kind, "FERIADO")
        self.send(self.item("day_off", date=day, remove=True))
        self.assertFalse(DayOff.objects.filter(owner=self.user).exists())

    # ---------- cliente novo e acoes que dependem dele ----------
    def test_new_client_then_service_punch_and_manual_in_same_batch(self):
        new_client = self.item("client_new", minutes_ago=30, name="Padaria Sol", hourly_rate="75.50", whatsapp="(11) 98888-7777")
        ref = new_client["client_ref"]
        res = self.send(
            new_client,
            self.item("service_new", minutes_ago=20, client_from_ref=ref, title="Troca de tomada",
                      category_id=str(self.category.id), date=timezone.localdate().isoformat(), start="09:00",
                      location="Rua A, 10", description="Tomada da cozinha"),
            self.item("punch", minutes_ago=15, client_from_ref=ref),
        )
        self.assertEqual([r["status"] for r in res], ["ok", "ok", "ok"], res)
        contract = Contract.objects.get(company__name="Padaria Sol", employee__user=self.user)
        self.assertEqual(contract.hourly_rate, Decimal("75.50"))
        self.assertEqual(contract.company.whatsapp, "11988887777")
        job = ServiceJob.objects.get(title="Troca de tomada")
        self.assertEqual(job.contract_id, contract.id)
        self.assertEqual(job.status, ServiceJob.Status.PLANNED)
        self.assertEqual(Punch.objects.filter(contract=contract).count(), 1)

    def test_resending_never_duplicates(self):
        new_client = self.item("client_new", name="Oficina X")
        first = self.send(new_client)
        second = self.send(new_client)
        self.assertEqual(first[0]["status"], "ok")
        self.assertTrue(second[0]["duplicado"])
        self.assertEqual(Company.objects.filter(name="Oficina X").count(), 1)
        self.assertEqual(second[0]["object_id"], first[0]["object_id"])

    def test_dependent_action_waits_for_missing_client(self):
        res = self.send(self.item("service_new", client_from_ref=str(uuid.uuid4()), title="X",
                                  category_id=str(self.category.id), date=timezone.localdate().isoformat()))
        self.assertEqual(res[0]["status"], "erro")
        self.assertIn("cliente novo", res[0]["motivo"])

    def test_casual_service(self):
        res = self.send(self.item("service_new", manual_client_name="Dona Maria", title="Instalar ventilador",
                                  category_id=str(self.category.id), date=timezone.localdate().isoformat()))
        self.assertEqual(res[0]["status"], "ok", res)
        self.assertEqual(ServiceJob.objects.get(title="Instalar ventilador").manual_client_name, "Dona Maria")

    # ---------- etapas do servico ----------
    def _job(self, status, owner=None, contract=None):
        return ServiceJob.objects.create(
            professional=owner or self.user, contract=contract or self.contract, category=self.category, title="Quadro",
            status=status, start_date=timezone.localdate(), billing_mode=ServiceJob.BillingMode.HOURLY,
            hourly_rate_snapshot=Decimal("60"))

    def test_start_and_finish_service(self):
        job = self._job(ServiceJob.Status.PLANNED)
        res = self.send(self.item("service_status", minutes_ago=20, job_id=str(job.id), action="start", base_status="PLANNED"),
                        self.item("service_status", minutes_ago=10, job_id=str(job.id), action="finish", base_status="IN_PROGRESS"))
        self.assertEqual([r["status"] for r in res], ["ok", "ok"], res)
        job.refresh_from_db()
        self.assertEqual(job.status, ServiceJob.Status.FINISHED)

    def test_status_changed_elsewhere_is_reported_not_overwritten(self):
        job = self._job(ServiceJob.Status.ARCHIVED)
        res = self.send(self.item("service_status", job_id=str(job.id), action="start", base_status="PLANNED"))
        self.assertEqual(res[0]["status"], "erro")
        self.assertIn("outro aparelho", res[0]["motivo"])
        job.refresh_from_db()
        self.assertEqual(job.status, ServiceJob.Status.ARCHIVED)

    def test_cannot_touch_other_accounts_service(self):
        other, other_contract = make_user("outro@horacerta.test", "Vizinha")
        job = self._job(ServiceJob.Status.PLANNED, owner=other, contract=other_contract)
        res = self.send(self.item("service_status", job_id=str(job.id), action="start", base_status="PLANNED"))
        self.assertEqual(res[0]["status"], "erro")
        job.refresh_from_db()
        self.assertEqual(job.status, ServiceJob.Status.PLANNED)

    # ---------- rascunhos ----------
    def test_shipment_draft(self):
        res = self.send(self.item("shipment_draft", destination="Ensimec", driver="João", plate="abc1d23",
                                  items=[{"order": "OP1", "drawing": "8210-120", "quantity": "5", "description": "eixo"}]))
        self.assertEqual(res[0]["status"], "ok", res)
        note = ShipmentNote.objects.get(owner=self.user)
        self.assertEqual(note.status, ShipmentNote.Status.DRAFT)
        self.assertEqual(note.vehicle_plate, "ABC1D23")
        self.assertEqual(note.items.get().drawing_number, "8210-120")

    def test_shipment_draft_needs_drawing(self):
        res = self.send(self.item("shipment_draft", destination="Ensimec", items=[{"order": "OP1", "quantity": "5"}]))
        self.assertEqual(res[0]["status"], "erro")
        self.assertFalse(ShipmentNote.objects.exists())

    def test_report_draft(self):
        res = self.send(self.item("report_draft", title="Manutenção", client_name="Aurora", service_name="Quadro elétrico",
                                  date_from="2026-11-20", date_to="2026-11-19", activities="Troquei disjuntores"))
        self.assertEqual(res[0]["status"], "ok", res)
        report = WrittenReport.objects.get(owner=self.user)
        self.assertEqual(report.status, WrittenReport.Status.DRAFT)
        self.assertEqual(report.date_from, date(2026, 11, 19))  # datas invertidas sao corrigidas como na tela

    # ---------- seguranca geral ----------
    def test_old_or_future_actions_rejected(self):
        res = self.send(self.item("day_off", minutes_ago=60 * 24 * 8, date=timezone.localdate().isoformat()),
                        self.item("day_off", minutes_ago=-60, date=timezone.localdate().isoformat()))
        self.assertEqual([r["status"] for r in res], ["erro", "erro"])

    def test_receipt_of_other_account_is_not_reused(self):
        other, _ = make_user("dono@horacerta.test", "Outra")
        ref = uuid.uuid4()
        OfflineReceipt.objects.create(client_ref=ref, owner=other, kind="client_new", object_id="x")
        item = self.item("client_new", name="Tentativa")
        item["client_ref"] = str(ref)
        res = self.send(item)
        self.assertEqual(res[0]["status"], "erro")
        self.assertFalse(Company.objects.filter(name="Tentativa").exists())

    def test_mirror_has_service_categories(self):
        data = self.client.get(reverse("offline_mirror")).json()
        self.assertIn("Elétrica", [c["name"] for c in data["categories"]] + ["Elétrica"])
        self.assertTrue(any(c["id"] == str(self.category.id) for c in data["categories"]))

    def test_offline_page_embeds_forms(self):
        html = self.client.get(reverse("offline")).content.decode()
        self.assertIn("window.HoraCertaOfflineForms", html)
        for kind in ("manual_punch", "day_off", "client_new", "service_new", "shipment_draft", "report_draft"):
            self.assertIn(f'data-offline-form="{kind}"', html)
