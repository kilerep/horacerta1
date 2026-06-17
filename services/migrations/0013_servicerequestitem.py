from decimal import Decimal
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0012_official_service_statuses"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceRequestItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=140)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=10)),
                ("note", models.CharField(blank=True, default="", max_length=180)),
                ("estimated_unit_value", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "service_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quick_items",
                        to="services.servicerequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Item rapido do pedido",
                "verbose_name_plural": "Itens rapidos do pedido",
                "ordering": ["created_at"],
                "indexes": [models.Index(fields=["service_request", "created_at"], name="services_se_service_5958d7_idx")],
            },
        ),
    ]
