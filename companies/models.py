import uuid
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=120)
    cnpj = models.CharField(max_length=18, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    logo = models.ImageField(upload_to="company_logos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    internal_note = models.TextField(blank=True, default="")

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

    def current_subscription(self):
        return (
            self.subscriptions.filter(is_current=True)
            .select_related("plan")
            .first()
        )

    def has_feature(self, feature_code: str, user_role: str | None = None, at_time=None) -> bool:
        return company_has_feature(
            company=self,
            feature_code=feature_code,
            user_role=user_role,
            at_time=at_time,
        )


class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profiles",
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
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"],
                name="unique_employee_per_user_company",
            ),
        ]

    def clean(self):
        errors = {}
        if not self.user_id:
            errors["user"] = "Employee precisa de um usuario valido."
        if not self.company_id:
            errors["company"] = "Employee precisa de uma empresa valida."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        user_label = "-"
        company_label = "-"
        if getattr(self, "user", None):
            user_label = self.user.email or self.user.username or "-"
        if getattr(self, "company", None):
            company_label = self.company.name or "-"
        return f"Employee<{self.id}> {self.full_name} [{user_label}] - {company_label}"


class Plan(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True, default="")
    tier = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier"]
        verbose_name = "Plan"
        verbose_name_plural = "Plans"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Feature(models.Model):
    class RequiredRole(models.TextChoices):
        ANY = "ANY", "Qualquer papel"
        EMPRESA = "EMPRESA", "Somente empresa"
        FUNCIONARIO = "FUNCIONARIO", "Somente funcionario/MEI"

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="general")
    required_role = models.CharField(
        max_length=20,
        choices=RequiredRole.choices,
        default=RequiredRole.ANY,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "code"]
        verbose_name = "Feature"
        verbose_name_plural = "Features"

    def __str__(self) -> str:
        return f"{self.code} ({self.required_role})"


class PlanFeature(models.Model):
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="plan_features",
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="feature_plans",
    )
    is_enabled = models.BooleanField(default=True)
    limit_value = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("plan", "feature")]
        verbose_name = "Plan Feature"
        verbose_name_plural = "Plan Features"

    def __str__(self) -> str:
        state = "enabled" if self.is_enabled else "disabled"
        return f"{self.plan.code}:{self.feature.code} ({state})"


class CompanySubscription(models.Model):
    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Trial"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        CANCELED = "CANCELED", "Canceled"
        EXPIRED = "EXPIRED", "Expired"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_current = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    external_customer_id = models.CharField(max_length=120, blank=True, default="")
    external_subscription_id = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_current=True),
                name="unique_current_subscription_per_company",
            )
        ]
        verbose_name = "Company Subscription"
        verbose_name_plural = "Company Subscriptions"

    def __str__(self) -> str:
        return f"{self.company.name} -> {self.plan.code} ({self.status})"

    def is_access_active(self, at_time=None) -> bool:
        at = at_time or timezone.now()
        if self.status not in {self.Status.ACTIVE, self.Status.TRIAL}:
            return False
        if self.starts_at and at < self.starts_at:
            return False
        if self.ends_at and at > self.ends_at:
            return False
        return True


