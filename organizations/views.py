from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User

from .forms import (
    HiringOrganizationSetupForm,
    OrganizationMemberInviteForm,
    ProviderLinkEndForm,
    ProviderLinkInviteForm,
)
from .models import HiringOrganization, OrganizationAuditEvent, OrganizationMember, ProviderOrganizationLink


def _require_company_account(user):
    if user.role != User.Role.EMPRESA:
        raise PermissionDenied("Esta área é exclusiva para empresas contratantes.")


def _require_provider_account(user):
    if user.role != User.Role.FUNCIONARIO:
        raise PermissionDenied("Esta área é exclusiva para prestadores de serviço.")


def _active_membership_or_404(user, organization_id):
    return get_object_or_404(
        OrganizationMember.objects.select_related("organization", "user"),
        organization_id=organization_id,
        user=user,
        status=OrganizationMember.Status.ACTIVE,
        organization__status=HiringOrganization.Status.ACTIVE,
    )


def _record_event(*, organization, actor, event_type, summary, target=None, metadata=None):
    OrganizationAuditEvent.objects.create(
        organization=organization,
        actor=actor,
        event_type=event_type,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        summary=summary,
        metadata=metadata or {},
    )


@login_required
def organization_entry(request):
    _require_company_account(request.user)
    membership = (
        OrganizationMember.objects.filter(
            user=request.user,
            status=OrganizationMember.Status.ACTIVE,
            organization__status=HiringOrganization.Status.ACTIVE,
        )
        .select_related("organization")
        .order_by("organization__name")
        .first()
    )
    if membership:
        return redirect("organization_dashboard", organization_id=membership.organization_id)

    if OrganizationMember.objects.filter(
        user=request.user,
        status=OrganizationMember.Status.INVITED,
    ).exists():
        return redirect("organization_invites")

    return redirect("organization_setup")


@login_required
def organization_setup(request):
    _require_company_account(request.user)
    if OrganizationMember.objects.filter(
        user=request.user,
        status=OrganizationMember.Status.ACTIVE,
        organization__status=HiringOrganization.Status.ACTIVE,
    ).exists():
        messages.info(request, "Sua conta já participa de uma empresa contratante.")
        return redirect("organization_entry")

    form = HiringOrganizationSetupForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            organization = form.save()
            membership = OrganizationMember.objects.create(
                organization=organization,
                user=request.user,
                role=OrganizationMember.Role.ADMIN,
                status=OrganizationMember.Status.ACTIVE,
            )
            _record_event(
                organization=organization,
                actor=request.user,
                event_type="organization.created",
                summary="Empresa contratante criada e primeiro administrador definido.",
                target=membership,
            )
        messages.success(
            request,
            "Empresa criada. Agora você pode revisar os dados e convidar pessoas da sua equipe.",
        )
        return redirect("organization_dashboard", organization_id=organization.id)

    return render(request, "organizations/setup.html", {"form": form})


