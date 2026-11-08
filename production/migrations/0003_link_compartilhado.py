import uuid

from django.db import migrations, models


def gerar_codigos(apps, schema_editor):
    ProductionSheet = apps.get_model("production", "ProductionSheet")
    for sheet in ProductionSheet.objects.filter(share_token__isnull=True):
        sheet.share_token = uuid.uuid4()
        sheet.save(update_fields=["share_token"])


class Migration(migrations.Migration):
    """Link secreto por relatorio: cria vazio, preenche um codigo diferente para cada folha
    existente e so entao torna unico e obrigatorio."""

    dependencies = [
        ("production", "0002_encarregado_whatsapp"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionsheet",
            name="share_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(gerar_codigos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="productionsheet",
            name="share_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
