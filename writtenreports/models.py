"""Relatorio escrito: documento formal que o prestador redige para o cliente (de horas ou de um servico).

Rascunho pode ser editado; ao emitir ganha numero, congela os dados (snapshot) e trava. Para mudar, o
prestador exclui e faz outro.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

SECTIONS = (
    ("objective", "Objetivo"),
    ("activities", "Atividades realizadas"),
    ("observations", "Observações e pendências"),
    ("conclusion", "Conclusão"),
)


class WrittenReport(models.Model):
    class Kind(models.TextChoices):
        HOURS = "HOURS", "Relatório de horas"
        SERVICE = "SERVICE", "Relatório de serviço"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        ISSUED = "ISSUED", "Emitido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="written_reports")
    # So "de servico" e criado hoje; HOURS fica para relatorios antigos (o de horas e o Fechamento de horas).
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SERVICE)
    number = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    title = models.CharField("Título", max_length=140)
    contract = models.ForeignKey("timeclock.Contract", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="written_reports")
    service_job = models.ForeignKey("services.ServiceJob", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="written_reports")
    client_name = models.CharField("Cliente / empresa", max_length=140, blank=True, default="")
    service_name = models.CharField("Serviço realizado", max_length=160, blank=True, default="")
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    objective = models.TextField("Objetivo", blank=True, default="")
    activities = models.TextField("Atividades realizadas", blank=True, default="")
    observations = models.TextField("Observações e pendências", blank=True, default="")
    conclusion = models.TextField("Conclusão", blank=True, default="")
    # Dados congelados na emissao (cliente, linhas, totais): o relatorio emitido nunca muda.
    snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.number_label})"

    @property
    def number_label(self):
        return f"{self.number:04d}" if self.number else "Rascunho"

    @property
    def is_locked(self):
        return self.status == self.Status.ISSUED

    @property
    def sections(self):
        """[(titulo, texto)] so das secoes escritas, na ordem do documento."""
        return [(label, getattr(self, field).strip()) for field, label in SECTIONS if getattr(self, field).strip()]

    @property
    def client_label(self):
        """Nome do cliente para exibir: o congelado na emissao, o digitado ou o do cliente/servico antigo."""
        if self.snapshot.get("client"):
            return self.snapshot["client"]
        if self.client_name:
            return self.client_name
        if self.kind == self.Kind.SERVICE and self.service_job:
            return self.service_job.client_display_name
        return self.contract.company.name if self.contract else ""

    def issue(self):
        """Emite: confere, congela os dados e da o proximo numero do dono. Repetir nao faz nada."""
        from .data import build_snapshot

        if self.is_locked:
            return
        if not self.sections:
            raise ValidationError("Escreva pelo menos uma seção antes de emitir o relatório.")
        if self.kind == self.Kind.HOURS and not (self.contract and self.date_from and self.date_to):
            raise ValidationError("Escolha o cliente e o período do relatório de horas.")
        if self.kind == self.Kind.SERVICE and not self.service_job and not (self.client_name and self.service_name):
            raise ValidationError("Informe o cliente e o serviço do relatório.")
        with transaction.atomic():
            list(WrittenReport.objects.select_for_update().filter(owner=self.owner).values_list("id", flat=True))
            current = WrittenReport.objects.select_for_update().get(pk=self.pk)
            if current.is_locked:
                return
            last = WrittenReport.objects.filter(owner=self.owner).aggregate(models.Max("number"))["number__max"] or 0
            self.snapshot = build_snapshot(self)
            self.number = last + 1
            self.status = self.Status.ISSUED
            self.issued_at = timezone.now()
            self.save(update_fields=["snapshot", "number", "status", "issued_at", "updated_at"])
