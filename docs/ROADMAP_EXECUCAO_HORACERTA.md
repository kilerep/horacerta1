# Roadmap de execução — HoraCerta

Este documento transforma a análise interna do produto em blocos executáveis, com escopo controlado e critérios mínimos de qualidade.

## Regra de entrega

Nenhuma melhoria é considerada pronta sem:

1. revisão das regras de acesso e dados envolvidos;
2. teste automatizado das regras novas ou alteradas;
3. CI aprovada (`check`, migrations, testes, estáticos e `check --deploy`);
4. validação visual curta em computador ou celular quando a mudança afetar interface;
5. revisão antes de merge ou deploy.

`main`, produção, RDS, `.env` e dados reais ficam fora de qualquer alteração automática.

---

## Bloco 0 — Estabilização da base

### Objetivo

Manter a branch verde antes de ampliar o produto.

### Itens

- Corrigir expectativas de testes que ficaram desatualizadas após ajustes de texto da Sprint 1.
- Manter saída dos testes como artefato da CI para diagnóstico de futuras falhas.
- Evitar migrations não planejadas e manter `makemigrations --check` obrigatório.
- Registrar o roteiro de validação manual de cada Sprint.

### Critérios de aceite

- CI aprovada sem testes ignorados.
- Não reduzir cobertura apenas para obter aprovação.
- PR mantém base explícita e escopo descrito.

---

## Bloco 1 — Clientes e fechamento

### Objetivo

Deixar a carteira de clientes rápida de entender e segura para uso diário.

### Itens

- Accordion com apenas um cliente aberto por vez.
- Busca e filtros de clientes.
- Estado vazio de busca e mensagens de próximo passo.
- Indicador de cliente sem valor/hora, contrato encerrado e fechamento personalizado.
- Ação rápida para abrir histórico, relatórios e serviço do cliente.
- Evolução posterior: alerta de contrato próximo do vencimento e histórico de recebimentos.

### Critérios de aceite

- Um prestador só visualiza contratos, relatórios e ações da própria conta.
- Seleção de cliente por URL não expõe contratos de outros usuários.
- Listas continuam utilizáveis em telas pequenas.

---

## Bloco 2 — Pedidos, serviços e catálogo

### Objetivo

Transformar uma solicitação em serviço executável sem perda de contexto.

### Itens

- Buscar itens rápidos pelo código interno ou nome do catálogo.
- Preencher nome, quantidade, observação e valor sugerido ao selecionar item.
- Timeline visual do serviço: rascunho, planejado, em execução, finalizado e relatório enviado.
- Checklist de execução e progresso de itens.
- Histórico de alteração de status para auditoria interna.
- Estrutura futura para anexos/fotos, sem publicar arquivos sem regra de privacidade e retenção.

### Critérios de aceite

- Catálogo é sempre isolado por prestador.
- Pedido de outro usuário responde 404 e nunca revela itens.
- Itens de pedido convertidos para serviço mantêm quantidade e valores registrados.

---

## Bloco 3 — Home inteligente e notificações úteis

### Objetivo

Transformar o painel em uma tela de decisão diária, não apenas uma lista de números.

### Itens

- Destaque para horas do dia, valor estimado, registros incompletos, clientes sem valor/hora e serviços de hoje.
- Atalhos para registrar horário, abrir serviço e concluir pendência.
- Alertas de dia incompleto, fechamento próximo, relatório visualizado e contrato sem valor/hora.
- Separar avisos informativos de ações urgentes.
- Preparar preferências de notificação antes de implementar push, e-mail ou WhatsApp automático.

### Critérios de aceite

- Alertas não podem duplicar mensagens equivalentes.
- Cada alerta deve ter uma ação clara ou explicar por que não exige ação.
- Não prometer envio automático sem infraestrutura real configurada.

---

## Bloco 4 — Relatórios e acompanhamento financeiro

### Objetivo

Dar ao prestador uma visão confiável de horas, valores, visualização e recebimento.

### Itens

- Melhorar leitura do relatório no celular e no PDF.
- Consolidar status: gerado, enviado, visualizado e recebido.
- Lembretes internos para relatório não visualizado e pagamento pendente.
- Comparativo simples por cliente e período.
- Evolução posterior: modelos de relatório, versões e assinatura somente após análise jurídica e técnica.

### Critérios de aceite

- Link público não expõe relatórios de outro cliente.
- Alteração de recebido/pendente registra corretamente data e status.
- PDF e interface representam os mesmos totais.

---

## Bloco 5 — Segurança, conta e LGPD

### Objetivo

Preparar o produto para operação real sem promessas jurídicas indevidas.

### Itens

- Fluxo seguro de redefinição de senha e análise do fluxo de mudança de senha autenticada.
- Planejar mudança de e-mail com confirmação e reautenticação.
- Inventário de dados pessoais, base de retenção, exportação e exclusão de conta.
- Política de privacidade e termos revisados antes de divulgação pública.
- Histórico de atividades sensíveis para admin interno.
- Avaliar 2FA em fase posterior, com desenho de recuperação de conta.

### Critérios de aceite

- Nunca armazenar senha em código, commits ou logs.
- Mudanças sensíveis exigem autenticação e auditoria.
- Recursos de LGPD só podem ser apresentados como conformes após revisão jurídica apropriada.

---

## Bloco 6 — PWA e operação offline

### Objetivo

Ter uma experiência instalável e resiliente, sem declarar offline completo antes de validar a sincronização.

### Itens

- Manter manifest, service worker e rota offline verificáveis por teste.
- Definir claramente o que funciona offline e o que depende de conexão.
- Não persistir batidas offline até existir fila, resolução de conflito e confirmação de sincronização.
- Preparar feedback visual de conexão e estado de sincronização.

### Critérios de aceite

- Manifest, service worker e página offline respondem corretamente.
- Nenhum registro é apresentado como salvo antes de confirmação do servidor.

---

## Ordem recomendada

1. Base e CI verde.
2. Conclusão da Sprint 1: Clientes e Catálogo/Pedidos.
3. Home inteligente e notificações internas.
4. Relatórios e acompanhamentos.
5. Segurança de conta e preparação LGPD.
6. Serviços avançados, anexos e integrações externas.

## Fora do escopo automático

- Merge em `main`.
- Deploy ou alteração no servidor.
- Rotação de credenciais RDS e atualização de `.env`.
- Exclusão ou alteração de dados reais.
- Integrações pagas, WhatsApp automatizado, nota fiscal, assinatura digital ou 2FA sem requisitos aprovados.
