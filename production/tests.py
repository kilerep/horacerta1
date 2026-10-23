import json
import shutil
import subprocess
from datetime import date, time
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .forms import parse_duration
from .models import ProductionEntry, ProductionSheet

BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)


def make_user(email, **extra):
    return User.objects.create_user(username=email, email=email, password="x-Senha-123456",
                                    role=User.Role.FUNCIONARIO, **extra)


class ParseDurationTests(SimpleTestCase):
    def test_accepts_the_ways_people_write_hours(self):
        for text, minutes in (("4", 240), ("4h", 240), ("1:30", 90), ("1h30", 90), ("1,5", 90),
                              ("0:45", 45), ("90min", 90), ("", None), ("  ", None)):
            with self.subTest(text=text):
                self.assertEqual(parse_duration(text), minutes)

    def test_rejects_nonsense(self):
        from django import forms

        for text in ("abc", "1:75", "-2"):
            with self.subTest(text=text):
                with self.assertRaises(forms.ValidationError):
                    parse_duration(text)


class DurationAndTotalsTests(TestCase):
    def setUp(self):
        self.sheet = ProductionSheet.objects.create(owner=make_user("t@example.com"), equipment="Chenlong")

    def _entry(self, **kw):
        return ProductionEntry.objects.create(sheet=self.sheet, **kw)

    def test_duration_from_times_manual_and_overnight(self):
        self.assertEqual(self._entry(start_time=time(7, 30), end_time=time(11, 30)).duration_label, "4:00")
        self.assertEqual(self._entry(manual_minutes=90).duration_label, "1:30")
        self.assertEqual(self._entry(start_time=time(22, 0), end_time=time(1, 30)).duration_minutes, 210)
        running = self._entry(start_time=time(14, 0))
        self.assertIsNone(running.duration_minutes)
        self.assertTrue(running.is_running)

    def test_paper_sheet_example_totals_by_destination(self):
        G, I = ProductionEntry.Destination.GUINCHO, ProductionEntry.Destination.IMPLEMENTO
        self._entry(work_date=date(2026, 9, 23), item_code="0011-024", destination=I, start_time=time(7, 0), end_time=time(11, 0))
        self._entry(work_date=date(2026, 10, 1), item_code="0011-031", destination=G, start_time=time(13, 0), end_time=time(14, 30))
        self._entry(work_date=date(2026, 10, 5), destination=I, manual_minutes=180)
        self._entry(work_date=date(2026, 10, 8), destination=G, manual_minutes=60)
        self._entry(work_date=date(2026, 10, 8), start_time=time(15, 0))  # ainda sem fim

        totals = self.sheet.totals()

        self.assertEqual(totals["total"], 240 + 90 + 180 + 60)
        self.assertEqual(totals[G], 150)
        self.assertEqual(totals[I], 420)
        self.assertEqual(totals["pending"], 1)
        self.assertEqual(self.sheet.date_range(), (date(2026, 9, 23), date(2026, 10, 8)))


