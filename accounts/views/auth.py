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
    return redirect("login")


@login_required
def dashboard(request):
    return _redirect_for_role(request.user)




# Re-export everything defined/imported above (including helpers
# with a leading underscore, which default `import *` would
# otherwise skip) so `accounts/views/__init__.py` can re-export it
# with a plain `from .this_module import *`.
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
