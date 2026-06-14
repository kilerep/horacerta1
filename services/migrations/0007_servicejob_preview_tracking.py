from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0006_service_order_statuses_open_worklog"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicejob",
            name="preview_first_viewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicejob",
            name="preview_generated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicejob",
            name="preview_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicejob",
            name="preview_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