@override_settings(**BASE)
class ProductionFlowTests(TestCase):
    def setUp(self):
        self.user = make_user("op@example.com", first_name="Fagner", last_name="Santos")
        self.client.force_login(self.user)

    def _create_sheet(self, **data):
        payload = {"equipment": "Chenlong", "company_name": "", "operator_name": "Fagner", "notes": ""}
        payload.update(data)
        self.client.post(reverse("production_sheet_create"), payload)
        return ProductionSheet.objects.get(owner=self.user, equipment=payload["equipment"])

    def test_menu_has_the_new_tab(self):
        html = self.client.get(reverse("employee_dashboard"), follow=True).content.decode()

        self.assertIn(reverse("production_sheet_list"), html)
        self.assertIn("Relatórios de produção", html)

    def test_new_report_prefills_the_operator_and_suggests_previous_machines(self):
        self._create_sheet(equipment="Lippel")

        html = self.client.get(reverse("production_sheet_create")).content.decode()

        self.assertIn('value="Fagner Santos"', html)
        self.assertIn('<option value="Lippel">', html)

    def test_create_report_then_add_items_like_the_paper_sheet(self):
        sheet = self._create_sheet(company_name="Empresa X")
        url = reverse("production_sheet_detail", args=[sheet.id])

        self.client.post(url, {"work_date": "2026-10-20", "item_code": "0011-024", "destination": "IMPLEMENTO",
                               "start_time": "07:00", "end_time": "11:00"})
        self.client.post(url, {"work_date": "2026-10-20", "destination": "GUINCHO", "duration": "1:30"})
        response = self.client.get(url)

        self.assertContains(response, "0011-024")
        self.assertContains(response, "<strong>5:30</strong>", html=False)
        self.assertContains(response, "<span>Guincho</span><strong>1:30</strong>", html=False)
        self.assertContains(response, "<span>Implemento</span><strong>4:00</strong>", html=False)

    def test_start_now_finish_later(self):
        sheet = self._create_sheet()
        url = reverse("production_sheet_detail", args=[sheet.id])
        self.client.post(url, {"work_date": "2026-10-20", "item_code": "A-1", "start_time": "08:00"})
        entry = sheet.entries.get()

        self.assertContains(self.client.get(url), "Anotar fim")
        self.client.post(reverse("production_entry_edit", args=[sheet.id, entry.id]),
                         {"work_date": "2026-10-20", "item_code": "A-1", "start_time": "08:00", "end_time": "09:15"})
        entry.refresh_from_db()

        self.assertEqual(entry.duration_label, "1:15")

    def test_validation_messages(self):
        sheet = self._create_sheet()
        url = reverse("production_sheet_detail", args=[sheet.id])

        empty = self.client.post(url, {"work_date": "2026-10-20"})
        only_end = self.client.post(url, {"work_date": "2026-10-20", "item_code": "B", "end_time": "10:00"})
        bad = self.client.post(url, {"work_date": "2026-10-20", "item_code": "B", "duration": "abc"})

        self.assertContains(empty, "Preencha pelo menos o código do item")
        self.assertContains(only_end, "Informe o início")
        self.assertContains(bad, "Use horas como")
        self.assertEqual(sheet.entries.count(), 0)

    def test_times_win_over_typed_duration(self):
        sheet = self._create_sheet()
        self.client.post(reverse("production_sheet_detail", args=[sheet.id]),
                         {"work_date": "2026-10-20", "start_time": "07:00", "end_time": "08:00", "duration": "5"})

        entry = sheet.entries.get()
        self.assertIsNone(entry.manual_minutes)
        self.assertEqual(entry.duration_minutes, 60)

    def test_close_blocks_changes_and_reopen_allows_them(self):
        sheet = self._create_sheet()
        url = reverse("production_sheet_detail", args=[sheet.id])
        self.client.post(reverse("production_sheet_status", args=[sheet.id]), {"action": "close"})

        self.client.post(url, {"work_date": "2026-10-20", "item_code": "C"})
        self.assertEqual(sheet.entries.count(), 0)
        self.assertNotContains(self.client.get(url), 'id="new-entry"')

        self.client.post(reverse("production_sheet_status", args=[sheet.id]), {"action": "reopen"})
        self.client.post(url, {"work_date": "2026-10-20", "item_code": "C"})
        self.assertEqual(sheet.entries.count(), 1)

    def test_delete_item(self):
        sheet = self._create_sheet()
        entry = ProductionEntry.objects.create(sheet=sheet, item_code="D")

        self.assertEqual(self.client.get(reverse("production_entry_delete", args=[sheet.id, entry.id])).status_code, 405)
        self.client.post(reverse("production_entry_delete", args=[sheet.id, entry.id]))

        self.assertFalse(sheet.entries.exists())

    def test_csv_export_has_rows_and_totals(self):
        sheet = self._create_sheet(company_name="Empresa X")
        ProductionEntry.objects.create(sheet=sheet, work_date=date(2026, 10, 20), item_code="0011-024",
                                       destination="IMPLEMENTO", start_time=time(7, 0), end_time=time(11, 0))

        response = self.client.get(reverse("production_sheet_csv", args=[sheet.id]))
        text = response.content.decode("utf-8-sig")

        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("20/10/2026;0011-024;Implemento;07:00;11:00;4:00", text)
        self.assertIn("Implemento;;;;;4:00", text)
        self.assertIn("Empresa;Empresa X", text)

    def test_list_separates_open_and_closed(self):
        open_sheet = self._create_sheet(equipment="Chenlong")
        closed = self._create_sheet(equipment="Lippel")
        closed.close()
        closed.save()

        html = self.client.get(reverse("production_sheet_list")).content.decode()

        self.assertLess(html.index("Chenlong"), html.index("Relatórios fechados"))
        self.assertGreater(html.index("Lippel"), html.index("Relatórios fechados"))
        self.assertTrue(open_sheet.is_open)


