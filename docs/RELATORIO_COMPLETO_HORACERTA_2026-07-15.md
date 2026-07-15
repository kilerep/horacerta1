# Relatório completo do HoraCerta — 15/07/2026

## 1. Resumo executivo

O HoraCerta já ultrapassou o estágio de simples registrador de horas. O produto possui um núcleo utilizável para prestadores de serviço, com clientes, contratos, horas, pedidos, serviços, materiais, propostas, folhas profissionais, execução, relatórios e compartilhamento por link.

A evolução para empresas contratantes também já começou no GitHub. Existe uma cadeia de Sprints com linguagem profissional, fundação organizacional, cadastro da empresa, membros e vínculo seguro com prestadores. Essa área ainda não está conectada aos serviços, horas e relatórios reais do prestador.

O principal risco atual não é ausência de funcionalidades. É a diferença entre o que está em `main`, o que está na release publicada e o que está nas branches de desenvolvimento. Antes de ampliar o produto, o repositório precisa de uma release candidata única, validação visual e publicação controlada.

## 2. Estado das branches

### `main`

- Continua sendo a base antiga.
- Está 143 commits atrás da `release-beta-2026-07-10`.
- Não representa o produto atualmente desenvolvido.

### `release-beta-2026-07-10`

- Consolida Sprints 0 a 5.
- Head conhecido: `38f1e3f8f77452fc70de17f80e7163678be03238`.
- CI aprovada.
- Inclui o hotfix do CSS da landing e a correção da página 500.

### Desenvolvimento posterior

A cadeia posterior à release beta é linear:

1. `post-release-stabilization-2026-07-11`;
2. `service-template-library-2026-07-11`;
3. `sprint-14-linguagem-profissional`;
4. `sprint-15-empresas-fundacao`;
5. `sprint-16-empresa-cadastro-painel`;
6. `sprint-17-empresas-vinculo-prestador`;
7. `release-candidate-2026-07-15`.

As Sprints 14, 15, 16 e 17 possuem CI aprovada em seus heads atuais.

## 3. Situação conhecida do servidor

O último estado confirmado em terminal foi:

- branch `release-beta-2026-07-10`;
- commit `93fa27b8769184027e18cce979522892c44b602e`;
- PostgreSQL conectado;
- Nginx válido;
- `horacerta.service` ativo;
- migration `services.0015` pendente e depois autorizada para aplicação;
- landing retornando HTTP 500 por asset ausente.

O hotfix `38f1e3f8f77452fc70de17f80e7163678be03238` foi criado depois desse diagnóstico. Não há, neste histórico, confirmação final do `git rev-parse HEAD` do servidor após o hotfix. Portanto, a versão efetivamente ativa precisa ser verificada antes da próxima publicação.

## 4. Produto atual para prestadores de serviço

### 4.1 Conta e acesso

Implementado:

- cadastro, login e logout;
- autenticação por e-mail ou usuário;
- recuperação de senha;
- alteração autenticada de senha;
- temas visuais;
- perfil do prestador;
- central de ajuda;
- configuração segura para produção;
- página 404 e página 500;
- proteção de cookies e HTTPS em produção.

Pendente:

- alteração confirmada de e-mail;
- encerramento das outras sessões;
- histórico de acessos;
- dispositivos conectados;
- autenticação em dois fatores;
- exportação dos dados pessoais;
- solicitação de exclusão da conta;
- preferências de notificações.

### 4.2 Clientes e contratos

Implementado:

- cadastro de clientes e empresas atendidas;
- contratos por cliente;
- valor por hora;
- situação ativa ou inativa;
- busca e filtros;
- detalhes em accordion;
- fechamento rápido;
- histórico e relatórios relacionados;
- clientes avulsos em pedidos e serviços;
- opção de salvar cliente avulso.

Pendente:

