# Split from the former monolithic accounts/views.py — see
# docs/EMPRESA_HORACERTA_ORGANIZACAO.md. Helpers/imports come from
# ._shared; this file only holds the views for its own audience.
from ._shared import *  # noqa: F401,F403


@require_GET
def public_service_report_conference(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
    )
    now = timezone.now()
    unavailable_reason = ""
    if report.conference_revoked_at:
        unavailable_reason = "Este link de conferencia foi revogado pelo profissional."
    elif report.conference_is_expired:
        unavailable_reason = "Este link de conferencia expirou."
        if report.conference_final_status != ServiceReport.ConferenceStatus.EXPIRED:
            report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
            report.save(update_fields=["conference_final_status", "updated_at"])

    if unavailable_reason:
        return render(
            request,
            "public/service_report_conference.html",
            {
                "report": None,
                "payload": {},
                "unavailable_reason": unavailable_reason,
            },
            status=410,
        )

    update_fields = []
    first_viewed_now = False
    if not report.conference_first_viewed_at:
        report.conference_first_viewed_at = now
        update_fields.append("conference_first_viewed_at")
        first_viewed_now = True
    if report.conference_final_status == ServiceReport.ConferenceStatus.PENDING:
        report.conference_final_status = ServiceReport.ConferenceStatus.VIEWED
        update_fields.append("conference_final_status")
    if report.status == ServiceReport.Status.SENT:
        report.status = ServiceReport.Status.VIEWED
        update_fields.append("status")
    if update_fields:
        update_fields.append("updated_at")
        report.save(update_fields=update_fields)
        if first_viewed_now:
            _notify_service_report_viewed(report, now)
            track(getattr(report.employee, "user", None), REPORT_PUBLIC_VIEWED)

    public_pdf_url = reverse("public_service_report_pdf", args=[report.conference_token])
    public_xlsx_url = reverse("public_service_report_xlsx", args=[report.conference_token])
    return render(
        request,
        "public/service_report_conference.html",
        {
            "report": report,
            "payload": report.summary_payload or {},
            "conference_url": request.build_absolute_uri(),
            "pdf_url": public_pdf_url,
            "xlsx_url": public_xlsx_url,
            "respond_url": reverse("public_service_report_respond", args=[report.conference_token]),
            "contest_reasons": CONTEST_REASONS,
            "already_responded": report.conference_final_status
            in {ServiceReport.ConferenceStatus.REVIEWED, ServiceReport.ConferenceStatus.DIVERGENT},
            "contest_error": request.GET.get("erro") == "contestacao",
        },
    )


CONTEST_REASONS = {
    "horarios": "Horários",
    "valor": "Valor",
    "periodo": "Período",
    "servico": "Serviço",
    "outro": "Outro",
}


@require_POST
def public_service_report_respond(request, token):
    """Resposta do cliente final ao relatorio, sem conta.

    "Confirmar recebimento" NAO e aprovacao de pagamento nem verificacao de
    identidade: so registra que alguem com o link recebeu e conferiu. So por POST
    (GET nunca confirma), so em link ativo, e a primeira resposta nao e
    sobrescrita por quem tem o mesmo link.
    """
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
    )
    back = reverse("public_service_report_conference", args=[report.conference_token])
    if not report.conference_is_accessible:
        return render(
            request,
            "public/service_report_conference.html",
            {"report": None, "payload": {}, "unavailable_reason": "Este link nao aceita mais respostas."},
            status=410,
        )
    if report.conference_final_status in {
        ServiceReport.ConferenceStatus.REVIEWED,
        ServiceReport.ConferenceStatus.DIVERGENT,
    }:
        return redirect(back)

    action = (request.POST.get("action") or "").strip()
    now = timezone.now()
    if action == "confirm":
        report.conference_final_status = ServiceReport.ConferenceStatus.REVIEWED
        report.conference_reviewed_at = now
        report.save(update_fields=["conference_final_status", "conference_reviewed_at", "updated_at"])
        _notify_service_report_client_response(report, contested=False)
        track(getattr(report.employee, "user", None), REPORT_CLIENT_RESPONDED, kind="confirm")
        return redirect(back)

    if action == "contest":
        reason_key = (request.POST.get("reason") or "").strip()
        text = " ".join((request.POST.get("message") or "").split())[:1000]
        if reason_key not in CONTEST_REASONS or len(text) < 3:
            return redirect(f"{back}?erro=contestacao")
        report.conference_final_status = ServiceReport.ConferenceStatus.DIVERGENT
        report.conference_reviewed_at = now
        report.conference_comment = f"[{CONTEST_REASONS[reason_key]}] {text}"
        report.save(
            update_fields=["conference_final_status", "conference_reviewed_at", "conference_comment", "updated_at"]
        )
        _notify_service_report_client_response(report, contested=True)
        track(getattr(report.employee, "user", None), REPORT_CLIENT_RESPONDED, kind="contest")
        return redirect(back)

    return redirect(back)


