from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import HiringOrganization, OrganizationAuditEvent, OrganizationMember, ProviderOrganizationLink


User = get_user_model()


class OrganizationFoundationTests(TestCase):
    def setUp(self):
        self.company_user = User.objects.create_user(
            username="empresa@example.test",
            email="empresa@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.manager_user = User.objects.create_user(
            username="gestor@example.test",
            email="gestor@example.test",
            password="Teste@12345",
            role=User.Role.EMPRESA,
        )
        self.provider = User.objects.create_user(
            username="prestador@example.test",
            email="prestador@example.test",
            password="Teste@12345",
            role=User.Role.FUNCIONARIO,
        )
        self.organization = HiringOrganization.objects.create(
            name="Empresa Contratante Teste",
            legal_name="Empresa Contratante Teste Ltda.",
            cnpj="12.345.678/0001-90",
            created_by=self.company_user,
        )

    def test_organization_normalizes_cnpj_and_preserves_creator(self):
        self.assertEqual(self.organization.cnpj, "12345678000190")
        self.assertEqual(self.organization.created_by, self.company_user)
        self.assertEqual(self.organization.display_name, "Empresa Contratante Teste")
        self.assertTrue(self.organization.is_active)

    def test_invalid_cnpj_is_rejected(self):
        organization = HiringOrganization(
            name="Empresa inválida",
            cnpj="123",
            created_by=self.company_user,
        )

        with self.assertRaises(ValidationError):
            organization.save()

    def test_member_permissions_follow_role_and_active_status(self):
        admin = OrganizationMember.objects.create(
            organization=self.organization,
            user=self.company_user,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )
        manager = OrganizationMember.objects.create(
            organization=self.organization,
            user=self.manager_user,
            role=OrganizationMember.Role.SERVICE_MANAGER,
            status=OrganizationMember.Status.ACTIVE,
        )

        self.assertTrue(admin.can_manage_members)
        self.assertTrue(admin.can_manage_services)
        self.assertTrue(admin.can_view_financial)
        self.assertTrue(manager.can_manage_services)
        self.assertFalse(manager.can_manage_members)
        self.assertFalse(manager.can_view_financial)
        self.assertIsNotNone(admin.joined_at)

    def test_duplicate_member_is_rejected(self):
        OrganizationMember.objects.create(
            organization=self.organization,
            user=self.company_user,
            role=OrganizationMember.Role.ADMIN,
            status=OrganizationMember.Status.ACTIVE,
        )

        duplicate = OrganizationMember(
            organization=self.organization,
            user=self.company_user,
            role=OrganizationMember.Role.VIEWER,
            status=OrganizationMember.Status.ACTIVE,
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_provider_link_controls_shared_information(self):
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.ACTIVE,
            initiated_by=ProviderOrganizationLink.InitiatedBy.ORGANIZATION,
            invited_by=self.company_user,
            share_services=True,
            share_hours=True,
            share_reports=True,
            share_financial_values=False,
        )

        self.assertIsNotNone(link.started_at)
        self.assertTrue(link.can_share("services"))
        self.assertTrue(link.can_share("hours"))
        self.assertTrue(link.can_share("reports"))
        self.assertFalse(link.can_share("financial_values"))

    def test_company_account_cannot_be_registered_as_provider(self):
        link = ProviderOrganizationLink(
            organization=self.organization,
            provider=self.manager_user,
            status=ProviderOrganizationLink.Status.INVITED,
            invited_by=self.company_user,
        )

        with self.assertRaises(ValidationError):
            link.save()

    def test_ending_link_requires_reason_and_preserves_history(self):
        link = ProviderOrganizationLink.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=ProviderOrganizationLink.Status.ACTIVE,
            invited_by=self.company_user,
        )

        link.status = ProviderOrganizationLink.Status.ENDED
        with self.assertRaises(ValidationError):
            link.save()

        link.end_reason = "Prestação encerrada por decisão das partes."
        link.save()
        link.refresh_from_db()

        self.assertEqual(link.status, ProviderOrganizationLink.Status.ENDED)
        self.assertIsNotNone(link.ended_at)
        self.assertFalse(link.can_share("services"))

    def test_audit_event_is_immutable(self):
        event = OrganizationAuditEvent.objects.create(
            organization=self.organization,
            actor=self.company_user,
            event_type="organization.created",
            target_type="HiringOrganization",
            target_id=str(self.organization.id),
            summary="Empresa contratante criada.",
            metadata={"source": "test"},
        )

        event.summary = "Texto alterado."
        with self.assertRaises(ValidationError):
            event.save()
