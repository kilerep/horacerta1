from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="hiringorganization",
            name="cnpj",
            field=models.CharField(blank=True, default="", max_length=18),
        ),
    ]
