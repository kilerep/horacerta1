from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password-reset/",
        views.RenderAwarePasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    path("", views.dashboard),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/funcionario/", views.dashboard_employee, name="dashboard_employee"),
    path("dashboard/profile/", views.company_profile, name="company_profile"),
    path("empresa/", views.dashboard_empresa, name="dashboard_empresa"),
    path("empresa/meis/", views.company_meis, name="company_meis"),
    path("empresa/meis/<uuid:employee_id>/", views.company_mei_profile, name="company_mei_profile"),
    path("empresa/meis/<uuid:employee_id>/fechamento/", views.company_mei_closure, name="company_mei_closure"),
    path("empresa/contratos/", views.company_contracts, name="company_contracts"),
    path("empresa/relatorios-servico/", views.company_service_reports, name="company_service_reports"),
    path(
        "empresa/relatorios-servico/<uuid:report_id>/",
        views.company_service_report_detail,
        name="company_service_report_detail",
    ),
    path("empresa/relatorios/", views.company_reports, name="company_reports"),
    path("empresa/operacao-hoje/", views.company_today_center, name="company_today_center"),
    path("empresa/resumo-operacional/", views.company_operational_summary, name="company_operational_summary"),
    path("empresa/pendencias/", views.company_incident_center, name="company_incident_center"),
    path(
        "empresa/confiabilidade-registro/locais/<uuid:location_id>/qr/",
        views.company_location_qr_panel,
        name="company_location_qr_panel",
    ),
    path("empresa/revisao-registros/", views.company_records_review_center, name="company_records_review_center"),
    path(
        "empresa/revisao-registros/<uuid:punch_id>/",
        views.company_record_review_detail,
        name="company_record_review_detail",
    ),
    path("empresa/confiabilidade-registro/", views.company_attendance_reliability, name="company_attendance_reliability"),
    path("dashboard/history/", views.company_history, name="company_history"),
    path("empresa/historico/", views.company_history, name="company_history_legacy"),
    path("empresa/docs/", views.company_docs, name="company_docs"),
    path("empresa/meu-plano/", views.company_plan, name="company_plan"),
    path("empresa/configuracoes/", views.company_settings, name="company_settings"),

    path("me/painel/", views.mei_panel, name="mei_panel"),
    path("me/profile/", views.mei_profile, name="mei_profile"),
    path("me/historico/", views.mei_history, name="mei_history"),
    path("me/exportar/", views.mei_export, name="mei_export"),
    path("me/contract/", views.mei_contract, name="mei_contract_en"),
    path("me/contrato/", views.mei_contract, name="mei_contract"),
    path("me/relatorios/", views.mei_reports, name="mei_reports"),
    path("me/relatorios/<uuid:report_id>/", views.mei_service_report_detail, name="mei_service_report_detail"),
    path(
        "me/relatorios/solicitacoes/<uuid:request_id>/",
        views.mei_service_report_request_detail,
        name="mei_service_report_request_detail",
    ),

    path("help/", views.help_view, name="help"),
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("avaliacao/", views.evaluation_view, name="public_evaluation"),
    path("avaliacao/proximo-passo/", views.evaluation_next_step_view, name="public_evaluation_next_step"),
]
