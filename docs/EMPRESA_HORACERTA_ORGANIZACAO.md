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

## Próximo passo pendente

Conforme o encerramento da última sessão de deploy, ficou em aberto uma escolha do usuário entre
duas frentes (ainda não decidida):

1. Mais uma rodada de ajustes visuais (o usuário já validou o resultado da rodada anterior no
   celular).
2. Refatoração de `accounts/views.py` (limpeza técnica, sem mudança visível para o usuário).

Ambas cabem em [[horacerta-feature]]. A escolha entre elas é de produto — usar
[[horacerta-product]] (Bloco 0 do roadmap prioriza estabilização; refatoração técnica pura
tende a valer menos pontos de prioridade do que os itens de UX já sequenciados, mas a decisão
final é do usuário).

## Convenção de manutenção

Sempre que um destes docs de planejamento for atualizado por uma sessão, verificar se as skills
ainda batem com a realidade (comandos, nomes de branch, IDs de instância). Skills desatualizadas
são piores que a ausência delas, porque parecem autoritativas.
