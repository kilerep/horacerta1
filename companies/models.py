import uuid
from django.conf import settings
from django.db import models


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=120)
    cnpj = models.CharField(max_length=18, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    logo = models.ImageField(upload_to="company_logos/", null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self) -> str:
        return self.name


class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )

    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
        related_name="employees",
        null=False,
        blank=False,
    )

    full_name = models.CharField(max_length=120)
    document = models.CharField(max_length=20, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    profile_photo = models.ImageField(upload_to="employee_photos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"Employee<{self.id}> {self.full_name} [{self.user.email}] - {self.company.name}"
