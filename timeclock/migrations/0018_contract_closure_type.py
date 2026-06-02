from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timeclock", "0017_internalnotification_audience"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="closure_type",
            field=models.CharField(
                choices=[
                    ("WEEKLY", "Semanal"),
                    ("BIWEEKLY", "Quinzenal"),
                    ("MONTHLY", "Mensal"),
                    ("CUSTOM", "Personalizado"),
                ],
                default="MONTHLY",
                max_length=20,
            ),
        ),
    ]
