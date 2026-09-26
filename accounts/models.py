from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPRESA = "EMPRESA", "Empresa (RH/Admin)"
        FUNCIONARIO = "FUNCIONARIO", "Funcionário (MEI)"

    class VisualTheme(models.TextChoices):
        GRAPHITE = "graphite-premium", "Grafite Premium"
        NEUTRAL = "professional-neutral", "Neutro Profissional"
        BRAZIL = "brazil-corporate", "Brasil Corporativo"
        RUBRO = "rubro-professional", "Rubro Profissional"
        CLARO = "claro-operacional", "Claro Operacional"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.FUNCIONARIO,
    )

    email = models.EmailField(unique=True)  # <- importante
    visual_theme = models.CharField(
        max_length=40,
        choices=VisualTheme.choices,
        default=VisualTheme.GRAPHITE,
    )
    # Chaves dos tours guiados (baloes explicativos por tela) que o usuario
    # ja dispensou - fechou ou concluiu. Guardado no servidor (nao em
    # localStorage) para nao repetir o tour quando o mesmo usuario troca de
    # aparelho (ex.: viu no celular, depois abre no PC).
    dismissed_tours = models.JSONField(default=list, blank=True)
    # Quando a pessoa aceitou os Termos de Uso/Privacidade no autocadastro.
    # Nulo para contas criadas antes desse fluxo (empresa/admin ou manuais).
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True, default="")

    def has_dismissed_tour(self, tour_key):
        return tour_key in (self.dismissed_tours or [])

    def resolve_employee_profile(self, *, contract_id=None, company_id=None):
        """
        Resolve um perfil Employee para compatibilidade legada.

        Prioridade:
        1) Contract operacional selecionado (quando contract_id informado)
        2) Contract operacional mais recente do usuário
        3) Contract mais recente do usuário
        4) Employee ativo mais recente
        5) Employee mais recente
        """
        from companies.models import Employee
        from timeclock.models import Contract
        from timeclock.state import contract_operational_q

        contracts = Contract.objects.filter(
            employee__user=self,
            employee__isnull=False,
            employee__user__isnull=False,
        ).select_related("employee", "company")

        if company_id:
            contracts = contracts.filter(company_id=company_id)

        if contract_id:
            selected = contracts.filter(id=contract_id).first()
            if selected:
                return selected.employee

        selected = contracts.filter(contract_operational_q()).order_by("-start_date", "-created_at").first()
        if selected:
            return selected.employee

        selected = contracts.order_by("-start_date", "-created_at").first()
        if selected:
            return selected.employee

        employees = Employee.objects.filter(user=self)
        if company_id:
            employees = employees.filter(company_id=company_id)

        selected_employee = employees.filter(is_active=True).order_by("-created_at").first()
        if selected_employee:
            return selected_employee

        return employees.order_by("-created_at").first()

    @property
    def employee_profile(self):
        return self.resolve_employee_profile()

    def __str__(self):
        return f"{self.username} ({self.role})"


class ProductEvent(models.Model):
    """Evento de produto para medir ativacao/retencao (funil de uso).

    Sem PII: so o usuario (FK) e propriedades de uma allowlist fixa - ver
    accounts/analytics.py. Nada de nome, e-mail, cliente, token ou URL.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="product_events")
    event = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(auto_now_add=True)
    properties = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["event", "occurred_at"]),
            models.Index(fields=["user", "event", "occurred_at"]),
        ]

    def __str__(self):
        return f"{self.event} ({self.user_id})"
