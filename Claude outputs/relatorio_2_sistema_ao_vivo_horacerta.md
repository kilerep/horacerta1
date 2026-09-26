# Relatório 2 — Análise do Sistema ao Vivo (site)
**URL:** https://horacertagestao.com.br
**Testado logado como:** Fagner Dos Santos (perfil Profissional/MEI)
**Data:** 12/09/2026

## Visão geral

Sistema de gestão de jornada/ponto para empresas e profissionais MEI, com registro de horário validado por localização, gestão de clientes/contratos, serviços avulsos e relatórios. Design escuro (tema "Grafite Premium"), com 4 temas visuais disponíveis. Interface é clara e o menu lateral organiza bem as seções (Operação / Conta).

## Assuntos que precisam ser melhorados

**1. A página de erro 404 (e provavelmente a 500) tem um bug de acentuação — precisa ser corrigido.**
Ao acessar uma URL inexistente, o texto aparece como "PÃ¡gina nÃ£o encontrada" e "O endereÃ§o acessado nÃ£o existe" em vez de "Página não encontrada" e "O endereço acessado não existe". É um bug clássico de charset (UTF-8 sendo interpretado como Latin-1) isolado nessa página de erro — as outras telas do sistema não mostram esse problema. Isso passa uma impressão de descuido justamente na tela que o usuário vê quando algo já deu errado. Vale conferir o template `templates/404.html` (e o `500.html`) e garantir que estão sendo servidos com `charset=utf-8` explícito.

**2. A Política de Privacidade está fraca para os padrões da LGPD — precisa ser expandida.**
O texto atual é genérico: fala em "dados de cadastro" e "dados operacionais" sem detalhar que o sistema captura geolocalização (latitude/longitude/precisão) a cada registro de ponto, não define prazo de retenção dos dados, não indica um canal ou e-mail específico para o titular exercer direitos (fala só em "canais oficiais informados pela empresa", o que é vago), e não menciona um Encarregado de Dados (DPO), que a LGPD recomenda ter identificado. Como o sistema lida com dado de localização de pessoas físicas (funcionários/MEIs) de forma sistemática, essa é uma área que merece atenção jurídica antes de crescer a base de usuários — o risco cresce junto com o número de empresas usando a plataforma.

**3. O aviso "Este contrato valida localização no momento do registro. Não há rastreamento contínuo." é bom, mas falta um consentimento explícito antes da primeira captura.**
A frase no dashboard é transparente e isso é positivo, mas hoje ela é só um aviso informativo — não há uma tela de "aceito o uso da minha localização para bater ponto" no cadastro/primeiro acesso do profissional. Do ponto de vista de LGPD, consentimento informado explícito (ou pelo menos ciência ativa, com um clique de "entendi e aceito") é mais defensável do que um texto que o usuário pode nem ler.

**4. Notificações push aparecem como disponíveis no menu, mas não funcionam de fato.**
Do lado do usuário: existe a opção "Notificações" no menu e ela é apresentada como funcional. Como já identificado na análise de código, o botão de ativar sempre diz que deu certo mas nada é salvo — então isso é uma promessa quebrada de funcionalidade e vale decidir entre implementar de verdade ou esconder a opção até estar pronta, para não gerar reclamação de usuário que "achava que ia receber avisos".

**5. Termos de Uso estão honestos sobre o estágio de MVP, mas faltam cláusulas que uma empresa cliente vai querer ver.**
O texto atual é claro e direto, o que é positivo. Mas não há: cláusula de SLA/disponibilidade com números (hoje só diz "não há promessa de disponibilidade absoluta"), política de cancelamento/encerramento de conta, nem tratamento de responsabilidade em caso de perda de dados de ponto (que tem valor jurídico/trabalhista para a empresa cliente). Se o objetivo é vender para empresas de verdade, isso tende a ser perguntado por qualquer área jurídica antes de fechar contrato.

**6. Painel do profissional está funcional, mas pode reduzir cliques no fluxo principal.**
O fluxo de bater ponto exige: abrir o menu → conferir cliente atual → clicar em "Registrar horário". Como bater ponto é a ação mais frequente do dia a dia (o próprio propósito do app), pode valer a pena colocar o botão de registro em destaque já na tela inicial sem precisar confirmar o cliente toda vez, principalmente para quem atende só um cliente fixo.

**7. `/admin/` do Django é publicamente acessível (ainda que corretamente bloqueado para quem não é staff).**
Testei ao vivo: acessar `/admin/` como usuário comum mostra a mensagem "Você está autenticado... mas não está autorizado a acessar esta página" — ou seja, o controle de acesso em si está certo. Mas o caminho padrão `/admin/` ficar exposto publicamente é um convite para tentativas de força bruta contra contas de staff (reforça o ponto 4 do relatório de código: sem bloqueio de tentativas, é ainda mais importante não deixar o admin fácil de achar).

## Resumo direto

O sistema funciona e a experiência de uso do dia a dia é boa. Os pontos que mais pesam são: o texto quebrado da página 404 (rápido de corrigir, mas visível), a política de privacidade abaixo do necessário para um sistema que coleta localização de pessoas (isso é o item que eu trataria com mais prioridade, por ser uma exigência legal e não só estética), e a funcionalidade de notificações push que promete algo que não entrega hoje.
