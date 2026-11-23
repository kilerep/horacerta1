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

    def test_items_from_two_machines_go_to_the_same_draft_by_default(self):
        """2026-11-23: selecionar na Chenlong, depois na Lippel, e tudo cair no MESMO romaneio."""
        lippel = ProductionSheet.objects.create(owner=self.owner, equipment="Lippel")
        other = ProductionEntry.objects.create(sheet=lippel, item_code="0128-208", quantity=10, production_order="7542.1",
                                               manual_minutes=30)
        self.client.post(self.url, {"entry": [self.entry.id], "target": "new"})
        draft = ShipmentNote.objects.get(owner=self.owner, status=ShipmentNote.Status.DRAFT)

        html = self.client.get(reverse("production_sheet_detail", args=[lippel.id])).content.decode()
        self.assertIn("Romaneio em montagem", html)
        self.assertIn(f'<option value="{draft.id}" selected>Continuar romaneio', html)
        self.assertLess(html.index(f'value="{draft.id}"'), html.index('value="new"'))  # "Novo" deixa de ser o padrao

        self.client.post(reverse("shipment_from_entries", args=[lippel.id]), {"entry": [other.id], "target": str(draft.id)})
        self.assertEqual(ShipmentNote.objects.filter(owner=self.owner, status=ShipmentNote.Status.DRAFT).count(), 1)
        self.assertEqual(draft.items.count(), 2)

    def test_most_recently_used_draft_is_the_default(self):
        old = ShipmentNote.objects.create(owner=self.owner, destination_company="Antigo")
        recent = ShipmentNote.objects.create(owner=self.owner, destination_company="Recente")
        self.client.post(self.url, {"entry": [self.entry.id], "target": str(old.id)})  # usar o antigo o torna o atual

        html = self.client.get(reverse("production_sheet_detail", args=[self.entry.sheet_id])).content.decode()
        self.assertIn(f'<option value="{old.id}" selected>', html)
        self.assertNotIn(f'<option value="{recent.id}" selected>', html)

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


@override_settings(**BASE)
class RomaneioNameTests(TestCase):
    def test_visible_name_is_romaneio(self):
        from production.shipment_exports import build_shipment_pdf, shipment_filename

        owner = make_user("nome-romaneio@example.com")
        self.client.force_login(owner)
        note = sent_note_with(make_entry(owner), 5)
        token = note.recipients.first().token
        pages = [self.client.get(reverse(name, args=args)).content.decode() for name, args in (
            ("shipment_list", []), ("shipment_detail", [note.id]), ("shipment_create", []),
            ("production_sheet_list", []),
        )]
        self.client.logout()
        pages.append(self.client.get(reverse("shipment_public", args=[token])).content.decode())

        for html in pages:
            self.assertIn("omaneio", html)
            self.assertNotRegex(html, r"\b[Nn]otas? de envio\b")
        self.assertEqual(shipment_filename(note, "pdf"), "romaneio-0001-gbach.pdf")
        self.assertTrue(build_shipment_pdf(note).startswith(b"%PDF"))


@override_settings(**BASE)
class LoadedConfirmationTests(TestCase):
    """2026-11-15: o romaneio registra quando a carga foi conferida e carregada (automatico, travado),
    nao a saida do caminhao, e traz o termo de entrega."""

    def setUp(self):
        self.owner = make_user("carregado@example.com")
        self.client.force_login(self.owner)

    def test_form_has_no_departure_input_and_send_button_confirms_loading(self):
        create = self.client.get(reverse("shipment_create")).content.decode()
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="Gbach")
        detail = self.client.get(reverse("shipment_detail", args=[draft.id])).content.decode()

        self.assertNotIn('name="departed_at"', create)
        self.assertIn("Carga conferida e carregada", detail)

    def test_send_records_loaded_time_automatically(self):
        from datetime import datetime

        from django.utils import timezone

        note = sent_note_with(make_entry(self.owner), 3)
        note.refresh_from_db()

        self.assertEqual(note.loaded_at, note.sent_at)
        self.assertEqual(note.departed_at, note.sent_at)
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="X",
                                            departed_at=timezone.make_aware(datetime(2020, 1, 1)))
        self.assertIsNone(draft.loaded_at)

    def test_delivery_term_in_public_page_and_files(self):
        from io import BytesIO

        from openpyxl import load_workbook

        from production.shipment_exports import build_shipment_xlsx, delivery_term

        note = sent_note_with(make_entry(self.owner), 3)
        note.driver_name, note.vehicle_plate = "Carlos", "RTX4B21"
        note.save()
        term = delivery_term(note)
        self.client.logout()
        html = self.client.get(reverse("shipment_public", args=[note.recipients.first().token])).content.decode()
        ws = load_workbook(BytesIO(build_shipment_xlsx(note))).active
        cells = " ".join(str(c) for row in ws.iter_rows(values_only=True) for c in row if c)

        self.assertIn("foram conferidas e carregadas em", term)
        self.assertIn("sob responsabilidade de carregado", term)
        self.assertIn("motorista Carlos (placa RTX4B21)", term)
        self.assertIn("foram conferidas e carregadas em", html)
        self.assertIn("foram conferidas e carregadas em", cells)
        self.assertNotIn("Saída do caminhão", html)