- saúde do contrato;
- aviso de vencimento;
- histórico financeiro do cliente;
- valor gerado por cliente;
- próxima ação sugerida;
- deduplicação assistida de clientes;
- importação estruturada de clientes;
- separação mais clara entre pessoa física e pessoa jurídica.

### 4.3 Horas e jornada

Implementado:

- registro automático e manual;
- pares de entrada e saída;
- histórico por período;
- totais diários, semanais e mensais;
- valor estimado;
- seleção de cliente e contrato;
- edição apenas do dia atual;
- bloqueio de dias passados e futuros para o prestador;
- bloqueio de período após relatório;
- logs internos de alteração;
- relatórios de horas;
- exportação CSV dentro de Relatórios.

Regras consolidadas:

- o prestador edita o dia, não uma batida isolada;
- somente o dia atual pode ser editado;
- um período fechado fica bloqueado, inclusive o dia atual;
- correções retroativas pertencem ao fluxo administrativo;
- GPS não faz parte do fluxo atual do produto.

Pendente:

- solicitação formal de correção pela empresa;
- aprovação ou confirmação de fechamento;
- histórico de decisões da empresa;
- lembrete de período não enviado;
- comparação entre períodos;
- indicadores de horas e faturamento.

### 4.4 Pedidos de serviço

Implementado:

- pedido simples antes do serviço;
- cliente cadastrado ou avulso;
- origem e urgência;
- itens rápidos;
- busca de catálogo por código interno ou nome;
- mensagem simples ao cliente;
- cotação inicial para organização interna;
- transformação do pedido em serviço;
- transferência dos itens previstos.

Pendente:

- pedido criado diretamente pela empresa contratante;
- conversa estruturada no pedido;
- anexos e referências;
- prazo de resposta;
- recusa com motivo;
- histórico de alterações do pedido;
- notificações de novo pedido e resposta.

### 4.5 Serviços

Implementado:

- serviço com cliente, local, categoria e escopo;
- cobrança por hora, valor fixo ou valor indefinido;
- materiais, peças, despesas e catálogo;
- itens previstos, cotados, comprados, usados, parcialmente usados, não usados e devolvidos;
- checklist do serviço;
- timeline visual;
- registro de períodos de execução;
- comparação previsto versus realizado;
- calendário `.ics`;
- criação de próxima visita;
- recorrência assistida;
- relatório final;
- isolamento por prestador;
- categorias e playbooks profissionais;
- propostas específicas para eventos;
- biblioteca com 14 modelos profissionais.

Pendente:

- fotos antes, durante e depois;
- anexos, recibos e documentos;
- histórico persistente de mudanças de status;
- motivo de cancelamento;
- garantia do serviço;
- equipamento ou ativo atendido;
- checklist marcável por item;
- responsável pela execução;
- equipe do serviço;
- lembretes de visita;
- comunicação registrada com o cliente;
- aprovação de alteração de escopo;
- ordem de mudança e serviços adicionais.

### 4.6 Folha profissional, propostas e portal por link

Implementado:

- folha profissional adaptada à categoria;
- escopo, logística, itens e valores;
- link público;
- primeira visualização registrada;
- WhatsApp;
- proposta de evento com valor fechado;
- portal simples com status e execução;
- aviso de que a folha não substitui contrato, nota fiscal, ART/RRT, laudo ou obrigação regulatória.

Pendente:

- expiração configurável do link;
- revogação e rotação do token;
- histórico de versões da proposta;
- confirmação ou solicitação de alteração registrada;
- comentários do cliente;
- aceite com trilha de auditoria, sem prometer assinatura jurídica;
- identidade visual e logo do prestador;
- modelos visuais de PDF.

### 4.7 Relatórios

Implementado:

- relatório por período;
- PDF;
- link público;
- WhatsApp;
- filtros;
- horas, mão de obra e itens;
- primeira visualização;
- relatório final do serviço.

Pendente:

