from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from companies.models import Company, CompanyAttendancePolicy, CompanyAuthorizedLocation, Employee
from timeclock.models import ActivityReportRequest, Contract, Punch, PunchCorrectionRequest, ServiceReport
from .services import MeiLinkError, create_or_link_mei_by_email

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


class PunchCorrectionRequestForm(forms.ModelForm):
    contract = forms.ModelChoiceField(
        label="Cliente/contrato",
        queryset=Contract.objects.none(),
        required=False,
        empty_label="Selecionar contrato",
    )
    punch = forms.ModelChoiceField(
        label="Registro relacionado (opcional)",
        queryset=Punch.all_objects.none(),
        required=False,
        empty_label="Nenhum registro especifico",
    )

    class Meta:
        model = PunchCorrectionRequest
        fields = ["problem_date", "problem_type", "contract", "punch", "description"]
        widgets = {
            "problem_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Descreva o que aconteceu e qual ajuste voce acredita ser necessario.",
                }
            ),
        }
        labels = {
            "problem_date": "Data do problema",
            "problem_type": "Tipo de problema",
            "description": "Descricao",
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        contracts_qs = Contract.objects.none()
        punches_qs = Punch.all_objects.none()
        if employee:
            contracts_qs = (
                Contract.objects.filter(employee=employee, company__isnull=False)
                .select_related("company")
                .order_by("-is_active", "company__name", "-start_date")
            )
            punches_qs = (
                Punch.all_objects.filter(contract__employee=employee)
                .select_related("contract", "contract__company")
                .order_by("-timestamp")
            )
        self.fields["contract"].queryset = contracts_qs
        self.fields["problem_date"].required = True
        self.fields["contract"].label_from_instance = (
            lambda obj: f"{obj.company.name} | inicio {obj.start_date.strftime('%d/%m/%Y') if obj.start_date else '-'}"
        )
        self.fields["punch"].queryset = punches_qs
        self.fields["punch"].label_from_instance = (
            lambda obj: f"{obj.timestamp.strftime('%d/%m/%Y %H:%M')} | {obj.contract.company.name}"
        )

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if not description:
            raise forms.ValidationError("Descreva o problema para enviar a solicitacao.")
        return description

    def clean(self):
        data = super().clean()
        contract = data.get("contract")
        punch = data.get("punch")
        if self.employee and contract and contract.employee_id != self.employee.id:
            self.add_error("contract", "Selecione um contrato do seu perfil.")
        if self.employee and punch and punch.contract.employee_id != self.employee.id:
            self.add_error("punch", "Selecione um registro do seu perfil.")
        if punch and contract and punch.contract_id != contract.id:
            self.add_error("punch", "O registro precisa pertencer ao contrato selecionado.")
        if punch and not contract:
            data["contract"] = punch.contract
        return data

    def save(self, commit=True):
        request_obj = super().save(commit=False)
        if self.employee:
            request_obj.employee = self.employee
            request_obj.user = self.employee.user
            contract = self.cleaned_data.get("contract")
            if contract:
                request_obj.contract = contract
                request_obj.company = contract.company
            else:
                request_obj.company = self.employee.company
            punch = self.cleaned_data.get("punch")
            if punch:
                request_obj.punch = punch
                request_obj.contract = punch.contract
                request_obj.company = punch.contract.company
        request_obj.status = PunchCorrectionRequest.Status.OPEN
        if commit:
            request_obj.save()
        return request_obj
    date_to = forms.DateField(
        label="Ate",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class ServiceReportCreateForm(forms.ModelForm):
    contract = forms.ModelChoiceField(
        label="Cliente/contrato",
        queryset=Contract.objects.none(),
        empty_label="Selecione um contrato",
    )

    class Meta:
        model = ServiceReport
        fields = ["contract", "date_from", "date_to", "status", "title", "description"]
        widgets = {
            "date_from": forms.DateInput(attrs={"type": "date"}),
            "date_to": forms.DateInput(attrs={"type": "date"}),
            "title": forms.TextInput(attrs={"placeholder": "Ex.: Relatório de horas do período"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Observações gerais, entregas ou contexto para conferência do cliente.",
                }
            ),
        }
        labels = {
            "date_from": "Data inicial",
            "date_to": "Data final",
            "status": "Status",
            "title": "Título",
            "description": "Observações",
        }

    def __init__(self, *args, employee=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.user = user
        contracts_qs = Contract.objects.none()
        if user:
            contracts_qs = (
                Contract.objects.filter(
                    employee__user=user,
                    is_active=True,
                    employee__is_active=True,
                    company__isnull=False,
                )
                .select_related("company", "employee")
                .order_by("company__name", "-start_date", "-created_at")
            )
        elif employee:
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
        self.fields["title"].required = True
        self.fields["description"].required = False
        self.fields["contract"].label_from_instance = (
            lambda obj: f"{obj.company.name} | inicio {obj.start_date.strftime('%d/%m/%Y') if obj.start_date else '-'} | R$ {obj.hourly_rate}/h"
        )
        if not self.is_bound:
            today = timezone.localdate()
            self.initial.setdefault("date_from", today.replace(day=1))
            self.initial.setdefault("date_to", today)
            self.initial.setdefault("status", ServiceReport.Status.DRAFT)

    def clean(self):
        data = super().clean()
        contract = data.get("contract")
        if contract:
            self.instance.contract = contract
            self.instance.company = contract.company
            self.instance.employee = contract.employee
            self.instance.report_date = data.get("date_to") or timezone.localdate()
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "Data final nao pode ser anterior a data inicial.")
        return data

    def clean_contract(self):
        contract = self.cleaned_data.get("contract")
        if not contract:
            return contract
        if self.employee and contract.employee_id != self.employee.id:
            raise forms.ValidationError("Selecione um contrato valido do seu perfil.")
        if self.user and contract.employee.user_id != self.user.id:
            raise forms.ValidationError("Selecione um contrato valido do seu perfil.")
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
        report.report_date = self.cleaned_data.get("date_to") or timezone.localdate()
        if commit:
            report.save()
        return report


class CompanyActivityReportRequestForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        label="Profissional",
        queryset=Employee.objects.none(),
    )
    contract = forms.ModelChoiceField(
        label="Contrato (opcional)",
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
            self.add_error("contract", "O contrato selecionado deve pertencer ao profissional escolhido.")
        if self.company and contract and contract.company_id != self.company.id:
            self.add_error("contract", "Selecione um contrato deste cliente.")

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
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Defina uma senha segura", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        required=False,
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
        label="Inicio do contrato (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    contract_end_date = forms.DateField(
        label="Fim do contrato (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    contract_file = forms.FileField(
        label="PDF do contrato (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )
    contract_notes = forms.CharField(
        label="Observacoes (opcional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Informacoes complementares para a operacao"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.account_mode = "unknown"
        self.account_hint = ""
        self.account_conflict = False

        self.fields["password1"].widget.attrs.update({"data-role": "mei-password"})
        self.fields["password2"].widget.attrs.update({"data-role": "mei-password"})

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
        mei_email = (data.get("mei_email") or "").strip().lower()
        password1 = data.get("password1")
        password2 = data.get("password2")

        existing_user = None
        if mei_email:
            existing_user = User.objects.filter(Q(email__iexact=mei_email) | Q(username__iexact=mei_email)).first()

        if existing_user:
            if existing_user.role != User.Role.FUNCIONARIO:
                self.account_mode = "conflict"
                self.account_conflict = True
                self.account_hint = "Este email pertence a uma conta de empresa/admin."
                self.add_error("mei_email", "Este email pertence a uma conta de empresa/admin. Use outro email do MEI.")
            else:
                self.account_mode = "existing"
                self.account_hint = (
                    "Este profissional ja possui conta no HoraCerta. "
                    "Sera criado apenas um novo contrato com este cliente."
                )
                if self.company and Employee.objects.filter(user=existing_user, company=self.company).exists():
                    self.add_error(
                        "mei_email",
                        "Este MEI ja possui contrato com este cliente. Use o gerenciamento de contratos para continuar.",
                    )
        else:
            self.account_mode = "new"
            self.account_hint = "Novo email: sera criada a conta principal do MEI com senha."
            if not password1:
                self.add_error("password1", "Defina uma senha para criar a conta do MEI.")
            if not password2:
                self.add_error("password2", "Confirme a senha para criar a conta do MEI.")
            if password1 and password2 and password1 != password2:
                self.add_error("password2", "As senhas nao conferem.")

        contract_requested = self._contract_requested(data)
        start_date = data.get("contract_start_date")
        end_date = data.get("contract_end_date")
        hourly_rate = data.get("contract_hourly_rate")

        if contract_requested and hourly_rate is None:
            self.add_error("contract_hourly_rate", "Informe o valor/hora para criar o contrato inicial.")

        if contract_requested and start_date and end_date and end_date < start_date:
            self.add_error("contract_end_date", "A data final nao pode ser anterior a data inicial.")

        return data

    def clean_mei_email(self):
        email = (self.cleaned_data.get("mei_email") or "").strip().lower()
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

    def create_or_link_mei_and_optional_contract(self, company):
        try:
            result = create_or_link_mei_by_email(
                company=company,
                full_name=self.cleaned_data["full_name"],
                mei_email=self.cleaned_data["mei_email"],
                password=self.cleaned_data.get("password1"),
                contract_payload={
                    "hourly_rate": self.cleaned_data.get("contract_hourly_rate"),
                    "start_date": self.cleaned_data.get("contract_start_date"),
                    "end_date": self.cleaned_data.get("contract_end_date"),
                    "contract_file": self.cleaned_data.get("contract_file"),
                    "notes": self.cleaned_data.get("contract_notes"),
                },
            )
        except MeiLinkError as exc:
            if exc.code in {"email_role_conflict", "already_linked_company"}:
                self.add_error("mei_email", exc.message)
            elif exc.code == "password_required":
                self.add_error("password1", exc.message)
            else:
                self.add_error(None, exc.message)
            return None, None, None

        if result.linked_existing_user:
            self.account_mode = "existing"
            self.account_hint = (
                "Este profissional ja possui conta no HoraCerta. "
                "Sera criado apenas um novo contrato com este cliente."
            )
        else:
            self.account_mode = "new"
            self.account_hint = "Novo email: sera criada a conta principal do MEI com senha."
        return result.employee, result.contract, result

    def create_mei_for_company(self, company):
        employee, _contract, _result = self.create_or_link_mei_and_optional_contract(company)
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
        label="Prestador",
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
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Observacoes do contrato (opcional)"}),
            "contract_file": forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
        }
        labels = {
            "hourly_rate": "Valor/hora do contrato",
            "start_date": "Inicio da vigencia",
            "end_date": "Fim da vigencia (opcional)",
            "contract_file": "PDF do contrato (opcional)",
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
        self.fields["employee"].empty_label = "Selecione um prestador"
        self.fields["employee"].widget.attrs.update({"title": "Selecione o prestador do contrato"})

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
            self.add_error("employee", "Selecione um prestador valido.")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "A data final nao pode ser anterior a data inicial.")

        if self.company and employee and employee.company_id != self.company.id:
            self.add_error("employee", "Selecione um prestador da sua empresa.")
        if employee and not employee.user_id:
            self.add_error("employee", "Prestador selecionado sem usuario valido.")
        if employee and not employee.company_id:
            self.add_error("employee", "Prestador selecionado sem empresa valida.")
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


class MEIClientForm(forms.Form):
    name = forms.CharField(label="Nome do cliente/empresa", max_length=120)
    cnpj = forms.CharField(label="CNPJ (opcional)", max_length=18, required=False)
    contact_name = forms.CharField(label="Contato responsavel (opcional)", max_length=120, required=False)
    whatsapp = forms.CharField(label="WhatsApp (opcional)", max_length=30, required=False)
    email = forms.EmailField(label="E-mail (opcional)", required=False)
    hourly_rate = forms.DecimalField(
        label="Valor por hora",
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "Ex.: 95.00"}),
    )
    start_date = forms.DateField(
        label="Data de inicio",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    closure_type = forms.ChoiceField(
        label="Tipo de fechamento",
        choices=Contract.ClosureType.choices,
    )
    require_location = forms.BooleanField(label="Exige localizacao no registro", required=False)
    notes = forms.CharField(
        label="Observacoes internas",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Informacoes internas sobre o atendimento, combinados ou faturamento."}),
    )

    def __init__(self, *args, user=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance = instance
        if instance and not self.is_bound:
            policy = getattr(instance.company, "attendance_policy", None)
            self.initial.update(
                {
                    "name": instance.company.name,
                    "cnpj": instance.company.cnpj,
                    "contact_name": getattr(instance.company, "contact_name", ""),
                    "whatsapp": getattr(instance.company, "whatsapp", "") or instance.company.phone,
                    "email": instance.company.email or "",
                    "hourly_rate": instance.hourly_rate,
                    "start_date": instance.start_date,
                    "closure_type": getattr(instance, "closure_type", Contract.ClosureType.MONTHLY),
                    "require_location": bool(policy and policy.require_location),
                    "notes": instance.notes or instance.company.internal_note,
                }
            )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean_cnpj(self):
        return (self.cleaned_data.get("cnpj") or "").strip()

    def clean_contact_name(self):
        return (self.cleaned_data.get("contact_name") or "").strip()

    def clean_whatsapp(self):
        return (self.cleaned_data.get("whatsapp") or "").strip()

    def clean_email(self):
        value = (self.cleaned_data.get("email") or "").strip().lower()
        return value or None

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()

    def clean(self):
        data = super().clean()
        if not self.user:
            raise forms.ValidationError("Usuario MEI nao identificado.")
        if getattr(self.user, "role", None) != User.Role.FUNCIONARIO:
            raise forms.ValidationError("Apenas profissionais podem cadastrar clientes.")
        return data

    def save(self):
        data = self.cleaned_data
        require_location = bool(data.get("require_location"))
        with transaction.atomic():
            if self.instance:
                company = self.instance.company
                employee = self.instance.employee
                contract = self.instance
            else:
                company = Company(owner=self.user)
                employee = Employee(user=self.user, company=company)
                contract = Contract(company=company, employee=employee, is_active=True)

            company.name = data["name"]
            company.cnpj = data.get("cnpj") or ""
            company.contact_name = data.get("contact_name") or ""
            company.whatsapp = data.get("whatsapp") or ""
            company.phone = data.get("whatsapp") or company.phone or ""
            company.email = data.get("email")
            company.internal_note = data.get("notes") or ""
            company.save()

            employee.company = company
            employee.user = self.user
            employee.full_name = self.user.get_full_name() or self.user.email or self.user.username
            employee.phone = employee.phone or company.whatsapp or company.phone
            employee.is_active = True
            employee.save()

            contract.company = company
            contract.employee = employee
            contract.hourly_rate = data["hourly_rate"]
            contract.start_date = data["start_date"]
            contract.closure_type = data["closure_type"]
            contract.notes = data.get("notes") or ""
            contract.is_active = True
            contract.save()

            policy, _created = CompanyAttendancePolicy.objects.get_or_create(company=company)
            policy.validation_mode = (
                CompanyAttendancePolicy.ValidationMode.GEOLOCATION
                if require_location
                else CompanyAttendancePolicy.ValidationMode.FREE
            )
            policy.require_location = require_location
            policy.updated_by = self.user
            policy.save()
            return contract


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
            "validation_mode": "Como validar os registros",
            "require_location": "Validar localizacao no registro",
            "require_qr": "Exigir confirmacao presencial por QR",
            "qr_requirement": "Quando exigir QR",
            "default_allowed_radius_m": "Raio padrao sugerido (metros)",
            "default_location": "Local padrao (opcional)",
        }
        widgets = {
            "default_allowed_radius_m": forms.NumberInput(attrs={"min": 30, "step": 10, "placeholder": "100"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        default_location_qs = CompanyAuthorizedLocation.objects.none()
        if company:
            default_location_qs = CompanyAuthorizedLocation.objects.filter(company=company, is_active=True).order_by("name")
        self.fields["default_location"].queryset = default_location_qs
        self.fields["default_location"].label_from_instance = lambda obj: f"{obj.name} | raio {obj.allowed_radius_m}m"
        if not self.is_bound and not self.initial.get("default_allowed_radius_m"):
            self.initial["default_allowed_radius_m"] = 100

    def clean(self):
        data = super().clean()
        mode = data.get("validation_mode")
        require_location = bool(data.get("require_location"))
        require_qr = bool(data.get("require_qr"))
        qr_requirement = data.get("qr_requirement")
        default_radius = data.get("default_allowed_radius_m")
        default_location = data.get("default_location")

        if default_radius is not None and default_radius < 30:
            self.add_error("default_allowed_radius_m", "Use no minimo 30 metros para evitar leituras instaveis de GPS.")
        if default_radius is not None and default_radius > 5000:
            self.add_error("default_allowed_radius_m", "Para V1, o limite maximo permitido e 5000 metros.")

        if mode == CompanyAttendancePolicy.ValidationMode.FREE:
            data["require_location"] = False
            data["require_qr"] = False
            data["qr_requirement"] = CompanyAttendancePolicy.QrRequirement.NONE
        elif mode == CompanyAttendancePolicy.ValidationMode.GEOLOCATION and not require_location:
            data["require_location"] = True
        elif mode == CompanyAttendancePolicy.ValidationMode.PRESENTIAL_QR:
            data["require_qr"] = True
            data["require_location"] = True

        if not data.get("require_qr"):
            data["qr_requirement"] = CompanyAttendancePolicy.QrRequirement.NONE
        elif data.get("require_qr") and qr_requirement == CompanyAttendancePolicy.QrRequirement.NONE:
            self.add_error("qr_requirement", "Selecione quando o QR deve ser exigido.")

        if default_location and self.company and default_location.company_id != self.company.id:
            self.add_error("default_location", "Selecione um local da sua empresa.")

        return data


class CompanyAuthorizedLocationForm(forms.ModelForm):
    latitude = forms.CharField(required=True)
    longitude = forms.CharField(required=True)

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
            "latitude": "Latitude (avancado)",
            "longitude": "Longitude (avancado)",
            "allowed_radius_m": "Raio permitido (metros)",
            "is_active": "Local ativo",
        }
        widgets = {
            "address_or_description": forms.TextInput(attrs={"placeholder": "Ex.: Unidade Centro - Recepcao principal"}),
            "latitude": forms.TextInput(
                attrs={
                    "placeholder": "-23.550520",
                    "inputmode": "decimal",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "longitude": forms.TextInput(
                attrs={
                    "placeholder": "-46.633308",
                    "inputmode": "decimal",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "allowed_radius_m": forms.NumberInput(attrs={"min": 30, "step": 10, "placeholder": "100"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not self.instance or not self.instance.pk) and not self.initial.get("allowed_radius_m"):
            self.initial["allowed_radius_m"] = 100

    def _parse_coordinate(self, raw_value, *, field_name, min_value, max_value):
        value = (raw_value or "").strip()
        if value == "":
            raise forms.ValidationError("Use 'Usar localizacao atual' ou informe manualmente no modo avancado.")
        normalized = value.replace(",", ".").replace(" ", "")
        try:
            parsed = Decimal(normalized)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError("Informe um numero valido.")
        if parsed < Decimal(str(min_value)) or parsed > Decimal(str(max_value)):
            raise forms.ValidationError(f"{field_name} deve ficar entre {min_value} e {max_value}.")
        return parsed.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def clean_latitude(self):
        return self._parse_coordinate(
            self.cleaned_data.get("latitude"),
            field_name="Latitude",
            min_value=-90,
            max_value=90,
        )

    def clean_longitude(self):
        return self._parse_coordinate(
            self.cleaned_data.get("longitude"),
            field_name="Longitude",
            min_value=-180,
            max_value=180,
        )

    def clean_allowed_radius_m(self):
        radius = self.cleaned_data.get("allowed_radius_m")
        if radius is None:
            return radius
        if radius < 30:
            raise forms.ValidationError("Use no minimo 30 metros para evitar falsas divergencias de GPS.")
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
