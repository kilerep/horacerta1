from django import forms

from accounts.mei_context import mei_contracts_for_user
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceJob, ServiceWorkLog


class ServiceJobForm(forms.ModelForm):
    client_mode = forms.ChoiceField(
        choices=(("registered", "Cliente cadastrado"), ("casual", "Cliente avulso")),
        required=False,
        widget=forms.RadioSelect,
        label="Tipo de cliente",
    )
    contract = forms.ModelChoiceField(
        queryset=Contract.objects.none(),
        required=False,
        empty_label="Selecione um cliente cadastrado",
        label="Cliente cadastrado",
    )

    class Meta:
        model = ServiceJob
        fields = [
            "contract",
            "manual_client_name",
            "manual_client_whatsapp",
            "manual_client_email",
            "service_zip_code",
            "service_street",
            "service_number",
            "service_complement",
            "service_district",
            "service_city",
            "service_state",
            "service_reference",
            "category",
            "title",
            "description",
            "start_date",
            "planned_start_time",
            "planned_end_time",
            "billing_mode",
            "hourly_rate_snapshot",
            "fixed_labor_value",
            "notes",
        ]
        labels = {
            "manual_client_name": "Nome do cliente",
            "manual_client_whatsapp": "WhatsApp",
            "manual_client_email": "E-mail",
            "service_zip_code": "CEP",
            "service_street": "Rua",
            "service_number": "Numero",
            "service_complement": "Complemento",
            "service_district": "Bairro",
            "service_city": "Cidade",
            "service_state": "UF",
            "service_reference": "Ponto de referencia",
            "category": "Categoria",
            "title": "Titulo do servico",
            "description": "O que sera feito",
            "start_date": "Data prevista",
            "planned_start_time": "Hora inicial prevista",
            "planned_end_time": "Hora final prevista",
            "billing_mode": "Modo de cobranca",
            "hourly_rate_snapshot": "Valor por hora",
            "fixed_labor_value": "Valor fixo da mao de obra",
            "notes": "Observacoes finais do prestador",
        }
        widgets = {
            "manual_client_whatsapp": forms.TextInput(attrs={"placeholder": "Opcional"}),
            "manual_client_email": forms.EmailInput(attrs={"placeholder": "Opcional"}),
            "service_zip_code": forms.TextInput(attrs={"placeholder": "00000-000", "inputmode": "numeric"}),
            "service_street": forms.TextInput(attrs={"placeholder": "Rua, avenida ou estrada"}),
            "service_number": forms.TextInput(attrs={"placeholder": "Numero"}),
            "service_complement": forms.TextInput(attrs={"placeholder": "Casa, bloco, sala..."}),
            "service_district": forms.TextInput(attrs={"placeholder": "Bairro"}),
            "service_city": forms.TextInput(attrs={"placeholder": "Cidade"}),
            "service_state": forms.TextInput(attrs={"placeholder": "UF", "maxlength": "2"}),
            "service_reference": forms.TextInput(attrs={"placeholder": "Ponto de referencia, opcional"}),
            "title": forms.TextInput(attrs={"placeholder": "Ex.: Revisao eletrica residencial"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Ex.: Troca de disjuntores, revisão de tomadas e teste do quadro elétrico.",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Observacoes finais, combinados ou pendencias do atendimento."}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "planned_start_time": forms.TimeInput(attrs={"type": "time"}),
            "planned_end_time": forms.TimeInput(attrs={"type": "time"}),
            "hourly_rate_snapshot": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "fixed_labor_value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.instance.professional = user
        self.fields["client_mode"].initial = "registered"
        self.fields["billing_mode"].initial = ServiceJob.BillingMode.UNDEFINED
        if self.instance and self.instance.pk:
            self.fields["client_mode"].initial = "registered" if self.instance.contract_id else "casual"
            self.fields["billing_mode"].initial = self.instance.billing_mode
            self.fields["contract"].initial = self.instance.contract
        self.fields["billing_mode"].required = False
        self.fields["hourly_rate_snapshot"].required = False
        self.fields["contract"].queryset = mei_contracts_for_user(
            user,
            include_inactive_contracts=True,
        )
        self.fields["contract"].label_from_instance = self._contract_label
        self.fields["category"].queryset = ServiceCategory.objects.filter(is_active=True)
        self.fields["manual_client_name"].help_text = "Use quando o cliente nao estiver cadastrado no HoraCerta."
        self.fields["start_date"].help_text = "Use a previsao para organizar o atendimento. As horas realizadas serão registradas dentro do serviço."
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def _contract_label(self, contract):
        company_name = getattr(getattr(contract, "company", None), "name", "Cliente")
        hourly_rate = getattr(contract, "hourly_rate", None)
        if hourly_rate:
            return f"{company_name} - R$ {hourly_rate}/h"
        return f"{company_name} - cliente cadastrado"

    def clean_client_mode(self):
        mode = (self.cleaned_data.get("client_mode") or "").strip()
        if mode:
            return mode
        return "registered" if self.data.get("contract") else "casual"

    def clean_manual_client_name(self):
        return (self.cleaned_data.get("manual_client_name") or "").strip()

    def clean_manual_client_whatsapp(self):
        return (self.cleaned_data.get("manual_client_whatsapp") or "").strip()

    def clean_manual_client_email(self):
        value = (self.cleaned_data.get("manual_client_email") or "").strip().lower()
        return value or None

    def clean_service_zip_code(self):
        value = (self.cleaned_data.get("service_zip_code") or "").strip()
        digits = "".join(ch for ch in value if ch.isdigit())
        if value and len(digits) != 8:
            raise forms.ValidationError("Informe um CEP com 8 digitos.")
        return value

    def clean_service_state(self):
        return (self.cleaned_data.get("service_state") or "").strip().upper()

    def clean_billing_mode(self):
        mode = (self.cleaned_data.get("billing_mode") or "").strip()
        if mode:
            return mode
        if self.data.get("fixed_labor_value"):
            return ServiceJob.BillingMode.FIXED
        if self.data.get("hourly_rate_snapshot") or self.data.get("contract"):
            return ServiceJob.BillingMode.HOURLY
        return ServiceJob.BillingMode.UNDEFINED

    def clean_title(self):
        return (self.cleaned_data.get("title") or "").strip()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_service_location(self):
        return (self.cleaned_data.get("service_location") or "").strip()

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()

    def clean(self):
        data = super().clean()
        mode = data.get("client_mode")
        contract = data.get("contract")
        if mode == "registered" and not contract:
            self.add_error("contract", "Selecione um cliente cadastrado ou escolha cliente avulso.")
        if mode == "casual" and not data.get("manual_client_name"):
            self.add_error("manual_client_name", "Informe o nome do cliente avulso.")
        billing_mode = data.get("billing_mode")
        if billing_mode == ServiceJob.BillingMode.HOURLY and not data.get("hourly_rate_snapshot") and not contract:
            self.add_error("hourly_rate_snapshot", "Informe o valor/hora ou escolha outro modo de cobranca.")
        if billing_mode == ServiceJob.BillingMode.FIXED and data.get("fixed_labor_value") in (None, ""):
            self.add_error("fixed_labor_value", "Informe o valor fixo ou escolha outro modo de cobranca.")
        return data

    def save(self, commit=True, status=None):
        instance = super().save(commit=False)
        instance.professional = self.user
        contract = self.cleaned_data.get("contract")
        client_mode = self.cleaned_data.get("client_mode")
        if client_mode == "registered" and contract:
            instance.contract = contract
            instance.client = contract.company
            if instance.billing_mode == ServiceJob.BillingMode.HOURLY and not instance.hourly_rate_snapshot:
                instance.hourly_rate_snapshot = contract.hourly_rate or 0
        else:
            instance.contract = None
            instance.client = None
        if instance.hourly_rate_snapshot in (None, ""):
            instance.hourly_rate_snapshot = 0
        if status:
            instance.status = status
        instance.end_date = instance.start_date
        address_parts = [
            instance.service_street,
            instance.service_number,
            instance.service_complement,
            instance.service_district,
            instance.service_city,
            instance.service_state,
        ]
        instance.service_location = ", ".join(part for part in address_parts if part)
        if commit:
            instance.save()
        return instance


class ServiceWorkLogForm(forms.ModelForm):
    class Meta:
        model = ServiceWorkLog
        fields = ["work_date", "start_time", "end_time", "description"]
        labels = {
            "work_date": "Data",
            "start_time": "Inicio",
            "end_time": "Fim",
            "description": "Atividade realizada",
        }
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.TextInput(attrs={"placeholder": "Ex.: Troca das tomadas da sala"}),
        }

    def __init__(self, *args, service_job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_job = service_job
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.service_job = self.service_job
        if commit:
            instance.save()
        return instance


class ServiceItemExpenseForm(forms.ModelForm):
    class Meta:
        model = ServiceItemExpense
        fields = [
            "type",
            "name",
            "description",
            "quantity",
            "unit_value",
            "usage_status",
            "receipt_note",
        ]
        labels = {
            "type": "Tipo",
            "name": "Nome",
            "description": "Observacao",
            "quantity": "Quantidade",
            "unit_value": "Valor unitario",
            "usage_status": "Status de uso",
            "receipt_note": "Observacao",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "unit_value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "receipt_note": forms.TextInput(attrs={"placeholder": "Ex.: cupom, NF ou observacao"}),
        }

    def __init__(self, *args, service_job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_job = service_job
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_receipt_note(self):
        return (self.cleaned_data.get("receipt_note") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.service_job = self.service_job
        if commit:
            instance.save()
        return instance
