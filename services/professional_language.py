"""Configuração de linguagem apresentada nos formulários de Serviços.

Os identificadores internos permanecem estáveis para preservar compatibilidade. Este
módulo altera somente rótulos, textos de ajuda e exemplos mostrados ao usuário.
"""


def _configure_field(form_class, field_name, *, label=None, placeholder=None, help_text=None):
    field = form_class.base_fields[field_name]
    if label is not None:
        field.label = label
    if placeholder is not None:
        field.widget.attrs["placeholder"] = placeholder
    if help_text is not None:
        field.help_text = help_text


def apply_professional_form_copy():
    from .forms import (
        PlannedServiceItemForm,
        ServiceItemCatalogForm,
        ServiceItemExpenseForm,
        ServiceJobForm,
        ServiceRequestForm,
        ServiceRequestItemForm,
        ServiceWorkLogForm,
    )

    service_job_copy = {
        "client_mode": {"label": "Forma de cadastro do cliente"},
        "manual_client_name": {
            "label": "Nome do cliente",
            "help_text": "Use esta opção quando o cliente ainda não estiver cadastrado no HoraCerta.",
        },
        "service_number": {"label": "Número", "placeholder": "Número"},
        "service_reference": {
            "label": "Ponto de referência",
            "placeholder": "Ponto de referência, opcional",
        },
        "category": {"label": "Categoria do serviço"},
        "title": {"label": "Título do serviço", "placeholder": "Ex.: Revisão elétrica residencial"},
        "description": {
            "label": "Escopo do serviço",
            "placeholder": "Descreva o que será realizado, os limites do atendimento e o resultado esperado.",
        },
        "planned_start_time": {"label": "Horário inicial previsto"},
        "planned_end_time": {"label": "Horário final previsto"},
        "billing_mode": {"label": "Forma de cobrança"},
        "fixed_labor_value": {"label": "Valor fixo da mão de obra"},
        "notes": {
            "label": "Observações e condições do atendimento",
            "placeholder": "Registre combinados, responsabilidades, condições de acesso ou pendências.",
        },
    }
    for field_name, options in service_job_copy.items():
        _configure_field(ServiceJobForm, field_name, **options)

    request_copy = {
        "client_mode": {"label": "Forma de cadastro do cliente"},
        "client_name": {
            "label": "Nome do cliente",
            "help_text": "Use esta opção quando o cliente ainda não estiver cadastrado.",
        },
        "category": {"label": "Categoria do serviço"},
        "title": {"label": "Título do pedido", "placeholder": "Ex.: Revisão elétrica residencial"},
        "description": {
            "label": "Descrição do pedido",
            "placeholder": "Descreva o que o cliente solicitou e registre informações importantes do primeiro contato.",
        },
        "urgency": {"label": "Prioridade"},
        "source": {"label": "Origem do pedido"},
    }
    for field_name, options in request_copy.items():
        _configure_field(ServiceRequestForm, field_name, **options)

    _configure_field(ServiceRequestItemForm, "note", label="Observação")
    _configure_field(ServiceWorkLogForm, "start_time", label="Início")
    _configure_field(ServiceItemExpenseForm, "description", label="Observação")
    _configure_field(ServiceItemExpenseForm, "unit_value", label="Valor unitário")
    _configure_field(ServiceItemExpenseForm, "receipt_note", label="Comprovante ou observação")
    _configure_field(ServiceItemExpenseForm, "save_to_catalog", label="Salvar este item no meu catálogo")
    _configure_field(ServiceItemExpenseForm, "update_catalog_price", label="Atualizar o preço estimado")
    _configure_field(PlannedServiceItemForm, "description", label="Observação")
    _configure_field(PlannedServiceItemForm, "unit_value", label="Valor estimado por unidade")
    _configure_field(ServiceItemCatalogForm, "internal_code", label="Código interno")
    _configure_field(ServiceItemCatalogForm, "description", label="Descrição")
    _configure_field(ServiceItemCatalogForm, "estimated_unit_value", label="Valor estimado por unidade")
    _configure_field(ServiceItemCatalogForm, "default_quantity", label="Quantidade padrão")
