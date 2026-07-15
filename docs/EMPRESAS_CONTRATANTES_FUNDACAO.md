# HoraCerta — Fundação da área de empresas contratantes

## Objetivo

Criar um domínio próprio para empresas que contratam prestadores, sem transformar automaticamente os cadastros atuais de clientes em contas empresariais e sem expor dados privados do prestador.

## Decisão arquitetural

O modelo legado `companies.Company` continua representando o cadastro de cliente mantido pelo prestador. Ele não será convertido silenciosamente em uma organização autenticada.

A nova área utiliza entidades próprias:

- `HiringOrganization`: empresa contratante autenticada;
- `OrganizationMember`: usuários e papéis internos da empresa;
- `ProviderOrganizationLink`: vínculo controlado entre empresa e prestador;
- `OrganizationAuditEvent`: histórico imutável de decisões relevantes.

## Papéis empresariais

### Administrador

- gerencia dados da empresa;
- gerencia membros;
- gerencia prestadores vinculados;
- visualiza informações financeiras compartilhadas.

### Gestor de serviços

- cria e acompanha pedidos;
- acompanha propostas e serviços;
- não gerencia membros;
- não visualiza valores financeiros sem permissão específica.

### Financeiro

- visualiza horas, fechamentos, valores e relatórios compartilhados;
- não gerencia membros ou execução operacional.

### Consulta

- acesso somente para leitura ao conteúdo permitido.

## Compartilhamento com o prestador

O vínculo registra permissões independentes para:

- serviços;
- horas;
- relatórios;
- valores financeiros.

A permissão de valores financeiros começa desativada. Um vínculo inativo, suspenso, recusado ou encerrado não compartilha informações.

## Dados que permanecem privados do prestador

- outros clientes;
- outros serviços;
- agenda completa;
- catálogo completo;
- notas internas;
- faturamento global;
- despesas de trabalhos não relacionados à empresa;
- dados pessoais não necessários ao vínculo.

## Auditoria

Eventos empresariais devem registrar:

- organização;
- usuário responsável;
- tipo do evento;
- objeto afetado;
- resumo legível;
- metadados mínimos;
- data e hora.

Eventos de auditoria não podem ser editados pelo fluxo normal.

## Compatibilidade

Esta fundação não altera:

- clientes existentes;
- contratos existentes;
- registros de horas;
- pedidos e serviços atuais;
- links públicos;
- regras de edição do dia atual;
- bloqueios após fechamento;
- produção ou servidor.

## Próxima Sprint

A próxima etapa deve criar:

1. cadastro inicial da empresa contratante;
2. primeiro membro administrador;
3. painel empresarial vazio com próximos passos;
4. convite de membros;
5. testes de acesso por papel.

A integração com pedidos, serviços, horas e relatórios deve ocorrer somente depois da validação da organização, dos membros e do vínculo com o prestador.
