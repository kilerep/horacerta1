"""2026-11-22: avisos no celular (notificacao push / Web Push).

O envio de verdade (pywebpush) e trocado por um dublê: os testes conferem quem recebe,
o que recebe e que nada sai quando o recurso esta desligado ou o aviso e do proprio usuario.
"""

import json
import uuid
from datetime import date, time
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import PushSubscription
from accounts.push import send_push_to_user
from companies.models import Company, Employee
from services.models import ServiceCategory, ServiceJob
from timeclock.models import Contract, InternalNotification, Punch

User = get_user_model()
BASE = dict(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
KEYS = dict(VAPID_PUBLIC_KEY="BPub-chave-de-teste", VAPID_PRIVATE_KEY="priv-chave-de-teste",
            VAPID_SUBJECT="https://horacertagestao.com.br")
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123", "keys": {"p256dh": "BKey", "auth": "AuthKey"}}


def make_user(email):
    return User.objects.create_user(username=email, email=email, password="Teste@12345", role=User.Role.FUNCIONARIO)


class FakePushError(Exception):
    def __init__(self, status):
        super().__init__(f"push {status}")
        self.response = SimpleNamespace(status_code=status)


@override_settings(**BASE, **KEYS)
class PushBase(TestCase):
    def setUp(self):
        self.user = make_user("push@example.com")
        self.company = Company.objects.create(owner=self.user, name="Ensimec", email="cli-push@example.com")
        self.employee = Employee.objects.create(user=self.user, company=self.company, full_name="Fagner", is_active=True)
        self.contract = Contract.objects.create(company=self.company, employee=self.employee,
                                                hourly_rate=Decimal("50.00"), start_date=date(2025, 1, 1), is_active=True)
        self.client.force_login(self.user)
        patcher = mock.patch("accounts.push._webpush")
        self.webpush = patcher.start()
        self.addCleanup(patcher.stop)

    def subscribe(self, user=None, endpoint=SUB["endpoint"]):
        return PushSubscription.objects.create(user=user or self.user, endpoint=endpoint, p256dh="BKey", auth="AuthKey")

    def sent_payloads(self):
        return [json.loads(call.kwargs["data"]) for call in self.webpush.call_args_list]


class SubscribeTests(PushBase):
    def test_subscribe_saves_device_and_status_says_available(self):
        response = self.client.post(reverse("register_push"), data=json.dumps(SUB), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        sub = PushSubscription.objects.get(user=self.user)
        self.assertEqual(sub.endpoint, SUB["endpoint"])
        self.assertTrue(self.client.get(reverse("pwa_status")).json()["push_notifications_available"])

    def test_same_device_twice_keeps_one_row(self):
        for _ in range(2):
            self.client.post(reverse("register_push"), data=json.dumps(SUB), content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_rejects_incomplete_or_non_https_subscription(self):
        for bad in ({"endpoint": "http://x.test/a", "keys": SUB["keys"]}, {"endpoint": SUB["endpoint"]}, ["lista"]):
            response = self.client.post(reverse("register_push"), data=json.dumps(bad), content_type="application/json")
            self.assertEqual(response.status_code, 400, bad)
        self.assertFalse(PushSubscription.objects.exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse("register_push"), data=json.dumps(SUB), content_type="application/json")
        self.assertEqual(response.status_code, 302)

    def test_unsubscribe_only_removes_own_device(self):
        other = make_user("outro@example.com")
        self.subscribe(user=other, endpoint="https://fcm.googleapis.com/fcm/send/outro")
        self.subscribe()

        self.client.post(reverse("unregister_push"), data=json.dumps({"endpoint": "https://fcm.googleapis.com/fcm/send/outro"}),
                         content_type="application/json")
        self.assertTrue(PushSubscription.objects.filter(user=other).exists())

        self.client.post(reverse("unregister_push"), data=json.dumps({"endpoint": SUB["endpoint"]}),
                         content_type="application/json")
        self.assertFalse(PushSubscription.objects.filter(user=self.user).exists())

    def test_profile_shows_panel_and_test_button_sends(self):
        html = self.client.get(reverse("mei_profile")).content.decode()
        self.assertIn("Avisos no celular", html)
        self.assertIn('data-push-key="BPub-chave-de-teste"', html)

        self.subscribe()
        response = self.client.post(reverse("push_test"))
        self.assertEqual(response.json()["sent"], 1)
        self.assertEqual(self.sent_payloads()[0]["title"], "HoraCerta")

    def test_only_the_right_button_shows(self):
        """[hidden] precisa valer mesmo com o estilo .btn (antes os 3 botoes apareciam sempre)."""
        html = self.client.get(reverse("mei_profile")).content.decode()
        self.assertIn("[data-push-panel] [hidden]{display:none!important}", html)
        self.assertRegex(html, r"data-push-try hidden")

    def test_client_error_is_logged(self):
        with self.assertLogs("accounts.pwa", level="WARNING") as logs:
            response = self.client.post(reverse("push_client_error"),
                                        data=json.dumps({"stage": "ativar", "error": "AbortError: push service error"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AbortError: push service error", logs.output[0])

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_without_keys_feature_is_off(self):
        response = self.client.post(reverse("register_push"), data=json.dumps(SUB), content_type="application/json")
        self.assertEqual(response.status_code, 501)
        self.assertIn("ainda não estão ligados", self.client.get(reverse("mei_profile")).content.decode())
        self.subscribe()
        self.assertEqual(send_push_to_user(self.user, title="x"), 0)
        self.webpush.assert_not_called()


class SendTests(PushBase):
    def test_gone_device_is_removed_and_other_errors_kept(self):
        self.subscribe()
        self.subscribe(endpoint="https://fcm.googleapis.com/fcm/send/segundo")
        self.webpush.side_effect = [FakePushError(410), FakePushError(500)]

        self.assertEqual(send_push_to_user(self.user, title="Oi"), 0)

        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_success_marks_last_success(self):
        sub = self.subscribe()
        self.assertEqual(send_push_to_user(self.user, title="Oi", body="Corpo", url="/me/"), 1)
        sub.refresh_from_db()
        self.assertIsNotNone(sub.last_success_at)
        self.assertEqual(self.sent_payloads()[0]["data"]["url"], "/me/")

    def test_bell_notification_without_push_flag_does_not_reach_phone(self):
        from timeclock.notifications import create_internal_notification

        self.subscribe()
        with self.captureOnCommitCallbacks(execute=True):
            create_internal_notification(notification_type=InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
                                         title="Período fechado", message="x", recipient_user=self.user)
        self.webpush.assert_not_called()


class EventTests(PushBase):
    """Os 5 avisos combinados com o Fagner chegam no celular."""

    def setUp(self):
        super().setUp()
        self.subscribe()

    def test_1_client_opened_quote_preview(self):
        category = ServiceCategory.objects.get(slug="eletrica")
        job = ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=category, title="Troca de chuveiro",
            status=ServiceJob.Status.PLANNED, start_date=timezone.localdate(),
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("50.00"),
            preview_generated_at=timezone.now(),
        )
        url = reverse("public_service_job_preview", args=[job.public_token])

        self.client.get(url)  # o proprio prestador abrindo: nao avisa
        self.webpush.assert_not_called()

        self.client.logout()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get(url)
            self.client.get(url)  # segunda vez: nao repete

        payloads = self.sent_payloads()
        self.assertEqual(len(payloads), 1)
        self.assertIn("abriu o orçamento", payloads[0]["title"])
        self.assertTrue(InternalNotification.objects.filter(recipient_user=self.user, title__contains="orçamento").exists())

    def test_2_shipment_seen_or_authorized(self):
        from production.shipment_views import _notify_owner

        note = SimpleNamespace(id=uuid.uuid4(), owner=self.user, number_label="12", destination_company="Ensimec")
        with self.captureOnCommitCallbacks(execute=True):
            _notify_owner(SimpleNamespace(note=note, name="Carlos"), "autorizado")

        self.assertEqual(self.sent_payloads()[0]["title"], "Romaneio nº 12 autorizado por Carlos")

    def test_3_daily_agenda_at_7(self):
        category = ServiceCategory.objects.get(slug="eletrica")
        ServiceJob.objects.create(
            professional=self.user, contract=self.contract, category=category, title="Instalar tomada",
            status=ServiceJob.Status.PLANNED, start_date=timezone.localdate(), planned_start_time=time(8, 0),
            billing_mode=ServiceJob.BillingMode.HOURLY, hourly_rate_snapshot=Decimal("50.00"),
        )
        with self.captureOnCommitCallbacks(execute=True):
            call_command("push_lembretes", "--agenda", stdout=StringIO())
            call_command("push_lembretes", "--agenda", stdout=StringIO())  # nao repete no mesmo dia

        payloads = self.sent_payloads()
        self.assertEqual(len(payloads), 1)
        self.assertIn("você tem 1 serviço", payloads[0]["title"])
        self.assertIn("08:00 Instalar tomada", payloads[0]["body"])

    def test_4_open_entry_reminder_at_19(self):
        out = StringIO()
        call_command("push_lembretes", "--saida", stdout=out)
        self.webpush.assert_not_called()  # sem entrada aberta

        Punch.objects.create(contract=self.contract)
        call_command("push_lembretes", "--saida", stdout=out)
        payload = self.sent_payloads()[0]
        self.assertEqual(payload["title"], "Você ainda está trabalhando?")
        self.assertIn("Ensimec", payload["body"])

        Punch.objects.create(contract=self.contract)  # saiu: par fechado
        self.webpush.reset_mock()
        call_command("push_lembretes", "--saida", stdout=out)
        self.webpush.assert_not_called()

    def test_5_report_opened_and_answered_by_client(self):
        from accounts.views._shared import _notify_service_report_client_response, _notify_service_report_viewed

        report = SimpleNamespace(pk=1, id=uuid.uuid4(), employee=self.employee, company=self.company,
                                 conference_first_viewed_at=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            _notify_service_report_viewed(report)
            _notify_service_report_client_response(report, contested=False)

        titles = [p["title"] for p in self.sent_payloads()]
        self.assertEqual(titles, ["Relatório visualizado", "Cliente confirmou o recebimento"])

    def test_other_users_device_never_gets_my_notices(self):
        other = make_user("vizinho@example.com")
        PushSubscription.objects.filter(user=self.user).update(user=other)
        from production.shipment_views import _notify_owner

        note = SimpleNamespace(id=uuid.uuid4(), owner=self.user, number_label="1", destination_company="X")
        with self.captureOnCommitCallbacks(execute=True):
            _notify_owner(SimpleNamespace(note=note, name="Ana"), "visto")
        self.webpush.assert_not_called()
