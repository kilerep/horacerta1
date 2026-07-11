from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import HiringOrganization, OrganizationMember, ProviderOrganizationLink


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class ProviderLinkPortalTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin-vinculo@example.test",
            email="admin-vinculo@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.manager_user = User.objects.create_user(
            username="gestor-vinculo@example.test",
            email="gestor-vinculo@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.provider = User.objects.create_user(
            username="prestador-vinculo@example.test",
            email="prestador-vinculo@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.other_provider = User.objects.create_user(
            username="outro-prestador@example.test",
            email="outro-prestador@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.organization = HiringOrganization.objects.create(
            name="Empresa Vínculos",
            created_by=self.admin_user,
        )
        OrganizationMember.objects.create(
            organization=self.organization,
            user=self.admin_user,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )
        OrganizationMember.objects.create(
            organization=self.organization,
            user=self.manager_user,
            role=OrganizationMember.Role.SERVICE_MANAGER,
            status=OrganizationMember.Status.ACTIVE,
        )

    def test_manager_invites_provider_without_financial_permission(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse("organization_provider_invite", args=[self.organization.id]),
            {
                "email": self.provider.email,
                "share_services": "on",
                "share_hours": "on",
                "share_reports": "on",
                "share_financial_values": "on",
            },
        )

        link = ProviderOrganizationLink.objects.get(organization=self.organization, provider=self.provider)
        self.assertRedirects(response, reverse("organization_providers", args=[self.organization.id]))
        self.assertEqual(link.status, ProviderOrganizationLink.Status.AWAITING_PROVIDER)
        self.assertTrue(link.share_services)
        self.assertTrue(link.share_hours)
        self.assertTrue(link.share_reports)
        self.assertFalse(link.share_financial_values)

    def test_admin_can_explicitly_share_financial_values(self):
        self.client.force_login(self.admin_user)

        self.client.post(
            reverse("organization_provider_invite", args=[self.organization.id]),
            {
                "email": self.provider.email,
                "share_services": "on",
                "share_hours": "on",
                "share_reports": "on",
                "share_financial_values": "on",
            },
        )

        link = ProviderOrganizationLink.objects.get(organization=self.organization, provider=self.provider)
        self.assertTrue(link.share_financial_values)

    def test_provider_accepts_only_own_invite(self):
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
            invited_by=self.admin_user,
        )
        self.client.force_login(self.provider)

        response = self.client.post(reverse("provider_link_accept", args=[link.id]))

        link.refresh_from_db()
        self.assertRedirects(response, reverse("provider_link_invites"))
        self.assertEqual(link.status, ProviderOrganizationLink.Status.ACTIVE)
        self.assertIsNotNone(link.started_at)
        self.assertTrue(link.can_share("services"))

        self.client.force_login(self.other_provider)
        response = self.client.post(reverse("provider_link_accept", args=[link.id]))
        self.assertEqual(response.status_code, 404)

    def test_provider_declines_invite_without_sharing_information(self):
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
            invited_by=self.admin_user,
        )
        self.client.force_login(self.provider)

        self.client.post(reverse("provider_link_decline", args=[link.id]))

        link.refresh_from_db()
        self.assertEqual(link.status, ProviderOrganizationLink.Status.DECLINED)
        self.assertFalse(link.can_share("services"))
        self.assertFalse(link.can_share("hours"))

    def test_admin_suspends_resumes_and_ends_link(self):
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.ACTIVE,
            invited_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)

        self.client.post(reverse("organization_provider_suspend", args=[self.organization.id, link.id]))
        link.refresh_from_db()
        self.assertEqual(link.status, ProviderOrganizationLink.Status.SUSPENDED)
        self.assertFalse(link.can_share("services"))

        self.client.post(reverse("organization_provider_resume", args=[self.organization.id, link.id]))
        link.refresh_from_db()
        self.assertEqual(link.status, ProviderOrganizationLink.Status.ACTIVE)
        self.assertTrue(link.can_share("services"))

        response = self.client.post(
            reverse("organization_provider_end", args=[self.organization.id, link.id]),
            {"reason": "Contrato de prestação encerrado."},
        )
        link.refresh_from_db()
        self.assertRedirects(response, reverse("organization_providers", args=[self.organization.id]))
        self.assertEqual(link.status, ProviderOrganizationLink.Status.ENDED)
        self.assertEqual(link.end_reason, "Contrato de prestação encerrado.")
        self.assertFalse(link.can_share("services"))

    def test_other_company_cannot_manage_link(self):
        other_company_user = User.objects.create_user(
            username="outra-empresa-vinculo@example.test",
            email="outra-empresa-vinculo@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        other_organization = HiringOrganization.objects.create(
            name="Outra Empresa",
            created_by=other_company_user,
        )
        OrganizationMember.objects.create(
            organization=other_organization,
            user=other_company_user,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.ACTIVE,
            invited_by=self.admin_user,
        )
        self.client.force_login(other_company_user)

        response = self.client.post(
            reverse("organization_provider_suspend", args=[other_organization.id, link.id])
        )

        self.assertEqual(response.status_code, 404)
        link.refresh_from_db()
        self.assertEqual(link.status, ProviderOrganizationLink.Status.ACTIVE)
