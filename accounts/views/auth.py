# Split from the former monolithic accounts/views.py — see
# docs/EMPRESA_HORACERTA_ORGANIZACAO.md. Helpers/imports come from
# ._shared; this file only holds the views for its own audience.
from ._shared import *  # noqa: F401,F403


def signup(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if request.method == "POST":
        form = UnifiedSignupForm(request.POST)
        if form.is_valid():
            pwd = form.cleaned_data["password1"]
            rh_email = form.cleaned_data["rh_email"]
            user = User.objects.create_user(
                username=rh_email,
                email=rh_email,
                password=pwd,
                role=User.Role.EMPRESA,
            )
            Company.objects.create(
                name=form.cleaned_data["company_name"],
                email=form.cleaned_data.get("company_email") or None,
                owner=user,
            )
            login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
            return _redirect_for_role(user)
    else:
        form = UnifiedSignupForm()

    return render(request, "accounts/signup.html", {"form": form})


def signup_mei(request):
    """Autocadastro publico do prestador/MEI (fluxo principal do produto)."""
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if not getattr(settings, "MEI_SIGNUP_ENABLED", True):
        return render(request, "accounts/signup_mei_closed.html", status=403)

    if request.method == "POST":
        recent_signups = User.objects.filter(
            role=User.Role.FUNCIONARIO, date_joined__gte=timezone.now() - timedelta(minutes=10)
        ).count()
        if recent_signups >= settings.MEI_SIGNUP_MAX_PER_10_MIN:
            return render(request, "accounts/signup_mei_closed.html", {"busy": True}, status=429)
        form = MEISignupForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            first_name, _sep, last_name = data["full_name"].partition(" ")
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data["email"],
                    email=data["email"],
                    password=data["password1"],
                    role=User.Role.FUNCIONARIO,
                    first_name=first_name[:150],
                    last_name=last_name[:150],
                    terms_accepted_at=timezone.now(),
                    terms_version=settings.TERMS_VERSION,
                )
                track(user, SIGNUP_COMPLETED)
            login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
            return _redirect_for_role(user)
    else:
        form = MEISignupForm()

    return render(request, "accounts/signup_mei.html", {"form": form})


# A proteção contra força bruta no login (bloqueio por IP + usuário após
# várias senhas erradas) é feita pelo django-axes — ver AUTHENTICATION_BACKENDS
# e AXES_* em config/settings.py, e accounts/axes_lockout.py para a resposta
# customizada. Ele age no nível do backend de autenticação, então cobre tanto
# esta view quanto o /admin/ nativo do Django com a mesma configuração.
LOGIN_ATTEMPT_LIMIT = settings.AXES_FAILURE_LIMIT


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return _redirect_for_role(user)
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    response = redirect("login")
    # Pede ao navegador que descarte caches HTTP deste site ao sair (aparelho
    # compartilhado). Só "cache": "storage" apagaria também o localStorage
    # (tema, tours dispensados) e desregistraria o service worker.
    response["Clear-Site-Data"] = '"cache"'
    return response


@login_required
def dashboard(request):
    return _redirect_for_role(request.user)




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
