import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ServiceCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.TextField(blank=True, default="")
    icon_name = models.CharField(max_length=40, blank=True, default="")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Categoria de servico"
        verbose_name_plural = "Categorias de servico"

    def __str__(self):
        return self.name


class ServiceJob(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        IN_PROGRESS = "IN_PROGRESS", "Em andamento"
        FINISHED = "FINISHED", "Finalizado"
        ARCHIVED = "ARCHIVED", "Arquivado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="service_jobs",
    )
    client = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="service_jobs",
        null=True,
        blank=True,
    )
    contract = models.ForeignKey(
        "timeclock.Contract",
        on_delete=models.PROTECT,
        related_name="service_jobs",
        null=True,
        blank=True,
    )
    manual_client_name = models.CharField(max_length=120, blank=True, default="")
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="service_jobs",
    )
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, default="")
    service_location = models.CharField(max_length=180, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fixed_labor_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["professional", "status", "-created_at"]),
            models.Index(fields=["professional", "category", "-created_at"]),
            models.Index(fields=["professional", "client", "-created_at"]),
        ]
        verbose_name = "Servico"
        verbose_name_plural = "Servicos"

    def __str__(self):
        return self.title

    @property
    def client_display_name(self):
        if self.client_id and self.client:
            return self.client.name
        return self.manual_client_name or "Cliente nao informado"

    def clean(self):
        errors = {}
        if self.contract_id:
            if self.contract.employee.user_id != self.professional_id:
                errors["contract"] = "Selecione um contrato da sua conta."
            if self.client_id and self.contract.company_id != self.client_id:
                errors["client"] = "Cliente e contrato precisam corresponder."
        if self.client_id and self.client.owner_id != self.professional_id:
            contract_matches = (
                self.contract_id
                and self.contract.company_id == self.client_id
                and self.contract.employee.user_id == self.professional_id
            )
            if not contract_matches:
                errors["client"] = "Selecione um cliente da sua conta."
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "A data final nao pode ser anterior a data inicial."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.contract_id:
            self.client = self.contract.company
            if not self.hourly_rate_snapshot:
                self.hourly_rate_snapshot = self.contract.hourly_rate or 0
        if self.status == self.Status.FINISHED and not self.finished_at:
            self.finished_at = timezone.now()
        if self.status != self.Status.FINISHED:
            self.finished_at = None
        self.full_clean()
        return super().save(*args, **kwargs)
