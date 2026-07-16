# Sprint 19 — Privacidade da prestação de contas

## Objetivo

Endurecer o documento público de prestação de contas sem alterar horas, valores, serviços ou regras de fechamento.

## Problemas encontrados

1. A página pública podia ser armazenada pelo navegador, proxy ou cache intermediário.
2. Não havia instrução explícita para mecanismos de busca não indexarem o documento.
3. O e-mail de login do prestador era usado como contato público quando não havia telefone profissional.
4. A abertura da prestação de contas não registrava a primeira visualização do documento final.
5. O compartilhamento pelo WhatsApp enviava apenas o endereço, sem explicar qual documento estava sendo enviado.
6. Existiam duas PRs concorrentes para a mesma jornada de Serviços, baseadas em branches diferentes.

## Correções

### Cabeçalhos de privacidade

As respostas HTML e PDF passam a usar:

- `Cache-Control: private, no-store, no-cache, max-age=0, must-revalidate`;
- `Pragma: no-cache`;
- `Expires: 0`;
- `X-Robots-Tag: noindex, nofollow, noarchive`;
- `Referrer-Policy: no-referrer`.

A página HTML também possui metatags `robots` e `referrer`.

### Contato profissional

A página pública utiliza somente o telefone cadastrado no perfil profissional relacionado ao contrato. Quando esse telefone não existe, mostra **Não divulgado**.

O e-mail usado para autenticação não é mais publicado automaticamente.

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
- registro da primeira visualização em HTML e PDF;
- bloqueio antes do relatório final;
- isolamento entre prestadores;
- mensagem contextual do WhatsApp.
