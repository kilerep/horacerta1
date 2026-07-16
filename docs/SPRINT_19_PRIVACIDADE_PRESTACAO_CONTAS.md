# Sprint 19 — Privacidade da prestação de contas

## Objetivo

Endurecer o documento público de prestação de contas sem alterar horas, valores, serviços ou regras de fechamento.

## Problemas encontrados

1. A página pública podia ser armazenada pelo navegador, proxy ou cache intermediário.
2. O service worker armazenava navegações e imagens dinâmicas, podendo manter relatórios, documentos compartilhados ou arquivos de `media/` no dispositivo.
3. Não havia instrução explícita para mecanismos de busca não indexarem o documento.
4. O e-mail de login podia aparecer como nome ou contato do prestador.
5. O campo legado `Employee.phone` não é uma fonte pública confiável: em alguns cadastros criados a partir de cliente avulso, ele pode conter o telefone do próprio cliente.
6. A abertura da prestação de contas não registrava a primeira visualização do documento final.
7. O compartilhamento pelo WhatsApp enviava apenas o endereço, sem explicar qual documento estava sendo enviado.
8. Existiam duas PRs concorrentes para a mesma jornada de Serviços, baseadas em branches diferentes.

## Correções

### Cabeçalhos de privacidade

As respostas HTML e PDF passam a usar:

- `Cache-Control: private, no-store, no-cache, max-age=0, must-revalidate`;
- `Pragma: no-cache`;
- `Expires: 0`;
- `X-Robots-Tag: noindex, nofollow, noarchive`;
- `Referrer-Policy: no-referrer`.

A página HTML também possui metatags `robots` e `referrer`.

### Cache seguro no PWA

O service worker foi atualizado para `hc-sw-v4`. Ao ativar, ele remove os caches antigos do HoraCerta, incluindo o cache dinâmico anterior.

Nunca são armazenados pelo service worker:

- área do prestador (`/me/`);
- portal da empresa (`/contratante/`);
- administração e APIs;
- links públicos de serviços, propostas e relatórios (`/servicos/`);
- login, logout e recuperação de senha;
- arquivos enviados em `/media/`;
- respostas marcadas como `private` ou `no-store`.

Somente arquivos localizados em `/static/` podem usar a estratégia de cache de assets. Rotas sensíveis passam a operar em modo somente rede e mostram apenas a página offline genérica quando não houver conexão.

### Identidade pública do prestador

A página pública usa o nome profissional relacionado ao contrato somente quando ele não se parece com um identificador de login. Na ausência de um nome seguro, apresenta **Prestador de serviço**.

O documento público não mostra automaticamente:

- e-mail de autenticação;
- nome de usuário em formato de e-mail;
- telefone armazenado no perfil legado `Employee`.

Enquanto não existir um campo específico de contato profissional, a página apresenta **Não divulgado**. Isso evita publicar por engano o telefone do próprio cliente.

### Primeira visualização

A abertura da página pública ou do PDF registra `public_report_first_viewed_at` quando ainda não houver visualização registrada. A atualização é condicional para evitar sobrescrever a data original em acessos simultâneos.

### Compartilhamento

O botão do WhatsApp envia uma mensagem contextual:

> Olá, segue a prestação de contas do serviço [título]: [link]

### Organização do repositório

A PR duplicada baseada na biblioteca antiga de modelos foi encerrada. A implementação preservada é a PR da jornada guiada baseada na release candidata de 15/07.

## Segurança preservada

- link público continua disponível somente em serviço com status `REPORT_SENT`;
- outro prestador recebe 404 nas rotas internas;
- token público não é exposto em logs ou mensagens de erro;
- nenhum dado, migration ou preço foi alterado;
- não há GPS, rastreamento em segundo plano ou promessa fiscal/jurídica.

## Validação automatizada

Os testes cobrem:

- cabeçalhos de cache, indexação e referência;
- ausência do e-mail de login na página pública;
- ausência de telefone legado na página e no PDF públicos;
- serviço avulso sem nome profissional explícito;
- registro da primeira visualização em HTML e PDF;
- bloqueio antes do relatório final;
- isolamento entre prestadores;
- mensagem contextual do WhatsApp;
- versão nova do service worker;
- exclusão de rotas e mídia privadas do cache PWA;
- respeito a `private` e `no-store`.
