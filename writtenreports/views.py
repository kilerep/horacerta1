"""Telas do relatorio escrito: lista, rascunho, emitir, excluir, PDF e link publico do cliente."""

from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .data import sender_name
from .exports import build_pdf, pdf_filename
from .models import SECTIONS, WrittenReport


def _client_suggestions(user):
    """Nomes de clientes ja cadastrados, so como sugestao no campo livre."""
    from accounts.mei_context import mei_contracts_for_user

    names = []
    for contract in mei_contracts_for_user(user, include_inactive_contracts=True):
        if contract.company.name not in names:
            names.append(contract.company.name)
    return names


def _report_for(request, report_id):
    return get_object_or_404(WrittenReport, id=report_id, owner=request.user)


def _parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _read_form(request, report):
    """Preenche o rascunho com o POST; devolve a lista de erros (vazia = ok)."""
    post = request.POST
    errors = []
    report.kind = WrittenReport.Kind.SERVICE
    report.title = (post.get("title") or "").strip()[:140]
    report.client_name = (post.get("client_name") or "").strip()[:140]
    report.service_name = (post.get("service_name") or "").strip()[:160]
    report.date_from, report.date_to = _parse_date(post.get("date_from")), _parse_date(post.get("date_to"))
    if report.date_from and report.date_to and report.date_from > report.date_to:
        report.date_from, report.date_to = report.date_to, report.date_from
    for field, _label in SECTIONS:
        setattr(report, field, (post.get(field) or "").strip())
    if not report.title:
        errors.append("Dê um título ao relatório.")
    if not report.client_name:
        errors.append("Informe o cliente ou a empresa.")
    if not report.service_name:
        errors.append("Informe o serviço realizado.")
    return errors


def _form(request, report, errors=()):
    return render(request, "writtenreports/form.html", {
        "report": report, "is_new": report._state.adding, "errors": errors,
        "sections": [(f, l, getattr(report, f)) for f, l in SECTIONS],
        "client_suggestions": _client_suggestions(request.user),
        "today": timezone.localdate().isoformat(),
    })


@login_required
def report_list(request):
    reports = WrittenReport.objects.filter(owner=request.user).select_related("contract__company", "service_job")
    return render(request, "writtenreports/list.html", {
        "drafts": [r for r in reports if not r.is_locked], "issued": [r for r in reports if r.is_locked],
    })


@login_required
def report_create(request):
    report = WrittenReport(owner=request.user, kind=WrittenReport.Kind.SERVICE)
    if request.method == "POST":
        errors = _read_form(request, report)
        if not errors:
            report.save()
            messages.success(request, "Rascunho salvo. Confira o documento e toque em Emitir.")
            return redirect("written_report_detail", report_id=report.id)
        return _form(request, report, errors)
    return _form(request, report)


@login_required
def report_edit(request, report_id):
    report = _report_for(request, report_id)
    if report.is_locked:
        messages.info(request, "Relatório emitido fica travado. Para mudar, exclua e faça outro.")
        return redirect("written_report_detail", report_id=report.id)
    if request.method == "POST":
        errors = _read_form(request, report)
        if not errors:
            report.save()
            messages.success(request, "Rascunho atualizado.")
            return redirect("written_report_detail", report_id=report.id)
        return _form(request, report, errors)
    return _form(request, report)


@login_required
def report_detail(request, report_id):
    report = _report_for(request, report_id)
    preview = report.snapshot if report.is_locked else _preview(report)
    return render(request, "writtenreports/detail.html", {"report": report, "data": preview})


def _preview(report):
    """Rascunho mostra os numeros atuais; so a emissao congela."""
    from .data import build_snapshot

    try:
        return build_snapshot(report)
    except Exception:  # rascunho incompleto (sem cliente/servico): mostra so o texto
        return {}


@login_required
@require_POST
def report_issue(request, report_id):
    report = _report_for(request, report_id)
    try:
        report.issue()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, f"Relatório nº {report.number_label} emitido e travado.")
    return redirect("written_report_detail", report_id=report.id)


@login_required
@require_POST
def report_delete(request, report_id):
    report = _report_for(request, report_id)
    label = report.number_label
    report.delete()
    messages.success(request, f"Relatório {label} excluído." if report.number else "Rascunho excluído.")
    return redirect("written_report_list")


def _pdf_response(report, inline=True):
    response = HttpResponse(build_pdf(report), content_type="application/pdf")
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{pdf_filename(report)}"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def report_pdf(request, report_id):
    return _pdf_response(_report_for(request, report_id))


@login_required
def report_whatsapp(request, report_id):
    report = _report_for(request, report_id)
    if not report.is_locked:
        raise Http404
    link = request.build_absolute_uri(reverse("written_report_public", args=[report.share_token]))
    text = (f"Olá! Segue o *{report.get_kind_display().lower()} nº {report.number_label}* "
            f"({report.title}). Para ler e baixar em PDF: {link}")
    return redirect(f"https://wa.me/?text={quote(text, safe='')}")


def _public(token):
    report = get_object_or_404(WrittenReport.objects.select_related("owner"), share_token=token)
    if not report.is_locked:
        raise Http404
    return report


def report_public(request, token):
    report = _public(token)
    is_owner = request.user.is_authenticated and request.user.pk == report.owner_id
    if not is_owner and not report.viewed_at:
        WrittenReport.objects.filter(pk=report.pk, viewed_at__isnull=True).update(viewed_at=timezone.now())
    response = render(request, "writtenreports/public.html", {
        "report": report, "data": report.snapshot, "sender": report.snapshot.get("sender") or sender_name(report.owner),
    })
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def report_public_pdf(request, token):
    return _pdf_response(_public(token))
