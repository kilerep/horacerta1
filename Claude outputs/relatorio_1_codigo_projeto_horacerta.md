# Relatório 1 — Análise Técnica do Código (pasta do projeto)
**Projeto:** HoraCerta (Django) — pasta `C:\deploy\horacerta`
**Data:** 12/09/2026

## Visão geral

Django 6.0.2, 4 apps (`accounts`, `companies`, `timeclock`, `services`), banco Postgres na AWS em produção (confirmado no `.env`), deploy com script para Render (`.render.yaml`) e também um script `fix.sh` de recuperação manual via systemd/nginx (indica que já rodou ou roda em VPS próprio além do Render). Tem CI no GitHub Actions rodando testes e `manage.py check --deploy`. Sistema ainda é "MVP" segundo os próprios Termos de Uso.

## O que já está bem feito (para não parecer que só tem problema)

Headers de segurança em produção (HSTS, `X-Frame-Options: DENY`, cookies `Secure`/`HttpOnly`/`SameSite`), `SECRET_KEY` obrigatória fora de debug, CI rodando `check --deploy` e suíte de testes automaticamente, e boa parte dos apps (`accounts`, `timeclock`, `services`) tem arquivos de teste robustos (o de `accounts` sozinho tem quase 79 mil linhas de teste). Isso é acima da média de um projeto em estágio de MVP.

## Assuntos que precisam ser melhorados (direto ao ponto)

**1. `accounts/views.py` com 6.787 linhas (286 KB) — precisa ser quebrado.**
Um arquivo desse tamanho concentra login, dashboard, contratos, relatórios, PWA, tudo junto. Isso já é difícil de revisar, difícil de testar isoladamente e vira terreno fértil pra bug. Recomendação prática: dividir em submódulos por domínio — `accounts/views/auth.py`, `accounts/views/dashboard_mei.py`, `accounts/views/dashboard_empresa.py`, `accounts/views/relatorios.py`, `accounts/pwa_views.py` (esse já existe separado, seguir o mesmo padrão pros demais).

**2. App `companies` está praticamente vazio de lógica (`views.py` com 66 bytes) e sem testes (`tests.py` com 63 bytes) — a lógica de empresa mora dentro de `accounts/views.py`.**
Isso quebra a separação de responsabilidades: o app que deveria cuidar de empresas, planos e contratos não tem views nem testes próprios, e tudo isso foi parar no arquivo gigante do item 1. Você pode mover as views relacionadas a empresa/contrato/plano para dentro de `companies/views.py` e escrever testes específicos lá — hoje, se algo quebrar em "planos" ou "contratos", o teste que vai pegar isso está espalhado em outro app.

**3. Existem arquivos de "lixo" de deploy dentro da pasta de produção que precisam ser removidos:**
- `accounts/views.py.backup.2026-06-22-220845` — cópia duplicada de 286 KB do próprio `views.py`. Isso não deveria estar no servidor; se precisa de histórico, é pra isso que existe o Git.
- `templates/public/landing_old_backup.html` — mesma lógica, backup manual dentro de `templates/`.
- `horacerta_update.tar.gz` (13,8 MB!) — parece ser um artefato de atualização antigo esquecido na raiz do projeto.
- `db.sqlite3` (815 KB) — a produção usa Postgres na AWS (confirmado no `.env`), então esse arquivo sqlite solto na pasta é lixo de desenvolvimento ou de um fallback antigo; pode confundir alguém que rodar `manage.py` sem `DATABASE_URL` configurada corretamente e sem perceber que está lendo um banco errado.
Você pode apagar os três primeiros com segurança e mover o `db.sqlite3` para fora da pasta de produção (mantendo só em ambiente local de dev).

**4. Não existe nenhuma proteção contra força bruta no login (nem no login normal, nem no `/admin/`).**
Procurei por rate limit, bloqueio de conta ou controle de tentativas (`ratelimit`, `throttle`, `lockout`, `failed_login`) no código inteiro e não existe nada disso. Hoje alguém pode tentar senha infinitamente contra `login_view` ou contra `/admin/` sem ser bloqueado ou atrasado. Isso pode ser mudado instalando `django-ratelimit` (ou `django-axes`, que já cuida de bloqueio de conta + log de tentativas) e aplicando no `login_view` e na view de login do admin.

**5. O botão de "ativar notificações push" no app finge que funciona, mas não salva nada.**
Em `accounts/pwa.py`, a view `register_push_subscription` recebe os dados da assinatura push, mas o comentário no próprio código diz "Aqui você pode armazenar a subscription no banco de dados / Por enquanto, apenas retornar sucesso" — ou seja, ela sempre responde `"Notificações push ativadas com sucesso"` sem gravar nada. Resultado: o usuário acha que ativou notificações e nunca vai receber nenhuma. Essa view também está marcada com `@csrf_exempt`, o que não é necessário e é uma prática arriscada — o ideal é manter proteção CSRF e enviar o token via JS. Você pode: (a) implementar de fato o armazenamento da subscription num modelo novo, ou (b) se a feature não vai sair do papel agora, remover o botão da interface pra não prometer algo que não existe.

**6. E-mail transacional (recuperação de senha) sai por uma conta pessoal do Gmail.**
No `.env` de produção, o envio de e-mail está configurado com `smtp.gmail.com` e um usuário Gmail pessoal com senha de app. Isso funciona, mas é frágil: Gmail tem limite diário de envio, pode marcar como spam mais facilmente sem domínio próprio com SPF/DKIM/DMARC configurados, e amarra a operação do sistema a uma conta pessoal. Você pode migrar para um serviço transacional (Amazon SES — já que o banco já está na AWS —, Resend, ou Mailgun) usando o domínio `horacertagestao.com.br` como remetente.

**7. Falta configuração de `LOGGING` no `settings.py`.**
Não existe nenhum bloco `LOGGING` definido — hoje, se algo quebrar em produção fora do que o Django já mostra como erro 500 genérico, não tem registro estruturado nem alerta por e-mail pros administradores. Isso é coerente com o fato de existir um `fix.sh` de "recuperação de incidente" no projeto — ou seja, já tiveram problema em produção e provavelmente descobriram tarde. Recomendação: adicionar um `LOGGING` básico gravando erros em arquivo/console e, se possível, integrar com Sentry (tem plano gratuito, e a configuração no Django é de poucas linhas).

**8. Dependência `python-dotenv` instalada mas não usada.**
Está no `requirements.txt`, mas o `settings.py` implementa na mão uma função `_load_dotenv` própria para ler o `.env`, duplicando o que a biblioteca já faz pronta e testada. Ou usa a lib e remove o código manual, ou remove a dependência do `requirements.txt` — do jeito que está, é peso morto.

**9. `/admin/` do Django exposto no caminho padrão.**
O controle de acesso está funcionando corretamente (testei ao vivo: um usuário comum autenticado é barrado do admin), então isso não é uma falha grave — mas manter `/admin/` no caminho padrão é o primeiro lugar que qualquer bot de varredura testa. Trocar para um caminho não óbvio (ex: `/gestao-interna-x7f/`) e considerar autenticação em duas etapas para contas de staff é uma melhoria de baixo custo e alto retorno.

## Prioridade sugerida

Crítico (fazer logo): item 4 (força bruta no login) e item 7 (logging/monitoramento de erro).
Importante: item 5 (push fake — ou implementa ou remove da UI), item 3 (limpeza de lixo de deploy), item 1/2 (organização do código).
Desejável: item 6 (e-mail transacional), item 8 (dependência não usada), item 9 (admin em outro caminho).
