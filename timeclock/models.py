from datetime import datetime
import uuid
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from companies.models import Company


class Contract(models.Model):
    """
    Liga um MEI (User com role FUNCIONARIO) a uma Company.
    Aqui ficam regras de valor/hora e futuras regras de sabado/feriado.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="contracts",
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
                fields=["company", "employee_user"],
                condition=models.Q(is_active=True),
                name="unique_active_contract_per_company_employee",
            ),
        ]

    def __str__(self):
        return f"{self.company.name} (R$ {self.hourly_rate}/h)"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_active and self.company_id and self.employee_user_id:
                (
                    Contract.objects.select_for_update()
                    .filter(
                        company_id=self.company_id,
                        employee_user_id=self.employee_user_id,
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
    employee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_report_requests",
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

    def __str__(self):
        return f"Solicitacao {self.company.name} -> {self.employee_user.email}"
