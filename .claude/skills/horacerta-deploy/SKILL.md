---
name: horacerta-deploy
description: Use when the user asks to deploy HoraCerta to production, ship a merged/tested branch to the AWS EC2 server, restart the live site, or roll back a bad release. Encodes the full SSM-based deploy pipeline for horacertagestao.com.br and its guardrails.
---

# HoraCerta — Deploy para produção (Infra/DevOps)

Departamento: **Infraestrutura**. Único skill autorizado a tocar o servidor de produção.

## Regra de ouro

Deploy nunca é automático por padrão — está explicitamente "fora do escopo automático" em
`docs/ROADMAP_EXECUCAO_HORACERTA.md`. Mesmo com este skill carregado:

1. Rode **[[horacerta-qa]]** primeiro (suíte completa verde, `check --deploy` sem erros).
2. Confirme com o usuário, em texto, qual branch/commit vai para produção e o que muda.
3. Só então execute os passos abaixo. Uma autorização vale para o deploy pedido, não para os próximos.

## Ambiente

- App: Django, servidor systemd `horacerta` (gunicorn), nginx como reverse proxy na frente.
- Servidor: AWS EC2 (instância `i-0139f2d2f4a0066e7`), acesso via **SSM Session Manager**
  (console EC2 → selecionar instância → Connect → Session Manager). Não existe mais chave `.pem`
  válida — não tente EC2 Instance Connect nem SSH direto, vá direto de SSM.
- Repositório remoto: `github.com/kilerep/horacerta1`. Branch de release atual: `release-beta-2026-07-10`.
- Domínio: `horacertagestao.com.br` (HTTPS forçado quando `DEBUG=False`, via `SECURE_SSL_REDIRECT`).
- Se o caminho do projeto no servidor não estiver óbvio, descubra com
  `sudo systemctl cat horacerta` (mostra `WorkingDirectory=`).

## Passo a passo (pipeline usado nos 3 deploys anteriores)

Dentro da sessão SSM, no diretório do projeto:

```bash
git status --short        # deve estar limpo (fora de media/ ou uploads)
git fetch origin
git log --oneline -1      # commit atual, para comparar depois
git pull origin release-beta-2026-07-10
```

Se `requirements.txt` mudou desde o último deploy:

```bash
source venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt
```

Depois, sempre nesta ordem:

```bash
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart horacerta
sleep 2 && sudo systemctl status horacerta   # confirmar "active (running)"
```

Verificação ao vivo (fora ou dentro da sessão):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://horacertagestao.com.br/
curl -s -o /dev/null -w "%{http_code}\n" https://horacertagestao.com.br/login/
```

Confirme sincronismo final:

```bash
git log --oneline -1        # deve bater com origin/release-beta-2026-07-10 e com o local
git status --short          # só deve sobrar diretórios esperados (ex.: media/)
```

Encerre a sessão SSM (botão "Encerrar" no console) quando terminar.

## `manage.py migrate` / `makemigrations` em produção

O classificador do Claude Code bloqueia esses comandos em produção por padrão. Isso é esperado:
explique ao usuário por que, peça confirmação explícita (pergunta objetiva, não retórica) e só
então rode o mesmo comando de novo.

## Rollback

1. `git log --oneline -5` para achar o commit bom anterior.
2. `git checkout <sha-anterior>` (ou `git revert` se preferir manter histórico linear).
3. Repetir `migrate` (cuidado: reverter migrations de schema pode exigir migration reversa manual,
   não apenas checkout de código) → `collectstatic` → `systemctl restart horacerta`.
4. Verificar com os mesmos `curl` acima.
5. Avisar o usuário do que foi revertido e abrir um item de correção antes de tentar de novo.

## Checklist final de todo deploy

- [ ] `horacerta-qa` rodou verde antes deste deploy.
- [ ] Branch/commit confirmados com o usuário.
- [ ] `check`, `migrate`, `collectstatic` sem erro.
- [ ] Serviço `active (running)` após restart.
- [ ] `curl` em `/` e `/login/` retornando 200.
- [ ] `git log` do servidor == `origin/<branch>` == local.
- [ ] Sessão SSM encerrada.
- [ ] Usuário avisado em uma mensagem curta do que foi ao ar.
