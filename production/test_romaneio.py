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
