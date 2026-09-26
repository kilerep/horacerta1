# Decisões da revisão com o ChatGPT (2026-09-26)

Resumo das rodadas de revisão crítica (Claude Code implementa, ChatGPT revisa). Serve de memória para as próximas sessões.

## Feito e em produção
- PWA seguro: SW v4 (HTML privado nunca em cache; só /help/, /terms/, /privacy/ + assets com hash), `/ping/`,
  aviso de conexão que segura POST sem rede, `Cache-Control: no-store, private` + `Vary: Cookie` para HTML logado,
  `Clear-Site-Data: "cache"` no logout, atualização por botão (sem reload automático).
- Autocadastro de MEI em `/cadastro/` (nome, e-mail, senha, aceite de termos com `terms_version`, honeypot,
  teto global por 10 min, interruptor `MEI_SIGNUP_ENABLED`). Cria só o User; sem Company.
- `ProductEvent` + `accounts/analytics.track` (allowlist de propriedades, sem PII).
- Testes de isolamento MEI A x MEI B (`accounts/test_tenant_isolation_mei.py`): sem vazamento nas 19 rotas testadas.

## Decidido nesta rodada (4)
1. Ordem: C (linguagem Entrada/Saída) e B (painel do funil) agora; D (navigator.share) depois; A (trocar e-mail) antes de escalar;
   **F (convite/código) cortado** e **E (e-mails D1/D3) cortado até o SMTP ser provado**.
2. Painel do funil: rota `interno/funil/` (só superusuário, mesma regra do `interno/`), conta usuários distintos,
   "onde travaram" e retenção semana 1 + semana 2 por ação de produto (horário/relatório), nunca por login.
3. Troca de e-mail logada exige senha atual (`conta/email/`), com link no menu lateral (MEI sem cliente também acessa).
4. Cada clique em "Enviar pelo WhatsApp" do relatório grava `report_share_clicked` (canal whatsapp).

## Pendências / riscos apontados
- **SMTP em produção não foi provado.** Antes de convidar gente: testar "esqueci minha senha" com um e-mail real
  (chega? remetente e link https corretos? senha antiga falha, nova entra, sem usuário duplicado).
- O teto global de cadastros (20 / 10 min) pode ser esgotado por um script (DoS de cadastro). Mitigação futura:
  `limit_req` no Nginx por IP em `/cadastro/`.
- `punch_recorded` dispara a cada batida individual (entrada ou saída), não por período completo. O funil conta pessoas
  distintas, então serve; se precisar de "período completo", criar evento `work_period_completed`.
- Primeira tela do MEI novo (checklist + tour + cards) pode disputar atenção no celular: teste com uma pessoa nova, em silêncio, 3 minutos.
- Linguagem: o lado do MEI já evita "par/timestamp"; os textos técnicos que sobraram ficam nas telas da empresa (não MEI).