@require_GET
def public_service_report_pdf(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
        conference_revoked_at__isnull=True,
    )
    if report.conference_is_expired:
        report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
        report.save(update_fields=["conference_final_status", "updated_at"])
        raise PermissionDenied("Link de conferencia expirado.")
    if not report.conference_first_viewed_at:
        viewed_at = timezone.now()
        report.conference_first_viewed_at = viewed_at
        report.save(update_fields=["conference_first_viewed_at", "updated_at"])
        _notify_service_report_viewed(report, viewed_at)
    return _service_report_pdf_response(report)


@require_GET
def public_service_report_xlsx(request, token):
    report = get_object_or_404(
        ServiceReport.objects.select_related("company", "contract", "employee", "employee__user"),
        conference_token=token,
        conference_revoked_at__isnull=True,
    )
    if report.conference_is_expired:
        report.conference_final_status = ServiceReport.ConferenceStatus.EXPIRED
        report.save(update_fields=["conference_final_status", "updated_at"])
        raise PermissionDenied("Link de conferencia expirado.")
    if not report.conference_first_viewed_at:
        viewed_at = timezone.now()
        report.conference_first_viewed_at = viewed_at
        report.save(update_fields=["conference_first_viewed_at", "updated_at"])
        _notify_service_report_viewed(report, viewed_at)
    return _service_report_xlsx_response(report)


def terms_view(request):
    return render(request, "public/terms.html")


def help_view(request):
    return render(request, "public/help.html")


def privacy_view(request):
    return render(request, "public/privacy.html")


def _public_base_url(request):
    app_base_url = (settings.APP_BASE_URL or "").rstrip("/")
    return app_base_url or f"{request.scheme}://{request.get_host()}"


def _public_page_context(request, path="/"):
    base_url = _public_base_url(request)
    canonical_url = f"{base_url}{path}"
    og_image_url = f"{base_url}{static('img/public/prints/painel-profissional-mobile.png.jpg')}"
    return {
        "canonical_url": canonical_url,
        "og_url": canonical_url,
        "og_image_url": og_image_url,
    }


def landing_view(request):
    if request.user.is_authenticated:
        return redirect("employee_dashboard")
    context = _public_page_context(request, "/")
    return render(request, "public/landing.html", context)


def evaluation_view(request):
    context = _public_page_context(request, "/avaliacao/")
    return render(request, "public/evaluation.html", context)


def evaluation_next_step_view(request):
    context = _public_page_context(request, "/avaliacao/proximo-passo/")
    return render(request, "public/evaluation_next_step.html", context)


# Observação: as views "pwa_manifest", "pwa_service_worker" e a seção
# "PWA - PUSH NOTIFICATIONS" que existiam aqui foram removidas em 12/09/2026.
# Eram todas duplicatas mortas do módulo accounts/pwa.py, que é o que de fato
# está ligado nas URLs (config/urls.py usa `pwa.*`, nunca
# essas funções). Essas views nunca foram chamadas em produção, mas deixavam
# um `@csrf_exempt` e respostas de sucesso falsas soltas no código — risco de
# alguém religar isso sem perceber. accounts/pwa.py já responde de forma
# honesta (HTTP 501 / "ainda não disponível"), então nada muda pro usuário.


# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
