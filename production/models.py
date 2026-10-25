"""Relatorios de producao: a "folha" de papel por maquina, digital.

Uma folha (ProductionSheet) pertence a quem a criou e normalmente corresponde a uma
maquina/equipamento ao longo de varios dias. Cada linha (ProductionEntry) e um item
trabalhado: data, codigo da peca (opcional), destino (guincho/implemento), inicio e
fim (opcionais) ou so a duracao, e uma observacao livre.
"""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def format_minutes(minutes):
    """120 -> '2:00', 90 -> '1:30', None/0 -> '0:00'."""
    minutes = int(minutes or 0)
    return f"{minutes // 60}:{minutes % 60:02d}"


class ProductionSheet(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Aberto"
        CLOSED = "CLOSED", "Fechado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="production_sheets")
    company_name = models.CharField("Empresa", max_length=120, blank=True, default="")
    operator_name = models.CharField("Operador", max_length=120, blank=True, default="")
    equipment = models.CharField("Máquina / equipamento", max_length=80)
    notes = models.TextField("Observações", blank=True, default="")
    supervisor_name = models.CharField("Encarregado", max_length=80, blank=True, default="")
    supervisor_whatsapp = models.CharField("WhatsApp do encarregado", max_length=20, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # Codigo secreto do link do PDF/Excel enviado pelo WhatsApp (quem nao tem o link nao abre).
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status", "-created_at"])]

    def __str__(self):
        return f"{self.equipment} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    def close(self):
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()

    def reopen(self):
        self.status = self.Status.OPEN
        self.closed_at = None

    def totals(self):
        """Minutos totais e por destino (so linhas com duracao conhecida)."""
        result = {"total": 0, "pending": 0}
        for value, _label in ProductionEntry.Destination.choices:
            result[value] = 0
        for entry in self.entries.all():
            minutes = entry.duration_minutes
            if minutes is None:
                result["pending"] += 1
                continue
            result["total"] += minutes
            if entry.destination in result:
                result[entry.destination] += minutes
        return result

    def date_range(self):
        dates = [e.work_date for e in self.entries.all()]
        if not dates:
            return None, None
        return min(dates), max(dates)


class ProductionEntry(models.Model):
    class Destination(models.TextChoices):
        GUINCHO = "GUINCHO", "Guincho"
        IMPLEMENTO = "IMPLEMENTO", "Implemento"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sheet = models.ForeignKey(ProductionSheet, on_delete=models.CASCADE, related_name="entries")
    work_date = models.DateField("Data", default=timezone.localdate)
    item_code = models.CharField("Código do item", max_length=40, blank=True, default="")
    quantity = models.PositiveIntegerField("Quantidade", null=True, blank=True)
    destination = models.CharField("Destino", max_length=12, choices=Destination.choices, blank=True, default="")
    start_time = models.TimeField("Início", null=True, blank=True)
    end_time = models.TimeField("Fim", null=True, blank=True)
    manual_minutes = models.PositiveIntegerField("Duração informada (min)", null=True, blank=True)
    note = models.CharField("Observação", max_length=160, blank=True, default="")
    # Identificador gerado no aparelho quando o item foi anotado sem internet (evita duplicar no reenvio).
    client_ref = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "start_time", "created_at"]

    def __str__(self):
        return f"{self.work_date:%d/%m} {self.item_code or '-'}"

    @property
    def duration_minutes(self):
        """Duracao calculada pelos horarios; se nao houver, a informada; senao None."""
        if self.start_time and self.end_time:
            start = datetime.combine(self.work_date, self.start_time)
            end = datetime.combine(self.work_date, self.end_time)
            if end <= start:  # virou a meia-noite
                end += timedelta(days=1)
            return int((end - start).total_seconds() // 60)
        if self.manual_minutes is not None:
            return self.manual_minutes
        return None

    @property
    def duration_label(self):
        minutes = self.duration_minutes
        return format_minutes(minutes) if minutes is not None else ""

    @property
    def is_running(self):
        """Comecou mas ainda nao tem fim nem duracao: item em andamento."""
        return bool(self.start_time and not self.end_time and self.manual_minutes is None)
