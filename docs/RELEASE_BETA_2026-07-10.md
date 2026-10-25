# HoraCerta — Release Beta 2026-07-10

## Estado

- Branch de integração: `release-beta-2026-07-10`
- Ponto de partida congelado: `06abbffd9b2db3c2db1fc08e539df226d33ca64c`
- Base já incluída: Sprint 0 + Sprint 5
- Situação: preparação para integração local, validação e publicação assistida
- Regra: nenhuma feature nova entra antes da publicação e validação desta release

## Objetivo

Organizar tudo que foi desenvolvido até 10/07/2026 em uma única versão testável e publicável, sem enviar branches isoladas diretamente ao servidor.

## Escopo que deve entrar

### Sprint 0 — Fundação técnica

- Pipeline de CI Django.
- Testes de fumaça.
- Ajustes de PWA, manifest e service worker.
- Endurecimento de configuração.
- Migration técnica pendente.

### Sprint 1 — Clientes e itens rápidos

- Accordion de Meus Clientes.
- Apenas um cliente aberto por vez.
- Busca e filtros.
- Estados vazios.
- Busca de itens do pedido por código interno ou nome.
- Remover o workaround temporário `accounts/test_00_mei_clients_legacy_copy.py` durante a integração.

### Sprint 2 — Segurança da conta

- Troca autenticada de senha.
- Atalhos no perfil/configurações.
- Validações nativas do Django.

### Sprint 3 — Painel operacional

- Bloco “Ação de hoje”.
- Atalhos para registro incompleto, cliente sem valor/hora, pedidos, relatórios e notificações.

### Sprint 4 — Ajuda MEI-first

- Central de ajuda atualizada para prestador/MEI.
- Regras atuais de edição, relatórios, serviços e ausência de GPS contínuo.

### Sprint 5 — Serviços premium

- Pedido → Serviço → Folha profissional → Execução → Relatório.
- Checklist e timeline.
- Categorias e playbooks premium.
- Catálogo sugerido por segmento.
- Proposta de evento e valor fixo.
- Portal do cliente por link.
- Calendário `.ics`.
- Próxima visita recorrente assistida.
- Comparação previsto x realizado.
- Ambiente local de demonstração.

## Fora desta release

- Branch incompleta `sprint-6-primeiros-passos-mei`.
- GPS contínuo ou rastreamento em segundo plano.
- Assinatura com promessa de validade jurídica.
- NFS-e genérica.
- Financeiro completo.
- Novas features solicitadas após o congelamento.

## Ordem de integração no computador

A branch de release já contém Sprint 0 + Sprint 5. Integrar as demais nesta ordem:

1. `sprint-1-clientes-acabamento`
2. `sprint-2-seguranca-senha`
3. `sprint-3-home-atencao`
4. `sprint-4-ajuda-mei`

### Comandos iniciais

```powershell
cd C:\deploy\horacerta
.\.venv\Scripts\Activate.ps1

git fetch origin --prune
git status
git switch release-beta-2026-07-10
git pull --ff-only origin release-beta-2026-07-10
```

### Integração por branch

Executar uma branch por vez, resolvendo e testando antes da próxima:

```powershell
git merge --no-ff origin/sprint-1-clientes-acabamento
```

Depois da Sprint 1:

```powershell
git rm accounts/test_00_mei_clients_legacy_copy.py
```

Se houver conflito em `.github/workflows/ci.yml`, manter a versão da branch de release:

```powershell
git checkout --ours .github/workflows/ci.yml
git add .github/workflows/ci.yml
```

Finalizar a resolução:

```powershell
git status
git add -A
git commit
py manage.py test
```

Repetir:

```powershell
git merge --no-ff origin/sprint-2-seguranca-senha
py manage.py test

git merge --no-ff origin/sprint-3-home-atencao
py manage.py test

git merge --no-ff origin/sprint-4-ajuda-mei
py manage.py test
```

Não usar `git push --force`.

## Validação local obrigatória

```powershell
py manage.py check
py manage.py makemigrations --check --dry-run
py manage.py test -v 2
py manage.py collectstatic --noinput
py manage.py check --deploy
```

Depois:

```powershell
git status
git log --oneline --decorate -15
git push -u origin release-beta-2026-07-10
```

A publicação só deve continuar se:

- a suíte completa passar;
- não houver migration não planejada;
- o `git status` estiver limpo;
- a branch remota apontar para o mesmo commit local;
- a revisão visual básica funcionar no computador e no celular.

## Revisão visual mínima

1. Login de prestador.
2. Meu Resumo e “Ação de hoje”.
3. Meus Clientes: busca, filtros e accordion.
4. Troca de senha.
5. Central de Ajuda.
6. Criar Pedido.
7. Transformar Pedido em Serviço.
8. Criar serviço avulso e cadastrado.
9. Adicionar itens pelo catálogo/código interno.
10. Gerar folha profissional.
11. Abrir link público.
12. Registrar período de execução.
13. Finalizar e gerar relatório.
14. Exportar calendário `.ics`.
15. Criar próxima visita.
16. Conferir “Previsto x realizado”.

## Publicação no servidor — sequência

Os valores exatos de pasta, ambiente virtual e serviço Gunicorn serão confirmados no terminal antes de executar.

### 1. Diagnóstico antes da alteração

```bash
pwd
git status
git branch --show-current
git rev-parse HEAD
python --version
systemctl list-units --type=service | grep -Ei 'gunicorn|hora|django'
```

### 2. Registrar ponto de retorno

```bash
git tag pre-beta-2026-07-10-$(date +%Y%m%d-%H%M)
git rev-parse HEAD
```

### 3. Atualizar código

```bash
git fetch origin --prune
git switch release-beta-2026-07-10
git pull --ff-only origin release-beta-2026-07-10
```

### 4. Ativar ambiente e instalar dependências

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

O caminho do ambiente pode ser `venv/bin/activate` em vez de `.venv/bin/activate`; confirmar antes.

### 5. Validar antes da migration

```bash
python manage.py check
python manage.py showmigrations
python manage.py migrate --plan
```

### 6. Aplicar banco e arquivos estáticos

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

### 7. Reiniciar serviços

Usar o nome real identificado no diagnóstico:

```bash
sudo systemctl restart <SERVICO_GUNICORN>
sudo systemctl status <SERVICO_GUNICORN> --no-pager
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Teste de fumaça

- Abrir landing/login.
- Fazer login com conta de teste autorizada.
- Abrir Meu Resumo, Clientes, Serviços e Relatórios.
- Criar um registro simples sem dados sensíveis.
- Verificar erros do Gunicorn e Nginx.

```bash
sudo journalctl -u <SERVICO_GUNICORN> -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

## Rollback de código

Em caso de erro antes de alterações irreversíveis de dados:

```bash
git switch --detach <COMMIT_ANTERIOR>
source .venv/bin/activate
pip install -r requirements.txt
python manage.py collectstatic --noinput
sudo systemctl restart <SERVICO_GUNICORN>
```

Não reverter migrations automaticamente sem analisar a migration e o estado do banco.

## Critério de encerramento

A release será considerada implantada quando:

- código do servidor estiver na branch/commit aprovado;
- migrations terminarem sem erro;
- Gunicorn e Nginx estiverem ativos;
- login e áreas principais funcionarem;
- logs não apresentarem erro 500 recorrente;
- folha pública, relatório e serviços abrirem corretamente.
