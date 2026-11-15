"""Romaneio de envio a partir dos itens do relatorio de producao (2026-11-15)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from production.forms import ProductionEntryForm
from production.models import ProductionEntry, ProductionSheet, ShipmentItem, ShipmentNote, ShipmentRecipient

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_user(email):
    return User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)


def make_entry(owner, code="0128-208", quantity=49, order="7542.1"):
    sheet, _ = ProductionSheet.objects.get_or_create(owner=owner, equipment="Chenlong")
    return ProductionEntry.objects.create(sheet=sheet, item_code=code, quantity=quantity, production_order=order,
                                          manual_minutes=60)


def sent_note_with(entry, quantity):
    note = ShipmentNote.objects.create(owner=entry.sheet.owner, destination_company="Gbach")
    ShipmentItem.objects.create(note=note, production_order=entry.production_order, drawing_number=entry.item_code,
                                quantity=quantity, source_entry=entry)
    ShipmentRecipient.objects.create(note=note, role=ShipmentRecipient.Role.ENCARREGADO, name="João")
    note.send()
    return note


class EntryBalanceTests(TestCase):
    def setUp(self):
        self.owner = make_user("saldo@example.com")

    def test_shipped_counts_only_sent_notes(self):
        entry = make_entry(self.owner)
        sent_note_with(entry, 30)
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="Gbach")
        ShipmentItem.objects.create(note=draft, drawing_number="x", quantity=10, source_entry=entry)

        self.assertEqual(entry.shipped_quantity(), 30)
        self.assertEqual(entry.remaining_quantity(), 19)

    def test_remaining_never_negative_and_none_without_quantity(self):
        entry = make_entry(self.owner, quantity=5)
        sent_note_with(entry, 8)

        self.assertEqual(entry.remaining_quantity(), 0)
        self.assertIsNone(make_entry(self.owner, quantity=None).remaining_quantity())

    def test_form_has_production_order(self):
        self.assertIn("production_order", ProductionEntryForm().fields)


@override_settings(**BASE)
class FromEntriesTests(TestCase):
    def setUp(self):
        self.owner = make_user("romaneio@example.com")
        self.client.force_login(self.owner)
        self.entry = make_entry(self.owner)
        self.url = reverse("shipment_from_entries", args=[self.entry.sheet_id])

    def test_creates_draft_with_remaining_quantity(self):
        sent_note_with(self.entry, 30)
        other = make_entry(self.owner, code="8201-120-01", quantity=4, order="4030.6")

        response = self.client.post(self.url, {"entry": [self.entry.id, other.id], "target": "new"})
        draft = ShipmentNote.objects.get(owner=self.owner, status=ShipmentNote.Status.DRAFT)

        self.assertRedirects(response, reverse("shipment_edit", args=[draft.id]))
        rows = list(draft.items.values_list("production_order", "drawing_number", "quantity", "source_entry"))
        self.assertEqual(rows, [("7542.1", "0128-208", 19, self.entry.id), ("4030.6", "8201-120-01", 4, other.id)])
        self.assertEqual(draft.recipients.get().name, "João")  # herda quem recebeu o ultimo
        self.assertEqual(draft.destination_company, "Gbach")

    def test_adds_to_existing_draft(self):
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="Gbach")
        ShipmentItem.objects.create(note=draft, drawing_number="X", quantity=1)

        self.client.post(self.url, {"entry": [self.entry.id], "target": str(draft.id)})

        self.assertEqual(draft.items.count(), 2)
        self.assertEqual(draft.items.last().drawing_number, "0128-208")

    def test_sent_target_creates_new_draft(self):
        sent = sent_note_with(make_entry(self.owner, code="Z"), 1)

        self.client.post(self.url, {"entry": [self.entry.id], "target": str(sent.id)})

        self.assertEqual(sent.items.count(), 1)
        self.assertTrue(ShipmentNote.objects.filter(owner=self.owner, status=ShipmentNote.Status.DRAFT).exists())

    def test_other_owner_entries_ignored(self):
        intruder = make_entry(make_user("outro-romaneio@example.com"), code="ALHEIO")

        response = self.client.post(self.url, {"entry": [intruder.id], "target": "new"})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ShipmentNote.objects.filter(owner=self.owner).exists())

    def test_entry_without_quantity_or_code_and_fully_shipped(self):
        empty = make_entry(self.owner, code="", quantity=None, order="")
        sent_note_with(self.entry, 49)

        self.client.post(self.url, {"entry": [empty.id, self.entry.id], "target": "new"})
        draft = ShipmentNote.objects.get(owner=self.owner, status=ShipmentNote.Status.DRAFT)

        self.assertEqual(list(draft.items.values_list("drawing_number", "quantity")), [("-", 1), ("0128-208", 1)])


@override_settings(**BASE)
class SheetScreenTests(TestCase):
    def setUp(self):
        self.owner = make_user("tela-romaneio@example.com")
        self.client.force_login(self.owner)
        self.entry = make_entry(self.owner)

    def _html(self):
        return self.client.get(reverse("production_sheet_detail", args=[self.entry.sheet_id])).content.decode()

    def test_sheet_detail_has_select_mode_and_drafts(self):
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="Gbach")
        html = self._html()

        self.assertIn("data-select-toggle", html)
        self.assertIn(reverse("shipment_from_entries", args=[self.entry.sheet_id]), html)
        self.assertIn(f'value="{self.entry.id}"', html)
        self.assertIn(f'value="{draft.id}"', html)
        self.assertIn('name="production_order"', html)
        self.assertIn("7542.1", html)

    def test_entry_shows_sent_progress(self):
        sent_note_with(self.entry, 30)
        self.assertIn("30 de 49 enviadas", self._html())
        sent_note_with(self.entry, 19)
        self.assertIn("Enviado", self._html())

    def test_exports_include_production_order(self):
        from io import BytesIO

        from openpyxl import load_workbook

        from production.exports import build_xlsx

        ws = load_workbook(BytesIO(build_xlsx(self.entry.sheet))).active
        values = [c for row in ws.iter_rows(values_only=True) for c in row if c is not None]

        self.assertIn("Ordem de produção", values)
        self.assertIn("7542.1", values)
