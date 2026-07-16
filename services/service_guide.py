from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render

from . import views as service_views
from .forms import ServiceJobForm, ServiceRequestForm, ServiceRequestItemForm
from .models import (
    ServiceCategory,
    ServiceItemCatalog,
    ServiceItemExpense,
    ServiceItemUnit,
    ServiceJob,
    ServiceRequest,
)
from .workflow import planned_status_for_service


TRAVEL_CATEGORY_SLUGS = (
    "administrativo-escritorio",
    "aulas-consultoria",
    "assistencia-tecnica",
    "automotivo",
)

TRAVEL_PRESET_ITEMS = (
    {
        "name": "Pedágio",
        "type": ServiceItemExpense.ItemType.TOLL,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o trecho, a data e a referência do comprovante quando houver.",
    },
    {
        "name": "Combustível",
        "type": ServiceItemExpense.ItemType.FUEL,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o abastecimento relacionado ao atendimento e a referência do comprovante.",
    },
    {
        "name": "Estacionamento",
        "type": ServiceItemExpense.ItemType.PARKING,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o local, o período e a referência do comprovante.",
    },
    {
        "name": "Alimentação em viagem",
        "type": ServiceItemExpense.ItemType.FOOD,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Use somente quando a política da empresa ou o combinado permitir reembolso.",
    },
    {
        "name": "Hospedagem ou passagem",
        "type": ServiceItemExpense.ItemType.EXPENSE,
        "unit": ServiceItemUnit.SERVICE,
        "description": "Registre o período, a finalidade e a referência da reserva ou do comprovante.",
    },
)

GUIDED_REQUEST_SCENARIOS = {
    "evento": {
        "category_slugs": ("eventos-sonorizacao",),
        "title": "Evento ou sonorização",
        "description": (
            "Tipo de evento: \n"
            "Local e estrutura disponível: \n"
            "Horário de montagem: \n"
            "Horário de início e término: \n"
            "Público estimado: \n"
            "Equipamentos ou serviços solicitados: \n"
            "Observações do cliente:"
        ),
        "source": ServiceRequest.Source.WHATSAPP,
        "form_title": "Pedido de evento ou sonorização",
        "form_subtitle": (
            "Registre o que o cliente já informou. Depois você poderá transformar o pedido em serviço, completar a proposta "
            "técnica e enviar a folha profissional."
        ),
        "result_hint": "Ao transformar, o HoraCerta cria um rascunho de serviço para completar equipamentos, logística, cobrança e proposta.",
    },
    "viagem": {
        "category_slugs": TRAVEL_CATEGORY_SLUGS,
        "title": "Viagem de trabalho ou atendimento externo",
        "description": (
            "Objetivo da viagem ou atendimento: \n"
            "Destino: \n"
            "Empresa e responsável: \n"
            "Atividades previstas: \n"
            "Política de reembolso e limites: \n"
            "Documentos ou comprovantes exigidos:"
        ),
        "source": ServiceRequest.Source.WHATSAPP,
        "form_title": "Solicitação de viagem ou atendimento externo",
        "form_subtitle": (
            "Organize o pedido da empresa antes da autorização. Informe destino, previsão, responsável e regras de despesas; "
            "os dados serão levados para o serviço quando o pedido for transformado."
        ),
        "result_hint": "Data, horário e endereço informados no pedido serão copiados para o serviço quando ele for transformado.",
    },
}


class GuidedServiceRequestForm(ServiceRequestForm):
    class Meta(ServiceRequestForm.Meta):
        fields = [
            "contract",
            "client_name",
            "client_whatsapp",
            "client_email",
            "category",
            "title",
            "description",
            "preferred_date",
            "preferred_time",
            "address_zipcode",
            "address_street",
            "address_number",
            "address_complement",
            "address_neighborhood",
            "address_city",
            "address_state",
            "address_reference",
            "urgency",
            "source",
        ]
        labels = {
            **ServiceRequestForm.Meta.labels,
            "preferred_date": "Data desejada",
            "preferred_time": "Horário desejado",
            "address_zipcode": "CEP",
            "address_street": "Rua, avenida ou local",
            "address_number": "Número",
            "address_complement": "Complemento",
            "address_neighborhood": "Bairro",
            "address_city": "Cidade",
            "address_state": "UF",
            "address_reference": "Ponto de referência",
        }
        widgets = {
            **ServiceRequestForm.Meta.widgets,
            "preferred_date": forms.DateInput(attrs={"type": "date"}),
            "preferred_time": forms.TimeInput(attrs={"type": "time"}),
            "address_zipcode": forms.TextInput(attrs={"placeholder": "00000-000", "inputmode": "numeric"}),
            "address_street": forms.TextInput(attrs={"placeholder": "Rua, avenida, empresa ou espaço do evento"}),
            "address_number": forms.TextInput(attrs={"placeholder": "Número"}),
            "address_complement": forms.TextInput(attrs={"placeholder": "Sala, bloco, salão, auditório..."}),
            "address_neighborhood": forms.TextInput(attrs={"placeholder": "Bairro"}),
            "address_city": forms.TextInput(attrs={"placeholder": "Cidade"}),
            "address_state": forms.TextInput(attrs={"placeholder": "UF", "maxlength": "2"}),
            "address_reference": forms.TextInput(attrs={"placeholder": "Portaria, acesso, responsável no local..."}),
        }

    def clean_address_zipcode(self):
        value = (self.cleaned_data.get("address_zipcode") or "").strip()
        digits = "".join(character for character in value if character.isdigit())
        if value and len(digits) != 8:
            raise forms.ValidationError("Informe um CEP com 8 dígitos.")
        return value

    def clean_address_state(self):
        return (self.cleaned_data.get("address_state") or "").strip().upper()


