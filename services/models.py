import uuid
from decimal import Decimal

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

    class BillingMode(models.TextChoices):
        HOURLY = "HOURLY", "Por hora"
        FIXED = "FIXED", "Valor fixo"
        UNDEFINED = "UNDEFINED", "Sem valor definido ainda"

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
    manual_client_whatsapp = models.CharField(max_length=30, blank=True, default="")
    manual_client_email = models.EmailField(blank=True, null=True)
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="service_jobs",
    )
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, default="")
    service_location = models.CharField(max_length=180, blank=True, default="")
    service_zip_code = models.CharField(max_length=9, blank=True, default="")
    service_street = models.CharField(max_length=140, blank=True, default="")
    service_number = models.CharField(max_length=20, blank=True, default="")
    service_complement = models.CharField(max_length=80, blank=True, default="")
    service_district = models.CharField(max_length=80, blank=True, default="")
    service_city = models.CharField(max_length=80, blank=True, default="")
    service_state = models.CharField(max_length=2, blank=True, default="")
    service_reference = models.CharField(max_length=160, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    planned_start_time = models.TimeField(null=True, blank=True)
    planned_end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    billing_mode = models.CharField(max_length=20, choices=BillingMode.choices, default=BillingMode.UNDEFINED)
    hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fixed_labor_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    public_report_first_viewed_at = models.DateTimeField(null=True, blank=True)
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

    @property
    def total_work_minutes(self):
        if hasattr(self, "_prefetched_objects_cache") and "work_logs" in self._prefetched_objects_cache:
            return sum(log.duration_minutes or 0 for log in self.work_logs.all())
        return self.work_logs.aggregate(total=models.Sum("duration_minutes"))["total"] or 0

    @property
    def total_hours_decimal(self):
        return (Decimal(self.total_work_minutes) / Decimal("60")).quantize(Decimal("0.01"))

    @property
    def total_hours_label(self):
        minutes = self.total_work_minutes
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    @property
    def labor_total(self):
        if self.fixed_labor_value is not None:
            return self.fixed_labor_value
        return (self.total_hours_decimal * (self.hourly_rate_snapshot or Decimal("0"))).quantize(Decimal("0.01"))

    @property
    def used_items_total(self):
        return self.item_expenses.filter(
            usage_status__in=ServiceItemExpense.CHARGEABLE_USAGE_STATUSES
        ).aggregate(total=models.Sum("total_value"))["total"] or Decimal("0.00")

    @property
    def not_used_items_total(self):
        return self.item_expenses.filter(
            usage_status__in=ServiceItemExpense.NON_CHARGEABLE_USAGE_STATUSES
        ).aggregate(total=models.Sum("total_value"))["total"] or Decimal("0.00")

    @property
    def estimated_total(self):
        return (self.labor_total + self.used_items_total).quantize(Decimal("0.01"))

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
        if self.planned_start_time and self.planned_end_time and self.planned_end_time <= self.planned_start_time:
            errors["planned_end_time"] = "Hora final prevista precisa ser maior que a inicial."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.contract_id:
            self.client = self.contract.company
            if self.billing_mode == self.BillingMode.HOURLY and not self.hourly_rate_snapshot:
                self.hourly_rate_snapshot = self.contract.hourly_rate or 0
        if self.billing_mode == self.BillingMode.FIXED:
            self.hourly_rate_snapshot = Decimal("0.00")
        elif self.billing_mode == self.BillingMode.UNDEFINED:
            self.hourly_rate_snapshot = Decimal("0.00")
            self.fixed_labor_value = None
        elif self.billing_mode == self.BillingMode.HOURLY:
            self.fixed_labor_value = None
        if self.status == self.Status.FINISHED and not self.finished_at:
            self.finished_at = timezone.now()
        if self.status != self.Status.FINISHED:
            self.finished_at = None
        self.full_clean()
        return super().save(*args, **kwargs)


class ServiceWorkLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_job = models.ForeignKey(
        ServiceJob,
        on_delete=models.CASCADE,
        related_name="work_logs",
    )
    work_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=180, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-start_time", "-created_at"]
        indexes = [
            models.Index(fields=["service_job", "-work_date", "-start_time"]),
        ]
        verbose_name = "Horario do servico"
        verbose_name_plural = "Horarios do servico"

    def __str__(self):
        return f"{self.service_job_id} {self.work_date} {self.start_time}-{self.end_time}"

    @property
    def duration_label(self):
        minutes = self.duration_minutes or 0
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "Horario final precisa ser maior que o inicial."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            start_minutes = self.start_time.hour * 60 + self.start_time.minute
            end_minutes = self.end_time.hour * 60 + self.end_time.minute
            self.duration_minutes = max(end_minutes - start_minutes, 0)
        self.full_clean()
        return super().save(*args, **kwargs)


class ServiceItemExpense(models.Model):
    class ItemType(models.TextChoices):
        MATERIAL = "MATERIAL", "Material"
        EXPENSE = "EXPENSE", "Despesa"
        PART = "PART", "Peca"
        TOLL = "TOLL", "Pedagio"
        FUEL = "FUEL", "Combustivel"
        PARKING = "PARKING", "Estacionamento"
        FOOD = "FOOD", "Alimentacao"
        OTHER = "OTHER", "Outro"

    class UsageStatus(models.TextChoices):
        PLANNED = "PLANNED", "Previsto"
        PURCHASED = "PURCHASED", "Comprado"
        USED = "USED", "Usado"
        PARTIALLY_USED = "PARTIALLY_USED", "Parcialmente usado"
        NOT_USED = "NOT_USED", "Nao usado"
        RETURNED = "RETURNED", "Devolvido"

    CHARGEABLE_USAGE_STATUSES = (UsageStatus.USED, UsageStatus.PARTIALLY_USED)
    NON_CHARGEABLE_USAGE_STATUSES = (UsageStatus.NOT_USED, UsageStatus.RETURNED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_job = models.ForeignKey(
        ServiceJob,
        on_delete=models.CASCADE,
        related_name="item_expenses",
    )
    type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.MATERIAL)
    name = models.CharField(max_length=140)
    description = models.TextField(blank=True, default="")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    usage_status = models.CharField(max_length=24, choices=UsageStatus.choices, default=UsageStatus.PLANNED)
    receipt_note = models.CharField(max_length=180, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["service_job", "usage_status", "-created_at"]),
            models.Index(fields=["service_job", "type", "-created_at"]),
        ]
        verbose_name = "Item/despesa do servico"
        verbose_name_plural = "Itens/despesas do servico"

    def __str__(self):
        return f"{self.name} ({self.get_usage_status_display()})"

    @property
    def is_chargeable(self):
        return self.usage_status in self.CHARGEABLE_USAGE_STATUSES

    @property
    def short_usage_status(self):
        labels = {
            self.UsageStatus.PARTIALLY_USED: "Parcial",
            self.UsageStatus.NOT_USED: "Nao usado",
        }
        return labels.get(self.usage_status, self.get_usage_status_display())

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity < 0:
            errors["quantity"] = "Quantidade nao pode ser negativa."
        if self.unit_value is not None and self.unit_value < 0:
            errors["unit_value"] = "Valor unitario nao pode ser negativo."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        quantity = self.quantity or Decimal("0")
        unit_value = self.unit_value or Decimal("0")
        self.total_value = (quantity * unit_value).quantize(Decimal("0.01"))
        self.full_clean()
        return super().save(*args, **kwargs)
