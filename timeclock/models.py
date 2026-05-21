from datetime import datetime
import uuid
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from companies.models import Company, CompanyAuthorizedLocation, Employee


class Contract(models.Model):
    """
    Liga um MEI (User com role FUNCIONARIO) a uma Company.
    Aqui ficam regras de valor/hora e futuras regras de sabado/feriado.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="contracts",
        null=False,
        blank=False,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="contracts",
        null=False,
        blank=False,
    )

    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    contract_file = models.FileField(upload_to="contracts/", null=True, blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee"],
                condition=models.Q(is_active=True),
                name="unique_active_contract_per_company_employee",
            ),
        ]

    def __str__(self):
        return f"Contract<{self.id}> company={self.company_id} employee={self.employee_id} (R$ {self.hourly_rate}/h)"

    def clean(self):
        errors = {}
        if not self.employee_id:
            errors["employee"] = "Contract precisa de um employee valido."
        if not self.company_id:
            errors["company"] = "Contract precisa de uma company valida."
        if self.employee_id and self.company_id and not Employee.objects.filter(
            id=self.employee_id,
            company_id=self.company_id,
        ).exists():
            errors["employee"] = "Employee do contrato precisa pertencer a empresa do contrato."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            if self.is_active and self.company_id and self.employee_id:
                (
                    Contract.objects.select_for_update()
                    .filter(
                        company_id=self.company_id,
                        employee_id=self.employee_id,
                        is_active=True,
                    )
                    .exclude(pk=self.pk)
                    .update(is_active=False)
                )
            super().save(*args, **kwargs)


class ActivePunchManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_cancelled=False)


class Punch(models.Model):
    class ValidationMethod(models.TextChoices):
        FREE_POLICY = "FREE_POLICY", "Politica livre"
        GEOLOCATION = "GEOLOCATION", "Geolocalizacao"
        PRESENTIAL_QR_PENDING = "PRESENTIAL_QR_PENDING", "Presencial com QR (pendente)"

    class ConfidenceStatus(models.TextChoices):
        FREE = "FREE", "Livre"
        ON_SITE = "ON_SITE", "No local"
        OUT_OF_RADIUS = "OUT_OF_RADIUS", "Fora do raio"
        NO_LOCATION = "NO_LOCATION", "Sem localizacao"
        IMPRECISE = "IMPRECISE", "Localizacao imprecisa"

    class QrConfirmationStatus(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "Nao exigido"
        CONFIRMED = "CONFIRMED", "Confirmado por QR"
        REQUIRED_MISSING = "REQUIRED_MISSING", "QR exigido e nao confirmado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_event_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="punches",
    )

    timestamp = models.DateTimeField(default=timezone.now, editable=False)
    note = models.TextField(blank=True, default="")
    is_manual = models.BooleanField(default=False)
    geo_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_accuracy_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    validated_location = models.ForeignKey(
        CompanyAuthorizedLocation,
        on_delete=models.SET_NULL,
        related_name="validated_punches",
        null=True,
        blank=True,
    )
    distance_to_location_m = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    validation_method = models.CharField(
        max_length=30,
        choices=ValidationMethod.choices,
        default=ValidationMethod.FREE_POLICY,
    )
    confidence_status = models.CharField(
        max_length=20,
        choices=ConfidenceStatus.choices,
        default=ConfidenceStatus.FREE,
    )
    qr_confirmation_status = models.CharField(
        max_length=20,
        choices=QrConfirmationStatus.choices,
        default=QrConfirmationStatus.NOT_REQUIRED,
    )
    qr_confirmed_location = models.ForeignKey(
        CompanyAuthorizedLocation,
        on_delete=models.SET_NULL,
        related_name="qr_confirmed_punches",
        null=True,
        blank=True,
    )
    qr_confirmed_at = models.DateTimeField(null=True, blank=True)
    confidence_checked_at = models.DateTimeField(null=True, blank=True)
    audit_payload = models.JSONField(default=dict, blank=True)
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_punches",
        null=True,
        blank=True,
    )
    admin_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActivePunchManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.contract.company.name} - {self.timestamp:%d/%m/%Y %H:%M}"

    def save(self, *args, **kwargs):
        if self.timestamp is None:
            self.timestamp = timezone.now()
        elif isinstance(self.timestamp, datetime) and timezone.is_naive(self.timestamp):
            self.timestamp = timezone.make_aware(
                self.timestamp,
                timezone.get_current_timezone(),
            )
        elif not isinstance(self.timestamp, datetime):
            raise ValueError("Punch.timestamp must be a datetime instance.")

        if not self.validation_method:
            self.validation_method = self.ValidationMethod.FREE_POLICY
        if not self.confidence_status:
            self.confidence_status = self.ConfidenceStatus.FREE
        if not self.qr_confirmation_status:
            self.qr_confirmation_status = self.QrConfirmationStatus.NOT_REQUIRED
        if not self.confidence_checked_at:
            self.confidence_checked_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def confidence_tone(self):
        if self.confidence_status == self.ConfidenceStatus.ON_SITE:
            return "success"
        if self.confidence_status in {self.ConfidenceStatus.OUT_OF_RADIUS, self.ConfidenceStatus.NO_LOCATION}:
            return "warn"
        if self.confidence_status == self.ConfidenceStatus.IMPRECISE:
            return "pending"
        return "neutral"

    @property
    def qr_tone(self):
        if self.qr_confirmation_status == self.QrConfirmationStatus.CONFIRMED:
            return "success"
        if self.qr_confirmation_status == self.QrConfirmationStatus.REQUIRED_MISSING:
            return "warn"
        return "neutral"

    @property
    def audit_method_label(self):
        if self.qr_confirmation_status == self.QrConfirmationStatus.CONFIRMED:
            return "QR presencial"
        if self.validation_method == self.ValidationMethod.GEOLOCATION:
            return "Localizacao"
        if self.validation_method == self.ValidationMethod.PRESENTIAL_QR_PENDING:
            return "QR presencial (pendente)"
        return "Livre"


class PunchCorrectionLog(models.Model):
    class ActionType(models.TextChoices):
        TIME_CHANGED = "time_changed", "Horario corrigido"
        CANCELLED = "cancelled", "Cancelado"
        RESTORED = "restored", "Restaurado"
        ADMIN_NOTE_ADDED = "admin_note_added", "Observacao administrativa"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    punch = models.ForeignKey(
        Punch,
        on_delete=models.PROTECT,
        related_name="correction_logs",
    )
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="punch_correction_logs",
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    old_datetime = models.DateTimeField(null=True, blank=True)
    new_datetime = models.DateTimeField(null=True, blank=True)
    old_status = models.CharField(max_length=30, blank=True, default="")
    new_status = models.CharField(max_length=30, blank=True, default="")
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["punch", "-created_at"]),
            models.Index(fields=["action_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} - {self.punch_id}"


class PunchCorrectionRequest(models.Model):
    class ProblemType(models.TextChoices):
        EXTRA_PUNCH = "extra_punch", "Registro a mais"
        MISSED_PUNCH = "missed_punch", "Esqueci uma batida"
        WRONG_TIME = "wrong_time", "Horario errado"
        DUPLICATED_PUNCH = "duplicated_punch", "Registro duplicado"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        IN_REVIEW = "in_review", "Em analise"
        CORRECTED = "corrected", "Corrigida"
        REJECTED = "rejected", "Recusada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="punch_correction_requests",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="punch_correction_requests",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="punch_correction_requests",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="punch_correction_requests",
        null=True,
        blank=True,
    )
    punch = models.ForeignKey(
        Punch,
        on_delete=models.SET_NULL,
        related_name="correction_requests",
        null=True,
        blank=True,
    )
    problem_date = models.DateField()
    problem_type = models.CharField(max_length=30, choices=ProblemType.choices)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    admin_response = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resolved_punch_correction_requests",
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["problem_date"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.get_problem_type_display()} ({self.get_status_display()})"


class ActivityReportRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        RESPONDED = "RESPONDED", "Respondida"
        REVIEWED = "REVIEWED", "Revisada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="activity_report_requests",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="activity_report_requests",
        null=False,
        blank=False,
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="activity_report_requests",
        null=True,
        blank=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_activity_report_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_activity_report_requests",
        null=True,
        blank=True,
    )
    response_report = models.ForeignKey(
        "ServiceReport",
        on_delete=models.SET_NULL,
        related_name="linked_activity_report_requests",
        null=True,
        blank=True,
    )

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    subject = models.CharField(max_length=160, blank=True, default="")
    instruction = models.TextField(blank=True, default="")
    message = models.TextField(blank=True, default="")
    response_text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    is_answered = models.BooleanField(default=False)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def clean(self):
        errors = {}
        if not self.employee_id:
            errors["employee"] = "Solicitacao precisa de um employee valido."
        if not self.company_id:
            errors["company"] = "Solicitacao precisa de uma company valida."
        if self.employee_id and self.company_id and not Employee.objects.filter(
            id=self.employee_id,
            company_id=self.company_id,
        ).exists():
            errors["employee"] = "Employee da solicitacao precisa pertencer a empresa."
        if self.contract_id:
            contract = Contract.objects.select_related("employee", "company").filter(id=self.contract_id).first()
            if not contract:
                errors["contract"] = "Vinculo informado nao existe."
            else:
                if self.company_id and contract.company_id != self.company_id:
                    errors["company"] = "Empresa da solicitacao difere da empresa do vinculo."
                if self.employee_id and contract.employee_id != self.employee_id:
                    errors["employee"] = "Profissional da solicitacao difere do profissional do vinculo."
        if self.date_from and self.date_to and self.date_from > self.date_to:
            errors["date_to"] = "Data final nao pode ser anterior a data inicial."
        if self.status in {self.Status.RESPONDED, self.Status.REVIEWED} and not self.response_report_id:
            errors["response_report"] = "Solicitacao respondida precisa de relatorio vinculado."
        if self.status == self.Status.REVIEWED and not self.reviewed_by_id:
            errors["reviewed_by"] = "Solicitacao revisada precisa de usuario revisor."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.subject and self.message:
            self.subject = (self.message[:157] + "...") if len(self.message) > 160 else self.message
        if not self.instruction and self.message:
            self.instruction = self.message

        self.is_answered = self.status in {self.Status.RESPONDED, self.Status.REVIEWED}
        if self.status == self.Status.PENDING:
            self.responded_at = None
            self.reviewed_at = None
            self.reviewed_by = None
        elif self.status in {self.Status.RESPONDED, self.Status.REVIEWED} and not self.responded_at:
            self.responded_at = timezone.now()
        if self.status == self.Status.REVIEWED and not self.reviewed_at:
            self.reviewed_at = timezone.now()

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"ActivityReportRequest<{self.id}> {self.company.name} -> {self.employee.full_name}"


class ServiceReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="service_reports",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="service_reports",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="service_reports",
    )

    report_date = models.DateField(default=timezone.localdate)
    title = models.CharField(max_length=120)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date", "-created_at"]
        indexes = [
            models.Index(fields=["company", "report_date"]),
            models.Index(fields=["employee", "report_date"]),
            models.Index(fields=["contract", "report_date"]),
        ]

    def clean(self):
        errors = {}
        if not self.company_id:
            errors["company"] = "Relatorio precisa de uma empresa valida."
        if not self.employee_id:
            errors["employee"] = "Relatorio precisa de um profissional valido."
        if not self.contract_id:
            errors["contract"] = "Relatorio precisa de um vinculo valido."

        if self.contract_id:
            contract = Contract.objects.select_related("employee", "company").filter(id=self.contract_id).first()
            if not contract:
                errors["contract"] = "Vinculo informado nao existe."
            else:
                if self.company_id and contract.company_id != self.company_id:
                    errors["company"] = "Empresa do relatorio difere da empresa do vinculo."
                if self.employee_id and contract.employee_id != self.employee_id:
                    errors["employee"] = "Profissional do relatorio difere do profissional do vinculo."
                if self.company_id and self.employee_id and contract.employee.company_id != self.company_id:
                    errors["employee"] = "Profissional informado nao pertence a empresa."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"ServiceReport<{self.id}> {self.report_date:%d/%m/%Y} {self.title}"
