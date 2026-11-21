"""O cliente final (sem conta) responde ao relatorio publico: confirmar recebimento
ou contestar. Confirmar NAO e aprovar pagamento; so POST; so em link ativo; a
primeira resposta nao e sobrescrita."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ProductEvent, User
from companies.models import Company, Employee
from timeclock.models import Contract, ServiceReport

Status = ServiceReport.ConferenceStatus


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class PublicReportResponseTests(TestCase):
    def setUp(self):
        self.mei = User.objects.create_user(
            username="mei-resp@example.com", email="mei-resp@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=self.mei, name="Cliente Resp")
        employee = Employee.objects.create(user=self.mei, company=company, full_name="Prestador", is_active=True)
        contract = Contract.objects.create(
            company=company, employee=employee, hourly_rate=Decimal("50.00"), start_date=date(2026, 1, 1), is_active=True
        )
        self.report = ServiceReport.objects.create(
            company=company, employee=employee, contract=contract, report_date=date(2026, 6, 4),
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 4), title="Relatorio",
        )
        self.report.ensure_conference_link()
        self.report.save()
        self.page = reverse("public_service_report_conference", args=[self.report.conference_token])
        self.respond = reverse("public_service_report_respond", args=[self.report.conference_token])

    def _status(self):
        self.report.refresh_from_db()
        return self.report.conference_final_status

    def test_page_offers_confirm_and_contest_without_login(self):
        response = self.client.get(self.page)

        self.assertContains(response, "Confirmar recebimento")
        self.assertContains(response, "Contestar")
        self.assertContains(response, "nunca pede senha")

    def test_get_never_confirms(self):
        self.client.get(self.page)
        self.client.get(self.respond)

        self.assertNotEqual(self._status(), Status.REVIEWED)
        self.assertEqual(self.client.get(self.respond).status_code, 405)

    def test_confirm_records_receipt_notifies_the_mei_and_tracks_it(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.respond, {"action": "confirm"})

        self.assertRedirects(response, self.page, fetch_redirect_response=False)
        self.assertEqual(self._status(), Status.REVIEWED)
        self.assertIsNotNone(self.report.conference_reviewed_at)
        from timeclock.models import InternalNotification

        self.assertTrue(
            InternalNotification.objects.filter(recipient_user=self.mei, title="Cliente confirmou o recebimento").exists()
        )
        self.assertTrue(ProductEvent.objects.filter(user=self.mei, event="report_client_responded").exists())
        page = self.client.get(self.page)
        self.assertContains(page, "Recebimento confirmado em")
        self.assertContains(page, "não é aprovação de pagamento")
        self.assertNotContains(page, 'value="confirm"')

    def test_contest_stores_reason_and_message(self):
        response = self.client.post(
            self.respond, {"action": "contest", "reason": "horarios", "message": "  Faltou   o dia 3  "}
        )

        self.assertRedirects(response, self.page, fetch_redirect_response=False)
        self.assertEqual(self._status(), Status.DIVERGENT)
        self.assertEqual(self.report.conference_comment, "[Horários] Faltou o dia 3")
        self.assertContains(self.client.get(self.page), "Divergência registrada")

    def test_contest_needs_a_valid_reason_and_a_message(self):
        for data in (
            {"action": "contest", "reason": "horarios", "message": ""},
            {"action": "contest", "reason": "invalido", "message": "texto valido"},
            {"action": "contest", "message": "sem motivo"},
        ):
            with self.subTest(data=data):
                response = self.client.post(self.respond, data)
                self.assertIn("erro=contestacao", response["Location"])
                self.assertNotEqual(self._status(), Status.DIVERGENT)

    def test_first_response_is_not_overwritten_by_someone_else_with_the_link(self):
        self.client.post(self.respond, {"action": "confirm"})
        self.client.post(self.respond, {"action": "contest", "reason": "valor", "message": "mudei de ideia"})

        self.assertEqual(self._status(), Status.REVIEWED)
        self.assertEqual(self.report.conference_comment, "")

    def test_revoked_or_expired_links_do_not_accept_responses(self):
        self.report.revoke_conference_link()
        self.report.save()
        self.assertEqual(self.client.post(self.respond, {"action": "confirm"}).status_code, 410)
        self.assertEqual(self._status(), Status.REVOKED)

    def test_expired_link_does_not_accept_responses(self):
        self.report.conference_expires_at = timezone.now() - timedelta(days=1)
        self.report.save()

        self.assertEqual(self.client.post(self.respond, {"action": "confirm"}).status_code, 410)
        self.assertNotEqual(self._status(), Status.REVIEWED)

    def test_unknown_token_is_404(self):
        url = reverse("public_service_report_respond", args=["00000000-0000-0000-0000-000000000000"])

        self.assertEqual(self.client.post(url, {"action": "confirm"}).status_code, 404)

    def test_mei_sees_the_clients_message_escaped(self):
        self.client.post(
            self.respond, {"action": "contest", "reason": "outro", "message": "<script>alert(1)</script> valor errado"}
        )
        self.client.force_login(self.mei)

        response = self.client.get(reverse("mei_service_report_detail", args=[self.report.id]))

        self.assertContains(response, "Mensagem do cliente")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt; valor errado")
        self.assertNotContains(response, "<script>alert(1)</script>")
