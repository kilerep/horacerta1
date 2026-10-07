# Plano de trabalho — HoraCerta
**Atualizado em:** 12/09/2026

Este documento vai sendo atualizado conforme avançamos. Prioridade definida com você: **arrumar o sistema primeiro, blog depois.**

## 🚨 Achado crítico e já corrigido (12/09/2026)

O modelo antigo "empresa controla hora do MEI" (que você abandonou por preocupação com vínculo empregatício) **não era só código morto — estava público e ativo**. O formulário de cadastro (`/signup/`) criava, sem exceção, contas `role=EMPRESA` com acesso total ao modelo antigo, e a landing page pública tinha **3 botões "Criar conta"** linkando direto pra lá. Qualquer visitante podia criar uma conta desse tipo sem ninguém saber.

**Corrigido:** o `/signup/` agora não cria mais nenhuma conta — só redireciona pro login com a mesma orientação que já existe lá ("solicite seu acesso ao administrador"). Já está na sua pasta e comitado no seu commit local, falta só `git push`.

**Ainda pendente (decisão sua, não é só código):** a landing page (`templates/accounts/landing.html`) ainda descreve o modelo antigo no texto e na meta description ("HoraCerta é um sistema para empresas cadastrarem prestadores..."), e os 3 botões "Criar conta" agora levam a um beco sem saída (login com aviso). Isso é conteúdo/posicionamento, não só segurança — prefiro que você decida o texto novo comigo em vez de eu reescrever sozinho.

## ✅ Já feito (nesta conversa)

| Item | O que foi feito |
|---|---|
| Bug de encoding na página 404/500 | Corrigido "PÃ¡gina nÃ£o encontrada" → "Página não encontrada" nos dois templates |
| Sem LOGGING em produção | Adicionado bloco `LOGGING` em `settings.py` (console + e-mail de erro pra `ADMINS`) |
| Login sem proteção a força bruta | Bloqueio de 5 tentativas / 5 min por IP, via cache do Django, sem migração nova |
| Notificação push "fake" | Corrigido o diagnóstico: o endpoint real (`accounts/pwa.py`) já era honesto (HTTP 501). Removida a função duplicada e morta que mentia dizendo "ativado com sucesso", junto com um `@csrf_exempt` desnecessário |

**Importante:** essas 4 mudanças estão salvas na sua pasta `C:\deploy\horacerta`, mas só valem em produção depois que você der `git commit` + `git push` (o Render builda sozinho a partir daí). Isso ainda não foi feito.

## Fase 1: Segurança e limpeza

| # | Item | Status |
|---|---|---|
| 1 | Apagar lixo de deploy (`views.py.backup...`, `landing_old_backup.html`, `horacerta_update.tar.gz`, `db.sqlite3`) | ⛔ **Bloqueado** — o shell remoto no seu PC não sobe nesta sessão (erro "Workspace unavailable"). Não é falta de permissão. Apague manualmente por enquanto, ou tento de novo mais tarde |
| 2 | Remover mais código PWA morto (`pwa_manifest`/`pwa_service_worker` duplicados em `accounts/views.py`) | ✅ Feito |
| 3 | Caminho do `/admin/` configurável | ✅ Feito — `config/urls.py` agora lê `ADMIN_URL_PATH` do `.env` (padrão continua `admin/`, nada muda até você definir um valor novo) |
| 4 | Dependência `python-dotenv` não usada | ✅ Removida do `requirements.txt` (confirmei que não é importada em nenhum outro arquivo) |

## 🔜 Fase 2: Organização do código (mexe em arquivo grande, peço confirmação antes)

| # | Item | O que envolve |
|---|---|---|
| 5 | Quebrar `accounts/views.py` (6.778 linhas) | Separar em módulos por assunto: autenticação, dashboard MEI, dashboard empresa, relatórios. Trabalho maior, vou propor a divisão antes de mexer |
| 6 | Mover lógica de empresa pro app `companies` | Hoje `companies/views.py` está praticamente vazio e a lógica mora em `accounts` — separar deixa mais fácil de testar e manter |

