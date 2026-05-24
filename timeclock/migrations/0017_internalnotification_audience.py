from django.db import migrations, models


def classify_existing_notifications(apps, schema_editor):
    InternalNotification = apps.get_model("timeclock", "InternalNotification")
    User = apps.get_model("accounts", "User")
    for notification in InternalNotification.objects.all().iterator():
        if notification.recipient_company_id:
            audience = "company"
        elif notification.recipient_user_id:
            user = User.objects.filter(id=notification.recipient_user_id).first()
            audience = "internal_admin" if user and user.is_superuser else "mei"
        else:
            audience = "internal_admin"
        InternalNotification.objects.filter(id=notification.id).update(audience=audience)


class Migration(migrations.Migration):

    dependencies = [
        ("timeclock", "0016_internalnotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="internalnotification",
            name="audience",
            field=models.CharField(
                choices=[
                    ("internal_admin", "Admin interno"),
                    ("company", "Empresa"),
                    ("mei", "Prestador/MEI"),
                ],
                db_index=True,
                default="internal_admin",
                max_length=30,
            ),
        ),
        migrations.RunPython(classify_existing_notifications, migrations.RunPython.noop),
    ]
