# HoraCerta como empresa — organização e automação

Data: 2026-09-12

Este documento amarra os planos já existentes (`ROADMAP_EXECUCAO_HORACERTA.md`,
`HORACERTA_RELATORIO_INTERNO_STATUS_E_ROADMAP.md`,
`HORACERTA_ANALISE_MERCADO_PRESTADORES_2026.md`) a seis skills do Claude Code criadas em
`.claude/skills/`, uma por "setor". Cada skill é carregada automaticamente quando a conversa
pede algo daquele domínio — não precisa ser invocada manualmente.

## Organograma

| Setor | Skill | Responsabilidade | Nunca faz sozinho |
|---|---|---|---|
| Produto | `horacerta-product` | Priorização, posicionamento, pesquisa de mercado/regulatória | Reordenar prioridade sem avisar o usuário |
| Engenharia | `horacerta-feature` | Implementar item do roadmap, convenções do repo | Merge em `main` sem autorização |
| Qualidade | `horacerta-qa` | Suíte de testes, paridade com CI, armadilhas conhecidas | Pular teste "porque é pequeno" |
| Segurança/Compliance | `horacerta-security` | Auth, LGPD, segredos, superfície admin | Declarar conformidade LGPD sem revisão jurídica |
| Infraestrutura | `horacerta-deploy` | Pipeline SSM de deploy, rollback | Deploy sem confirmação explícita a cada vez |
| Suporte | `horacerta-support` | Triagem de bug/incidente em produção | Deploy de correção sem passar por QA |

Fluxo típico de uma mudança: `horacerta-product` decide o quê → `horacerta-feature` implementa →
`horacerta-qa` valida → `horacerta-security` revisa quando a mudança toca dado pessoal/auth →
`horacerta-deploy` publica com autorização explícita. `horacerta-support` entra quando algo já
em produção quebra, e pode acionar qualquer um dos outros conforme a causa raiz.

## Status atual (2026-09-12)

Mais avançado do que os relatórios de julho/2026 registram — desde então:

- Sprints 0-5 (fundação, clientes, segurança de senha, painel, ajuda MEI, serviços premium)
  integradas na branch `release-beta-2026-07-10` e **em produção**.
- Acesso ao servidor recuperado via IAM role + SSM Session Manager (chave `.pem` antiga estava
  perdida).
- Proteção contra força bruta migrada de solução caseira para `django-axes`, cobrindo `/login/`
  e `/admin/login/`, resistente a forjar `X-Forwarded-For` (fechava um buraco real: o rate limit
  antigo podia ser burlado só trocando o cabeçalho).
- Patch de 5 bugs de auditoria P1 aplicado e publicado (pré-preenchimento de quantidade em
  pedido, trava de relatório em registro manual, sobrescrita de nome de cliente, ação "Recebido"
  em rascunho, rótulo ambíguo em detalhe de relatório).
- Suíte de testes local: 174 testes, verde.

Isso quer dizer que os "bloqueadores críticos antes de produção" listados em
`HORACERTA_RELATORIO_INTERNO_STATUS_E_ROADMAP.md` (seção 6) já foram resolvidos na prática —
o sistema está no ar, testado e sincronizado entre servidor/GitHub/local.

## Decisão de engenharia executada em 2026-09-12

O usuário delegou a escolha entre "mais ajustes visuais" e "refatorar `accounts/views.py`" ao
julgamento técnico. Optamos pela refatoração: o arquivo tinha **6.647 linhas e ~120 views**
misturando back-office interno, telas de empresa, autoatendimento do MEI e páginas públicas no
mesmo módulo — e o Bloco 5 (segurança/LGPD), próximo na fila, precisa adicionar várias views
novas de conta (troca de e-mail, histórico de login, exportação/exclusão de dados) exatamente
nesse arquivo. Fazer isso em cima de um monólito de 6,6 mil linhas custa mais caro quanto mais
se espera.

Resultado: `accounts/views.py` virou o pacote `accounts/views/`, dividido só por organização —
nenhum comportamento mudou:

| Módulo | Conteúdo |
|---|---|
| `_shared.py` | Imports, constantes e ~70 helpers privados usados por mais de uma audiência |
| `auth.py` | `signup`, `login_view`, `logout_view`, redirect genérico por papel |
| `internal.py` | Back-office interno (`interno/...`) |
| `company.py` | Telas da empresa cliente (`empresa/...`) |
| `mei.py` | Autoatendimento do prestador/MEI (`me/...`) |
| `public.py` | Páginas públicas (landing, termos, link público de relatório) |

Verificação: superfície de nomes do módulo (`vars(accounts.views)`) comparada byte a byte antes
e depois — idêntica, à exceção da adição esperada dos próprios submódulos como atributos. Suíte
de testes completa (174 testes) reexecutada com as mesmas variáveis de ambiente da CI antes do
commit. Também removido `accounts/views.py.backup.2026-06-22-220845`, um backup de 286 KB
esquecido no repositório e já apontado como lixo em auditoria anterior
(`Claude outputs/relatorio_1_codigo_projeto_horacerta.md`).

A rodada de ajustes visuais continua na fila para uma próxima sessão — não foi descartada, só
adiada por ter menos urgência estrutural que este item.

## Convenção de manutenção

Sempre que um destes docs de planejamento for atualizado por uma sessão, verificar se as skills
ainda batem com a realidade (comandos, nomes de branch, IDs de instância). Skills desatualizadas
são piores que a ausência delas, porque parecem autoritativas.
