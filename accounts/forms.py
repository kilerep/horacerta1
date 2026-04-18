from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from companies.models import Company, CompanyAttendancePolicy, CompanyAuthorizedLocation, Employee
from timeclock.models import ActivityReportRequest, Contract, ServiceReport

User = get_user_model()


class UnifiedSignupForm(forms.Form):
    company_name = forms.CharField(label="Nome da empresa", max_length=120, required=False)
    company_email = forms.EmailField(label="Email da empresa (opcional)", required=False)
    rh_email = forms.EmailField(label="Email do RH/Admin", required=False)
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        pwd1 = data.get("password1")
        pwd2 = data.get("password2")

        if pwd1 != pwd2:
            self.add_error("password2", "As senhas nao conferem.")

        company_name = (data.get("company_name") or "").strip()
        if not company_name:
            self.add_error("company_name", "Informe o nome da empresa.")
        else:
            data["company_name"] = company_name

        company_email = (data.get("company_email") or "").strip().lower()
        data["company_email"] = company_email

        rh_email = (data.get("rh_email") or "").strip().lower()
        if not rh_email:
            self.add_error("rh_email", "Informe o email do RH/Admin.")
        else:
            data["rh_email"] = rh_email
            if User.objects.filter(email__iexact=rh_email).exists() or User.objects.filter(username__iexact=rh_email).exists():
                self.add_error("rh_email", "Ja existe um usuario com esse email.")

        return data


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Email ou usuario")  # aceita email via backend