## 🔜 Fase 3: LGPD e jurídico (preciso de informação sua antes de escrever)

| # | Item | O que preciso de você |
|---|---|---|
| 7 | Reescrever Política de Privacidade | Preciso: um e-mail/canal oficial de contato para pedidos de dados, e se já existe alguém definido como Encarregado de Dados (DPO) — se não existir, posso sugerir texto genérico até vocês definirem |
| 8 | Tela de consentimento de localização | Antes do primeiro registro de ponto, pedir um aceite explícito (hoje só tem um aviso, sem clique de confirmação) |
| 9 | Expandir Termos de Uso | Cláusulas de cancelamento de conta e responsabilidade por perda de dados — posso escrever um rascunho, mas recomendo revisão de um advogado antes de publicar (não sou advogado, e essa parte tem peso jurídico real) |

## 🔜 Fase 4: Infraestrutura (menor prioridade, mais caro/demorado)

| # | Item | O que envolve |
|---|---|---|
| 10 | E-mail transacional dedicado | Sair do Gmail pessoal pra SES/Resend/Mailgun com domínio próprio |
| 11 | Cache compartilhado (Redis) | Hoje o bloqueio de login (item já feito) usa cache local por processo — funciona, mas fica mais forte com Redis se o servidor rodar vários workers |

## ✅ Fase visual (12/09/2026)

Analisei o layout ao vivo (inclusive em largura de celular) e mexi direto no CSS/templates:

| # | Item | O que foi feito |
|---|---|---|
| 1 | Bug de contraste no botão principal | `color:#fff` fixo virou `color:var(--text-inverse)` — no tema "Neutro Profissional" o botão de bater ponto ficava quase invisível (texto branco em fundo quase branco). Corrigido nos 5 temas de uma vez |
| 2 | Botão principal subiu na hierarquia | No mobile, dava pra rolar quase 2 telas antes de ver o botão de registrar horário. Agora "Cliente atual" + botão aparecem logo após o relógio, antes dos cards de estatística |
| 3 | Cards de estatística compactados | "Data / Horários hoje / Último horário / Total parcial" empilhavam 1 por linha no celular (4 telas de card). Agora ficam 2x2, ocupando metade da altura |
| 4 | Hierarquia tipográfica | Quase tudo estava em peso 800–900 (negrito máximo), competindo por atenção. Suavizei títulos de seção, rótulos e botão secundário para 600–700, mantendo peso máximo só no relógio e no botão principal |
| 5 | Novo tema "Claro Operacional" | 5º tema (fundo claro, texto escuro) pensado pra quem bate ponto na rua sob sol forte, onde tema escuro reflete e ofusca a tela. Mesmo azul de marca do Grafite Premium. Registrado em `design_tokens.css`, `theme_engine.js`, `accounts/models.py` e nos 3 seletores de tema |

**Importante:** essas mudanças estão na sua pasta e comitadas localmente, mas eu não consigo abrir o site rodando aqui pra te mostrar print de como ficou (sem terminal no seu PC nesta sessão). Recomendo rodar localmente ou subir num preview antes de ir pra produção, só pra bater o olho antes do `git push` definitivo.

## 📌 Depois disso: Blog / SEO

Fica pra quando o sistema estiver estabilizado, como combinamos. Quando chegar lá, entram as skills de conteúdo/SEO que você tem instaladas.

---

### O que eu preciso de você agora
1. **Confirmar se posso seguir direto pra Fase 1** (itens 2, 3, 4 — não tocam em nada arriscado).
2. Pra Fase 3 (item 7): me passar um e-mail/canal de contato oficial pra privacidade, e se já tem um Encarregado de Dados definido.
3. Lembrar de rodar `git commit` + `git push` pra colocar no ar o que já foi corrigido.
