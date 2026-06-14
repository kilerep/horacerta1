import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("services", "0008_service_quote_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceitemexpense",
            name="unit",
            field=models.CharField(
                choices=[
                    ("UNIT", "unidade"),
                    ("METER", "metro"),
                    ("ROLL", "rolo"),
                    ("PACKAGE", "pacote"),
                    ("LITER", "litro"),
                    ("HOUR", "hora"),
                    ("SERVICE", "servico"),
                    ("OTHER", "outro"),
                ],
                default="UNIT",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ServiceItemCatalog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("item_type", models.CharField(choices=[("MATERIAL", "Material"), ("EXPENSE", "Despesa"), ("PART", "Peca"), ("TOLL", "Pedagio"), ("FUEL", "Combustivel"), ("PARKING", "Estacionamento"), ("FOOD", "Alimentacao"), ("OTHER", "Outro")], default="MATERIAL", max_length=20)),
                ("name", models.CharField(max_length=140)),
                ("description", models.TextField(blank=True, default="")),
                ("unit", models.CharField(choices=[("UNIT", "unidade"), ("METER", "metro"), ("ROLL", "rolo"), ("PACKAGE", "pacote"), ("LITER", "litro"), ("HOUR", "hora"), ("SERVICE", "servico"), ("OTHER", "outro")], default="UNIT", max_length=20)),
                ("estimated_unit_value", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("last_used_value", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("default_quantity", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=10)),
                ("favorite", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="catalog_items", to="services.servicecategory")),
                ("professional", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_item_catalog", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Item do catalogo",
                "verbose_name_plural": "Itens do catalogo",
                "ordering": ["-favorite", "name"],
                "indexes": [
                    models.Index(fields=["professional", "is_active", "name"], name="services_se_profess_8f9b2f_idx"),
                    models.Index(fields=["professional", "favorite", "name"], name="services_se_profess_fa8e6f_idx"),
                    models.Index(fields=["professional", "category", "name"], name="services_se_profess_6f5636_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="serviceitemexpense",
            name="catalog_item",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_items", to="services.serviceitemcatalog"),
        ),
        migrations.AddIndex(
            model_name="serviceitemexpense",
            index=models.Index(fields=["catalog_item", "-created_at"], name="services_se_catalog_808f76_idx"),
        ),
    ]
