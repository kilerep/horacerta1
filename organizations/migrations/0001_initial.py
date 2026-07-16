import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HiringOrganization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=140)),
                ("legal_name", models.CharField(blank=True, default="", max_length=180)),
                ("cnpj", models.CharField(blank=True, default="", max_length=14)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("whatsapp", models.CharField(blank=True, default="", max_length=30)),
                ("phone", models.CharField(blank=True, default="", max_length=30)),
                ("address", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Ativa"), ("SUSPENDED", "Suspensa"), ("ARCHIVED", "Arquivada")],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_hiring_organizations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Empresa contratante",
                "verbose_name_plural": "Empresas contratantes",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationMember",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("ADMIN", "Administrador"),
                            ("SERVICE_MANAGER", "Gestor de serviços"),
                            ("FINANCE", "Financeiro"),
                            ("VIEWER", "Consulta"),
                        ],
                        default="VIEWER",
                        max_length=24,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("INVITED", "Convite enviado"),
                            ("ACTIVE", "Ativo"),
                            ("SUSPENDED", "Suspenso"),
                            ("REMOVED", "Removido"),
                        ],
                        default="INVITED",
                        max_length=20,
                    ),
                ),
                ("invited_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("joined_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_member_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="organizations.hiringorganization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Membro da empresa contratante",
                "verbose_name_plural": "Membros das empresas contratantes",
                "ordering": ["organization__name", "user__email"],
            },
        ),
        migrations.CreateModel(
            name="ProviderOrganizationLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("INVITED", "Convite enviado"),
                            ("AWAITING_PROVIDER", "Aguardando prestador"),
                            ("ACTIVE", "Ativo"),
                            ("SUSPENDED", "Suspenso"),
                            ("ENDED", "Encerrado"),
                            ("DECLINED", "Recusado"),
                        ],
                        default="INVITED",
                        max_length=24,
                    ),
                ),
                (
                    "initiated_by",
                    models.CharField(
                        choices=[
                            ("ORGANIZATION", "Empresa contratante"),
                            ("PROVIDER", "Prestador de serviço"),
                        ],
                        default="ORGANIZATION",
                        max_length=20,
                    ),
                ),
                ("share_services", models.BooleanField(default=True)),
                ("share_hours", models.BooleanField(default=True)),
                ("share_reports", models.BooleanField(default=True)),
                ("share_financial_values", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("end_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="provider_link_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="provider_links",
                        to="organizations.hiringorganization",
                    ),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="provider_organization_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Vínculo entre empresa e prestador",
                "verbose_name_plural": "Vínculos entre empresas e prestadores",
                "ordering": ["organization__name", "provider__email"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationAuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=80)),
                ("target_type", models.CharField(blank=True, default="", max_length=80)),
                ("target_id", models.CharField(blank=True, default="", max_length=80)),
                ("summary", models.CharField(max_length=240)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="organizations.hiringorganization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de auditoria da empresa",
                "verbose_name_plural": "Eventos de auditoria das empresas",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="hiringorganization",
            index=models.Index(fields=["status", "name"], name="org_status_name_idx"),
        ),
        migrations.AddIndex(
            model_name="hiringorganization",
            index=models.Index(fields=["created_by", "status"], name="org_creator_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="hiringorganization",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("cnpj", "")),
                fields=("cnpj",),
                name="unique_hiring_org_cnpj",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(fields=["organization", "status"], name="org_member_status_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(fields=["user", "status"], name="user_org_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="organizationmember",
            constraint=models.UniqueConstraint(
                fields=("organization", "user"),
                name="unique_member_per_hiring_org",
            ),
        ),
        migrations.AddIndex(
            model_name="providerorganizationlink",
            index=models.Index(fields=["organization", "status"], name="org_provider_status_idx"),
        ),
        migrations.AddIndex(
            model_name="providerorganizationlink",
            index=models.Index(fields=["provider", "status"], name="provider_org_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="providerorganizationlink",
            constraint=models.UniqueConstraint(
                fields=("organization", "provider"),
                name="unique_provider_per_hiring_org",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationauditevent",
            index=models.Index(fields=["organization", "-created_at"], name="org_audit_created_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationauditevent",
            index=models.Index(fields=["event_type", "-created_at"], name="org_audit_type_idx"),
        ),
    ]
