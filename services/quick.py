"""Servico rapido: o caminho mais curto para quem so quer atender um cliente.

Quatro campos (cliente, WhatsApp, o que vai fazer, valor) criam o servico e levam
direto para a tela dele, onde ficam itens, orcamento, horas e relatorio. O formulario
completo continua existindo para quem quer preencher tudo.
"""

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import ServiceCategory, ServiceJob
from .views import _redirect_if_not_mei
from .workflow import planned_status_for_service

QUICK_CATEGORY_SLUG = "servico-geral"


def parse_brl(value):
    """'150' / '150,50' / '1.500,00' / 'R$ 150' -> Decimal; vazio -> None."""
    text = re.sub(r"[^\d,.]", "", value or "")
    if not text:
        return None
    if "," in text:  # formato brasileiro: ponto separa milhar, virgula separa centavos
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise forms.ValidationError("Digite o valor como 150 ou 150,50.")
    if amount < 0:
        raise forms.ValidationError("O valor não pode ser negativo.")
    return amount


class QuickServiceForm(forms.Form):
    client_name = forms.CharField(
        label="Cliente", max_length=120, error_messages={"required": "Informe o nome do cliente."},
        widget=forms.TextInput(attrs={"placeholder": "Nome de quem vai receber o serviço", "autocomplete": "off"}),
    )
    client_whatsapp = forms.CharField(
        label="WhatsApp do cliente (opcional)", max_length=30, required=False,
        widget=forms.TextInput(attrs={"placeholder": "(11) 99999-9999", "inputmode": "tel", "autocomplete": "off"}),
    )
    title = forms.CharField(
        label="O que você vai fazer", max_length=140,
        error_messages={"required": "Diga em poucas palavras o que vai ser feito."},
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Trocar chuveiro, instalar 3 tomadas", "autocomplete": "off"}),
    )
    price = forms.CharField(
        label="Valor combinado (opcional)", max_length=20, required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: 150,00", "inputmode": "decimal", "autocomplete": "off"}),
    )
    start_date = forms.DateField(
        label="Quando (opcional)", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def clean_client_name(self):
        value = " ".join((self.cleaned_data.get("client_name") or "").split())
        if not value:
            raise forms.ValidationError("Informe o nome do cliente.")
        return value

    def clean_title(self):
        value = " ".join((self.cleaned_data.get("title") or "").split())
        if not value:
            raise forms.ValidationError("Diga em poucas palavras o que vai ser feito.")
        return value

    def clean_client_whatsapp(self):
        digits = re.sub(r"\D", "", self.cleaned_data.get("client_whatsapp") or "")
        if digits and not 10 <= len(digits) <= 13:
            raise forms.ValidationError("Use o número com DDD, ex.: (11) 99999-9999.")
        return digits

    def clean_price(self):
        return parse_brl(self.cleaned_data.get("price"))


def _quick_category():
    return (
        ServiceCategory.objects.filter(slug=QUICK_CATEGORY_SLUG).first()
        or ServiceCategory.objects.order_by("name").first()
    )


@login_required
def service_job_quick(request):
    denied = _redirect_if_not_mei(request)
    if denied:
        return denied

    category = _quick_category()
    if request.method == "POST":
        form = QuickServiceForm(request.POST)
        if category is None:
            form.add_error(None, "Nenhuma categoria de serviço cadastrada. Use o formulário completo.")
        if form.is_valid():
            data = form.cleaned_data
            price = data["price"]
            job = ServiceJob(
                professional=request.user,
                category=category,
                manual_client_name=data["client_name"],
                manual_client_whatsapp=data["client_whatsapp"],
                title=data["title"],
                start_date=data["start_date"],
                billing_mode=ServiceJob.BillingMode.FIXED if price else ServiceJob.BillingMode.UNDEFINED,
                fixed_labor_value=price,
                status=ServiceJob.Status.DRAFT,
            )
            job.full_clean()
            job.save()
            status = planned_status_for_service(job, requested_status=ServiceJob.Status.PLANNED)
            if status != job.status:
                job.status = status
                job.save(update_fields=["status", "updated_at"])
            messages.success(request, "Serviço criado. Agora é só adicionar itens ou enviar o orçamento.")
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = QuickServiceForm(initial={"start_date": timezone.localdate()})

    return render(request, "services/service_job_quick.html", {"form": form})
