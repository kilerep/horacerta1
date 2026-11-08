"""Relatorios de producao: a "folha" de papel por maquina, digital.

Uma folha (ProductionSheet) pertence a quem a criou e normalmente corresponde a uma
maquina/equipamento ao longo de varios dias. Cada linha (ProductionEntry) e um item
trabalhado: data, codigo da peca (opcional), destino (guincho/implemento), inicio e
fim (opcionais) ou so a duracao, e uma observacao livre.
"""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


def itens(n):
    """1 -> '1 item', 2 -> '2 itens' (portugues certo, sem 'item(ns)')."""
    n = int(n or 0)
    return f"{n} {'item' if n == 1 else 'itens'}"


def pending_note(n):
    """Frase dos itens sem fim que ficaram fora do total, no singular ou plural."""
    n = int(n or 0)
    return f"{itens(n)} sem horário de fim {'ficou' if n == 1 else 'ficaram'} fora do total."


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
        ordering = ["work_date", models.F("start_time").asc(nulls_last=True), "created_at"]

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


class ShipmentNote(models.Model):
    """Nota de envio: comprovante das pecas que saem no caminhao para outra empresa.

    Rascunho pode ser editado e apagado; ao enviar ganha numero sequencial do dono e fica
    travada para sempre (corrigir = nova nota que aponta a anterior em `replaces`).
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        SENT = "SENT", "Enviada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shipment_notes")
    number = models.PositiveIntegerField("Número", null=True, blank=True)
    destination_company = models.CharField("Empresa de destino", max_length=120)
    departed_at = models.DateTimeField("Saída", default=timezone.now)
    driver_name = models.CharField("Motorista", max_length=80, blank=True, default="")
    vehicle_plate = models.CharField("Placa", max_length=10, blank=True, default="")
    notes = models.TextField("Observação", blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replaced_by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "number"], name="shipment_number_per_owner")]

    def __str__(self):
        return f"Nota de envio {self.number_label}"

    @property
    def number_label(self):
        return f"{self.number:04d}" if self.number else "Rascunho"

    @property
    def is_locked(self):
        return self.status == self.Status.SENT

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def situation(self):
        """(rotulo, tom) para o selo da lista: tom segue as classes de status do sistema."""
        if not self.is_locked:
            return "Rascunho", "neutral"
        recipients = list(self.recipients.all())
        authorized = sum(1 for r in recipients if r.authorized_at)
        viewed = sum(1 for r in recipients if r.viewed_at)
        total = len(recipients)
        if authorized:
            return f"Autorizada {authorized} de {total}", "progress"
        if viewed:
            return f"Vista {viewed} de {total}", "warning"
        return "Enviada", "planned"

    def send(self):
        if self.is_locked:
            return
        if not self.items.exists():
            raise ValidationError("Adicione pelo menos um item antes de enviar.")
        recipients = list(self.recipients.all())
        if len(recipients) < 2 or any(not r.name.strip() for r in recipients):
            raise ValidationError("Informe o nome do encarregado e do supervisor antes de enviar.")
        with transaction.atomic():
            # Trava as notas do dono para dois envios ao mesmo tempo nao pegarem o mesmo numero.
            list(ShipmentNote.objects.select_for_update().filter(owner=self.owner).values_list("id", flat=True))
            current = ShipmentNote.objects.select_for_update().get(pk=self.pk)
            if current.status == self.Status.SENT:
                self.number, self.status, self.sent_at = current.number, current.status, current.sent_at
                return
            last = ShipmentNote.objects.filter(owner=self.owner).aggregate(models.Max("number"))["number__max"] or 0
            self.number = last + 1
            self.status = self.Status.SENT
            self.sent_at = timezone.now()
            self.save(update_fields=["number", "status", "sent_at", "updated_at"])


class ShipmentItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(ShipmentNote, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField(default=0)
    production_order = models.CharField("Ordem de produção", max_length=40)
    drawing_number = models.CharField("Nº do desenho", max_length=60)
    quantity = models.PositiveIntegerField("Quantidade", default=1)
    description = models.CharField("Descrição", max_length=120, blank=True, default="")

    class Meta:
        ordering = ["position", "id"]


class ShipmentRecipient(models.Model):
    """Encarregado ou supervisor: cada um recebe o proprio link (token) e deixa visto/autorizacao."""

    class Role(models.TextChoices):
        ENCARREGADO = "ENCARREGADO", "Encarregado"
        SUPERVISOR = "SUPERVISOR", "Supervisor"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(ShipmentNote, on_delete=models.CASCADE, related_name="recipients")
    role = models.CharField(max_length=12, choices=Role.choices)
    name = models.CharField("Nome", max_length=80, blank=True, default="")
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True, default="")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["role"]
        constraints = [models.UniqueConstraint(fields=["note", "role"], name="shipment_one_recipient_per_role")]

    def mark_viewed(self):
        """Registra o primeiro visto; devolve True so quando mudou algo."""
        if self.viewed_at:
            return False
        self.viewed_at = timezone.now()
        self.save(update_fields=["viewed_at"])
        return True

    def authorize(self):
        """Registra a primeira autorizacao (e o visto, se faltava); repetir nao muda o horario."""
        if self.authorized_at:
            return False
        now = timezone.now()
        self.authorized_at = now
        self.viewed_at = self.viewed_at or now
        self.save(update_fields=["authorized_at", "viewed_at"])
        return True
