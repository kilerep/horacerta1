from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0014_employee_end_reason_employee_ended_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="contact_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="company",
            name="whatsapp",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]
