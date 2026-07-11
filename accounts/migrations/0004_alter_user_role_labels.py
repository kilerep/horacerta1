from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_visual_theme"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("EMPRESA", "Empresa contratante"),
                    ("FUNCIONARIO", "Prestador de serviço"),
                ],
                default="FUNCIONARIO",
                max_length=20,
            ),
        ),
    ]
