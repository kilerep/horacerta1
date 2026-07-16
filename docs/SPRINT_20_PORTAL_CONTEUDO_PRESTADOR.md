# Sprint 20 — Portal de conteúdo do prestador

## Decisão de produto

A landing do HoraCerta permanece apresentando o produto e passa a destacar conteúdos recentes. O portal editorial completo fica em `/conteudos/`.

Essa arquitetura evita que uma pessoa interessada no sistema encontre apenas notícias e não entenda o que o HoraCerta oferece. Ao mesmo tempo, cria uma área pública capaz de atrair visitas recorrentes, explicar o mercado e fortalecer a autoridade da marca.

## Conteúdo suportado

- Notícia;
- Guia prático;
- Análise;
- Oportunidade.

Categorias iniciais:

- Gestão;
- Mercado;
- Finanças;
- Legislação;
- Tecnologia;
- Segurança;
- Marketing;
- Oportunidades.

## Transparência editorial

Cada publicação pode registrar:

- autor responsável;
- data de publicação;
- data de atualização;
- fonte externa;
- data da fonte;
- nota de correção;
- imagem e texto alternativo;
- título e descrição para busca;
- destaque na landing.

Notícias baseadas em terceiros devem utilizar resumo original e link para a fonte. O sistema não foi criado para copiar matérias completas.

## SEO e distribuição

- páginas públicas indexáveis;
- canonical URL;
- Open Graph;
- dados estruturados `Article` ou `NewsArticle`;
- sitemap em `/sitemap.xml`;
- feed RSS em `/conteudos/feed.xml`;
- autoria e datas visíveis;
- página pública de política editorial.

## Administração

O conteúdo é criado pelo Django Admin em **Portal do prestador → Publicações**.

Comando opcional e idempotente para criar quatro guias iniciais:

```bash
python manage.py seed_editorial_starter_content
```

O comando não importa notícias externas e não exige API de terceiros.

## Publicação no servidor

A migration cria tabelas novas e categorias editoriais. Não altera clientes, horas, serviços, relatórios ou vínculos existentes.

Sequência esperada:

```bash
python manage.py check
python manage.py migrate --plan
python manage.py migrate
python manage.py seed_editorial_starter_content
python manage.py collectstatic --noinput
python manage.py check_release_readiness --require-collected-static
```

Depois do restart, validar:

- `/`;
- `/conteudos/`;
- `/conteudos/politica-editorial/`;
- `/conteudos/feed.xml`;
- `/sitemap.xml`;
- Django Admin.

## Limites

- sem captura automática de notícias;
- sem republicação integral de terceiros;
- sem comentários públicos;
- sem personalização baseada em dados privados;
- sem misturar conteúdo editorial com documentos por token;
- sem alegação de aconselhamento jurídico, contábil ou técnico.