@override_settings(**BASE)
class ItemSearchTests(TestCase):
    """2026-11-17: 'quando o 8210-120 foi cortado?' - busca de item na producao e nos romaneios."""

    def setUp(self):
        self.owner = make_user("busca@example.com")
        self.client.force_login(self.owner)
        self.first = make_entry(self.owner, code="8210-120", quantity=10, order="7542.1")
        self.second = make_entry(self.owner, code="8210-120", quantity=5, order="7600.2")
        self.other = make_entry(self.owner, code="0128-208", quantity=3, order="1111.1")

    def _search(self, q):
        return self.client.get(reverse("production_item_search"), {"q": q}).content.decode()

    def test_shows_how_many_times_and_pieces(self):
        html = self._search("8210-120")

        self.assertIn("Cortado 2 vezes", html)
        self.assertIn("15 peças", html)
        self.assertIn("7542.1", html)
        self.assertIn("7600.2", html)
        self.assertNotIn("0128-208", html)

    def test_partial_code_and_production_order_match(self):
        self.assertIn("8210-120", self._search("8210"))
        self.assertIn("0128-208", self._search("1111"))

    def test_shows_sent_romaneios_but_not_drafts(self):
        sent = sent_note_with(self.first, 6)
        draft = ShipmentNote.objects.create(owner=self.owner, destination_company="Rascunho Ltda")
        ShipmentItem.objects.create(note=draft, drawing_number="8210-120", quantity=1, source_entry=self.first)

        html = self._search("8210-120")

        self.assertIn(f"nº {sent.number_label}", html)
        self.assertIn("Gbach", html)
        self.assertIn("Enviado em 1 romaneio", html)
        self.assertNotIn("Rascunho Ltda", html)

    def test_only_own_items_and_empty_states(self):
        make_entry(make_user("alheio-busca@example.com"), code="9999-ALHEIO")

        self.assertIn("Nenhum item encontrado", self._search("9999"))
        self.assertIn("Digite o código", self._search(""))

    def test_search_box_on_production_list(self):
        html = self.client.get(reverse("production_sheet_list")).content.decode()

        self.assertIn(reverse("production_item_search"), html)


@override_settings(**BASE)
class ItemHistoryPdfTests(TestCase):
    """2026-11-17: historico do item em PDF para mandar quando alguem perguntar."""

    def setUp(self):
        self.owner = make_user("historico@example.com")
        self.client.force_login(self.owner)
        self.entry = make_entry(self.owner, code="8210-120", quantity=10, order="7542.1")
        make_entry(self.owner, code="8210-1200", quantity=4, order="9")
        sent_note_with(self.entry, 6)

    def test_pdf_for_exact_item(self):
        from production.item_history import build_item_history_pdf, item_groups

        groups = item_groups(self.owner, "8210-120", exact=True)
        self.assertEqual([g["code"] for g in groups], ["8210-120"])
        self.assertEqual((len(groups[0]["cuts"]), groups[0]["sent_pieces"]), (1, 6))
        self.assertTrue(build_item_history_pdf(self.owner, "8210-120", groups).startswith(b"%PDF"))

        response = self.client.get(reverse("production_item_history_pdf"), {"q": "8210-120"})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("historico-8210-120", response["Content-Disposition"])

    def test_search_page_links_the_pdf_and_other_owner_gets_nothing(self):
        html = self.client.get(reverse("production_item_search"), {"q": "8210"}).content.decode()
        self.assertIn(reverse("production_item_history_pdf") + "?q=8210-120", html)

        self.client.force_login(make_user("outro-historico@example.com"))
        response = self.client.get(reverse("production_item_history_pdf"), {"q": "8210-120"})
        self.assertEqual(response.status_code, 404)


