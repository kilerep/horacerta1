# Publicação da release candidata — 15/07/2026

Branch:

```text
release-candidate-2026-07-15
```

Este roteiro pressupõe que a CI da branch esteja aprovada. Não use `git clean`, não remova `media/` e não descarte alterações locais sem revisar.

## 1. Verificar o estado atual

```bash
cd ~/horacerta
git status
git branch --show-current
git rev-parse HEAD
sudo systemctl status horacerta.service --no-pager -l
sudo nginx -t
```

Anote o commit atual para rollback.

## 2. Backup operacional

Faça backup do banco pelo procedimento habitual da infraestrutura e preserve a pasta de mídia:

```bash
mkdir -p ~/backups
if [ -d media ]; then
  tar -czf ~/backups/horacerta-media-$(date +%Y%m%d-%H%M).tar.gz media
fi
```

## 3. Atualizar o código

```bash
cd ~/horacerta
git fetch origin --prune
git switch -C release-candidate-2026-07-15 --track origin/release-candidate-2026-07-15
git status
git rev-parse HEAD
```

O status deve mostrar árvore limpa, exceto `media/` quando ela não for rastreada.

## 4. Ativar o ambiente e instalar dependências

```bash
source venv/bin/activate
which python
python --version
python -m pip install -r requirements.txt
```

## 5. Diagnóstico antes das migrations

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
```

Revise o plano antes de aplicar.

O comando de prontidão pode apontar migrations pendentes neste momento, o que é esperado antes de `migrate`:

```bash
python manage.py check_release_readiness
```

Ele deve confirmar configuração, banco e assets; caso indique migrations pendentes, aplique somente depois de revisar o plano.

## 6. Aplicar migrations e validar

```bash
python manage.py migrate
python manage.py check_release_readiness
```

Depois da migration, o comando deve terminar com:

```text
Release pronta para a etapa de publicacao.
```

## 7. Arquivos estáticos

```bash
python manage.py collectstatic --noinput
python manage.py check --deploy
```

## 8. Reiniciar aplicação

Use somente o serviço ativo do HoraCerta:

```bash
sudo systemctl restart horacerta.service
sudo systemctl status horacerta.service --no-pager -l
sudo nginx -t
sudo systemctl reload nginx
```

Não use o serviço legado `gunicorn.service`.

## 9. Smoke tests

```bash
curl -sS -o /dev/null -w "landing: %{http_code}\n" https://horacertagestao.com.br/
curl -sS -o /dev/null -w "health: %{http_code}\n" https://horacertagestao.com.br/health/
curl -sS https://horacertagestao.com.br/health/
```

Esperado:

- landing: `200`;
- health: `200`;
- JSON com aplicação e banco em estado `ok`.

## 10. Logs

```bash
sudo journalctl -u horacerta.service -n 150 --no-pager -o cat
sudo tail -n 100 /var/log/nginx/error.log
```

Não conclua a publicação se houver traceback, erro de migration, `TemplateSyntaxError`, `ProgrammingError`, `OperationalError` ou HTTP 500.

## 11. Validação funcional

### Prestador

1. login;
2. Meu Resumo e Ação de hoje;
3. clientes e contratos;
4. pedido com busca por código interno;
5. transformação em serviço;
6. modelo profissional;
7. folha e link público;
8. execução;
9. relatório final;
10. calendário e próxima visita.

### Empresa contratante

1. Configurações;
2. Portal da empresa contratante;
3. cadastro da organização;
4. convite de membro;
5. convite de prestador;
6. aceite pelo prestador;
7. suspensão, reativação e encerramento;
8. teste de isolamento com outra organização.

A empresa ainda não verá serviços, horas e relatórios reais nessa versão. Esse compartilhamento pertence à próxima Sprint.

## 12. Rollback de código

Em caso de falha após a publicação:

```bash
cd ~/horacerta
git switch release-beta-2026-07-10
git reset --hard origin/release-beta-2026-07-10
source venv/bin/activate
python manage.py collectstatic --noinput
sudo systemctl restart horacerta.service
```

Migrations de banco exigem análise específica antes de reversão. Não execute `migrate <app> <migration_anterior>` sem revisar dependências e dados.
