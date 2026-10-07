# HoraCerta — Portal do cliente, folha profissional e presença

## Objetivo

Criar uma experiência profissional para o cliente acompanhar um serviço sem transformar o HoraCerta em ferramenta de vigilância.

A ideia central é separar três coisas:

1. **Folha profissional / ordem de serviço** — antes da execução.
2. **Acompanhamento do serviço** — durante a execução.
3. **Relatório final** — depois da execução.

## 1. Folha profissional / ordem de serviço

A folha deve ser enviada pelo prestador antes do serviço. Ela deve parecer profissional, mas sem prometer que substitui contrato formal, nota fiscal, termo jurídico, ART/RRT ou documento regulatório quando aplicável.

Conteúdo mínimo:

- Prestador.
- Cliente.
- Categoria do serviço.
- Local combinado.
- Data e horário previstos.
- Escopo do que será feito.
- Itens, materiais, equipamentos ou recursos previstos.
- Valores estimados ou valor fechado.
- Observações e condições.
- Área de conferência/aceite.

## 2. Variação por tipo de serviço

A mesma base deve mudar a linguagem conforme a categoria:

- Eventos e sonorização: **Proposta técnica para evento**.
- Assistência técnica: **Ordem de serviço técnico**.
- Reformas e obras: **Memorial simples de execução**.
- Limpeza e conservação: **Plano de atendimento**.
- Aulas e consultoria: **Plano de aula ou consultoria**.
- Demais categorias: **Proposta técnica / Ordem de serviço**.

Essa abordagem deixa o projeto premium sem criar telas totalmente diferentes para cada profissão.

## 3. Acompanhamento pelo cliente

O cliente pode receber um link público e acompanhar o que o prestador decidiu compartilhar daquele serviço.

Conteúdo seguro para o MVP:

- Status atual do serviço.
- Local combinado.
- Data e horário previstos.
- Períodos registrados pelo prestador.
- Descrição das atividades realizadas.
- Itens previstos ou usados.
- Relatório final quando for gerado.

## 4. Presença e localização

O recurso de presença deve ser opcional, transparente e proporcional.

Não implementar rastreamento contínuo como padrão.

Caminho recomendado:

### Fase 1 — Local combinado e registros manuais

- Mostrar na folha o endereço/local combinado.
- Mostrar períodos registrados pelo prestador.
- Mostrar atividade/descrição do período.
- Mostrar quando o relatório foi visualizado.

### Fase 2 — Check-in de presença opcional

- Botão do prestador: “Registrar chegada ao local”.
- Captura opcional de localização aproximada somente no momento do check-in.
- Texto claro dizendo que a localização será registrada naquele serviço e poderá ser vista pelo cliente do link.
- Não coletar localização em segundo plano.
- Não coletar localização contínua.
- Registrar data/hora, tipo do evento e endereço combinado.

### Fase 3 — Comprovante avançado

- Check-in e check-out com consentimento.
- Raio aproximado, não mapa em tempo real.
- Histórico limitado ao serviço.
- Opção do prestador desativar em serviços onde não faça sentido.
- Política de privacidade atualizada antes de produção.

## 5. Regras de produto

- O prestador controla quando gerar/enviar a folha.
- O cliente não deve ver dados de outros clientes.
- Link público deve ser único por serviço.
- Link público deve mostrar somente o que for necessário para aquele serviço.
- GPS/presença só deve existir se houver aviso claro e finalidade definida.
- O sistema não deve prometer fiscalização trabalhista, controle de empregado ou prova jurídica absoluta.

## 6. Exemplo de uso

### Prestador de manutenção

1. Cliente pede serviço.
2. Prestador cria pedido.
3. Prestador transforma em serviço.
4. Prestador adiciona escopo, data, local e itens.
5. Sistema gera “Ordem de serviço técnico”.
6. Cliente acompanha o status pelo link.
7. Prestador registra períodos.
8. Prestador gera relatório final.

### Evento de som

1. Cliente contrata som para evento.
2. Prestador cria serviço com valor fechado.
3. Prestador lista equipamentos inclusos.
4. Sistema gera “Proposta técnica para evento”.
5. Cliente recebe link com local, data, horário, composição técnica e valor fechado.
6. No futuro, prestador poderá registrar check-in de presença no local combinado.

## 7. Implementação atual

A prévia pública do serviço foi evoluída para uma folha profissional por categoria.

Ela já inclui:

- título ajustado pela categoria;
- natureza da folha;
- prestador;
- cliente e local;
- escopo;
- itens previstos;
- valores estimados;
- acompanhamento do serviço;
- aviso de que GPS deve ser opcional e transparente;
- área de conferência/aceite.

## 8. Próximos passos técnicos

1. Corrigir CI atual da Sprint 5.
2. Criar testes específicos para a folha profissional por categoria.
3. Criar modelo de check-in opcional somente depois de revisar privacidade e termos.
4. Adicionar logs de visualização e eventos de acompanhamento.
5. Melhorar PDF da folha profissional.
