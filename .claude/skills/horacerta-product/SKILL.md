---
name: horacerta-product
description: Use when prioritizing what to build next for HoraCerta, evaluating a new feature idea, or refreshing competitive/regulatory research — keeps the roadmap grounded in the MEI/autônomo field-service niche instead of drifting into enterprise CLT ponto-eletrônico territory.
---

# HoraCerta — Produto e mercado

Departamento: **Produto**. Antes de propor algo novo, ler
`docs/HORACERTA_ANALISE_MERCADO_PRESTADORES_2026.md` (posicionamento e prioridades 1-6) e
`docs/ROADMAP_EXECUCAO_HORACERTA.md` (blocos 0-6 já sequenciados) — este skill não substitui
esses documentos, mantém-nos atualizados e evita retrabalho.

## Posicionamento (não mudar sem decisão explícita do usuário)

HoraCerta é um **portal operacional para MEI, autônomo e pequena operação de serviços** que
atende **vários clientes/contratos ao mesmo tempo** — não um sistema de ponto eletrônico CLT
para um único empregador. Esse é o diferencial real frente ao mercado, não um detalhe técnico.

## Panorama competitivo (atualizado 2026-09-12, refazer a busca a cada ~trimestre)

| Concorrente | Posicionamento | Observação |
|---|---|---|
| Ahgora (grupo TOTVS) | Corporativo, ponto + jornada + reconhecimento facial | Foco em RH de empresas médias/grandes |
| PontoMais (grupo VR, "VR RH Digital") | 4 planos fixos por empresa, não por funcionário | CLT-first |
| Genyo | Precificação por faixa de funcionários | CLT-first |
| Pontotel | Único auditado na Portaria 671 (REP-P/INPI) | Empresas médias/grandes, compliance pesado |
| Jibble | Plano grátis com usuários ilimitados, reconhecimento facial, geofencing | Genérico internacional, não MEI-first em português |
| PontoSoft / MobPonto | Escala de 1 a 1000+ funcionários, app simples | Mais próximo do porte pequeno, mas ainda ponto CLT |

Nenhum desses é otimizado para **um prestador com vários clientes/contratos e cobrança por
serviço** — esse nicho (gestão de horas + pedido + serviço + relatório + portal do cliente para
autônomos) é onde HoraCerta já está mais avançado que a maioria dos concorrentes diretos.
Fontes da pesquisa de 2026-09-12: [pontotel.com.br](https://www.pontotel.com.br/melhor-sistema-de-ponto-eletronico/),
[vr.com.br](https://www.vr.com.br/controle-de-ponto), [genyo.com.br](https://genyo.com.br/en/plans-and-prices/),
[jibble.io](https://www.jibble.io/pt-br/sistema-folha-ponto).

## Regulatório (contexto, não bloqueio hoje)

- **Portaria 671/2021 (MTE)**: obrigatória para empregador CLT com mais de 20 funcionários;
  exige REP-P registrado no INPI e recibos assinados com certificado ICP-Brasil quando o
  registro é feito por software puro. **Não se aplica** ao modelo atual de HoraCerta (prestador
  MEI multi-cliente), mas se o produto algum dia vender para empresas registrarem ponto de
  empregados CLT, isso vira um projeto de compliance à parte — não uma feature incremental.
- **LGPD**: aplica-se independente do porte da empresa; ver [[horacerta-security]] para o
  checklist técnico de dados pessoais.

## Como priorizar

Usar as prioridades já sequenciadas em `docs/HORACERTA_ANALISE_MERCADO_PRESTADORES_2026.md`
(seção 5, prioridades 1-6: previsto x realizado, fotos/anexos, histórico de status,
equipamentos/ativos, financeiro simples, lembretes) cruzadas com os blocos de
`docs/ROADMAP_EXECUCAO_HORACERTA.md`. Uma ideia nova só entra na frente dessas se:

1. Resolver um bloqueio de segurança/LGPD (sempre prioridade máxima), ou
2. For pré-requisito técnico para algo já priorizado, ou
3. O usuário pedir explicitamente para reordenar.

Evitar deliberadamente (lista já validada em `docs/HORACERTA_ANALISE_MERCADO_PRESTADORES_2026.md`,
seção 7): rastreamento GPS contínuo, prometer validade jurídica automática, assinatura eletrônica
sem provedor/requisitos jurídicos, NFS-e genérica, automação de cobrança real antes de regras
financeiras e segurança, recursos corporativos complexos antes de estabilizar o fluxo MEI-first.

## Ao usar este skill

- Para pesquisa nova de mercado/concorrência, usar busca na web e **atualizar a tabela acima com
  a data**, em vez de acumular análises duplicadas em `docs/`.
- Para decidir "o que fazer a seguir" no dia a dia, ir direto ao próximo item não feito da
  seção "Ordem recomendada" do roadmap — não reabrir a priorização do zero a cada conversa.
- Repassar o item escolhido para [[horacerta-feature]] assim que definido.
