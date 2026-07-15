from django import forms

from accounts.models import User

from .models import HiringOrganization, OrganizationMember, ProviderOrganizationLink


class HiringOrganizationSetupForm(forms.ModelForm):
    class Meta:
        model = HiringOrganization
        fields = ["name", "legal_name", "cnpj", "email", "whatsapp", "phone", "address"]
        labels = {
            "name": "Nome de exibição",
            "legal_name": "Razão social",
            "cnpj": "CNPJ",
            "email": "E-mail da empresa",
            "whatsapp": "WhatsApp",
            "phone": "Telefone",
            "address": "Endereço principal",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Empresa Blumenau"}),
            "legal_name": forms.TextInput(attrs={"placeholder": "Opcional nesta etapa"}),
            "cnpj": forms.TextInput(attrs={"placeholder": "00.000.000/0000-00", "inputmode": "numeric"}),
            "email": forms.EmailInput(attrs={"placeholder": "contato@empresa.com.br"}),
            "whatsapp": forms.TextInput(attrs={"placeholder": "Ex.: 47999999999"}),
            "phone": forms.TextInput(attrs={"placeholder": "Opcional"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Rua, número, bairro, cidade e UF"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        for name in ("legal_name", "cnpj", "email", "whatsapp", "phone", "address"):
            self.fields[name].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")

    def save(self, commit=True):
        organization = super().save(commit=False)
        organization.created_by = self.user
        if commit:
            organization.save()
        return organization


class OrganizationMemberInviteForm(forms.Form):
    email = forms.EmailField(
        label="E-mail do usuário",
        widget=forms.EmailInput(
            attrs={"class": "hc-input", "placeholder": "pessoa@empresa.com.br", "autocomplete": "email"}
        ),
    )
    role = forms.ChoiceField(
        label="Papel na empresa",
        choices=OrganizationMember.Role.choices,
        widget=forms.Select(attrs={"class": "hc-input"}),
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.user_to_invite = None

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise forms.ValidationError(
                "Ainda não existe uma conta com este e-mail. Peça para a pessoa criar a conta antes do convite."
            )
        if user.role != User.Role.EMPRESA:
            raise forms.ValidationError("Convide uma conta do perfil Empresa contratante.")
        if self.organization and OrganizationMember.objects.filter(
            organization=self.organization,
            user=user,
        ).exists():
            raise forms.ValidationError(
                "Esta pessoa já possui histórico na empresa. Reative o vínculo existente em vez de criar outro convite."
            )
        self.user_to_invite = user
        return email


class ProviderLinkInviteForm(forms.Form):
    email = forms.EmailField(
        label="E-mail do prestador",
        widget=forms.EmailInput(
            attrs={"class": "hc-input", "placeholder": "prestador@email.com", "autocomplete": "email"}
        ),
    )
    share_services = forms.BooleanField(required=False, initial=True, label="Compartilhar serviços")
    share_hours = forms.BooleanField(required=False, initial=True, label="Compartilhar horas")
    share_reports = forms.BooleanField(required=False, initial=True, label="Compartilhar relatórios")
    share_financial_values = forms.BooleanField(
        required=False,
        initial=False,
        label="Compartilhar valores financeiros",
        help_text="Permissão sensível. Mantenha desativada quando a empresa não precisar conferir valores.",
    )

    def __init__(self, *args, organization=None, allow_financial=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.allow_financial = allow_financial
        self.provider = None
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "hc-input")
        if not allow_financial:
            self.fields["share_financial_values"].disabled = True

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        provider = User.objects.filter(email__iexact=email).first()
        if provider is None:
            raise forms.ValidationError(
                "Ainda não existe uma conta com este e-mail. O prestador precisa criar a conta antes do convite."
            )
        if provider.role != User.Role.FUNCIONARIO:
            raise forms.ValidationError("Selecione uma conta do perfil Prestador de serviço.")
        if self.organization and ProviderOrganizationLink.objects.filter(
            organization=self.organization,
            provider=provider,
        ).exists():
            raise forms.ValidationError(
                "Este prestador já possui histórico com a empresa. Atualize o vínculo existente em vez de criar outro."
            )
        self.provider = provider
        return email

    def clean_share_financial_values(self):
        return bool(self.cleaned_data.get("share_financial_values")) if self.allow_financial else False


class ProviderLinkEndForm(forms.Form):
    reason = forms.CharField(
        label="Motivo do encerramento",
        min_length=5,
        widget=forms.Textarea(
            attrs={
                "class": "hc-input",
                "rows": 3,
                "placeholder": "Explique por que o vínculo será encerrado. O histórico será preservado.",
            }
        ),
    )

    def clean_reason(self):
        return (self.cleaned_data.get("reason") or "").strip()
