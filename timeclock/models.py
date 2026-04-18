from datetime import datetime
import uuid
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from companies.models import Company, Employee


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


class Punch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="punches",
    )

    timestamp = models.DateTimeField(default=timezone.now, editable=False)
    note = models.TextField(blank=True, default="")
    is_manual = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

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

        super().save(*args, **kwargs)


class ActivityReportRequest(models.Model):
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
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_activity_report_requests",
    )

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    response_text = models.TextField(blank=True, default="")

    is_answered = models.BooleanField(default=False)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

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
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
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