- modelos de relatório;
- logo e dados comerciais do prestador;
- histórico de versões;
- lembrete de relatório não visualizado;
- confirmação de recebimento;
- solicitação de correção;
- status financeiro simples;
- gráficos e comparações;
- exportação estruturada para contabilidade.

### 4.8 PWA e experiência móvel

Implementado:

- manifest;
- service worker;
- ícones;
- instalação como PWA;
- layout mobile-first;
- testes de assets críticos.

Pendente:

- validação completa de instalação em Android, Windows e iOS;
- estratégia de atualização do service worker;
- mensagem de nova versão disponível;
- definição precisa do que funciona offline;
- testes reais em conexão instável;
- monitoramento de erros no navegador.

## 5. Área de empresas contratantes

### 5.1 Fundação concluída no GitHub

A nova área usa um domínio separado do cadastro legado `Company`.

Implementado:

- `HiringOrganization` para a empresa contratante autenticada;
- `OrganizationMember` para vários usuários na mesma organização;
- papéis Administrador, Gestor de serviços, Financeiro e Consulta;
- `ProviderOrganizationLink` para vínculo com o prestador;
- permissões independentes para serviços, horas, relatórios e valores;
- `OrganizationAuditEvent` para auditoria;
- cadastro inicial da empresa;
- primeiro administrador;
- painel empresarial;
- convite e aceite de membros;
- convite, aceite e recusa de prestador;
- suspensão, reativação e encerramento do vínculo;
- isolamento entre organizações;
- testes de acesso e permissões.

### 5.2 O que ainda falta para a área empresarial ser útil

A empresa ainda não visualiza dados reais do prestador.

Próxima etapa necessária:

1. relacionar o vínculo empresarial ao cadastro de cliente usado pelo prestador;
2. permitir ao prestador confirmar qual cliente corresponde à organização;
3. criar portal empresarial somente leitura;
4. mostrar serviços autorizados;
5. mostrar próximas visitas;
6. mostrar propostas e relatórios autorizados;
7. mostrar horas quando `share_hours=True`;
8. ocultar valores quando `share_financial_values=False`;
9. garantir que notas internas e outros clientes nunca sejam expostos;
10. registrar toda decisão em auditoria.

Depois disso:

- empresa cria pedido;
- prestador aceita, recusa ou solicita informação;
- empresa confirma proposta ou solicita alteração;
- prestador envia fechamento;
- empresa confirma ou solicita correção.

## 6. Arquitetura e qualidade técnica

### Pontos fortes

- regras de negócio importantes possuem testes;
- CI valida configuração, migrations, testes, estáticos e deploy checks;
- ambiente de demonstração local é separado de produção;
- serviços estão isolados por prestador;
- a área empresarial nasceu separada do modelo legado de cliente;
- links públicos usam tokens não sequenciais;
- operações críticas usam POST e validação de permissão;
- documentação técnica e de produto aumentou significativamente.

### Dívidas técnicas

1. `main` não representa o produto atual.
2. Existem muitas PRs antigas abertas, embora suas mudanças já estejam na release.
3. A cadeia de branches empilhadas dificulta publicação e rollback.
4. `accounts/tests.py` continua grande e concentrado.
5. `accounts/test_00_mei_clients_legacy_copy.py` altera testes legados em tempo de execução e precisa ser removido após corrigir as asserções originais.
6. `companies.models.Company` ainda mistura cliente legado, assinatura, features e políticas antigas.
7. Existem modelos legados de geolocalização/QR no domínio `companies`, apesar de GPS não fazer parte do produto atual.
8. Há metadados e rótulos antigos em inglês ou sem acentuação no domínio legado.
9. Uploads continuam no filesystem local; é necessário plano de backup e armazenamento externo antes de crescimento real.
10. Falta monitoramento de exceções e métricas de aplicação.
11. Faltam testes end-to-end reais de navegador.
12. Falta uma política explícita de expiração e revogação dos links públicos.

