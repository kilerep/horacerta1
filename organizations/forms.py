from django import forms

from accounts.models import User

from .models import HiringOrganization, OrganizationMember


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
        self.fields["legal_name"].required = False
        self.fields["cnpj"].required = False
        self.fields["email"].required = False
        self.fields["whatsapp"].required = False
        self.fields["phone"].required = False
        self.fields["address"].required = False
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
            attrs={
                "class": "hc-input",
                "placeholder": "pessoa@empresa.com.br",
                "autocomplete": "email",
            }
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
        ).exclude(status=OrganizationMember.Status.REMOVED).exists():
            raise forms.ValidationError("Esta pessoa já possui vínculo com a empresa.")
        self.user_to_invite = user
        return email
