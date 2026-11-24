---
name: horacerta-qa
description: Use before every commit, push, PR, or deploy of HoraCerta — runs the Django test suite and pre-flight checks the same way GitHub Actions CI does, and pre-empts the known flaky patterns (SECURE_SSL_REDIRECT under DEBUG=False, django-axes cross-test lockout) before they break CI or block a deploy.
---

# HoraCerta — Qualidade e testes (QA)

Departamento: **Qualidade**. Portão de saída obrigatório antes de qualquer commit relevante,
push ou deploy (ver `docs/ROADMAP_EXECUCAO_HORACERTA.md`, seção "Regra de entrega": nenhuma
melhoria é considerada pronta sem teste automatizado da regra nova/alterada e CI aprovada).

## Sequência (espelha `.github/workflows/ci.yml`)

Usar as mesmas variáveis de ambiente da CI para reproduzir localmente o que vai rodar no GitHub:

```bash
export SECRET_KEY=ci-only-secret-key-not-for-production
export DEBUG=False
export APP_BASE_URL=https://horacertagestao.com.br
export USE_CONSOLE_EMAIL=True
export DATABASE_URL=sqlite:///db.sqlite3
```

Depois, nesta ordem:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test -v 2
python manage.py collectstatic --noinput
python manage.py check --deploy
```

A suíte completa tem ~174 testes e leva entre 14 e 15 minutos localmente — não é curto. Ao
iterar em uma app específica, rode só ela para feedback rápido:

```bash
python manage.py test accounts
python manage.py test timeclock
python manage.py test services
```

Só rode a suíte completa (comando de cima) antes de commit/push/deploy final.

## Armadilhas conhecidas (já causaram falhas reais nesta base)

1. **`SECURE_SSL_REDIRECT` com `DEBUG=False`**: qualquer `TestCase` nova que use `self.client`
   sem marcar `@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])`
   recebe 301 em vez do status esperado quando `.env` local tem `DEBUG=False` (mesmo valor da CI).
   Classes-irmãs no mesmo arquivo de teste já usam esse decorator — copie o padrão.
2. **`django-axes` vazando estado entre testes**: usar `Client(REMOTE_ADDR=f"198.51.100.{n}")`
   com um contador incremental por teste que faz login, em vez do IP fixo padrão do client de
   teste do Django. Sem isso, tentativas de um teste contam para o lockout de outro.
   `AXES_LOCKOUT_PARAMETERS` também precisa ser lista aninhada (`[["ip_address", "username"]]`,
   combinação/AND) e não lista plana (`["ip_address", "username"]`, que vira OR e bloqueia
   qualquer usuário vindo do mesmo IP).
3. **Bloqueio ocorre na N-ésima tentativa, não na N+1**: com `AXES_FAILURE_LIMIT=5`, a 5ª
   tentativa errada já retorna 429/lockout. Testes que contam tentativas devem fazer
   `LOGIN_ATTEMPT_LIMIT - 1` tentativas "normais" e só then checar o 429 na última.

## Antes de considerar uma mudança "pronta" (Bloco 0 do roadmap)

- [ ] Regra nova ou alterada tem teste automatizado cobrindo o caso feliz e o caso de acesso
      cruzado (ex.: "prestador A não vê dados de prestador B").
- [ ] `makemigrations --check --dry-run` não aponta migration faltando.
- [ ] Suíte completa rodou verde com as env vars da CI (não só com `.env` de desenvolvimento).
- [ ] Nenhum teste foi comentado/pulado só para "passar".
- [ ] Se a mudança afeta template/CSS, validação visual rápida (celular ou desktop) foi feita —
      ver [[horacerta-feature]].

Quando tudo isso estiver marcado, o commit está liberado para [[horacerta-feature]] finalizar
e, com autorização explícita do usuário, para [[horacerta-deploy]] publicar.
