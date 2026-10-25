"""Cenario completo de uso do HoraCerta para os testes de QA.

Usa o seed oficial de demonstracao (prestador com cliente, horas, pedido, servicos,
proposta de evento e catalogo) e completa com o que o seed nao cria: relatorio de
horas com link de conferencia, relatorio de producao, aviso interno, local com QR e
um administrador interno. Os testes de rotas e as jornadas por persona usam isto.
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

PASSWORD = "Teste@12345"
MEI_EMAIL = "qa.prestador@horacerta.test"
COMPANY_EMAIL = "demo.cliente@horacerta.test"


def build_world():
    from accounts.models import User
    from companies.models import CompanyAuthorizedLocation, Employee
    from production.models import ProductionEntry, ProductionSheet
    from services.models import ServiceItemCatalog, ServiceItemExpense, ServiceJob, ServiceRequest
    from timeclock.models import Contract, InternalNotification, Punch, PunchCorrectionRequest, ServiceReport

    with override_settings(DEBUG=True):
        call_command("seed_local_demo_scenarios", "--email", MEI_EMAIL, "--password", PASSWORD, stdout=StringIO())

    mei = User.objects.get(email=MEI_EMAIL)
    company_user = User.objects.get(email=COMPANY_EMAIL)
    employee = Employee.objects.filter(user=mei).first()
    contract = Contract.objects.filter(employee__user=mei, is_active=True).first()
    company = contract.company

    today = timezone.localdate()
    report = ServiceReport(
        company=company, employee=employee, contract=contract, title="Relatório QA",
        date_from=today - timedelta(days=14), date_to=today,
    )
    from accounts.views._shared import _build_service_report_payload

    report.summary_payload = _build_service_report_payload(contract, report.date_from, report.date_to)
    report.ensure_conference_link()
    report.save()

    sheet = ProductionSheet.objects.create(owner=mei, equipment="Chenlong QA", company_name=company.name,
                                           operator_name="Prestador QA", supervisor_name="Carlos",
                                           supervisor_whatsapp="11988887777")
    entry = ProductionEntry.objects.create(sheet=sheet, item_code="0011-024", destination="IMPLEMENTO",
                                           manual_minutes=90)

    mei_notice = InternalNotification.objects.create(
        recipient_user=mei, audience=InternalNotification.Audience.MEI,
        notification_type=InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
        title="Aviso QA", message="Mensagem de teste.",
    )
    company_notice = InternalNotification.objects.create(
        recipient_company=company, audience=InternalNotification.Audience.COMPANY,
        notification_type=InternalNotification.NotificationType.ADMIN_NOTE_ADDED,
        title="Aviso empresa QA", message="Mensagem de teste.",
    )
    location = CompanyAuthorizedLocation.objects.create(
        company=company, name="Obra QA", latitude=Decimal("-23.550520"), longitude=Decimal("-46.633308"),
        qr_token="qa-token-local-1",
    )
    staff = User.objects.create_superuser(username="qa.admin@horacerta.test", email="qa.admin@horacerta.test",
                                          password=PASSWORD)
    punch = Punch.objects.filter(contract=contract).first()
    correction = None
    if punch is not None:
        correction = PunchCorrectionRequest.objects.filter(contract=contract).first()

    return {
        "mei": mei,
        "company_user": company_user,
        "staff": staff,
        "employee": employee,
        "contract": contract,
        "company": company,
        "report": report,
        "sheet": sheet,
        "entry": entry,
        "mei_notice": mei_notice,
        "company_notice": company_notice,
        "location": location,
        "punch": punch,
        "correction": correction,
        "job": ServiceJob.objects.filter(professional=mei).order_by("created_at").first(),
        "service_request": ServiceRequest.objects.filter(professional=mei).first(),
        "catalog_item": ServiceItemCatalog.objects.filter(professional=mei).first(),
        "job_item": ServiceItemExpense.objects.filter(service_job__professional=mei).first(),
    }
