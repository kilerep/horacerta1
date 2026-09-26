from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.analytics import funnel_summary
from accounts.models import ProductEvent, User

PWD = "Uma-Senha-Forte-482"


def make_user(email, **extra):
    return User.objects.create_user(username=email, email=email, password=PWD, **extra)


def add_event(user, event, at):
    row = ProductEvent.objects.create(user=user, event=event)
    ProductEvent.objects.filter(pk=row.pk).update(occurred_at=at)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class InternalFunnelAccessTests(TestCase):
    def setUp(self):
        self.mei = make_user("mei-funil-secreto@example.com", role=User.Role.FUNCIONARIO, first_name="Fulana")
        self.admin = make_user("admin-funil@example.com", is_superuser=True, is_staff=True, role=User.Role.EMPRESA)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("internal_funnel"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_regular_mei_is_denied(self):
        self.client.force_login(self.mei)

        self.assertEqual(self.client.get(reverse("internal_funnel")).status_code, 403)

    def test_superuser_sees_funnel_without_personal_data(self):
        add_event(self.mei, "signup_completed", timezone.now() - timedelta(days=2))
        self.client.force_login(self.admin)

        response = self.client.get(reverse("internal_funnel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criaram conta")
        self.assertNotContains(response, "mei-funil-secreto@example.com")
        self.assertNotContains(response, "Fulana")


class FunnelSummaryTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_counts_distinct_users_not_events(self):
        user = make_user("a@example.com")
        add_event(user, "signup_completed", self.now - timedelta(days=3))
        for _ in range(15):
            add_event(user, "punch_recorded", self.now - timedelta(days=2))

        steps = {s["event"]: s["users"] for s in funnel_summary(now=self.now)["steps"]}

        self.assertEqual(steps["signup_completed"], 1)
        self.assertEqual(steps["punch_recorded"], 1)

    def test_stuck_users_are_split_by_last_step_reached(self):
        no_client = make_user("nc@example.com")
        no_punch = make_user("np@example.com")
        no_report = make_user("nr@example.com")
        recent = make_user("recent@example.com")
        old = self.now - timedelta(days=3)
        for user in (no_client, no_punch, no_report):
            add_event(user, "signup_completed", old)
        add_event(no_punch, "client_created", old)
        add_event(no_report, "client_created", old)
        add_event(no_report, "punch_recorded", old)
        add_event(recent, "signup_completed", self.now - timedelta(hours=2))

        stuck = {s["label"]: s["users"] for s in funnel_summary(now=self.now)["stuck"]}

        self.assertEqual(stuck["Cadastro → sem cliente"], 1)
        self.assertEqual(stuck["Cliente → sem horário"], 1)
        self.assertEqual(stuck["Horário → sem relatório"], 1)

    def test_retention_needs_action_in_week_one_and_week_two(self):
        signup = self.now - timedelta(days=20)
        kept = make_user("kept@example.com")
        dropped = make_user("dropped@example.com")
        login_only = make_user("login@example.com")
        for user in (kept, dropped, login_only):
            add_event(user, "signup_completed", signup)
        add_event(kept, "punch_recorded", signup + timedelta(days=1))
        add_event(kept, "punch_recorded", signup + timedelta(days=9))
        add_event(dropped, "punch_recorded", signup + timedelta(days=1))

        retention = funnel_summary(now=self.now)["retention"]

        self.assertEqual(retention["cohort"], 3)
        self.assertEqual(retention["active_week1"], 2)
        self.assertEqual(retention["returned_week2"], 1)
        self.assertEqual(retention["percent"], 50)
