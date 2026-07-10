from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import ServiceItemExpense, ServiceJob
from .workflow import planned_status_for_service


class RepeatServiceForm(forms.Form):
    title = forms.CharField(label="Título da próxima visita", max_length=140)
    next_date = forms.DateField(
        label="Data da próxima visita",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    planned_start_time = forms.TimeField(
        label="Horário de início",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    planned_end_time = forms.TimeField(
        label="Horário de término",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    copy_items = forms.BooleanField(
        label="Copiar itens, materiais e recursos como previstos",
        required=False,
        initial=True,
    )
    copy_notes = forms.BooleanField(
        label="Copiar observações do serviço anterior",
        required=False,
        initial=True,
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("planned_start_time")
        end = cleaned.get("planned_end_time")
        if start and end and end <= start:
            self.add_error("planned_end_time", "O horário final precisa ser maior que o horário inicial.")
        return cleaned


def _initial_date(job):
    base = job.start_date or timezone.localdate()
    category_slug = job.category.slug if job.category_id else ""
    weekly_categories = {"limpeza-conservacao", "jardinagem-paisagismo", "beleza-bem-estar", "aulas-consultoria"}
    return base + timedelta(days=7 if category_slug in weekly_categories else 30)


def _clone_items(source, target):
    clones = []
    for item in source.item_expenses.all():
        clones.append(
            ServiceItemExpense(
                service_job=target,
                catalog_item=item.catalog_item,
                type=item.type,
                name=item.name,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                unit_value=item.unit_value,
                usage_status=ServiceItemExpense.UsageStatus.PLANNED,
                receipt_note="",
            )
        )
    for clone in clones:
        clone.save()
    return len(clones)


@login_required
def service_job_repeat(request, job_id):
    source = get_object_or_404(
        ServiceJob.objects.select_related("professional", "client", "contract", "category").prefetch_related("item_expenses"),
        id=job_id,
        professional=request.user,
    )

    initial = {
        "title": source.title,
        "next_date": _initial_date(source),
        "planned_start_time": source.planned_start_time,
        "planned_end_time": source.planned_end_time,
        "copy_items": True,
        "copy_notes": True,
    }
    form = RepeatServiceForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        old_days = 0
        if source.start_date and source.end_date:
            old_days = max((source.end_date - source.start_date).days, 0)
        next_date = form.cleaned_data["next_date"]

        with transaction.atomic():
            job = ServiceJob.objects.create(
                professional=request.user,
                client=source.client,
                contract=source.contract,
                manual_client_name=source.manual_client_name,
                manual_client_whatsapp=source.manual_client_whatsapp,
                manual_client_email=source.manual_client_email,
                category=source.category,
                title=form.cleaned_data["title"].strip(),
                description=source.description,
                service_location=source.service_location,
                service_zip_code=source.service_zip_code,
                service_street=source.service_street,
                service_number=source.service_number,
                service_complement=source.service_complement,
                service_district=source.service_district,
                service_city=source.service_city,
                service_state=source.service_state,
                service_reference=source.service_reference,
                start_date=next_date,
                end_date=next_date + timedelta(days=old_days) if old_days else None,
                planned_start_time=form.cleaned_data.get("planned_start_time"),
                planned_end_time=form.cleaned_data.get("planned_end_time"),
                status=ServiceJob.Status.DRAFT,
                billing_mode=source.billing_mode,
                hourly_rate_snapshot=source.hourly_rate_snapshot,
                fixed_labor_value=source.fixed_labor_value,
                notes=source.notes if form.cleaned_data.get("copy_notes") else "",
            )
            if form.cleaned_data.get("copy_items"):
                copied = _clone_items(source, job)
            else:
                copied = 0
            job.status = planned_status_for_service(job, requested_status=ServiceJob.Status.PLANNED)
            job.save(update_fields=["status", "finished_at", "updated_at"])

        messages.success(
            request,
            f"Próxima visita criada para {next_date.strftime('%d/%m/%Y')}. {copied} item(ns) copiado(s) como previstos.",
        )
        return redirect("service_job_detail", job_id=job.id)

    return render(
        request,
        "services/service_job_repeat.html",
        {
            "form": form,
            "source": source,
        },
    )
