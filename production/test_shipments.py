"""Notas de envio: comprovante numerado e travado das pecas que saem no caminhao."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from production.models import ShipmentItem, ShipmentNote, ShipmentRecipient

User = get_user_model()


def make_user(email):
    return User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)


def make_note(owner, *, items=1, names=("João", "Maria"), destination="Ensimec"):
    note = ShipmentNote.objects.create(owner=owner, destination_company=destination)
    for i in range(items):
        ShipmentItem.objects.create(note=note, position=i, production_order=f"OP-{100 + i}",
                                    drawing_number=f"DES-{i}", quantity=2)
    for role, name in zip((ShipmentRecipient.Role.ENCARREGADO, ShipmentRecipient.Role.SUPERVISOR), names):
        ShipmentRecipient.objects.create(note=note, role=role, name=name, whatsapp="11999990000")
    return note


class ShipmentModelTests(TestCase):
    def setUp(self):
        self.owner = make_user("envio@example.com")

    def test_send_numbers_sequentially_per_owner(self):
        first, second = make_note(self.owner), make_note(self.owner)
        other = make_note(make_user("outro-envio@example.com"))

        first.send()
        second.send()
        other.send()

        self.assertEqual((first.number, second.number, other.number), (1, 2, 1))
        self.assertEqual(first.status, ShipmentNote.Status.SENT)
        self.assertIsNotNone(first.sent_at)

    def test_send_twice_keeps_number(self):
        note = make_note(self.owner)
        note.send()
        note.send()
        note.refresh_from_db()

        self.assertEqual(note.number, 1)
        self.assertEqual(ShipmentNote.objects.filter(owner=self.owner, number__isnull=False).count(), 1)

    def test_send_requires_items_and_recipient_names(self):
        with self.assertRaises(ValidationError):
            make_note(self.owner, items=0).send()
        with self.assertRaises(ValidationError):
            make_note(self.owner, names=("João", "")).send()
        self.assertFalse(ShipmentNote.objects.filter(status=ShipmentNote.Status.SENT).exists())

    def test_authorize_keeps_first_timestamp_and_marks_viewed(self):
        note = make_note(self.owner)
        note.send()
        recipient = note.recipients.get(role=ShipmentRecipient.Role.ENCARREGADO)

        self.assertTrue(recipient.authorize())
        first = recipient.authorized_at
        self.assertFalse(recipient.authorize())
        recipient.refresh_from_db()

        self.assertEqual(recipient.authorized_at, first)
        self.assertIsNotNone(recipient.viewed_at)
        self.assertFalse(recipient.mark_viewed())

    def test_situation_labels(self):
        note = make_note(self.owner)
        self.assertEqual(note.situation[0], "Rascunho")
        note.send()
        self.assertEqual(note.situation[0], "Enviada")
        boss, supervisor = note.recipients.order_by("role")
        boss.mark_viewed()
        self.assertEqual(note.situation[0], "Vista 1 de 2")
        boss.authorize()
        supervisor.authorize()
        self.assertEqual(note.situation[0], "Autorizada 2 de 2")

    def test_number_label(self):
        note = make_note(self.owner)
        self.assertEqual(note.number_label, "Rascunho")
        note.number = 7
        self.assertEqual(note.number_label, "0007")
        self.assertEqual(make_note(self.owner, items=3).total_quantity, 6)
