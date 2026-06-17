from django.db import migrations, models


def move_legacy_scheduled_to_planned(apps, schema_editor):
    ServiceJob = apps.get_model("services", "ServiceJob")
    ServiceJob.objects.filter(status="SCHEDULED").update(status="PLANNED")


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0011_servicejob_quote_last_message"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicejob",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Rascunho"),
                    ("PLANNED", "Planejado"),
                    ("SENT", "Previa enviada"),
                    ("SCHEDULED", "Planejado"),
                    ("IN_PROGRESS", "Em execucao"),
                    ("FINISHED", "Finalizado"),
                    ("REPORT_SENT", "Relatorio enviado"),
                    ("ARCHIVED", "Arquivado"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.RunPython(move_legacy_scheduled_to_planned, migrations.RunPython.noop),
    ]
