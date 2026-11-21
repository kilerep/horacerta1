---
name: horacerta-feature
description: Use when implementing a new HoraCerta feature or working through a roadmap block (Bloco 0-6 in docs/ROADMAP_EXECUCAO_HORACERTA.md) — standard branch/test/commit workflow matching this repo's conventions and multi-tenant isolation rules, ending at the QA gate before merge/deploy.
---

# HoraCerta — Engenharia de produto (Feature workflow)

Departamento: **Engenharia**. Fluxo padrão para transformar um item do roadmap em código
mergeável. Usar `docs/ROADMAP_EXECUCAO_HORACERTA.md` como fonte da verdade de escopo e critérios
de aceite — não redefinir prioridades aqui, isso é trabalho do [[horacerta-product]].

## Antes de codar

1. Identificar o bloco/sprint do roadmap ao qual a mudança pertence (0 a 6). Se não pertencer a
   nenhum, é possível que esteja fora do escopo atual — confirmar com o usuário antes de seguir.
2. Ler o modelo, a view e o template envolvidos antes de editar (convenção já usada nesta base:
   `accounts/`, `companies/`, `services/`, `timeclock/` — cada um dono do seu domínio).
3. Confirmar a regra de isolamento por prestador/contrato que já existe nas telas vizinhas
   (ex.: `templates/accounts/mei_profile.html` mostra dado por `selected_contract`, nunca um
   perfil global). Toda tela nova de listagem/detalhe precisa responder 404 — nunca vazar
   existência — para dado de outro prestador.

## Convenções do repositório

- Branch a partir de `release-beta-2026-07-10` (branch de integração atual), nome
  `sprint-N-slug` (convenção usada nas sprints 0-5) ou `feature/slug` para itens avulsos.
- Strings de UI em português, tom direto (ver textos existentes em `templates/`).
- CSS inline por template usa variáveis (`var(--border)`, `var(--text)`, `var(--muted)`,
  `var(--radius)`, `var(--color-primary-soft)`) definidas no tema — não hardcode cores.
- Migration só quando o model muda de verdade; mesmo uma `AlterField` só de `choices` precisa de
  migration (Django rastreia isso no histórico mesmo sem mudança de schema).
- Mensagem de commit: `tipo(escopo): descrição curta` (ex.: `fix(templates): corrige...`,
  `test(timeclock): corrige...`). Sempre encerrar com a linha de atribuição do Claude Code.

## Passo a passo

1. Escrever o teste da regra nova/alterada **antes ou junto** da implementação — nunca depois
   "para confirmar", especialmente para regra de acesso/isolamento (é o tipo de bug que passa
   despercebido sem teste).
2. Implementar a mudança mínima que satisfaz o critério de aceite do bloco do roadmap.
3. Rodar **[[horacerta-qa]]** (app específica durante iteração, suíte completa antes do commit
   final).
4. Validação visual curta quando a mudança afeta template/CSS — captura de tela ou navegador,
   não assumir que "deve estar certo".
5. Commit com mensagem no padrão acima.
6. Handoff:
   - Se o trabalho for entregue por outra sessão/ambiente sem acesso direto a este repositório,
     usar `git format-patch`/`git bundle` (já usado para o patch de bugs P1) e documentar no
     commit de qual sessão veio.
   - Merge em `main` e deploy em produção continuam fora do escopo automático — precisam de
     autorização explícita do usuário a cada vez (ver [[horacerta-deploy]]).

## Ao aplicar um patch vindo de outra sessão (`git am`)

- Preferir `git am -3` (three-way) em vez de `git am` puro — resolve automaticamente a maioria
  dos conflitos de contexto quando o patch foi gerado a partir de uma base ligeiramente
  diferente.
- Conflito real em template (dois blocos de CSS/HTML novos no mesmo ponto): resolver mantendo
  ambos os blocos, não descartar nenhum lado sem entender o que cada um faz.
- Continuar com `GIT_EDITOR=true git am --continue` (evitar `--no-edit`, que não é uma flag
  válida deste comando).
- Depois de aplicar, rodar [[horacerta-qa]] completo — um patch de outra sessão pode trazer
  testes que dependem de configuração local que aquela sessão não tinha (foi o caso do
  `SECURE_SSL_REDIRECT`).
