from django import forms

from accounts.mei_context import mei_contracts_for_user
from timeclock.models import Contract

from .models import ServiceCategory, ServiceJob


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
