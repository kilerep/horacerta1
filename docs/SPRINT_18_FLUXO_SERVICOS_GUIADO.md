# Sprint 18 — Fluxo guiado de serviços

## Objetivo

Tornar a área de Serviços fácil de entender para prestadores de diferentes segmentos, sem obrigar o usuário a conhecer previamente a diferença entre pedido, serviço, proposta, execução e relatório.

## Princípio do fluxo

1. Registrar como o atendimento começou.
2. Organizar cliente, local, escopo, agenda e cobrança.
3. Enviar uma folha ou proposta para conferência.
4. Registrar períodos, materiais e despesas durante a execução.
5. Entregar relatório final e, quando necessário, prestação de contas.

## Assistente de início

A rota `/me/servicos/comecar/` apresenta caminhos por situação:

- pedido recebido no WhatsApp;
- evento ou sonorização;
- viagem de trabalho ou atendimento externo;
- visita recorrente ou manutenção;
- serviço já combinado;
- consulta aos modelos profissionais.

O assistente não cria dados automaticamente. Ele direciona o prestador para o fluxo correto.

## Evento e sonorização

O caminho de evento utiliza o modelo profissional existente e orienta o prestador a registrar:

- programação e responsável;
- local, acesso e energia;
- montagem, testes, operação e desmontagem;
- equipamentos previstos;
- horários e valor fixo;
- proposta técnica antes da execução;
- relatório final após o evento.

## Viagem de trabalho e atendimento externo

O novo caminho prepara um serviço por hora e adiciona, sem valor, despesas comuns:

- pedágio;
- combustível;
- estacionamento;
- alimentação em viagem;
- hospedagem ou passagem.

O prestador deve remover o que não usar e preencher somente valores reais. Cada dia ou período trabalhado deve ser registrado separadamente.

## Prestação de contas

A prestação de contas reúne:

- prestador e cliente/empresa;
- serviço, local e período;
- horas e descrição das atividades;
- despesas de viagem ou atendimento;
- referências de comprovantes;
- materiais e outros itens consumidos;
- mão de obra, despesas, materiais e total geral.

O documento possui visualização interna, PDF e link público somente depois que o relatório final do serviço foi gerado.

## Segurança

- somente o prestador proprietário acessa a prestação interna;
- o link público exige o token do serviço;
- o link público só funciona quando o serviço está em `REPORT_SENT`;
- outro prestador recebe 404;
- nenhuma despesa recebe valor automático;
- não há GPS contínuo ou rastreamento em segundo plano.

## Limites

- comprovantes ainda não são enviados como arquivos; o campo de referência deve registrar número, descrição ou observação;
- a prestação de contas é um documento operacional e não substitui nota fiscal, política interna, aprovação financeira ou obrigação fiscal;
- o fluxo não altera clientes, contratos e serviços existentes;
- não há migration nesta Sprint.

## Validação manual

1. Abrir Serviços nos quatro temas.
2. Conferir o layout em computador e celular.
3. Registrar um pedido vindo do WhatsApp.
4. Criar um evento pelo assistente.
5. Criar uma viagem de trabalho.
6. Registrar dois períodos de horas em dias diferentes.
7. Marcar combustível e alimentação como usados.
8. Informar referências de comprovantes.
9. Abrir a prestação de contas.
10. Baixar o PDF.
11. Gerar o relatório final e testar o link público.
