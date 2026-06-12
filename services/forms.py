from django import forms

from accounts.mei_context import mei_contracts_for_user
from timeclock.models import Contract

from .models import ServiceCategory, ServiceItemExpense, ServiceJob, ServiceWorkLog


class ServiceJobForm(forms.ModelForm):
    contract = forms.ModelChoiceField(
        queryset=Contract.objects.none(),
        required=False,
        empty_label="Sem cliente fixo",
        label="Cliente cadastrado",
    )

    class Meta:
        model = ServiceJob
        fields = [
            "contract",
            "manual_client_name",
            "category",
            "title",
            "description",
            "service_location",
            "start_date",
            "end_date",
            "status",
            "hourly_rate_snapshot",
            "fixed_labor_value",
            "notes",
        ]
        labels = {
            "manual_client_name": "Nome manual do cliente",
            "category": "Categoria",
            "title": "Titulo do servico",
            "description": "O que sera feito",
            "service_location": "Local do servico",
            "start_date": "Data inicial",
            "end_date": "Data final",
            "status": "Status",
            "hourly_rate_snapshot": "Valor por hora",
            "fixed_labor_value": "Valor fixo da mao de obra",
            "notes": "Anotacoes internas",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "hourly_rate_snapshot": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "fixed_labor_value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.instance.professional = user
        self.fields["contract"].queryset = mei_contracts_for_user(
            user,
            include_inactive_contracts=True,
        )
        self.fields["category"].queryset = ServiceCategory.objects.filter(is_active=True)
        self.fields["manual_client_name"].help_text = "Use apenas quando o cliente ainda nao estiver cadastrado."
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def clean_manual_client_name(self):
        return (self.cleaned_data.get("manual_client_name") or "").strip()

    def clean_title(self):
        return (self.cleaned_data.get("title") or "").strip()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_service_location(self):
        return (self.cleaned_data.get("service_location") or "").strip()

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.professional = self.user
        contract = self.cleaned_data.get("contract")
        if contract:
            instance.contract = contract
            instance.client = contract.company
            if not instance.hourly_rate_snapshot:
                instance.hourly_rate_snapshot = contract.hourly_rate or 0
        else:
            instance.contract = None
            instance.client = None
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
            "description": "Descricao",
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
            "description": "Descricao",
            "quantity": "Quantidade",
            "unit_value": "Valor unitario",
            "usage_status": "Status de uso",
            "receipt_note": "Nota/recibo",
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