class EmployeeSearchForm(forms.Form):
    q = forms.CharField(
        label="Buscar MEI",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Buscar MEI por nome ou email"}),
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


class ServiceReportCreateForm(forms.ModelForm):
    contract = forms.ModelChoiceField(
        label="Vinculo/empresa",
        queryset=Contract.objects.none(),
        empty_label="Selecione um vinculo",
    )

    class Meta:
        model = ServiceReport
        fields = ["report_date", "contract", "title", "description"]
        widgets = {
            "report_date": forms.DateInput(attrs={"type": "date"}),
            "title": forms.TextInput(attrs={"placeholder": "Resumo curto do servico executado"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Descreva o trabalho realizado no dia, entregas e contexto operacional.",
                }
            ),
        }
        labels = {
            "report_date": "Data do servico",
            "title": "Titulo",
            "description": "Descricao do servico",
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        contracts_qs = Contract.objects.none()
        if employee:
            contracts_qs = (
                Contract.objects.filter(
                    employee=employee,
                    is_active=True,
                    company__isnull=False,
                )
                .select_related("company")
                .order_by("company__name", "-start_date", "-created_at")
            )
        self.fields["contract"].queryset = contracts_qs
        self.fields["contract"].label_from_instance = (
            lambda obj: f"{obj.company.name} | inicio {obj.start_date.strftime('%d/%m/%Y') if obj.start_date else '-'} | R$ {obj.hourly_rate}/h"
        )

    def clean_contract(self):
        contract = self.cleaned_data.get("contract")
        if not contract:
            return contract
        if self.employee and contract.employee_id != self.employee.id:
            raise forms.ValidationError("Selecione um vinculo valido do seu perfil.")
        return contract

    def save(self, commit=True):
        report = super().save(commit=False)
        if self.employee:
            report.employee = self.employee
            report.company = self.employee.company
        contract = self.cleaned_data.get("contract")
        if contract:
            report.contract = contract
            report.company = contract.company
            report.employee = contract.employee
        if commit:
            report.save()
        return report


class CompanyActivityReportRequestForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        label="Profissional",
        queryset=Employee.objects.none(),
    )
    contract = forms.ModelChoiceField(
        label="Vinculo (opcional)",
        queryset=Contract.objects.none(),
        required=False,
        empty_label="Selecionar depois",
    )

    class Meta:
        model = ActivityReportRequest
        fields = ["employee", "contract", "date_from", "date_to", "subject", "instruction"]
        widgets = {
            "date_from": forms.DateInput(attrs={"type": "date"}),
            "date_to": forms.DateInput(attrs={"type": "date"}),
            "subject": forms.TextInput(attrs={"placeholder": "Ex.: Relatorio de servico semanal"}),
            "instruction": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Instrucao curta para orientar o profissional na resposta.",
                }
            ),
        }
        labels = {
            "date_from": "Data inicial",
            "date_to": "Data final",
            "subject": "Titulo/assunto",
            "instruction": "Instrucao",
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        employee_qs = Employee.objects.none()
        contract_qs = Contract.objects.none()
        if company:
            employee_qs = (
                Employee.objects.filter(company=company, user__role=User.Role.FUNCIONARIO, user__isnull=False)
                .select_related("user")
                .order_by("full_name")
            )
            contract_qs = (
                Contract.objects.filter(
                    company=company,
                    employee__in=employee_qs,
                    employee__isnull=False,
                    employee__user__isnull=False,
                )
                .select_related("employee", "employee__user", "company")
                .order_by("employee__full_name", "-start_date", "-created_at")
            )
        self.fields["employee"].queryset = employee_qs
        self.fields["employee"].label_from_instance = (
            lambda obj: f"{obj.full_name} - {(obj.user.email or obj.user.username)}"
        )
        self.fields["contract"].queryset = contract_qs
        self.fields["contract"].label_from_instance = (
            lambda obj: (
                f"{obj.employee.full_name} | inicio {obj.start_date.strftime('%d/%m/%Y') if obj.start_date else '-'}"
                f" | R$ {obj.hourly_rate}/h"
            )
        )

    def clean(self):
        data = super().clean()
        employee = data.get("employee")
        contract = data.get("contract")
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        subject = (data.get("subject") or "").strip()
        instruction = (data.get("instruction") or "").strip()

        if not subject:
            self.add_error("subject", "Informe o titulo da solicitacao.")
        if not (date_from or date_to):
            self.add_error("date_from", "Informe uma data ou periodo para a solicitacao.")
        if date_from and date_to and date_to < date_from:
            self.add_error("date_to", "Data final nao pode ser anterior a data inicial.")

        if self.company and employee and employee.company_id != self.company.id:
            self.add_error("employee", "Selecione um profissional da sua empresa.")
        if contract and employee and contract.employee_id != employee.id:
            self.add_error("contract", "O vinculo selecionado deve pertencer ao profissional escolhido.")
        if self.company and contract and contract.company_id != self.company.id:
            self.add_error("contract", "Selecione um vinculo da sua empresa.")

        data["subject"] = subject
        data["instruction"] = instruction
        return data

    def save(self, commit=True, requested_by=None):
        request_obj = super().save(commit=False)
        if self.company:
            request_obj.company = self.company
        if requested_by:
            request_obj.requested_by = requested_by
        request_obj.message = request_obj.instruction
        request_obj.status = ActivityReportRequest.Status.PENDING
        if commit:
            request_obj.save()
        return request_obj


class CompanyMEICreateForm(forms.Form):
    full_name = forms.CharField(
        label="Nome completo",
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Nome completo do MEI"}),
    )
    mei_email = forms.EmailField(
        label="Email do MEI",
        widget=forms.EmailInput(attrs={"placeholder": "mei@empresa.com"}),
    )
    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Defina uma senha segura", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Repita a senha", "autocomplete": "new-password"}),
    )
    contract_hourly_rate = forms.DecimalField(
        label="Valor/hora inicial (opcional)",
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "Ex.: 95.00"}),
    )
    contract_start_date = forms.DateField(
        label="Inicio do vinculo (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    contract_end_date = forms.DateField(
        label="Fim do vinculo (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    contract_file = forms.FileField(
        label="PDF do vinculo (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )
    contract_notes = forms.CharField(
        label="Observacoes (opcional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Informacoes complementares para a operacao"}),
    )

    def _contract_requested(self, data):
        notes = (data.get("contract_notes") or "").strip()
        return any(
            [
                data.get("contract_hourly_rate") is not None,
                data.get("contract_start_date"),
                data.get("contract_end_date"),
                data.get("contract_file"),
                notes,
            ]
        )

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas nao conferem.")

        contract_requested = self._contract_requested(data)
        start_date = data.get("contract_start_date")
        end_date = data.get("contract_end_date")
        hourly_rate = data.get("contract_hourly_rate")

        if contract_requested and hourly_rate is None:
            self.add_error("contract_hourly_rate", "Informe o valor/hora para criar o vinculo inicial.")

        if contract_requested and start_date and end_date and end_date < start_date:
            self.add_error("contract_end_date", "A data final nao pode ser anterior a data inicial.")

        return data

    def clean_mei_email(self):
        email = (self.cleaned_data.get("mei_email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Ja existe um usuario com esse email.")
        return email

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_contract_file(self):
        file_obj = self.cleaned_data.get("contract_file")
        if not file_obj:
            return file_obj
        if not file_obj.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Envie um arquivo PDF (.pdf).")
        return file_obj

    def create_mei_and_optional_contract(self, company):
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

            contract = None
            if self._contract_requested(self.cleaned_data):
                contract = Contract.objects.create(
                    employee=employee,
                    company=company,
                    hourly_rate=self.cleaned_data["contract_hourly_rate"],
                    start_date=self.cleaned_data.get("contract_start_date") or timezone.localdate(),
                    end_date=self.cleaned_data.get("contract_end_date"),
                    contract_file=self.cleaned_data.get("contract_file"),
                    notes=(self.cleaned_data.get("contract_notes") or "").strip(),
                    is_active=True,
                )

        return employee, contract

    def create_mei_for_company(self, company):
        employee, _contract = self.create_mei_and_optional_contract(company)
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
            "notes",
        ]
        widgets = {
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Ex.: 95.00"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Observacoes do vinculo (opcional)"}),
            "contract_file": forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
        }
        labels = {
            "hourly_rate": "Valor/hora do vinculo",
            "start_date": "Inicio da vigencia",
            "end_date": "Fim da vigencia (opcional)",
            "contract_file": "PDF do vinculo (opcional)",
            "notes": "Observacoes internas (opcional)",
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
        self.fields["employee"].empty_label = "Selecione um MEI"
        self.fields["employee"].widget.attrs.update({"title": "Selecione o MEI do vinculo"})

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
        if not contract.pk:
            contract.is_active = True
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


class CompanyAttendancePolicyForm(forms.ModelForm):
    default_location = forms.ModelChoiceField(
        queryset=CompanyAuthorizedLocation.objects.none(),
        required=False,
        empty_label="Sem local padrao",
        label="Local padrao (opcional)",
    )

    class Meta:
        model = CompanyAttendancePolicy
        fields = [
            "validation_mode",
            "require_location",
            "require_qr",
            "qr_requirement",
            "default_allowed_radius_m",
            "default_location",
        ]
        labels = {
            "validation_mode": "Modo de validacao de horarios",
            "require_location": "Exigir localizacao no registro",
            "require_qr": "Exigir confirmacao por QR presencial",
            "qr_requirement": "Regra de exigencia de QR presencial",
            "default_allowed_radius_m": "Raio padrao de validacao (metros)",
            "default_location": "Local padrao (opcional)",
        }
        widgets = {
            "default_allowed_radius_m": forms.NumberInput(attrs={"min": 10, "step": 1}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        default_location_qs = CompanyAuthorizedLocation.objects.none()
        if company:
            default_location_qs = CompanyAuthorizedLocation.objects.filter(company=company, is_active=True).order_by("name")
        self.fields["default_location"].queryset = default_location_qs
        self.fields["default_location"].label_from_instance = lambda obj: f"{obj.name} | raio {obj.allowed_radius_m}m"

    def clean(self):
        data = super().clean()
        mode = data.get("validation_mode")
        require_location = bool(data.get("require_location"))
        require_qr = bool(data.get("require_qr"))
        qr_requirement = data.get("qr_requirement")
        default_radius = data.get("default_allowed_radius_m")
        default_location = data.get("default_location")

        if default_radius is not None and default_radius < 10:
            self.add_error("default_allowed_radius_m", "Informe no minimo 10 metros.")
        if default_radius is not None and default_radius > 5000:
            self.add_error("default_allowed_radius_m", "Para V1, o limite maximo permitido e 5000 metros.")

        if mode == CompanyAttendancePolicy.ValidationMode.FREE:
            data["require_location"] = False
            data["require_qr"] = False
            data["qr_requirement"] = CompanyAttendancePolicy.QrRequirement.NONE
        elif mode == CompanyAttendancePolicy.ValidationMode.GEOLOCATION and not require_location:
            data["require_location"] = True
        elif mode == CompanyAttendancePolicy.ValidationMode.PRESENTIAL_QR and not require_qr:
            data["require_qr"] = True

        if not data.get("require_qr"):
            data["qr_requirement"] = CompanyAttendancePolicy.QrRequirement.NONE
        elif data.get("require_qr") and qr_requirement == CompanyAttendancePolicy.QrRequirement.NONE:
            self.add_error("qr_requirement", "Selecione quando o QR deve ser exigido.")

        if default_location and self.company and default_location.company_id != self.company.id:
            self.add_error("default_location", "Selecione um local da sua empresa.")

        return data


class CompanyAuthorizedLocationForm(forms.ModelForm):
    class Meta:
        model = CompanyAuthorizedLocation
        fields = [
            "name",
            "address_or_description",
            "latitude",
            "longitude",
            "allowed_radius_m",
            "is_active",
        ]
        labels = {
            "name": "Nome do local",
            "address_or_description": "Endereco ou descricao",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "allowed_radius_m": "Raio permitido (metros)",
            "is_active": "Local ativo",
        }
        widgets = {
            "address_or_description": forms.TextInput(attrs={"placeholder": "Ex.: Unidade Centro - Recepcao principal"}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "-23.550520"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "-46.633308"}),
            "allowed_radius_m": forms.NumberInput(attrs={"min": 10, "step": 1}),
        }

    def clean_allowed_radius_m(self):
        radius = self.cleaned_data.get("allowed_radius_m")
        if radius is None:
            return radius
        if radius < 10:
            raise forms.ValidationError("Informe no minimo 10 metros.")
        if radius > 5000:
            raise forms.ValidationError("Para V1, o limite maximo permitido e 5000 metros.")
        return radius


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
