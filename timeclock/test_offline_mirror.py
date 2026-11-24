"""Offline 2.0, etapa 1: copia dos dados para o celular (/me/offline/copia/).

Garante que a copia so tem dados do proprio usuario, nunca links secretos, nao fica
em cache HTTP e que as telas carregam o script que cifra e apaga a copia.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Company, Employee
from production.models import ProductionEntry, ProductionSheet, ShipmentItem, ShipmentNote, ShipmentRecipient
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract, DayOff, Punch

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_world(email, client_name):
    user = User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)
    company = Company.objects.create(owner=user, name=client_name)
    employee = Employee.objects.create(user=user, company=company, full_name="Rita", is_active=True)
    contract = Contract.objects.create(company=company, employee=employee, hourly_rate=Decimal("60.00"),
                                       start_date=date(2026, 1, 1), is_active=True)
    today = timezone.localdate()
    Punch.objects.create(contract=contract)
    DayOff.objects.create(owner=user, date=today, kind=DayOff.Kind.FERIADO, note="Feriado municipal")
    job = ServiceJob.objects.create(
        professional=user, contract=contract, category=ServiceCategory.objects.get(slug="eletrica"),
        title=f"Servico de {client_name}", status=ServiceJob.Status.PLANNED, start_date=today,
        billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("60.00"),
    )
    sheet = ProductionSheet.objects.create(owner=user, equipment=f"Torno {client_name}")
    ProductionEntry.objects.create(sheet=sheet, item_code="8210-120", quantity=5)
    note = ShipmentNote.objects.create(owner=user, destination_company=f"Destino {client_name}")
    ShipmentItem.objects.create(note=note, production_order="OP1", drawing_number="D-1", quantity=2)
    ShipmentRecipient.objects.create(note=note, role=ShipmentRecipient.Role.ENCARREGADO, name="Carlos",
                                     whatsapp="11999999999")
    return SimpleWorld(user, contract, job, sheet, note)


class SimpleWorld:
    def __init__(self, user, contract, job, sheet, note):
        self.user, self.contract, self.job, self.sheet, self.note = user, contract, job, sheet, note


@override_settings(**BASE)
class OfflineMirrorTests(TestCase):
    def setUp(self):
        self.me = make_world("rita@horacerta.test", "Condominio Aurora")
        self.other = make_world("outro@horacerta.test", "Empresa Vizinha")
        self.client.force_login(self.me.user)
        self.url = reverse("offline_mirror")

    def get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response, response.json()

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_contains_my_data_for_every_offline_screen(self):
        _, data = self.get()

        self.assertEqual(data["user_id"], str(self.me.user.id))
        self.assertEqual(data["ttl_days"], 30)
        self.assertEqual([c["name"] for c in data["clients"]], ["Condominio Aurora"])
        self.assertEqual(data["clients"][0]["hourly_rate"], "60.00")
        self.assertEqual(len(data["punches"]), 1)
        self.assertEqual(data["days_off"][0]["kind"], "FERIADO")
        self.assertEqual(data["jobs"][0]["title"], "Servico de Condominio Aurora")
        self.assertEqual(data["sheets"][0]["equipment"], "Torno Condominio Aurora")
        self.assertEqual(data["entries"][0]["item_code"], "8210-120")
        self.assertEqual(data["shipments"][0]["items"][0]["drawing"], "D-1")
        self.assertEqual(data["shipments"][0]["recipients"], 1)

    def test_never_contains_other_accounts_data(self):
        response, _ = self.get()
        text = response.content.decode()
        for leak in ("Empresa Vizinha", str(self.other.contract.id), str(self.other.job.id), str(self.other.sheet.id)):
            self.assertNotIn(leak, text)

    def test_never_contains_secret_links_or_contacts(self):
        response, _ = self.get()
        text = response.content.decode()
        recipient = self.me.note.recipients.first()
        for secret in (str(self.me.job.public_token), str(self.me.sheet.share_token), str(recipient.token),
                       "11999999999"):
            self.assertNotIn(secret, text)

    def test_not_cached_by_browser_or_proxy(self):
        response, _ = self.get()
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])

    def test_old_and_cancelled_punches_are_left_out(self):
        old = Punch.objects.create(contract=self.me.contract)
        Punch.all_objects.filter(pk=old.pk).update(timestamp=timezone.now() - timedelta(days=75))
        cancelled = Punch.objects.create(contract=self.me.contract)
        Punch.all_objects.filter(pk=cancelled.pk).update(is_cancelled=True)

        _, data = self.get()
        ids = {p["id"] for p in data["punches"]}
        self.assertNotIn(str(old.id), ids)
        self.assertNotIn(str(cancelled.id), ids)

    def test_post_is_not_allowed(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)


@override_settings(**BASE)
class OfflineScreensLoadMirrorScriptTests(TestCase):
    def test_login_page_loads_mirror_script_to_wipe_after_logout(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("js/offline_mirror.js", html)
        self.assertIn('data-authenticated="false"', html)

    def test_logged_pages_load_mirror_script(self):
        world = make_world("tela@horacerta.test", "Cliente Tela")
        self.client.force_login(world.user)
        html = self.client.get(reverse("employee_dashboard")).content.decode()
        self.assertIn("js/offline_mirror.js", html)
        self.assertIn(f'data-user-id="{world.user.id}"', html)


class OfflineScriptsContractTests(TestCase):
    """Regras de seguranca escritas nos scripts (sem navegador: confere o codigo)."""

    def read(self, name):
        return (Path(settings.BASE_DIR) / "static/js" / name).read_text(encoding="utf-8")

    def test_mirror_is_encrypted_with_non_extractable_key_and_wiped(self):
        js = self.read("offline_mirror.js")
        self.assertIn('generateKey({ name: "AES-GCM", length: 256 }, false', js)
        self.assertIn("getRandomValues(new Uint8Array(12))", js)
        self.assertIn('auth === "false"', js)          # tela deslogada apaga
        self.assertIn("resp.redirected", js)            # sessao expirada apaga
        self.assertIn("deleteDatabase(DB_NAME)", js)

    def test_guard_lets_offline_capable_forms_reach_the_queue(self):
        js = self.read("connection_guard.js")
        self.assertIn("#hcPunchForm, #new-entry, [data-offline-ok]", js)
        self.assertIn("Conectado de novo", js)