@override_settings(**BASE)
class ProductionPhaseTwoTests(TestCase):
    """Fase 2: enviar pelo WhatsApp ao encarregado e anotar o item falando."""

    def setUp(self):
        self.user = make_user("fase2@example.com", first_name="Fagner")
        self.client.force_login(self.user)

    def _sheet(self, **extra):
        data = {"equipment": "Chenlong", "company_name": "Empresa X", "operator_name": "Fagner"}
        data.update(extra)
        return ProductionSheet.objects.create(owner=self.user, **data)

    def test_whatsapp_goes_to_the_supervisor_with_items_and_totals(self):
        sheet = self._sheet(supervisor_name="Carlos", supervisor_whatsapp="11988887777")
        ProductionEntry.objects.create(sheet=sheet, work_date=date(2026, 10, 20), item_code="0011-024",
                                       destination="IMPLEMENTO", start_time=time(7, 0), end_time=time(11, 0))
        ProductionEntry.objects.create(sheet=sheet, work_date=date(2026, 10, 21), destination="GUINCHO", manual_minutes=90)

        response = self.client.get(reverse("production_sheet_whatsapp", args=[sheet.id]))
        location = response["Location"]
        from urllib.parse import unquote

        text = unquote(location.split("text=", 1)[1])
        self.assertEqual(response.status_code, 302)
        self.assertTrue(location.startswith("https://wa.me/5511988887777?text="))
        self.assertIn("Relatório de produção - Chenlong", text)
        self.assertIn("20/10 · 0011-024 · Implemento · 07:00-11:00 · 4:00", text)
        self.assertIn("Período: 20/10 a 21/10", text)
        self.assertIn("*Total: 5:30* (Guincho 1:30 | Implemento 4:00)", text)

    def test_whatsapp_without_number_lets_the_person_pick_the_contact(self):
        sheet = self._sheet()

        response = self.client.get(reverse("production_sheet_whatsapp", args=[sheet.id]))

        self.assertTrue(response["Location"].startswith("https://wa.me/?text="))

    def test_new_report_remembers_the_last_supervisor(self):
        self._sheet(supervisor_name="Carlos", supervisor_whatsapp="11988887777")

        html = self.client.get(reverse("production_sheet_create")).content.decode()

        self.assertIn('value="Carlos"', html)
        self.assertIn('value="11988887777"', html)

    def test_edit_report_saves_supervisor_phone_as_digits(self):
        sheet = self._sheet()

        self.client.post(reverse("production_sheet_edit", args=[sheet.id]), {
            "equipment": "Chenlong", "company_name": "Empresa X", "operator_name": "Fagner",
            "supervisor_name": "Carlos", "supervisor_whatsapp": "(11) 98888-7777", "notes": "",
        })
        bad = self.client.post(reverse("production_sheet_edit", args=[sheet.id]), {
            "equipment": "Chenlong", "supervisor_whatsapp": "123",
        })
        sheet.refresh_from_db()

        self.assertEqual(sheet.supervisor_whatsapp, "11988887777")
        self.assertContains(bad, "Use o número com DDD")

    def test_detail_has_voice_button_whatsapp_and_edit(self):
        sheet = self._sheet(supervisor_name="Carlos")

        html = self.client.get(reverse("production_sheet_detail", args=[sheet.id])).content.decode()

        self.assertIn("data-voice-entry", html)
        self.assertIn("js/production_voice.js", html)
        self.assertIn("Enviar pelo WhatsApp para Carlos", html)
        self.assertIn(reverse("production_sheet_edit", args=[sheet.id]), html)

    def test_other_user_cannot_send_or_edit(self):
        sheet = self._sheet()
        self.client.force_login(make_user("intruso@example.com"))

        for name in ("production_sheet_whatsapp", "production_sheet_edit"):
            self.assertEqual(self.client.get(reverse(name, args=[sheet.id])).status_code, 404)


