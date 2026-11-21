# HoraCerta — Relatório interno de status e roadmap

Data: 2026-07-08
Branch de trabalho: `sprint-5-service-timeline`
Base técnica atual das PRs: `sprint-0-fundacao`

## 1. Limite desta análise

Este relatório foi feito a partir do repositório GitHub, das PRs abertas e do documento interno de análise do HoraCerta. Não houve acesso ao servidor de produção, RDS, `.env`, banco real ou dados reais de usuário.

O usuário real não deve ser usado para teste automatizado ou validação em produção enquanto houver bloqueadores de segurança. Para testes locais, usar conta de demonstração criada por comando seguro em `DEBUG=True`.

## 2. Leitura do documento interno

O documento interno aponta que o HoraCerta já possui base sólida, navegação clara e funcionalidades bem pensadas, mas precisa evoluir em UX/UI, automações, segurança e conformidade.

Principais lacunas citadas:

- Dashboard com widgets e atalhos rápidos.
- Meus Clientes com accordion melhor, busca/filtro, saúde do contrato e próximas ações.
- Serviços com timeline visual, checklist, anexos/fotos, comunicação com cliente, notificações, histórico de status e calendário.
- Relatórios com templates, histórico, lembretes, análise de dados e experiência mais profissional.
- Perfil com mudança de senha/e-mail, segurança, preferências e recursos LGPD.
- PWA/offline e experiência mobile-first.

## 3. O que já temos no produto

### 3.1 Base MEI/prestador

- Prestador/MEI como usuário principal.
- Clientes/empresas vinculados ao prestador.
- Contratos com valor/hora.
- Registro de horários.
- Histórico e relatórios.
- Serviços e pedidos separados do controle normal de horas.
- Link público para cliente consultar relatório/previsão.

### 3.2 Regras de negócio consolidadas

- Prestador edita horário apenas do dia atual.
- Dias passados, dias futuros e período fechado por relatório ficam bloqueados para o prestador.
- Correção retroativa fica reservada ao admin interno.
- GPS/localização não é escopo central do produto neste momento.
- Auditoria e rastreio devem priorizar organização e clareza, não vigilância.

### 3.3 Serviços

O módulo de serviços já cobre:

- Pedido simples.
- Transformação de pedido em serviço.
- Serviço planejado.
- Cliente cadastrado ou cliente avulso.
- Endereço/data/horário.
- Itens previstos, usados, não usados/devolvidos.
- Períodos de execução.
- Cotação via WhatsApp.
- Prévia para cliente.
- Relatório final.
- Valor por hora ou valor fixo.

## 4. Sprints e PRs abertas

### Sprint 0 — Fundação técnica

Status: PR aberta em rascunho.

Inclui:

- CI Django.
- Testes de fumaça.
- PWA/manifest/service worker.
- Endurecimento de configuração.
- Remoção de arquivo local com credencial do conteúdo atual da branch.

Bloqueador:

- Credencial antiga apareceu no histórico do repositório. Antes de deploy real, rotacionar a senha do RDS e atualizar o servidor.

### Sprint 1 — Clientes e itens rápidos

Status: PR aberta em rascunho.

Inclui:

- Meus Clientes com accordion mais controlado.
- Busca/filtros por cliente.
- Estados vazios.
- Próximos passos nos cards.
- Busca de item rápido do pedido por código interno ou nome do catálogo.

Ponto de atenção:

- Houve workaround temporário em teste legado. Precisa ser limpo antes de considerar a PR final.

### Sprint 2 — Segurança de senha

Status: PR aberta em rascunho.

Inclui:

- Troca autenticada de senha com validações nativas do Django.
- Atalhos no perfil/configurações.
- Testes de acesso, troca válida e senha antiga incorreta.

Falta:

- Alteração de e-mail.
- Logout de todas as sessões.
- 2FA.
- Histórico de login.
- Exportação/exclusão de dados.

### Sprint 3 — Painel MEI com ações prioritárias

Status: PR aberta em rascunho.

Inclui:

- Bloco Ação de hoje.
- Atalhos para registro incompleto, cliente sem valor/hora, relatório pendente, pedidos novos e notificações.

Falta:

- Widgets visuais completos.
- Gráficos.
- Sincronização mais forte com serviços próximos.
- Estado de trabalho/pausa/offline.

### Sprint 4 — Ajuda MEI-first

Status: PR aberta em rascunho.

Inclui:

- Central de ajuda alinhada ao fluxo atual do prestador.
- Explicação de clientes, contratos, horas, pedidos, serviços e relatórios.
- Remoção de textos antigos empresa-first.
- Regra explícita de ausência de GPS como escopo central atual.

### Sprint 5 — Serviços, demonstração e taxonomia premium

Status: PR aberta em rascunho.

Inclui:

