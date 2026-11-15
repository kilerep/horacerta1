# Romaneio de envio a partir da produção — design

Data: 2026-11-15 · Pedido de: Fagner · Abordagem escolhida: A (linha do romaneio ligada ao item de produção)

## Por que

Hoje Fagner anota a produção (desenho, quantidade, horários) e depois redigita cada peça numa nota
de envio. Ele quer mandar itens da produção direto para o documento de envio, e ajustar lá a
quantidade quando só parte da ordem vai no caminhão. Também quer um nome mais formal que "nota".

## Metas

- Item de produção ganha o campo **Ordem de produção** (opcional), ao lado do desenho (código do
  item) e da quantidade; aparece no formulário, na lista de itens, no PDF/Excel do relatório e na fala
  ("Falar o item" não muda).
- Na lista de itens do relatório: modo **Selecionar** (tocar nos itens) com barra fixa
  "Criar romaneio com N itens" e "Adicionar ao rascunho nº…" (rascunhos do dono). No computador,
  botão direito num item abre o mesmo menu com aquele item já marcado.
- Cada linha do romaneio guarda o item de origem (`source_entry`, opcional). Ao entrar, a quantidade
  vem com **o que falta enviar** (quantidade do item menos o que já saiu em romaneios **enviados**);
  o dono edita no rascunho.
- Na produção, item mostra "30 de 49 enviadas" ou "Enviado" (só contam romaneios enviados).
- "Nota de envio" vira **"Romaneio de envio"** em telas, PDF, Excel, WhatsApp, avisos e aba.

## Fora do escopo

- Bloquear envio acima da quantidade produzida (só mostrar o saldo).
- Mudar URLs: links públicos já enviados (`/nota-envio/<token>/`) continuam valendo.
- Renomear modelos/tabelas no banco.

## Anti-metas

- Item sem quantidade ou sem desenho quebrar a criação do romaneio (entra com quantidade 1 e o
  dono ajusta; desenho vazio vira o código do item ou "-").
- Item de outro dono/relatório entrar no romaneio (sempre filtrar por dono).
- Romaneio enviado mudar quando o item de produção for editado ou apagado (linha guarda cópia dos
  dados; `source_entry` com SET_NULL).

## Como (decidido)

- `ProductionEntry.production_order` (CharField 40, blank) + migração.
- `ShipmentItem.source_entry` FK → ProductionEntry, null, SET_NULL + migração.
- `ProductionEntry.shipped_quantity()` = soma das linhas de romaneios SENT ligadas; `remaining`.
- POST `me/relatorios-producao/<sheet>/romaneio/` com `entry` (lista) e `target` ("new" ou id de
  rascunho): cria/usa rascunho do dono, adiciona linhas, redireciona para editar o rascunho.
- Rascunho novo herda destino/pessoas do último enviado (mesma regra do formulário).

## Abordagens consideradas

- **A (escolhida):** linha ligada ao item; mostra saldo e "enviado".
- **B:** só copiar dados; mais simples, mas a produção não sabe o que já saiu.
