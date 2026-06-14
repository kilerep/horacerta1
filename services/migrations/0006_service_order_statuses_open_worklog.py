from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0005_servicejob_billing_mode_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicejob",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Rascunho"),
                    ("PLANNED", "Planejado"),
                    ("SENT", "Enviado ao cliente"),
                    ("SCHEDULED", "Agendado"),
                    ("IN_PROGRESS", "Em execucao"),
                    ("FINISHED", "Finalizado"),
                    ("ARCHIVED", "Arquivado"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="serviceworklog",
            name="end_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