class CompanyFeatureOverride(models.Model):
    class Mode(models.TextChoices):
        FORCE_ENABLE = "FORCE_ENABLE", "Force enable"
        FORCE_DISABLE = "FORCE_DISABLE", "Force disable"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="feature_overrides",
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="company_overrides",
    )
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.FORCE_ENABLE,
    )
    reason = models.CharField(max_length=200, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_feature_overrides",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("company", "feature")]
        verbose_name = "Company Feature Override"
        verbose_name_plural = "Company Feature Overrides"

    def __str__(self) -> str:
        return f"{self.company.name}:{self.feature.code} ({self.mode})"

    def is_valid(self, at_time=None) -> bool:
        at = at_time or timezone.now()
        if self.expires_at and at > self.expires_at:
            return False
        return True


class CompanyAttendancePolicy(models.Model):
    class ValidationMode(models.TextChoices):
        FREE = "FREE", "Livre"
        GEOLOCATION = "GEOLOCATION", "Com localizacao"
        PRESENTIAL_QR = "PRESENTIAL_QR", "Presencial com QR"

    class QrRequirement(models.TextChoices):
        NONE = "NONE", "Nao exigir QR"
        FIRST_PUNCH = "FIRST_PUNCH", "Exigir QR na primeira marcacao"
        FIRST_AND_LAST = "FIRST_AND_LAST", "Exigir QR na primeira e ultima marcacao"

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="attendance_policy",
    )
    validation_mode = models.CharField(
        max_length=20,
        choices=ValidationMode.choices,
        default=ValidationMode.FREE,
    )
    require_location = models.BooleanField(default=False)
    require_qr = models.BooleanField(default=False)
    qr_requirement = models.CharField(
        max_length=20,
        choices=QrRequirement.choices,
        default=QrRequirement.NONE,
    )
    default_allowed_radius_m = models.PositiveIntegerField(default=120)
    default_location = models.ForeignKey(
        "CompanyAuthorizedLocation",
        on_delete=models.SET_NULL,
        related_name="default_for_attendance_policies",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_attendance_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Attendance Policy"
        verbose_name_plural = "Company Attendance Policies"

    def clean(self):
        errors = {}
        if self.default_allowed_radius_m and self.default_allowed_radius_m < 10:
            errors["default_allowed_radius_m"] = "Raio padrao precisa ser de no minimo 10 metros."
        if self.default_location_id and self.company_id:
            if self.default_location.company_id != self.company_id:
                errors["default_location"] = "Local padrao precisa pertencer a mesma empresa da politica."
        if self.validation_mode == self.ValidationMode.FREE:
            self.require_location = False
            self.require_qr = False
            self.qr_requirement = self.QrRequirement.NONE
        if not self.require_qr:
            self.qr_requirement = self.QrRequirement.NONE
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.company.name} -> {self.get_validation_mode_display()}"


class CompanyAuthorizedLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="authorized_locations",
    )
    name = models.CharField(max_length=120)
    address_or_description = models.CharField(max_length=220, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    allowed_radius_m = models.PositiveIntegerField(default=120)
    qr_token = models.CharField(max_length=64, unique=True, default="", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-updated_at"]
        verbose_name = "Company Authorized Location"
        verbose_name_plural = "Company Authorized Locations"
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["company", "name"]),
        ]

    def clean(self):
        errors = {}
        if not self.company_id:
            errors["company"] = "Local autorizado precisa de uma empresa valida."
        if self.latitude is None or self.latitude < -90 or self.latitude > 90:
            errors["latitude"] = "Latitude precisa estar entre -90 e 90."
        if self.longitude is None or self.longitude < -180 or self.longitude > 180:
            errors["longitude"] = "Longitude precisa estar entre -180 e 180."
        if not self.allowed_radius_m or self.allowed_radius_m < 10:
            errors["allowed_radius_m"] = "Raio permitido precisa ser de no minimo 10 metros."
        if errors:
            raise ValidationError(errors)

    @staticmethod
    def generate_qr_token():
        return secrets.token_hex(16)

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = self.generate_qr_token()
        self.full_clean()
        return super().save(*args, **kwargs)

    def rotate_qr_token(self):
        self.qr_token = self.generate_qr_token()
        self.save(update_fields=["qr_token", "updated_at"])

    def __str__(self) -> str:
        return f"{self.company.name} | {self.name}"


def company_has_feature(company: Company, feature_code: str, user_role: str | None = None, at_time=None) -> bool:
    at = at_time or timezone.now()
    feature = Feature.objects.filter(code=feature_code, is_active=True).first()
    if not feature:
        return False

    if user_role and feature.required_role != Feature.RequiredRole.ANY and feature.required_role != user_role:
        return False

    override = (
        CompanyFeatureOverride.objects.filter(
            company=company,
            feature=feature,
        )
        .order_by("-updated_at")
        .first()
    )
    if override and override.is_valid(at):
        return override.mode == CompanyFeatureOverride.Mode.FORCE_ENABLE

    subscription = (
        CompanySubscription.objects.filter(company=company, is_current=True)
        .select_related("plan")
        .first()
    )
    if not subscription or not subscription.is_access_active(at):
        return False

    return PlanFeature.objects.filter(
        plan=subscription.plan,
        feature=feature,
        is_enabled=True,
    ).exists()


class InternalAdminActionLog(models.Model):
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="internal_admin_action_logs",
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=80)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.target_type}:{self.target_id}"
