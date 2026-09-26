from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from companies.models import Company

VALID = {
    "full_name": "Maria da Silva",
    "email": "Maria@Example.com",
    "password1": "Uma-Senha-Forte-482",
    "password2": "Uma-Senha-Forte-482",
    "accept_terms": "on",
    "website": "",
}


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class MeiSelfSignupTests(TestCase):
    def test_signup_page_is_public(self):
        response = self.client.get(reverse("signup_mei"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criar minha conta")

    def test_signup_creates_mei_user_without_any_company_and_logs_in(self):
        response = self.client.post(reverse("signup_mei"), VALID)

        self.assertRedirects(response, reverse("employee_dashboard"), fetch_redirect_response=False)
        user = User.objects.get(email="maria@example.com")
        self.assertEqual(user.role, User.Role.FUNCIONARIO)
        self.assertEqual(user.username, "maria@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Maria", "da Silva"))
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertEqual(Company.objects.filter(owner=user).count(), 0)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_new_mei_with_no_client_can_open_the_main_screens(self):
        self.client.post(reverse("signup_mei"), VALID)

        for name in ("employee_dashboard", "mei_panel", "mei_contract", "service_job_list", "help"):
            with self.subTest(screen=name):
                response = self.client.get(reverse(name), follow=True)
                self.assertEqual(response.status_code, 200)

    def test_terms_must_be_accepted(self):
        data = {**VALID}
        data.pop("accept_terms")

        response = self.client.post(reverse("signup_mei"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aceite os Termos de Uso")
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(username="maria@example.com", email="maria@example.com", password="x-Senha-123456")

        response = self.client.post(reverse("signup_mei"), VALID)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível usar este e-mail")
        self.assertEqual(User.objects.filter(email__iexact="maria@example.com").count(), 1)

    def test_weak_and_mismatched_passwords_are_rejected(self):
        weak = self.client.post(reverse("signup_mei"), {**VALID, "password1": "12345678", "password2": "12345678"})
        mismatch = self.client.post(reverse("signup_mei"), {**VALID, "password2": "Outra-Senha-999"})

        self.assertEqual(weak.status_code, 200)
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, "As senhas não conferem")
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    def test_honeypot_blocks_bots(self):
        response = self.client.post(reverse("signup_mei"), {**VALID, "website": "http://spam.example"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    @override_settings(MEI_SIGNUP_ENABLED=False)
    def test_kill_switch_closes_public_signup(self):
        get = self.client.get(reverse("signup_mei"))
        post = self.client.post(reverse("signup_mei"), VALID)

        self.assertEqual(get.status_code, 403)
        self.assertEqual(post.status_code, 403)
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    def test_logged_in_user_is_redirected_away(self):
        self.client.post(reverse("signup_mei"), VALID)

        response = self.client.get(reverse("signup_mei"))

        self.assertEqual(response.status_code, 302)

    def test_landing_and_login_point_to_signup(self):
        landing = self.client.get(reverse("landing"))
        login = self.client.get(reverse("login"))

        self.assertContains(landing, reverse("signup_mei"))
        self.assertContains(login, reverse("signup_mei"))


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class MeiSignupHardeningTests(TestCase):
    def test_duplicate_email_message_does_not_confirm_the_account_exists(self):
        User.objects.create_user(username="maria@example.com", email="maria@example.com", password="x-Senha-123456")

        response = self.client.post(reverse("signup_mei"), VALID)

        self.assertContains(response, "Não foi possível usar este e-mail")
        self.assertNotContains(response, "Já existe uma conta")

    @override_settings(MEI_SIGNUP_MAX_PER_10_MIN=2)
    def test_global_velocity_cap_returns_429(self):
        for i in range(2):
            User.objects.create_user(username=f"u{i}@example.com", email=f"u{i}@example.com", password="x-Senha-123456")

        response = self.client.post(reverse("signup_mei"), VALID)

        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    def test_signup_records_terms_version_and_signup_event(self):
        from accounts.models import ProductEvent

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("signup_mei"), VALID)

        user = User.objects.get(email="maria@example.com")
        self.assertEqual(user.terms_version, "2026-09")
        self.assertTrue(ProductEvent.objects.filter(user=user, event="signup_completed").exists())

    def test_first_client_sends_mei_to_the_first_punch(self):
        from django.utils import timezone

        self.client.post(reverse("signup_mei"), VALID)

        response = self.client.post(
            reverse("mei_client_create"),
            {
                "name": "Cliente ABC",
                "hourly_rate": "40.00",
                "start_date": timezone.localdate().isoformat(),
                "closure_type": "MONTHLY",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("employee_dashboard")))

        second = self.client.post(
            reverse("mei_client_create"),
            {
                "name": "Cliente XYZ",
                "hourly_rate": "50.00",
                "start_date": timezone.localdate().isoformat(),
                "closure_type": "MONTHLY",
            },
        )
        self.assertTrue(second["Location"].startswith(reverse("mei_contract")))


class ProductEventPrivacyTests(TestCase):
    def test_track_drops_properties_outside_the_allowlist(self):
        from accounts.analytics import track
        from accounts.models import ProductEvent

        user = User.objects.create_user(username="t@example.com", email="t@example.com", password="x-Senha-123456")

        with self.captureOnCommitCallbacks(execute=True):
            track(user, "client_created", is_first=True, email="t@example.com", client_name="Fulano")

        event = ProductEvent.objects.get(user=user)
        self.assertEqual(event.properties, {"is_first": True})


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class NewMeiFirstScreenTests(TestCase):
    def test_new_mei_sees_a_welcome_with_one_clear_next_step(self):
        self.client.post(reverse("signup_mei"), VALID)

        response = self.client.get(reverse("employee_dashboard"))

        self.assertContains(response, "Bem-vindo ao HoraCerta, Maria")
        self.assertContains(response, reverse("mei_client_create"))
        self.assertNotContains(response, "aguardando liberacao operacional")
        self.assertNotContains(response, "Solicite ao cliente")

    def test_mei_with_a_link_but_no_active_contract_keeps_the_waiting_message(self):
        from companies.models import Company, Employee

        user = User.objects.create_user(
            username="vinculado@example.com", email="vinculado@example.com", password="x-Senha-123456",
            role=User.Role.FUNCIONARIO,
        )
        company = Company.objects.create(owner=user, name="Cliente Sem Contrato")
        Employee.objects.create(user=user, company=company, full_name="Vinculado", is_active=True)
        self.client.force_login(user)

        response = self.client.get(reverse("employee_dashboard"))

        self.assertNotContains(response, "Bem-vindo ao HoraCerta")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class FirstClientFormTests(TestCase):
    def test_new_client_form_shows_essentials_first_and_prefills_todays_date(self):
        from django.utils import timezone

        self.client.post(reverse("signup_mei"), VALID)

        response = self.client.get(reverse("mei_client_create"))

        html = response.content.decode()
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')
        self.assertLess(html.index('name="hourly_rate"'), html.index("Mais informações do cliente"))
        self.assertLess(html.index("Mais informações do cliente"), html.index('name="cnpj"'))
        self.assertNotIn("<details class=\"client-form-more\" open", html)

    def test_errors_in_optional_fields_keep_the_details_open(self):
        from django.utils import timezone

        self.client.post(reverse("signup_mei"), VALID)

        response = self.client.post(
            reverse("mei_client_create"),
            {
                "name": "Cliente ABC",
                "hourly_rate": "40.00",
                "start_date": timezone.localdate().isoformat(),
                "closure_type": "MONTHLY",
                "email": "isto-nao-e-email",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details class="client-form-more" open')
