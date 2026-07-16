from django.db import migrations


CATEGORIES = [
    ("Gestão", "gestao", "Organização da rotina, clientes, serviços e processos.", 10),
    ("Mercado", "mercado", "Tendências e movimentos que afetam prestadores e empresas contratantes.", 20),
    ("Finanças", "financas", "Formação de preço, custos, cobrança e organização financeira.", 30),
    ("Legislação", "legislacao", "Atualizações explicadas com referência a fontes oficiais.", 40),
    ("Tecnologia", "tecnologia", "Ferramentas, automação e inteligência artificial aplicadas à prestação de serviços.", 50),
    ("Segurança", "seguranca", "Boas práticas operacionais, digitais e de proteção de dados.", 60),
    ("Marketing", "marketing", "Comunicação, proposta de valor, atendimento e relacionamento com clientes.", 70),
    ("Oportunidades", "oportunidades", "Capacitações, programas e oportunidades relevantes para o setor.", 80),
]


def seed_categories(apps, schema_editor):
    category_model = apps.get_model("editorial", "EditorialCategory")
    for name, slug, description, sort_order in CATEGORIES:
        category_model.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def reverse_seed(apps, schema_editor):
    category_model = apps.get_model("editorial", "EditorialCategory")
    category_model.objects.filter(slug__in=[item[1] for item in CATEGORIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("editorial", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_seed),
    ]
