# Notas de envio (comprovante de peças enviadas) — design

Data: 2026-11-08 · Pedido de: Fagner · Abordagem escolhida: A (dentro de Relatórios de produção)

## Por que

Fagner corta peças que às vezes vão de caminhão para outra empresa (ele carrega, o motorista leva).
Lá "ninguém acha" e a cobrança volta para ele, mesmo tendo enviado. Ele quer um comprovante:
na saída do caminhão monta uma **nota de envio** com os itens e manda para o **encarregado** e o
**supervisor**. Os dois abrem um link do HoraCerta, o sistema registra o **Visto**, eles podem
**Autorizar**, e baixam PDF/Excel. Tudo fica guardado e travado na conta dele: se alguém apagar a
mensagem ou o arquivo, ele ainda tem a nota numerada.

Sucesso = quando alguém cobrar uma peça, Fagner acha em segundos a nota com número, data/hora de
saída, ordem de produção e desenho, e mostra quem viu e autorizou e quando.

## Metas

- Criar nota com: destino (empresa), data/hora de saída, motorista e placa (opcionais),
  observação, e itens com **nº da ordem de produção**, **nº do desenho**, **quantidade** e
  descrição curta opcional.
- Ao **Enviar**: número sequencial por usuário (nº 0001, 0002…) e nota **travada** (ninguém edita,
  nem o dono; não pode ser apagada).
- Dois links pessoais (encarregado e supervisor), sem login, enviados pelo WhatsApp com mensagem
  pronta.
- Página pública bonita da nota: registra **Visto** (nome + data/hora) ao abrir, botão
  **Autorizar** (nome + data/hora), botões **Baixar PDF** e **Baixar Excel**.
- PDF e Excel no padrão visual dos relatórios (accounts/print_theme.py), com o bloco de
  Visto/Autorizado de cada destinatário, linhas de assinatura e código de conferência.
- Arquivo de notas com busca por nº da nota, ordem de produção, desenho e destino, e selo de
  situação.

## Fora do escopo

- Foto da carga (Fagner não fica com o celular no trabalho).
- Confirmação de recebimento pela empresa de destino.
- Login para encarregado/supervisor; contas para eles.
- Editar nota enviada. Correção = **nova nota** que aponta a anterior ("Substitui a nota nº 0004").
- Puxar itens dos relatórios de produção (eles não guardam OP + desenho).

## Anti-metas (falharia mesmo funcionando)

- Nota enviada que possa ser alterada ou apagada: perde o valor de prova.
- "Visto" marcado sozinho pela prévia de link do WhatsApp, sem a pessoa ter aberto.
- Mexer no fluxo atual dos relatórios de produção.
- Vocabulário de ponto eletrônico (o teste `SemVocabularioDePontoTests` continua valendo).

## Como (decidido)

**Lugar:** app `production`. Aba "Notas de envio" ao lado de "Relatórios" na tela
`/me/relatorios-producao/`; menu lateral continua com um item só ("Relatórios de produção").

**Modelos** (production/models.py, migração nova):

- `ShipmentNote`: id UUID, owner FK, number (inteiro, nulo no rascunho, único por owner),
  destination_company, departed_at (default agora), driver_name, vehicle_plate, notes,
  status (DRAFT/SENT), sent_at, replaces (FK para outra nota do mesmo dono, opcional),
  created_at/updated_at.
- `ShipmentItem`: note FK, position, production_order, drawing_number, quantity (inteiro ≥ 1),
  description (opcional).
- `ShipmentRecipient`: note FK, role (ENCARREGADO/SUPERVISOR), name, whatsapp, token UUID único,
  viewed_at, authorized_at.

**Regras:**
- Número atribuído no Enviar, em transação (max+1 do dono, com lock), formatado com 4 dígitos.
- Enviar exige pelo menos 1 item e os 2 destinatários com nome.
- Depois de SENT: views de edição/remoção de item recusam (redireciona com aviso); só rascunho
  pode ser excluído.
- Nome/WhatsApp dos destinatários e o destino vêm preenchidos com os da última nota enviada.

**Página pública** `/nota-envio/<token>/`:
- Mostra a nota completa e a situação dos dois destinatários.
- Visto: registrado por POST feito pelo JavaScript da página depois de carregar (robôs de prévia
  não executam JS) e só na primeira vez; o GET em si não marca nada.
- Autorizar: POST com CSRF, idempotente; confirmação em linha na página (sem alert/confirm nativo).
- `/nota-envio/<token>/pdf/` e `/excel/` para baixar. Token de um destinatário só serve para a nota
  dele.

**Tela do dono:** lista (busca + selos Rascunho / Enviada / Vista 1 de 2 / Autorizada 2 de 2),
formulário com linhas de itens adicionáveis, detalhe com botões "Enviar ao encarregado" e
"Enviar ao supervisor" (wa.me com a mensagem e o link de cada um) e downloads PDF/Excel.

**Aviso ao dono:** quando alguém vê ou autoriza, cria uma notificação no sininho
("Nota nº 0007 autorizada por João").

## Abordagens consideradas

- **A (escolhida):** dentro do app `production`, reaproveitando print_theme, padrão de link público
  por token e WhatsApp. Menos código e mesmo visual já aprovado; fica ligada à produção.
- **B:** app separado com menu próprio. Mais isolado, mais arquivos e visual duplicado; mesmo
  resultado para o usuário.
- **Descartada:** gerar nota a partir dos relatórios de produção (não guardam OP + desenho).

## Deixado para quem constrói

- Layout exato das telas e do PDF (seguir tokens dos temas e o teste de contraste; caprichar:
  é a peça "profissional" que vai para os patrões).
- Texto da mensagem de WhatsApp.
- Testes: travamento após envio, numeração sequencial e isolada por dono, visto só via POST,
  autorizar idempotente, token de um destinatário não serve para outro, PDF/Excel geram,
  vocabulário.
