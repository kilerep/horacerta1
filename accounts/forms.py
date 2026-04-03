from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import Q

from companies.models import Company, Employee
from timeclock.models import Contract

User = get_user_model()


class UnifiedSignupForm(forms.Form):
    ROLE_CHOICES = (
        ("EMPRESA", "Empresa (RH/Admin)"),
        ("FUNCIONARIO", "Funcionario / MEI"),
    )

    account_type = forms.ChoiceField(
        label="Tipo de conta",
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
    )

    # Campos EMPRESA
    company_name = forms.CharField(label="Nome da empresa", max_length=120, required=False)
    company_email = forms.EmailField(label="Email da empresa (opcional)", required=False)
    rh_email = forms.EmailField(label="Email do RH/Admin", required=False)

    # Campos MEI
    full_name = forms.CharField(label="Nome completo", max_length=120, required=False)
    mei_email = forms.EmailField(label="Email do MEI", required=False)

    # Senha (para ambos)
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def _clear_irrelevant_fields(self, field_names):
        # Remove erros e valores de campos que nao pertencem ao tipo escolhido.
        for field_name in field_names:
            self.cleaned_data[field_name] = ""
            if field_name in self.errors:
                del self.errors[field_name]

    def clean(self):
        data = super().clean()

        acc_type = data.get("account_type")
        pwd1 = data.get("password1")
        pwd2 = data.get("password2")

        if pwd1 != pwd2:
            self.add_error("password2", "As senhas nao conferem.")

        if acc_type == "EMPRESA":
            self._clear_irrelevant_fields(("full_name", "mei_email"))

            if not data.get("company_name"):
                self.add_error("company_name", "Informe o nome da empresa.")

            if not data.get("rh_email"):
                self.add_error("rh_email", "Informe o email do RH/Admin.")
            else:
                email = data["rh_email"].strip().lower()
                if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
                    self.add_error("rh_email", "Ja existe um usuario com esse email.")

        elif acc_type == "FUNCIONARIO":
            self._clear_irrelevant_fields(("company_name", "company_email", "rh_email"))

            if not data.get("full_name"):
                self.add_error("full_name", "Informe seu nome completo.")

            if not data.get("mei_email"):
                self.add_error("mei_email", "Informe seu email.")
            else:
                email = data["mei_email"].strip().lower()
                if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
                    self.add_error("mei_email", "Ja existe um usuario com esse email.")

        return data


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Email ou usuario")  # aceita email via backend


class EmployeeSearchForm(forms.Form):
    q = forms.CharField(
        label="Buscar funcionario",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Nome ou email"}),
    )


class PeriodSearchForm(forms.Form):
    date_from = forms.DateField(
        label="De",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Ate",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class CompanyMEICreateForm(forms.Form):
    full_name = forms.CharField(
        label="Nome completo",
        max_length=120,
    )
    mei_email = forms.EmailField(label="Email do MEI")
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas nao conferem.")
        return data

    def clean_mei_email(self):
        email = (self.cleaned_data.get("mei_email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Ja existe um usuario com esse email.")
        return email

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def create_mei_for_company(self, company):
        if not company:
            raise ValueError("Company is required to create MEI.")

        with transaction.atomic():
            mei_email = self.cleaned_data["mei_email"].strip().lower()
            user = User.objects.create_user(
                username=mei_email,
                email=mei_email,
                password=self.cleaned_data["password1"],
                role=User.Role.FUNCIONARIO,
            )
            employee = Employee.objects.create(
                user=user,
                company=company,
                full_name=self.cleaned_data["full_name"],
                is_active=True,
            )
        return employee


class EmployeeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        user = getattr(obj, "user", None)
        email = (getattr(user, "email", "") or getattr(user, "username", "")).strip()
        if email:
            return f"{obj.full_name} - {email}"
        return obj.full_name


class CompanyContractForm(forms.ModelForm):
    employee = EmployeeChoiceField(
        label="MEI",
        queryset=Employee.objects.none(),
    )

    class Meta:
        model = Contract
        fields = [
            "hourly_rate",
            "start_date",
            "end_date",
            "contract_file",
            "is_active",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Observacoes do contrato (opcional)"}),
        }

    def __init__(self, *args, company=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if self.company is None and request is not None and getattr(request.user, "is_authenticated", False):
            self.company = Company.objects.filter(owner=request.user).first()

        self.fields["contract_file"].required = False
        self.fields["end_date"].required = False
        self.fields["notes"].required = False

        employee_queryset = Employee.objects.none()
        if self.company:
            employee_queryset = Employee.objects.filter(
                company=self.company,
                user__role=User.Role.FUNCIONARIO,
                user__isnull=False,
            )
            if self.instance and self.instance.pk and self.instance.employee_id:
                employee_queryset = employee_queryset.filter(Q(is_active=True) | Q(id=self.instance.employee_id))
            else:
                employee_queryset = employee_queryset.filter(is_active=True)
            employee_queryset = employee_queryset.select_related("user").order_by("full_name")

        self.fields["employee"].queryset = employee_queryset

        if self.instance and self.instance.pk and self.instance.employee_id:
            initial_employee = self.fields["employee"].queryset.filter(id=self.instance.employee_id).first()
            if initial_employee:
                self.initial["employee"] = initial_employee

    def clean(self):
        data = super().clean()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        employee = data.get("employee")

        if not employee:
            self.add_error("employee", "Selecione um MEI valido.")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "A data final nao pode ser anterior a data inicial.")

        if self.company and employee and employee.company_id != self.company.id:
            self.add_error("employee", "Selecione um MEI da sua empresa.")
        if employee and not employee.user_id:
            self.add_error("employee", "MEI selecionado sem usuario valido.")
        if employee and not employee.company_id:
            self.add_error("employee", "MEI selecionado sem empresa valida.")
        return data

    def clean_contract_file(self):
        file_obj = self.cleaned_data.get("contract_file")
        if not file_obj:
            return file_obj

        if not file_obj.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Envie um arquivo PDF (.pdf).")
        return file_obj

    def save(self, commit=True):
        contract = super().save(commit=False)
        employee = self.cleaned_data.get("employee")
        if employee:
            contract.employee = employee
        if self.company and not contract.company_id:
            contract.company = self.company
        if commit:
            contract.save()
        return contract


class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "cnpj", "email", "phone", "address", "logo"]
        labels = {
            "name": "Nome da empresa",
            "cnpj": "CNPJ",
            "email": "Email",
            "phone": "Telefone",
            "address": "Endereco",
            "logo": "Logo",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class MEIProfileForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "document", "phone", "address", "profile_photo"]
        labels = {
            "full_name": "Nome completo",
            "document": "CPF ou CNPJ",
            "phone": "Telefone",
            "address": "Endereco",
            "profile_photo": "Foto de perfil",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        data = super().clean()
        if self.instance and not self.instance.company_id:
            raise forms.ValidationError("Perfil MEI sem empresa vinculada.")
        if self.instance and not self.instance.user_id:
            raise forms.ValidationError("Perfil MEI sem usuario vinculado.")
        return data
