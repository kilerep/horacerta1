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


from django.test import override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def form_data(**extra):
    data = {
        "destination_company": "Ensimec", "departed_at": "2026-11-08T07:30", "driver_name": "Carlos",
        "vehicle_plate": "ABC1D23", "notes": "",
        "item_order": ["OP-501", "OP-502", ""], "item_drawing": ["D-11", "D-12", ""],
        "item_quantity": ["4", "2", ""], "item_description": ["Chapa", "", ""],
        "boss_name": "João", "boss_whatsapp": "11988887777",
        "supervisor_name": "Maria", "supervisor_whatsapp": "11977776666",
    }
    data.update(extra)
    return data


@override_settings(**BASE)
class ShipmentOwnerViewTests(TestCase):
    def setUp(self):
        self.owner = make_user("dono-envio@example.com")
        self.client.force_login(self.owner)

    def _create(self, **extra):
        self.client.post(reverse("shipment_create"), form_data(**extra))
        return ShipmentNote.objects.filter(owner=self.owner).latest("created_at")

    def test_create_draft_with_items_and_recipients(self):
        note = self._create()

        self.assertEqual(note.status, ShipmentNote.Status.DRAFT)
        self.assertEqual(list(note.items.values_list("drawing_number", "quantity")), [("D-11", 4), ("D-12", 2)])
        self.assertEqual(note.recipients.get(role=ShipmentRecipient.Role.SUPERVISOR).name, "Maria")

    def test_send_locks_note(self):
        note = self._create()
        self.client.post(reverse("shipment_send", args=[note.id]))
        note.refresh_from_db()

        self.assertEqual(note.number, 1)
        response = self.client.get(reverse("shipment_edit", args=[note.id]))
        self.assertRedirects(response, reverse("shipment_detail", args=[note.id]))
        self.client.post(reverse("shipment_edit", args=[note.id]), form_data(destination_company="Outra"))
        self.client.post(reverse("shipment_delete", args=[note.id]))
        note.refresh_from_db()
        self.assertEqual(note.destination_company, "Ensimec")
        self.assertEqual(note.items.count(), 2)

    def test_send_without_items_shows_message(self):
        note = self._create(item_order=[""], item_drawing=[""], item_quantity=[""], item_description=[""])
        response = self.client.post(reverse("shipment_send", args=[note.id]), follow=True)

        self.assertContains(response, "Adicione pelo menos um item")
        note.refresh_from_db()
        self.assertIsNone(note.number)

    def test_other_owner_gets_404(self):
        note = self._create()
        self.client.force_login(make_user("intruso-envio@example.com"))

        self.assertEqual(self.client.get(reverse("shipment_detail", args=[note.id])).status_code, 404)

    def test_search_by_drawing_number(self):
        self._create()
        self._create(item_order=["OP-9"], item_drawing=["ZZ-77"], item_quantity=["1"], item_description=[""],
                     destination_company="Metal Sul")

        html = self.client.get(reverse("shipment_list"), {"q": "ZZ-77"}).content.decode()

        self.assertIn("Metal Sul", html)
        self.assertNotIn("Ensimec", html)

    def test_prefill_from_last_sent_note(self):
        note = self._create()
        self.client.post(reverse("shipment_send", args=[note.id]))

        html = self.client.get(reverse("shipment_create")).content.decode()

        self.assertIn('value="Ensimec"', html)
        self.assertIn('value="Maria"', html)

    def test_whatsapp_redirect_contains_recipient_token(self):
        note = self._create()
        self.client.post(reverse("shipment_send", args=[note.id]))
        boss = note.recipients.get(role=ShipmentRecipient.Role.ENCARREGADO)

        response = self.client.get(reverse("shipment_whatsapp", args=[note.id, "encarregado"]))

        self.assertTrue(response["Location"].startswith("https://wa.me/5511988887777?text="))
        self.assertIn(str(boss.token), response["Location"])

    def test_replace_creates_draft_pointing_to_original(self):
        note = self._create()
        self.client.post(reverse("shipment_send", args=[note.id]))

        self.client.post(reverse("shipment_replace", args=[note.id]))
        copy = ShipmentNote.objects.filter(owner=self.owner, status=ShipmentNote.Status.DRAFT).get()

        self.assertEqual(copy.replaces, note)
        self.assertEqual(copy.items.count(), 2)
        self.assertEqual(copy.recipients.count(), 2)

    def test_sheet_list_shows_tabs(self):
        html = self.client.get(reverse("production_sheet_list")).content.decode()

        self.assertIn(reverse("shipment_list"), html)
        self.assertIn("Notas de envio", html)
