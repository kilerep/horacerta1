---
name: horacerta-support
description: Use when triaging a bug report, production incident, or "the site is broken/wrong" for the live HoraCerta app — reproduce, root-cause, write a regression test, fix, and (only with explicit confirmation) ship via horacerta-qa + horacerta-deploy.
---

# HoraCerta — Suporte e incidentes

Departamento: **Suporte**. Ponto de entrada quando algo já em produção está errado, em vez de
uma feature nova (isso é [[horacerta-feature]]).

## Triagem

1. **É o site inteiro fora do ar (5xx, timeout, não carrega)?**
   Prioridade máxima: ir direto para o final de [[horacerta-deploy]] (verificação `curl` +
   `systemctl status`) para confirmar se é o processo Gunicorn caído antes de investigar causa
   raiz. Reiniciar o serviço restaura o ar rapidamente; a causa raiz vem depois, sem pressa
   artificial.

2. **É um comportamento incorreto (bug funcional, texto errado, cálculo errado)?**
   Seguir os passos abaixo com calma — não precisa de deploy de emergência.

## Reprodução local

Reproduzir com o mesmo ambiente da CI, não com `DEBUG=True` solto (ver [[horacerta-qa]] para as
env vars). Isso evita "não reproduz aqui" só porque o ambiente local está mais permissivo que
produção (foi exatamente o caso do bug de `SECURE_SSL_REDIRECT` nesta base).

## Causa raiz

- Localizar a app responsável pelo domínio do bug: `accounts` (login, perfil, segurança),
  `companies` (empresas/clientes), `services` (pedidos, serviços, propostas, catálogo),
  `timeclock` (registro de ponto, relatórios).
- Checar se é regra de isolamento por prestador/contrato antes de assumir que é lógica de
  negócio pura — vazamento de dado entre prestadores é sempre prioridade de segurança, não só
  bug funcional (escalar para [[horacerta-security]] se for o caso).

## Correção

1. Escrever o teste que reproduz o bug **antes** da correção (deve falhar primeiro).
2. Corrigir a causa raiz, não o sintoma.
3. Rodar [[horacerta-qa]] completo — correções pontuais têm efeito colateral em telas vizinhas
   com frequência maior do que parece.
4. Commit `fix(app): descrição curta` + atribuição.

## Publicar a correção

Nunca fazer deploy de correção sem pedir confirmação explícita, mesmo que pareça urgente —
seguir [[horacerta-deploy]] à risca, incluindo o checklist final. "Parece pequeno" não é critério
para pular a suíte de testes.

## Registro

Depois de resolvido, se o bug revelar um padrão maior (ex.: uma classe inteira de tela sem a
mesma trava de segurança), sinalizar para [[horacerta-feature]] como item de roadmap — não deixar
implícito só na mensagem de commit.
