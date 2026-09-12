# HoraCerta — Análise de mercado de prestadores e prioridades 2026

Data: 2026-07-10

## 1. Posição recomendada

O HoraCerta deve se posicionar como portal operacional simples para MEI, autônomo e pequena operação de serviços.

A proposta não é competir imediatamente com plataformas corporativas de despacho de grandes equipes. O diferencial deve ser:

- começar rápido;
- funcionar bem no celular;
- organizar cliente, pedido, serviço, horas, itens e relatório;
- gerar uma apresentação profissional para o cliente;
- manter o fluxo compreensível para quem não domina gestão empresarial.

## 2. Padrões observados no mercado

Produtos modernos de gestão de serviços de campo costumam convergir nos seguintes blocos:

1. Agendamento e calendário.
2. Ordens de serviço e propostas reutilizáveis.
3. Serviços recorrentes e planos de manutenção.
4. Portal do cliente e comunicação de status.
5. Registro móvel de execução, fotos e checklists.
6. Histórico do cliente, equipamento ou local atendido.
7. Controle de itens, despesas e custo real.
8. Relatório final, cobrança e acompanhamento de pagamento.
9. Indicadores de produtividade, margem e recorrência.
10. Despacho, rotas e equipes em operações maiores.

## 3. Diagnóstico do HoraCerta

### Já bem encaminhado

- Cliente e contrato.
- Valor por hora.
- Registro de horários.
- Pedido e transformação em serviço.
- Serviço avulso ou cliente cadastrado.
- Endereço, data e horário.
- Itens previstos, usados e devolvidos.
- Cotação e WhatsApp.
- Prévia/folha profissional.
- Relatório final.
- Link público e primeira visualização.
- Checklist e timeline.
- Playbooks por categoria.
- Proposta de evento com valor fechado.
- Exportação para calendário.
- Criação de próxima visita recorrente.

### Ainda incompleto

- Anexos e fotos.
- Histórico formal de mudanças de status.
- Registro de equipamento/ativo atendido.
- Comparação estimado x realizado.
- Status financeiro do serviço.
- Lembretes automáticos.
- Recorrência automática em série.
- Preferências de comunicação.
- Portal autenticado para clientes recorrentes.
- Avaliação pós-serviço.

## 4. Feature aplicada: próxima visita

A primeira evolução de recorrência foi implementada sem criar automação pesada.

No detalhe do serviço, o prestador pode escolher **Criar próxima visita**.

A nova visita reaproveita:

- cliente e contrato;
- categoria;
- endereço;
- escopo;
- modelo de cobrança;
- horários sugeridos;
- observações, quando escolhido;
- itens e recursos, quando escolhido.

Ela não reaproveita:

- horas trabalhadas;
- execução anterior;
- relatório;
- visualizações;
- status final;
- token público.

Os itens copiados voltam ao estado **Previsto**. A nova visita nasce como serviço independente.

Essa abordagem atende limpeza, jardinagem, manutenção preventiva, consultoria, aulas, beleza, suporte técnico e outros atendimentos recorrentes, sem criar compromissos automáticos antes de o prestador confirmar a data.

## 5. Próximas prioridades recomendadas

### Prioridade 1 — Custo previsto x custo realizado

Criar comparação clara entre:

- horas previstas e realizadas;
- mão de obra estimada e final;
- itens previstos e usados;
- total estimado e total final;
- diferença absoluta e percentual.

Benefício: o prestador entende onde perdeu margem e melhora futuros orçamentos.

### Prioridade 2 — Fotos e anexos

Adicionar evidências com categorias:

- antes;
- durante;
- depois;
- comprovante/recibo;
- referência técnica.

Requisitos:

- limite de tamanho;
- tipos permitidos;
- acesso isolado por prestador/serviço;
- definição do que pode aparecer no link público;
- política de retenção.

### Prioridade 3 — Histórico de status

Registrar eventos como:

- serviço criado;
- prévia gerada;
- prévia visualizada;
- serviço iniciado;
- período encerrado;
- serviço finalizado;
- relatório enviado;
- relatório visualizado;
- serviço reaberto ou arquivado.

Benefício: auditoria operacional e linha do tempo real.

### Prioridade 4 — Equipamentos e ativos do cliente

Para assistência técnica, manutenção, automotivo e segurança:

- nome do equipamento/ativo;
- marca/modelo;
- número de série opcional;
- local de instalação;
- histórico de visitas;
- observações e garantia de serviço.

### Prioridade 5 — Financeiro simples

Sem virar sistema contábil completo:

- aguardando cobrança;
- enviado para cobrança;
- parcialmente recebido;
- recebido;
- vencido/cancelado;
- data e observação de recebimento.

Não chamar de nota fiscal nem substituir contabilidade.

### Prioridade 6 — Lembretes

- serviço amanhã;
- serviço atrasado;
- prévia enviada e não visualizada;
- relatório não visualizado;
- próxima manutenção sugerida;
- cliente sem valor/hora;
- fechamento próximo.

## 6. Features para fase posterior

- Série de recorrência automática com pausa/cancelamento.
- Agenda semanal/mensal interna.
- Portal autenticado do cliente.
- Avaliação e pedido de indicação.
- Rotas e deslocamento para múltiplos serviços.
- Gestão de pequenas equipes.
- Integração financeira/contábil por API.
- Check-in opcional de presença com privacidade.

## 7. O que evitar agora

- Rastreamento GPS contínuo.
- Prometer validade jurídica automática.
- Assinatura eletrônica sem provedor e requisitos jurídicos.
- NFS-e genérica sem integração municipal específica.
- Automação de cobrança real antes de regras financeiras e segurança.
- Recursos corporativos complexos antes de estabilizar o fluxo MEI-first.

## 8. Sequência executiva

1. Estabilizar e revisar visualmente a Sprint 5.
2. Integrar as Sprints aprovadas em branch de release.
3. Implementar estimado x realizado.
4. Implementar histórico de status.
5. Implementar fotos/anexos com segurança.
6. Implementar financeiro simples.
7. Implementar recorrência automática somente após validar a criação manual de próxima visita.