## 7. Segurança e privacidade

Implementado:

- isolamento por usuário e organização;
- papéis empresariais;
- permissões de compartilhamento;
- valores financeiros privados por padrão;
- cookies seguros em produção;
- redirecionamento HTTPS;
- auditoria empresarial;
- healthcheck sem exposição de credenciais;
- `.env` fora do repositório atual.

Pendente:

- 2FA;
- histórico de login;
- encerramento de sessões;
- expiração de convites;
- revogação de links públicos;
- política de retenção de auditoria;
- política de retenção de arquivos;
- exportação e exclusão de dados;
- revisão formal de privacidade e termos;
- armazenamento externo de mídia;
- monitoramento e alertas de erro;
- revisão dos segredos históricos do Git.

## 8. Operação e publicação

### Melhoria adicionada nesta release candidata

Novo comando:

```bash
python manage.py check_release_readiness
```

Ele valida, em uma única execução:

- configuração Django;
- conexão com o banco;
- migrations pendentes;
- arquivos estáticos públicos críticos.

O comando interrompe a publicação quando encontra falha.

### Sequência operacional recomendada

1. confirmar branch e commit no servidor;
2. criar backup do banco e da pasta `media`;
3. buscar a release candidata;
4. instalar dependências;
5. executar `check_release_readiness` antes da migration;
6. revisar `migrate --plan`;
7. aplicar migrations;
8. executar novamente `check_release_readiness`;
9. coletar estáticos;
10. reiniciar somente `horacerta.service`;
11. validar `/health/`, landing, login e rotas autenticadas;
12. conferir logs;
13. manter referência do commit anterior para rollback.

## 9. Prioridades recomendadas

### Prioridade imediata — estabilização

- CI verde da release candidata;
- validação visual no computador e celular;
- confirmar versão ativa no servidor;
- consolidar branches;
- remover workaround de testes;
- fechar PRs supersededidas;
- atualizar `main` somente depois da validação.

### Próxima feature — portal empresarial somente leitura

- vínculo com cliente legado confirmado pelo prestador;
- serviços, visitas, propostas e relatórios compartilhados;
- horas e valores respeitando permissões;
- nenhum acesso a notas internas ou outros clientes.

### Depois — decisões e colaboração

- empresa cria pedido;
- prestador responde;
- empresa solicita alteração;
- empresa confirma proposta e relatório;
- fechamento com solicitação de correção;
- histórico completo de decisões.

### Depois — qualidade operacional do serviço

- fotos e anexos;
- histórico de status;
- checklist marcável;
- garantia;
- ativos/equipamentos;
- cancelamento;
- lembretes.

### Depois — segurança da conta

- sessões;
- 2FA;
- login history;
- exportação e exclusão;
- preferências de notificação.

## 10. Avaliação do investimento

O projeto não é perda de tempo. Existe um produto coerente e uma diferenciação possível: unir rotina do prestador e relacionamento com empresas contratantes sem transformar o sistema em um marketplace genérico.

O valor do HoraCerta está no fluxo completo:

`Cliente → Pedido → Proposta/Folha → Serviço → Execução → Horas/Itens → Relatório → Empresa contratante`

O investimento passa a fazer sentido quando o foco muda de quantidade de features para:

- estabilidade;
- clareza de uso;
- segurança de acesso;
- validação com prestadores reais;
- publicação controlada;
- métricas de utilização.

## 11. Critério para considerar a versão pronta

A release candidata só deve ser publicada quando:

- CI estiver verde;
- migrations estiverem consistentes;
- landing, login e healthcheck responderem;
- um prestador conseguir criar cliente, pedido, serviço, folha e relatório;
- um link público abrir no computador e celular;
- uma empresa conseguir criar organização, convidar membro e vincular prestador;
- dados de outra organização não forem acessíveis;
- backup e rollback estiverem preparados;
- logs não apresentarem traceback.
