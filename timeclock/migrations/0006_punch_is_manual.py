from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timeclock", "0005_enforce_unique_active_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="punch",
            name="is_manual",
            field=models.BooleanField(default=False),
        ),
    ]
