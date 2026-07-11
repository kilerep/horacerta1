# HoraCerta — Glossário e tom de voz

## Objetivo

Padronizar a linguagem do HoraCerta para que o portal seja profissional, claro e compreensível para prestadores de serviço, clientes particulares e empresas contratantes.

A interface deve explicar o que aconteceu, por que aconteceu e qual é o próximo passo. Textos internos de código podem preservar nomes legados enquanto a migração de domínio não estiver concluída, mas o usuário não deve receber termos contraditórios.

## Públicos do portal

### Prestador de serviço

Termo principal para quem executa e administra trabalhos no HoraCerta. Inclui MEI, autônomo, profissional liberal, técnico, consultor, pequena empresa prestadora e equipe de serviços.

Usar **MEI** somente quando a informação depender desse enquadramento. Evitar apresentar todo prestador como funcionário.

### Empresa contratante

Organização que contrata, acompanha, confere e recebe serviços. A futura área empresarial deve usar esse termo em menus, convites, permissões e mensagens.

### Cliente particular

Pessoa física que contrata um serviço. Em telas compartilhadas entre pessoa física e jurídica, usar apenas **cliente**.

## Vocabulário oficial

| Usar | Evitar na interface |
| --- | --- |
| Prestador de serviço | Funcionário (MEI), colaborador genérico |
| Empresa contratante | Empresa cliente, RH/Admin como nome do perfil |
| Cliente particular | Pessoa avulsa |
| Pedido de serviço | Chamado, ticket, ocorrência, quando não forem conceitos distintos |
| Serviço | Job, tarefa técnica, OS genérica |
| Proposta de serviço | Contrato, quando não houver contrato formal |
| Folha do serviço | Contrato informal |
| Escopo do serviço | O que será feito, quando usado como título formal |
| Forma de cobrança | Modo de cobrança |
| Registro de execução | Ponto do serviço |
| Relatório final | Comprovante jurídico |
| Solicitar alteração | Reprovar, quando a intenção for pedir ajuste |
| Confirmar recebimento | Assinar, quando não houver assinatura formal |
| Arquivar | Excluir, quando o histórico precisar ser preservado |

## Padrão de escrita

- Usar português do Brasil com acentuação correta.
- Preferir frases curtas e voz ativa.
- Dar nome claro à ação principal.
- Evitar abreviações que o usuário não conheça.
- Não prometer validade jurídica, conformidade total, rastreamento, integração ou segurança que não tenham sido implementados e validados.
- Não chamar uma folha operacional de contrato formal.
- Explicar bloqueios com uma ação de recuperação.
- Manter o mesmo termo em títulos, botões, mensagens, PDF, WhatsApp e páginas públicas.

## Estrutura de mensagens

### Sucesso

**Ação concluída + efeito produzido.**

Exemplo:

> Serviço criado. Agora você pode revisar os itens e gerar a proposta para o cliente.

### Erro recuperável

**O que falhou + orientação direta.**

Exemplo:

> Não foi possível atualizar o pedido. Atualize a página e tente novamente.

### Bloqueio por regra

**Regra aplicada + próximo passo disponível.**

Exemplo:

> Este serviço já foi finalizado. Reabra o serviço antes de alterar os dados.

### Estado vazio

**Situação atual + ação recomendada.**

Exemplo:

> Nenhum pedido foi registrado. Crie um pedido para organizar a solicitação antes de iniciar o serviço.

## Hierarquia das telas

Cada tela operacional deve apresentar, nesta ordem:

1. título orientado à tarefa;
2. explicação curta do objetivo;
3. ação principal;
4. dados ou etapas essenciais;
5. próximos passos;
6. ações secundárias.

## Menus recomendados

### Prestador de serviço

- Início
- Clientes
- Horários
- Serviços
- Relatórios
- Notificações
- Meu perfil

Dentro de Serviços:

- Pedidos
- Serviços
- Modelos profissionais
- Catálogo de itens
- Propostas

### Empresa contratante

- Início
- Prestadores
- Pedidos
- Serviços
- Horas e fechamentos
- Relatórios
- Notificações
- Configurações

## Revisão obrigatória antes de publicar

- Não há caracteres corrompidos como `Ã`, `Â` ou `�`.
- Títulos e botões usam o mesmo vocabulário.
- A mensagem informa o próximo passo.
- O texto não cria promessa jurídica ou comercial não validada.
- A empresa vê somente dados relacionados ao seu vínculo.
- O prestador mantém privados seus outros clientes, agenda, catálogo e notas internas.
