from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timeclock", "0018_contract_closure_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicereport",
            name="date_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicereport",
            name="date_to",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicereport",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Rascunho"),
                    ("SENT", "Enviado"),
                    ("VIEWED", "Visualizado"),
                    ("REVIEWED", "Conferido"),
                    ("DIVERGENT", "Com divergencia"),
                    ("PAID", "Pago"),
                    ("CANCELED", "Cancelado"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="servicereport",
            name="summary_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servicereport",
            name="conference_token",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="servicereport",
            name="conference_link_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="servicereport",
            index=models.Index(fields=["employee", "status", "report_date"], name="timeclock_s_employe_4bc698_idx"),
        ),
        migrations.AddIndex(
            model_name="servicereport",
            index=models.Index(fields=["conference_token"], name="timeclock_s_confere_70fe21_idx"),
        ),
    ]
