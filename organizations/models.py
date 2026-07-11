import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalize_cnpj(value: str) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


class HiringOrganization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativa"
        SUSPENDED = "SUSPENDED", "Suspensa"
        ARCHIVED = "ARCHIVED", "Arquivada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    legal_name = models.CharField(max_length=180, blank=True, default="")
    cnpj = models.CharField(max_length=14, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    whatsapp = models.CharField(max_length=30, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_hiring_organizations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Empresa contratante"
        verbose_name_plural = "Empresas contratantes"
        indexes = [
            models.Index(fields=["status", "name"], name="org_status_name_idx"),
            models.Index(fields=["created_by", "status"], name="org_creator_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=~models.Q(cnpj=""),
                name="unique_hiring_org_cnpj",
            ),
        ]

    def clean(self):
        errors = {}
        self.name = (self.name or "").strip()
        self.legal_name = (self.legal_name or "").strip()
        self.cnpj = normalize_cnpj(self.cnpj)

        if not self.name:
            errors["name"] = "Informe o nome da empresa contratante."
        if self.cnpj and len(self.cnpj) != 14:
            errors["cnpj"] = "Informe um CNPJ com 14 dígitos."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.name or self.legal_name

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def __str__(self):
        return self.display_name


class OrganizationMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        SERVICE_MANAGER = "SERVICE_MANAGER", "Gestor de serviços"
        FINANCE = "FINANCE", "Financeiro"
        VIEWER = "VIEWER", "Consulta"

    class Status(models.TextChoices):
        INVITED = "INVITED", "Convite enviado"
        ACTIVE = "ACTIVE", "Ativo"
        SUSPENDED = "SUSPENDED", "Suspenso"
        REMOVED = "REMOVED", "Removido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        HiringOrganization,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.VIEWER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="organization_member_invitations",
        null=True,
        blank=True,
    )
    invited_at = models.DateTimeField(default=timezone.now)
    joined_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization__name", "user__email"]
        verbose_name = "Membro da empresa contratante"
        verbose_name_plural = "Membros das empresas contratantes"
        indexes = [
            models.Index(fields=["organization", "status"], name="org_member_status_idx"),
            models.Index(fields=["user", "status"], name="user_org_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_member_per_hiring_org",
            ),
        ]

    def clean(self):
        errors = {}
        if self.invited_by_id and self.invited_by_id == self.user_id:
            errors["invited_by"] = "O convite deve ser enviado por outro usuário da empresa."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.Status.ACTIVE and not self.joined_at:
            self.joined_at = timezone.now()
        if self.status == self.Status.REMOVED and not self.ended_at:
            self.ended_at = timezone.now()
        if self.status != self.Status.REMOVED:
            self.ended_at = None
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_active_member(self):
        return self.status == self.Status.ACTIVE

    @property
    def can_manage_members(self):
        return self.is_active_member and self.role == self.Role.ADMIN

    @property
    def can_manage_services(self):
        return self.is_active_member and self.role in {self.Role.ADMIN, self.Role.SERVICE_MANAGER}

    @property
    def can_view_financial(self):
        return self.is_active_member and self.role in {self.Role.ADMIN, self.Role.FINANCE}

    @property
    def can_view_organization(self):
        return self.is_active_member

    def __str__(self):
        return f"{self.user} — {self.organization} ({self.get_role_display()})"


class ProviderOrganizationLink(models.Model):
    class Status(models.TextChoices):
        INVITED = "INVITED", "Convite enviado"
        AWAITING_PROVIDER = "AWAITING_PROVIDER", "Aguardando prestador"
        ACTIVE = "ACTIVE", "Ativo"
        SUSPENDED = "SUSPENDED", "Suspenso"
        ENDED = "ENDED", "Encerrado"
        DECLINED = "DECLINED", "Recusado"

    class InitiatedBy(models.TextChoices):
        ORGANIZATION = "ORGANIZATION", "Empresa contratante"
        PROVIDER = "PROVIDER", "Prestador de serviço"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        HiringOrganization,
        on_delete=models.CASCADE,
        related_name="provider_links",
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="provider_organization_links",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.INVITED)
    initiated_by = models.CharField(
        max_length=20,
        choices=InitiatedBy.choices,
        default=InitiatedBy.ORGANIZATION,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="provider_link_invitations",
        null=True,
        blank=True,
    )
    share_services = models.BooleanField(default=True)
    share_hours = models.BooleanField(default=True)
    share_reports = models.BooleanField(default=True)
    share_financial_values = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization__name", "provider__email"]
        verbose_name = "Vínculo entre empresa e prestador"
        verbose_name_plural = "Vínculos entre empresas e prestadores"
        indexes = [
            models.Index(fields=["organization", "status"], name="org_provider_status_idx"),
            models.Index(fields=["provider", "status"], name="provider_org_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "provider"],
                name="unique_provider_per_hiring_org",
            ),
        ]

    def clean(self):
        errors = {}
        provider_role = getattr(self.provider, "role", None) if self.provider_id else None
        if self.provider_id and provider_role != "FUNCIONARIO":
            errors["provider"] = "Selecione uma conta de prestador de serviço."
        if self.status == self.Status.ENDED and not (self.end_reason or "").strip():
            errors["end_reason"] = "Informe o motivo do encerramento do vínculo."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.end_reason = (self.end_reason or "").strip()
        if self.status == self.Status.ACTIVE and not self.started_at:
            self.started_at = timezone.now()
        if self.status == self.Status.ENDED and not self.ended_at:
            self.ended_at = timezone.now()
        if self.status != self.Status.ENDED:
            self.ended_at = None
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def can_share(self, information_type: str) -> bool:
        permissions = {
            "services": self.share_services,
            "hours": self.share_hours,
            "reports": self.share_reports,
            "financial_values": self.share_financial_values,
        }
        return self.is_active and permissions.get(information_type, False)

    def __str__(self):
        return f"{self.provider} — {self.organization} ({self.get_status_display()})"


class OrganizationAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        HiringOrganization,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="organization_audit_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True, default="")
    target_id = models.CharField(max_length=80, blank=True, default="")
    summary = models.CharField(max_length=240)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Evento de auditoria da empresa"
        verbose_name_plural = "Eventos de auditoria das empresas"
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="org_audit_created_idx"),
            models.Index(fields=["event_type", "-created_at"], name="org_audit_type_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Eventos de auditoria não podem ser alterados.")
        self.event_type = (self.event_type or "").strip()
        self.target_type = (self.target_type or "").strip()
        self.target_id = (self.target_id or "").strip()
        self.summary = (self.summary or "").strip()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.organization}: {self.summary}"
