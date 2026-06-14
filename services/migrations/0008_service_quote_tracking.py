from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0007_servicejob_preview_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicejob",
            name="quote_item_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="servicejob",
            name="quote_message_generated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="serviceitemexpense",
            name="usage_status",
            field=models.CharField(
                choices=[
                    ("PLANNED", "Previsto"),
                    ("QUOTED", "Cotado"),
                    ("PURCHASED", "Comprado"),
                    ("USED", "Usado"),
                    ("PARTIALLY_USED", "Parcialmente usado"),
                    ("NOT_USED", "Nao usado"),
                    ("RETURNED", "Devolvido"),
                ],
                default="PLANNED",
                max_length=24,
            ),
        ),
    ]
