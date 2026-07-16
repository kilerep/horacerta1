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


def preserve_categories(apps, schema_editor):
    # As categorias podem ter publicações associadas. A reversão preserva o
    # conteúdo editorial e deixa a remoção estrutural para a migration 0001.
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("editorial", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, preserve_categories),
    ]
