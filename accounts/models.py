from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPRESA = "EMPRESA", "Empresa (RH/Admin)"
        FUNCIONARIO = "FUNCIONARIO", "Funcionário (MEI)"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.FUNCIONARIO,
    )

    email = models.EmailField(unique=True)  # <- importante

    def __str__(self):
        return f"{self.username} ({self.role})"