@skipUnless(shutil.which("node"), "node nao instalado")
class VoiceParserTests(SimpleTestCase):
    """Roda o leitor de fala (static/js/production_voice.js) no node com frases reais."""

    def test_spoken_sentences_fill_the_right_fields(self):
        script = Path(settings.BASE_DIR) / "static/js/production_voice.js"
        cases = [
            ["código 0011 024 implemento das 7 às 11", {"code": "0011-024", "destination": "IMPLEMENTO", "start": "07:00", "end": "11:00"}],
            ["guincho uma hora e meia", {"destination": "GUINCHO", "duration": "1:30", "code": ""}],
            ["código X 123 guincho comecei agora", {"code": "X 123", "start": "14:05", "end": ""}],
            ["de sete e meia até onze e quinze implemento", {"start": "07:30", "end": "11:15"}],
            ["item 13 guincho 2h30", {"code": "13", "duration": "2:30"}],
            ["peça quebrou no meio", {"code": "", "note": "peça quebrou no meio"}],
            ["código 55 implemento 2 horas obs faltou material", {"code": "55", "duration": "2:00", "note": "faltou material"}],
        ]
        program = (
            "const v=require(process.argv[1]);const now=new Date(2026,9,22,14,5);"
            "const cases=JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(cases.map(c=>v.parse(c[0],now))));"
        )
        out = subprocess.run(["node", "-e", program, str(script), json.dumps(cases)],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        for (text, expected), got in zip(cases, json.loads(out)):
            for key, value in expected.items():
                with self.subTest(text=text, field=key):
                    self.assertEqual(got[key], value)


@override_settings(**BASE)
class ProductionIsolationTests(TestCase):
    def test_another_user_cannot_see_or_change_my_report(self):
        owner = make_user("dono@example.com")
        sheet = ProductionSheet.objects.create(owner=owner, equipment="Chenlong")
        entry = ProductionEntry.objects.create(sheet=sheet, item_code="SEGREDO")
        other = make_user("outro@example.com")
        self.client.force_login(other)

        for method, url in (
            ("get", reverse("production_sheet_detail", args=[sheet.id])),
            ("get", reverse("production_sheet_csv", args=[sheet.id])),
            ("get", reverse("production_entry_edit", args=[sheet.id, entry.id])),
            ("post", reverse("production_entry_delete", args=[sheet.id, entry.id])),
            ("post", reverse("production_sheet_status", args=[sheet.id])),
        ):
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 404)
        self.assertNotIn("SEGREDO", self.client.get(reverse("production_sheet_list")).content.decode())
        self.assertTrue(ProductionEntry.objects.filter(id=entry.id).exists())

    def test_login_required(self):
        response = self.client.get(reverse("production_sheet_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