- Conta/cenários locais de demonstração seguros para DEBUG=True.
- Cenário local com evento de sonorização.
- Proposta de evento com revisão interna antes de WhatsApp.
- Versão pública da proposta sem preço unitário de equipamentos.
- Checklist geral de serviço.
- Timeline visual do serviço.
- Categorias premium de prestadores.
- Catálogo premium por segmento via comando.
- Documento de taxonomia premium de serviços.

## 5. Melhorias aplicadas recentemente

### 5.1 Serviços gerais

- Checklist do serviço para qualquer categoria.
- Timeline visual: Rascunho → Planejado → Em execução → Finalizado → Relatório enviado.
- Testes automáticos para checklist/timeline.

### 5.2 Eventos e propostas

- Tela de revisão antes de enviar proposta.
- Avisos quando falta WhatsApp, local, data, horário, itens ou condições.
- Link público profissional.
- Valor fechado do pacote.
- Itens/equipamentos sem preço unitário para o cliente.

### 5.3 Premiumização por segmento

Foram adicionadas categorias para:

- Reformas e obras.
- Limpeza e conservação.
- Jardinagem e paisagismo.
- Marcenaria e serralheria.
- Assistência técnica.
- Automotivo.
- Beleza e bem-estar.
- Eventos e sonorização.
- Fotografia e vídeo.
- Aulas e consultoria.
- Administrativo e escritório.
- Segurança e monitoramento.

Também foi criado comando para sugerir itens de catálogo por segmento para o prestador.

## 6. O que ainda falta fazer

### Prioridade crítica antes de produção

1. Rotacionar senha do RDS.
2. Atualizar `.env` do servidor.
3. Validar que produção usa `DEBUG=False`, segredo forte, domínio correto e HTTPS.
4. Montar uma branch integrada com as Sprints aprovadas.
5. Rodar suíte completa local e CI.
6. Fazer backup antes de qualquer deploy.
7. Não publicar branch isolada com apenas parte das Sprints.

### Segurança e conta

1. Alterar e-mail com validação segura.
2. Logout de todas as sessões após troca de senha.
3. Histórico de login.
4. Preferências de notificação.
5. Exportar dados do usuário.
6. Solicitação de exclusão de conta.
7. 2FA em sprint posterior.

### Clientes

1. Limpar workaround de testes legados.
2. Consolidar accordion e filtros na branch final.
3. Saúde do contrato.
4. Alertas de cliente sem valor/hora.
5. Próximas ações por cliente.
6. Histórico de relatórios enviados/visualizados/pagos.

### Serviços

1. Histórico de mudanças de status.
2. Fotos/anexos antes/depois.
3. Modelos de descrição por categoria.
4. Checklist específico por categoria.
5. Calendário visual de serviços.
6. Notificações de serviço próximo ou atrasado.
7. Melhorias no relatório final por segmento.

### Relatórios

1. Melhorar layout PDF/print.
2. Templates de relatório.
3. Histórico de versões.
4. Lembretes de relatório não visualizado.
5. Métricas por cliente/período.
6. Marcar como pago/recebido com histórico simples.

### Dashboard

1. Widgets visuais de horas, valor, clientes pendentes e serviços em progresso.
2. Atalhos rápidos.
3. Visão de agenda/serviços próximos.
4. Indicador de status do dia.
5. Mais prevenção de erro para usuário novo.

### PWA/mobile

1. Revisar instalação no celular.
2. Corrigir ou limitar offline com segurança.
3. Tela inicial mais objetiva.
4. Teste visual mobile-first.

## 7. Ordem recomendada daqui para frente

### Sprint 6 — Relatório e limpeza técnica

- Atualizar PR body da Sprint 5 para refletir escopo real.
- Separar ou documentar melhor o que é demo, evento, serviços e premium.
- Limpar rota/lista de proposta se estiver sobrando.
- Garantir CI verde após os últimos commits.

### Sprint 7 — Relatórios profissionais

- Melhorar PDF/print.
- Adicionar status pago/recebido simples.
- Criar cards de histórico do relatório.

### Sprint 8 — Clientes premium

- Saúde do contrato.
- Próxima ação por cliente.
- Histórico de relatórios e pagamentos.

### Sprint 9 — Dashboard operacional

- Widgets principais.
- Serviços próximos.
- Alertas inteligentes.

### Sprint 10 — Segurança/LGPD

- Alterar e-mail.
- Exportar dados.
- Solicitação de exclusão.
- Histórico básico de login.

## 8. Decisão executiva

O HoraCerta está deixando de ser apenas controle de horas e passando a ser um portal de operação para prestadores.

A direção correta é manter o fluxo simples:

Pedido → Serviço → Prévia/Proposta → Execução → Itens → Relatório → Cliente visualiza → Fechamento.

O diferencial premium deve vir de clareza, checklist, comunicação organizada, relatórios profissionais e especialização por tipo de serviço, sem transformar o sistema em algo pesado.
