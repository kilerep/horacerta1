import re

from django import forms

from .models import ProductionEntry, ProductionSheet


def parse_duration(value):
    """Aceita '4', '4h', '1:30', '1h30', '1,5', '90min'. Devolve minutos (int) ou None."""
    text = (value or "").strip().lower().replace(" ", "")
    if not text:
        return None
    m = re.fullmatch(r"(\d+)min", text)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"(\d+)(?::|h)(\d{1,2})(?:min)?", text)
    if m:
        hours, mins = int(m.group(1)), int(m.group(2))
        if mins >= 60:
            raise forms.ValidationError("Minutos devem ficar entre 0 e 59 (ex.: 1:30).")
        return hours * 60 + mins
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)h?", text)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 60)
    raise forms.ValidationError("Use horas como 4, 1:30 ou 1,5.")


class ProductionSheetForm(forms.ModelForm):
    class Meta:
        model = ProductionSheet
        fields = ["equipment", "company_name", "operator_name", "supervisor_name", "supervisor_whatsapp", "notes"]
        widgets = {
            "equipment": forms.TextInput(attrs={"list": "equipment-suggestions", "placeholder": "Ex.: Chenlong", "autocomplete": "off"}),
            "company_name": forms.TextInput(attrs={"placeholder": "Opcional"}),
            "operator_name": forms.TextInput(attrs={"placeholder": "Seu nome"}),
            "supervisor_name": forms.TextInput(attrs={"placeholder": "Opcional"}),
            "supervisor_whatsapp": forms.TextInput(attrs={"placeholder": "(11) 99999-9999", "inputmode": "tel", "autocomplete": "off"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Opcional"}),
        }

    def clean_equipment(self):
        value = " ".join((self.cleaned_data.get("equipment") or "").split())
        if not value:
            raise forms.ValidationError("Informe a máquina ou equipamento.")
        return value

    def clean_supervisor_whatsapp(self):
        digits = re.sub(r"\D", "", self.cleaned_data.get("supervisor_whatsapp") or "")
        if digits and not 10 <= len(digits) <= 13:
            raise forms.ValidationError("Use o número com DDD, ex.: (11) 99999-9999.")
        return digits


class ProductionEntryForm(forms.ModelForm):
    duration = forms.CharField(
        label="Duração (se não tiver horário)", required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: 1:30", "inputmode": "decimal"}),
    )

    class Meta:
        model = ProductionEntry
        fields = ["work_date", "item_code", "destination", "start_time", "end_time", "note"]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "item_code": forms.TextInput(attrs={"placeholder": "Ex.: 0011-024", "autocomplete": "off"}),
            "destination": forms.RadioSelect,
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "note": forms.TextInput(attrs={"placeholder": "Opcional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].choices = list(ProductionEntry.Destination.choices)
        self.fields["destination"].required = False
        if self.instance and self.instance.pk and self.instance.manual_minutes is not None and not self.is_bound:
            m = self.instance.manual_minutes
            self.initial["duration"] = f"{m // 60}:{m % 60:02d}"

    def clean_item_code(self):
        return (self.cleaned_data.get("item_code") or "").strip()

    def clean_duration(self):
        return parse_duration(self.cleaned_data.get("duration"))

    def clean(self):
        data = super().clean()
        start, end, minutes = data.get("start_time"), data.get("end_time"), data.get("duration")
        if end and not start:
            self.add_error("start_time", "Informe o início para usar o horário de fim.")
        if minutes is not None and minutes <= 0:
            self.add_error("duration", "A duração precisa ser maior que zero.")
        if not any([data.get("item_code"), start, minutes, data.get("note")]):
            raise forms.ValidationError("Preencha pelo menos o código do item, o início ou a duração.")
        return data

    def save(self, commit=True):
        entry = super().save(commit=False)
        has_times = entry.start_time and entry.end_time
        entry.manual_minutes = None if has_times else self.cleaned_data.get("duration")
        if commit:
            entry.save()
        return entry
