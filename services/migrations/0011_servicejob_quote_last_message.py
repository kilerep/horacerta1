from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0010_servicerequest_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicejob",
            name="quote_last_message",
            field=models.TextField(blank=True, default=""),
        ),
    ]
