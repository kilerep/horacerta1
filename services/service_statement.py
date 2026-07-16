from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from . import views as service_views
from .models import ServiceItemExpense, ServiceJob


TRAVEL_EXPENSE_TYPES = (
    ServiceItemExpense.ItemType.EXPENSE,
    ServiceItemExpense.ItemType.TOLL,
    ServiceItemExpense.ItemType.FUEL,
    ServiceItemExpense.ItemType.PARKING,
    ServiceItemExpense.ItemType.FOOD,
)


def _sum_items(items):
    return sum((item.total_value or Decimal("0.00") for item in items), Decimal("0.00"))


def _statement_context(request, job, *, is_public):
    work_logs = list(job.work_logs.all())
    chargeable_items = list(
        job.item_expenses.filter(
            usage_status__in=ServiceItemExpense.CHARGEABLE_USAGE_STATUSES,
        ).order_by("created_at")
    )
    travel_expenses = [item for item in chargeable_items if item.type in TRAVEL_EXPENSE_TYPES]
    service_items = [item for item in chargeable_items if item.type not in TRAVEL_EXPENSE_TYPES]
    excluded_items = list(
        job.item_expenses.filter(
            usage_status__in=ServiceItemExpense.NON_CHARGEABLE_USAGE_STATUSES,
        ).order_by("created_at")
    )

    expense_total = _sum_items(travel_expenses)
    service_items_total = _sum_items(service_items)
    labor_total = job.labor_total or Decimal("0.00")
    grand_total = labor_total + expense_total + service_items_total

    public_path = reverse("public_service_statement", args=[job.public_token])
    public_url = request.build_absolute_uri(public_path)
    whatsapp_message = (
        f"Olá, segue a prestação de contas do serviço {job.title}, com horas e despesas registradas: {public_url}"
    )
    whatsapp_url = ""
    if job.client_whatsapp:
        digits = "".join(character for character in job.client_whatsapp if character.isdigit())
        if digits:
            whatsapp_url = f"https://wa.me/{digits}?text={quote(whatsapp_message)}"

    professional = job.professional
    professional_name = professional.get_full_name() or professional.email or professional.username

    return {
        "job": job,
        "work_logs": work_logs,
        "travel_expenses": travel_expenses,
        "service_items": service_items,
        "excluded_items": excluded_items,
        "expense_total": expense_total,
        "service_items_total": service_items_total,
        "labor_total": labor_total,
        "grand_total": grand_total,
        "professional_name": professional_name,
        "professional_contact": professional.email,
        "client_name": job.client_display_name,
        "emitted_at": timezone.localtime(),
        "public_url": public_url,
        "whatsapp_url": whatsapp_url,
        "is_public": is_public,
    }


@login_required
def service_statement(request, job_id):
    denied = service_views._redirect_if_not_mei(request)
    if denied:
        return denied
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "client", "category", "contract"),
        id=job_id,
        professional=request.user,
    )
    return render(
        request,
        "services/service_statement.html",
        _statement_context(request, job, is_public=False),
    )


def public_service_statement(request, token):
    job = get_object_or_404(
        ServiceJob.objects.select_related("professional", "client", "category", "contract"),
        public_token=token,
    )
    return render(
        request,
        "services/service_statement.html",
        _statement_context(request, job, is_public=True),
    )