@override_settings(**BASE)
class SameItemTwoMachinesTests(TestCase):
    """2026-11-23: o mesmo item cortado na Lippel e na Chenlong vira 1 linha no romaneio."""

    def setUp(self):
        self.owner = make_user("duas-maquinas@example.com")
        self.client.force_login(self.owner)
        self.chen = make_entry(self.owner, code="0128-208", quantity=5, order="7542.1")
        lippel = ProductionSheet.objects.create(owner=self.owner, equipment="Lippel")
        self.lip = ProductionEntry.objects.create(sheet=lippel, item_code="0128-208", quantity=10,
                                                  production_order="7542.1", manual_minutes=30)
        self.other = make_entry(self.owner, code="9999-1", quantity=2, order="1.1")
        self.client.post(reverse("shipment_from_entries", args=[lippel.id]), {"entry": [self.lip.id], "target": "new"})
        self.note = ShipmentNote.objects.get(owner=self.owner, status=ShipmentNote.Status.DRAFT)
        self.client.post(reverse("shipment_from_entries", args=[self.chen.sheet_id]),
                         {"entry": [self.chen.id, self.other.id], "target": str(self.note.id)})

    def test_grouped_line_with_both_machines(self):
        groups = self.note.grouped_items()
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["quantity"], 15)
        self.assertEqual(groups[0]["machines_label"], "Lippel 10 + Chenlong 5")
        self.assertEqual(groups[1]["machines_label"], "")  # item de uma maquina so nao ganha explicacao

    def test_documents_show_the_grouped_line(self):
        from production.shipment_exports import item_rows

        rows = item_rows(self.note)
        self.assertEqual(rows[0], ("7542.1", "0128-208", "Lippel 10 + Chenlong 5", 15))
        html = self.client.get(reverse("shipment_detail", args=[self.note.id])).content.decode()
        self.assertIn("Lippel 10 + Chenlong 5", html)

    def test_each_machine_still_tracks_what_was_shipped(self):
        self.assertEqual(self.note.items.count(), 3)  # no banco continuam separados
        self.assertEqual(set(self.note.items.values_list("source_entry", flat=True)), {self.chen.id, self.lip.id, self.other.id})

    def test_editing_the_draft_keeps_the_machine_link(self):
        edit = reverse("shipment_edit", args=[self.note.id])
        html = self.client.get(edit).content.decode()
        self.assertIn("Cortado na Lippel", html)
        items = list(self.note.items.order_by("position"))
        self.client.post(edit, {
            "destination_company": "Gbach",
            "item_order": [i.production_order for i in items],
            "item_drawing": [i.drawing_number for i in items],
            "item_quantity": ["8", "5", "2"],  # ajustou a quantidade da Lippel
            "item_description": ["", "", ""],
            "item_source": [str(i.source_entry_id) for i in items],
        })
        self.assertEqual(set(self.note.items.values_list("source_entry", flat=True)), {self.chen.id, self.lip.id, self.other.id})
        self.assertEqual(self.note.grouped_items()[0]["machines_label"], "Lippel 8 + Chenlong 5")

    def test_cannot_link_line_to_someone_elses_entry(self):
        intruder = make_entry(make_user("intruso-maquina@example.com"), code="ALHEIO")
        self.client.post(reverse("shipment_edit", args=[self.note.id]), {
            "destination_company": "Gbach", "item_order": ["1"], "item_drawing": ["X"], "item_quantity": ["1"],
            "item_description": [""], "item_source": [str(intruder.id)],
        })
        self.assertIsNone(self.note.items.get().source_entry_id)

    def test_search_shows_both_machines_and_where_each_shipment_came_from(self):
        ShipmentRecipient.objects.create(note=self.note, role=ShipmentRecipient.Role.ENCARREGADO, name="João")
        self.note.send()
        html = self.client.get(reverse("production_item_search"), {"q": "0128-208"}).content.decode()
        self.assertIn("Lippel", html)
        self.assertIn("Chenlong", html)
        self.assertIn("Cortado na Lippel", html)
        self.assertIn("Cortado na Chenlong", html)
