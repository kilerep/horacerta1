# HoraCerta — Estabilização pós-release 2026-07-11

## Objetivo

Aplicar melhorias operacionais pequenas e verificáveis depois da primeira publicação da release beta, sem misturar novas features de negócio com correções de produção.

## Estado conhecido

- A release integrada está na branch `release-beta-2026-07-10`.
- O hotfix de arquivos estáticos está no commit `38f1e3f8f77452fc70de17f80e7163678be03238`.
- A estabilização está na branch `post-release-stabilization-2026-07-11`.
- Esta branch não contém migrations.

## Melhorias desta estabilização

1. Endpoint `GET /health/` para validar aplicação e banco.
2. Teste automatizado dos assets públicos críticos.
3. Landing sem alegações comerciais, legais ou técnicas não comprovadas.
4. Conteúdo público alinhado ao beta privado e às funções existentes.

## Antes de publicar

```bash
cd ~/horacerta
source venv/bin/activate

git status
git branch --show-current
git rev-parse HEAD
```

Não publicar com alterações locais não compreendidas.

## Atualização do código

Depois de a PR passar na CI e ser aprovada para publicação:

```bash
git fetch origin --prune
git switch post-release-stabilization-2026-07-11
git pull --ff-only origin post-release-stabilization-2026-07-11
```

## Validação

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test config.test_health accounts.test_public_assets -v 2
python manage.py collectstatic --noinput
python manage.py check --deploy
```

## Reinício

```bash
sudo systemctl restart horacerta.service
sudo systemctl status horacerta.service --no-pager -l
sudo nginx -t
sudo systemctl reload nginx
```

## Teste operacional

```bash
curl -sS https://horacertagestao.com.br/health/
curl -sS -o /dev/null -w "landing=%{http_code}\n" https://horacertagestao.com.br/
curl -sS -o /dev/null -w "login=%{http_code}\n" https://horacertagestao.com.br/login/
```

Resultado saudável esperado:

```json
{"status":"ok","application":"ok","database":"ok"}
```

## Logs

```bash
sudo journalctl -u horacerta.service -n 100 --no-pager -o cat
sudo tail -n 100 /var/log/nginx/error.log
```

## Limites do healthcheck

- Não substitui monitoramento externo.
- Não mede fila, e-mail, armazenamento ou integrações futuras.
- Não deve retornar credenciais, host do banco, versão do framework ou traceback.
- Um `503` indica que a aplicação respondeu, mas a conexão com o banco falhou.