@login_required
def organization_dashboard(request, organization_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    organization = membership.organization

    provider_links = organization.provider_links.all()
    context = {
        "organization": organization,
        "membership": membership,
        "active_provider_count": provider_links.filter(status=ProviderOrganizationLink.Status.ACTIVE).count(),
        "pending_provider_count": provider_links.filter(
            status__in=[
                ProviderOrganizationLink.Status.INVITED,
                ProviderOrganizationLink.Status.AWAITING_PROVIDER,
            ]
        ).count(),
        "active_member_count": organization.members.filter(status=OrganizationMember.Status.ACTIVE).count(),
        "pending_member_count": organization.members.filter(status=OrganizationMember.Status.INVITED).count(),
        "recent_events": organization.audit_events.select_related("actor")[:8],
    }
    return render(request, "organizations/dashboard.html", context)


@login_required
def organization_members(request, organization_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    organization = membership.organization
    members = organization.members.select_related("user", "invited_by").order_by("status", "user__email")
    return render(
        request,
        "organizations/members.html",
        {"organization": organization, "membership": membership, "members": members},
    )


@login_required
def organization_member_invite(request, organization_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    if not membership.can_manage_members:
        raise PermissionDenied("Somente administradores podem convidar membros.")

    organization = membership.organization
    form = OrganizationMemberInviteForm(request.POST or None, organization=organization)
    if request.method == "POST" and form.is_valid():
        invited_user = form.user_to_invite
        invited_membership = OrganizationMember.objects.create(
            organization=organization,
            user=invited_user,
            role=form.cleaned_data["role"],
            status=OrganizationMember.Status.INVITED,
            invited_by=request.user,
        )
        _record_event(
            organization=organization,
            actor=request.user,
            event_type="member.invited",
            summary=f"Convite enviado para {invited_user.email}.",
            target=invited_membership,
            metadata={"role": invited_membership.role},
        )
        messages.success(request, "Convite registrado. A pessoa poderá aceitá-lo ao acessar a área empresarial.")
        return redirect("organization_members", organization_id=organization.id)

    return render(
        request,
        "organizations/member_invite.html",
        {"organization": organization, "membership": membership, "form": form},
    )


@login_required
def organization_invites(request):
    _require_company_account(request.user)
    invites = (
        OrganizationMember.objects.filter(
            user=request.user,
            status=OrganizationMember.Status.INVITED,
            organization__status=HiringOrganization.Status.ACTIVE,
        )
        .select_related("organization", "invited_by")
        .order_by("organization__name")
    )
    return render(request, "organizations/invites.html", {"invites": invites})


@login_required
def organization_invite_accept(request, membership_id):
    _require_company_account(request.user)
    membership = get_object_or_404(
        OrganizationMember.objects.select_related("organization"),
        id=membership_id,
        user=request.user,
        status=OrganizationMember.Status.INVITED,
        organization__status=HiringOrganization.Status.ACTIVE,
    )
    if request.method != "POST":
        return redirect("organization_invites")

    membership.status = OrganizationMember.Status.ACTIVE
    membership.save()
    _record_event(
        organization=membership.organization,
        actor=request.user,
        event_type="member.joined",
        summary=f"{request.user.email} aceitou o convite da empresa.",
        target=membership,
        metadata={"role": membership.role},
    )
    messages.success(request, "Convite aceito. Você já pode acessar o painel da empresa.")
    return redirect("organization_dashboard", organization_id=membership.organization_id)


@login_required
def organization_providers(request, organization_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    links = membership.organization.provider_links.select_related("provider", "invited_by").order_by(
        "status", "provider__email"
    )
    return render(
        request,
        "organizations/providers.html",
        {"organization": membership.organization, "membership": membership, "links": links},
    )


@login_required
def organization_provider_invite(request, organization_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    if not membership.can_manage_services:
        raise PermissionDenied("Seu papel não permite convidar prestadores.")

    organization = membership.organization
    form = ProviderLinkInviteForm(
        request.POST or None,
        organization=organization,
        allow_financial=membership.can_view_financial,
    )
    if request.method == "POST" and form.is_valid():
        link = ProviderOrganizationLink.objects.create(
            organization=organization,
            provider=form.provider,
            status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
            initiated_by=ProviderOrganizationLink.InitiatedBy.ORGANIZATION,
            invited_by=request.user,
            share_services=form.cleaned_data["share_services"],
            share_hours=form.cleaned_data["share_hours"],
            share_reports=form.cleaned_data["share_reports"],
            share_financial_values=form.cleaned_data["share_financial_values"],
        )
        _record_event(
            organization=organization,
            actor=request.user,
            event_type="provider.invited",
            summary=f"Convite de vínculo enviado para {link.provider.email}.",
            target=link,
            metadata={
                "share_services": link.share_services,
                "share_hours": link.share_hours,
                "share_reports": link.share_reports,
                "share_financial_values": link.share_financial_values,
            },
        )
        messages.success(request, "Convite registrado. O prestador precisa aceitar o vínculo.")
        return redirect("organization_providers", organization_id=organization.id)

    return render(
        request,
        "organizations/provider_invite.html",
        {"organization": organization, "membership": membership, "form": form},
    )


@login_required
def provider_link_invites(request):
    _require_provider_account(request.user)
    invites = (
        ProviderOrganizationLink.objects.filter(
            provider=request.user,
            status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
            organization__status=HiringOrganization.Status.ACTIVE,
        )
        .select_related("organization", "invited_by")
        .order_by("organization__name")
    )
    active_links = (
        ProviderOrganizationLink.objects.filter(
            provider=request.user,
            status=ProviderOrganizationLink.Status.ACTIVE,
            organization__status=HiringOrganization.Status.ACTIVE,
        )
        .select_related("organization")
        .order_by("organization__name")
    )
    return render(
        request,
        "organizations/provider_invites.html",
        {"invites": invites, "active_links": active_links},
    )


@login_required
def provider_link_accept(request, link_id):
    _require_provider_account(request.user)
    link = get_object_or_404(
        ProviderOrganizationLink.objects.select_related("organization"),
        id=link_id,
        provider=request.user,
        status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
        organization__status=HiringOrganization.Status.ACTIVE,
    )
    if request.method != "POST":
        return redirect("provider_link_invites")

    link.status = ProviderOrganizationLink.Status.ACTIVE
    link.save()
    _record_event(
        organization=link.organization,
        actor=request.user,
        event_type="provider.joined",
        summary=f"{request.user.email} aceitou o vínculo como prestador.",
        target=link,
    )
    messages.success(request, "Vínculo aceito. A empresa verá somente as informações autorizadas.")
    return redirect("provider_link_invites")


@login_required
def provider_link_decline(request, link_id):
    _require_provider_account(request.user)
    link = get_object_or_404(
        ProviderOrganizationLink.objects.select_related("organization"),
        id=link_id,
        provider=request.user,
        status=ProviderOrganizationLink.Status.AWAITING_PROVIDER,
    )
    if request.method != "POST":
        return redirect("provider_link_invites")

    link.status = ProviderOrganizationLink.Status.DECLINED
    link.save()
    _record_event(
        organization=link.organization,
        actor=request.user,
        event_type="provider.declined",
        summary=f"{request.user.email} recusou o vínculo como prestador.",
        target=link,
    )
    messages.info(request, "Convite recusado. Nenhuma informação foi compartilhada.")
    return redirect("provider_link_invites")


@login_required
def organization_provider_suspend(request, organization_id, link_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    if not membership.can_manage_members:
        raise PermissionDenied("Somente administradores podem suspender vínculos.")
    link = get_object_or_404(
        ProviderOrganizationLink,
        id=link_id,
        organization=membership.organization,
        status=ProviderOrganizationLink.Status.ACTIVE,
    )
    if request.method == "POST":
        link.status = ProviderOrganizationLink.Status.SUSPENDED
        link.save()
        _record_event(
            organization=membership.organization,
            actor=request.user,
            event_type="provider.suspended",
            summary=f"Vínculo com {link.provider.email} suspenso.",
            target=link,
        )
        messages.success(request, "Vínculo suspenso. O compartilhamento foi interrompido.")
    return redirect("organization_providers", organization_id=organization_id)


@login_required
def organization_provider_resume(request, organization_id, link_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    if not membership.can_manage_members:
        raise PermissionDenied("Somente administradores podem reativar vínculos.")
    link = get_object_or_404(
        ProviderOrganizationLink,
        id=link_id,
        organization=membership.organization,
        status=ProviderOrganizationLink.Status.SUSPENDED,
    )
    if request.method == "POST":
        link.status = ProviderOrganizationLink.Status.ACTIVE
        link.save()
        _record_event(
            organization=membership.organization,
            actor=request.user,
            event_type="provider.resumed",
            summary=f"Vínculo com {link.provider.email} reativado.",
            target=link,
        )
        messages.success(request, "Vínculo reativado com as permissões anteriores.")
    return redirect("organization_providers", organization_id=organization_id)


@login_required
def organization_provider_end(request, organization_id, link_id):
    _require_company_account(request.user)
    membership = _active_membership_or_404(request.user, organization_id)
    if not membership.can_manage_members:
        raise PermissionDenied("Somente administradores podem encerrar vínculos.")
    link = get_object_or_404(
        ProviderOrganizationLink.objects.select_related("provider"),
        id=link_id,
        organization=membership.organization,
        status__in=[ProviderOrganizationLink.Status.ACTIVE, ProviderOrganizationLink.Status.SUSPENDED],
    )
    form = ProviderLinkEndForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        link.status = ProviderOrganizationLink.Status.ENDED
        link.end_reason = form.cleaned_data["reason"]
        link.save()
        _record_event(
            organization=membership.organization,
            actor=request.user,
            event_type="provider.ended",
            summary=f"Vínculo com {link.provider.email} encerrado.",
            target=link,
            metadata={"reason": link.end_reason},
        )
        messages.success(request, "Vínculo encerrado. O histórico foi preservado.")
        return redirect("organization_providers", organization_id=organization_id)

    return render(
        request,
        "organizations/provider_end.html",
        {"organization": membership.organization, "membership": membership, "link": link, "form": form},
    )
