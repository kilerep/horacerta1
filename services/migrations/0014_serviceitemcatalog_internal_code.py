from collections import defaultdict

from django.db import migrations, models
from django.db.models import Q


TYPE_PREFIXES = {
    "MATERIAL": "MAT",
    "EXPENSE": "DES",
    "PART": "PEC",
    "TOLL": "VIA",
    "FUEL": "VIA",
    "PARKING": "VIA",
    "FOOD": "DES",
    "OTHER": "OUT",
}


def backfill_internal_codes(apps, schema_editor):
    ServiceItemCatalog = apps.get_model("services", "ServiceItemCatalog")
    counters = defaultdict(int)
    items = (
        ServiceItemCatalog.objects.select_related("category")
        .order_by("professional_id", "category__slug", "item_type", "created_at")
    )
    for item in items:
        if item.internal_code:
            continue
        if item.category_id and item.category and item.category.slug:
            prefix = item.category.slug[:3].upper()
        else:
            prefix = TYPE_PREFIXES.get(item.item_type, "ITE")
        key = (item.professional_id, prefix)
        counters[key] += 1
        candidate = f"{prefix}-{counters[key]:04d}"
        while ServiceItemCatalog.objects.filter(professional_id=item.professional_id, internal_code=candidate).exclude(pk=item.pk).exists():
            counters[key] += 1
            candidate = f"{prefix}-{counters[key]:04d}"
        item.internal_code = candidate
        item.save(update_fields=["internal_code"])


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0013_servicerequestitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceitemcatalog",
            name="internal_code",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.RunPython(backfill_internal_codes, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="serviceitemcatalog",
            index=models.Index(fields=["professional", "internal_code"], name="services_se_profess_code_idx"),
        ),
        migrations.AddConstraint(
            model_name="serviceitemcatalog",
            constraint=models.UniqueConstraint(
                fields=("professional", "internal_code"),
                condition=Q(internal_code__gt=""),
                name="unique_service_catalog_code_per_professional",
            ),
        ),
    ]