def _first_active_category(slugs):
    categories = ServiceCategory.objects.filter(is_active=True, slug__in=slugs)
    by_slug = {category.slug: category for category in categories}
    for slug in slugs:
        if slug in by_slug:
            return by_slug[slug]
    return None


def _travel_category():
    return _first_active_category(TRAVEL_CATEGORY_SLUGS)


def _create_travel_preset_items(job):
    existing_names = {name.casefold() for name in job.item_expenses.values_list("name", flat=True)}
    created = 0
    for preset in TRAVEL_PRESET_ITEMS:
        if preset["name"].casefold() in existing_names:
            continue
        ServiceItemExpense.objects.create(
            service_job=job,
            type=preset["type"],
            name=preset["name"],
            description=preset["description"],
            unit=preset["unit"],
            quantity=Decimal("1.00"),
            unit_value=Decimal("0.00"),
            usage_status=ServiceItemExpense.UsageStatus.PLANNED,
        )
        created += 1
    return created


@login_required
def service_start_guide(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    return render(request, "services/service_start_guide.html")


@login_required
def service_request_create_from_scenario(request, scenario):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    scenario_config = GUIDED_REQUEST_SCENARIOS.get(scenario)
    if not scenario_config:
        raise Http404("Cenário de serviço não encontrado.")

    category = _first_active_category(scenario_config["category_slugs"])
    initial = {
        "category": category,
        "title": scenario_config["title"],
        "description": scenario_config["description"],
        "source": scenario_config["source"],
    }

    if request.method == "POST":
        form = GuidedServiceRequestForm(request.POST, user=request.user)
        item_form = ServiceRequestItemForm(request.POST, prefix="quick")
        item_form_has_data = item_form.has_item_data()
        item_form_is_valid = item_form.is_valid() if item_form_has_data else True
        if form.is_valid() and item_form_is_valid:
            submit_action = (request.POST.get("submit_action") or "").strip()
            with transaction.atomic():
                service_request = form.save()
                if item_form_has_data:
                    item_form.service_request = service_request
                    item_form.save()
                if submit_action == "convert":
                    job = service_views._convert_service_request_to_job(service_request)
                    if scenario == "viagem":
                        _create_travel_preset_items(job)
                    messages.success(
                        request,
                        "Pedido salvo e transformado em rascunho de serviço. Complete o combinado antes de enviar ao cliente.",
                    )
                    return redirect("service_job_detail", job_id=job.id)
            messages.success(request, "Pedido salvo. Você pode completar as informações antes de transformar em serviço.")
            return redirect("service_request_detail", request_id=service_request.id)
    else:
        form = GuidedServiceRequestForm(user=request.user, initial=initial)
        item_form = ServiceRequestItemForm(prefix="quick")

    return render(
        request,
        "services/service_guided_request_form.html",
        {
            "form": form,
            "item_form": item_form,
            "scenario": scenario,
            "scenario_title": scenario_config["form_title"],
            "scenario_subtitle": scenario_config["form_subtitle"],
            "scenario_result_hint": scenario_config["result_hint"],
        },
    )


@login_required
def service_travel_create(request):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied

    category = _travel_category()
    initial = {
        "category": category,
        "title": "Viagem de trabalho e atendimento externo",
        "description": (
            "Realizar atendimento externo conforme o objetivo combinado com a empresa, registrando os períodos "
            "efetivamente trabalhados, as atividades executadas, os deslocamentos necessários e as despesas relacionadas."
        ),
        "notes": (
            "Antes da viagem, confirme destino, responsável, datas, política de reembolso, limites de despesas e documentos "
            "exigidos. Durante o atendimento, registre cada período de trabalho e marque somente as despesas realmente "
            "utilizadas. No encerramento, gere a prestação de contas com horas, consumo e referências de comprovantes."
        ),
        "billing_mode": ServiceJob.BillingMode.HOURLY,
    }

    if request.method == "POST":
        form = ServiceJobForm(request.POST, user=request.user)
        if form.is_valid():
            submit_action = (request.POST.get("submit_action") or "").strip()
            requested_status = ServiceJob.Status.DRAFT if submit_action == "draft" else ServiceJob.Status.PLANNED
            with transaction.atomic():
                job = form.save(status=ServiceJob.Status.DRAFT)
                service_views._create_planned_items(
                    job,
                    service_views._planned_item_rows_from_post(request.POST),
                )
                created_items = _create_travel_preset_items(job)
                status = planned_status_for_service(job, requested_status=requested_status)
                if job.status != status:
                    job.status = status
                    job.save(update_fields=["status", "finished_at", "updated_at"])
            messages.success(
                request,
                (
                    "Atendimento externo criado. "
                    f"{created_items} despesas comuns foram adicionadas sem valor; mantenha apenas as que realmente usar."
                ),
            )
            return redirect("service_job_detail", job_id=job.id)
    else:
        form = ServiceJobForm(user=request.user, initial=initial)

    return render(
        request,
        "services/service_job_form.html",
        {
            "form": form,
            "form_title": "Novo serviço — viagem e atendimento externo",
            "form_subtitle": (
                "Organize o combinado com a empresa, registre as horas de cada dia e feche o serviço com uma prestação "
                "de contas de despesas. Os valores começam zerados para você revisar."
            ),
            "is_edit": False,
            "item_type_choices": ServiceItemExpense.ItemType.choices,
            "item_unit_choices": ServiceItemCatalog._meta.get_field("unit").choices,
            "client_address_map": service_views._client_address_map(request.user),
        },
    )
