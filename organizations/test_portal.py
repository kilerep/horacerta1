from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import HiringOrganization, OrganizationAuditEvent, OrganizationMember


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class OrganizationPortalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="empresa-owner@example.test",
            email="empresa-owner@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.other_company_user = User.objects.create_user(
            username="empresa-outra@example.test",
            email="empresa-outra@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.provider = User.objects.create_user(
            username="prestador-portal@example.test",
            email="prestador-portal@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )

    def test_company_account_creates_organization_and_first_admin(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("organization_setup"),
            {
                "name": "Empresa Portal",
                "legal_name": "Empresa Portal Ltda.",
                "cnpj": "12.345.678/0001-90",
                "email": "contato@empresa.test",
                "whatsapp": "47999999999",
                "phone": "",
                "address": "Rua Teste, 10",
            },
        )

        organization = HiringOrganization.objects.get(name="Empresa Portal")
        membership = OrganizationMember.objects.get(organization=organization, user=self.owner)
        self.assertRedirects(response, reverse("organization_dashboard", args=[organization.id]))
        self.assertEqual(membership.role, OrganizationMember.Role.ADMIN)
        self.assertEqual(membership.status, OrganizationMember.Status.ACTIVE)
        self.assertTrue(membership.can_manage_members)
        self.assertTrue(
            OrganizationAuditEvent.objects.filter(
                organization=organization,
                event_type="organization.created",
            ).exists()
        )

    def test_provider_account_cannot_open_company_setup(self):
        self.client.force_login(self.provider)

        response = self.client.get(reverse("organization_setup"))

        self.assertEqual(response.status_code, 403)

    def test_company_cannot_open_another_organization_dashboard(self):
        organization = HiringOrganization.objects.create(
            name="Empresa Isolada",
            created_by=self.owner,
        )
        OrganizationMember.objects.create(
            organization=organization,
            user=self.owner,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )
        self.client.force_login(self.other_company_user)

        response = self.client.get(reverse("organization_dashboard", args=[organization.id]))

        self.assertEqual(response.status_code, 404)

    def test_admin_invites_existing_company_account(self):
        organization = HiringOrganization.objects.create(
            name="Empresa Convites",
            created_by=self.owner,
        )
        OrganizationMember.objects.create(
            organization=organization,
            user=self.owner,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("organization_member_invite", args=[organization.id]),
            {
                "email": self.other_company_user.email,
                "role": OrganizationMember.Role.SERVICE_MANAGER,
            },
        )

        membership = OrganizationMember.objects.get(
            organization=organization,
            user=self.other_company_user,
        )
        self.assertRedirects(response, reverse("organization_members", args=[organization.id]))
        self.assertEqual(membership.status, OrganizationMember.Status.INVITED)
        self.assertEqual(membership.role, OrganizationMember.Role.SERVICE_MANAGER)
        self.assertEqual(membership.invited_by, self.owner)

    def test_invited_user_accepts_only_own_invite(self):
        organization = HiringOrganization.objects.create(
            name="Empresa Aceite",
            created_by=self.owner,
        )
        invite = OrganizationMember.objects.create(
            organization=organization,
            user=self.other_company_user,
            role=OrganizationMember.Role.VIEWER,
            status=OrganizationMember.Status.INVITED,
            invited_by=self.owner,
        )
        self.client.force_login(self.other_company_user)

        response = self.client.post(reverse("organization_invite_accept", args=[invite.id]))

        invite.refresh_from_db()
        self.assertRedirects(response, reverse("organization_dashboard", args=[organization.id]))
        self.assertEqual(invite.status, OrganizationMember.Status.ACTIVE)
        self.assertIsNotNone(invite.joined_at)

    def test_non_admin_cannot_invite_members(self):
        organization = HiringOrganization.objects.create(
            name="Empresa Sem Permissão",
            created_by=self.owner,
        )
        OrganizationMember.objects.create(
            organization=organization,
            user=self.owner,
            role=OrganizationMember.Role.VIEWER,
            status=OrganizationMember.Status.ACTIVE,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("organization_member_invite", args=[organization.id]))

        self.assertEqual(response.status_code, 403)
