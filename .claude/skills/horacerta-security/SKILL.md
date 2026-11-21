---
name: horacerta-security
description: Use for periodic security/LGPD audits of HoraCerta, before shipping anything touching auth/session/proxy/IP handling, or before adding a feature that collects new personal data — checklist covering django-axes, HTTPS/CSRF, secrets, admin surface, dependency CVEs, and LGPD handling for the MEI/prestador data model.
---

# HoraCerta — Segurança e conformidade (Bloco 5 do roadmap)

Departamento: **Segurança/Compliance**. Ver `docs/ROADMAP_EXECUCAO_HORACERTA.md` (Bloco 5) —
objetivo é "preparar o produto para operação real sem promessas jurídicas indevidas".

## Checklist técnico

**Autenticação / força bruta**
- `django-axes` está ativo (`accounts/axes_lockout.py`, bloco `AXES_*` em `config/settings.py`)
  e cobre tanto `/login/` quanto `/admin/login/` (via `AUTHENTICATION_BACKENDS`, não só a view).
- `AXES_IPWARE_PROXY_COUNT` precisa bater com o número real de proxies na frente da aplicação
  (hoje: 1, o nginx local). Se a infra ganhar um CDN/load balancer extra na frente do nginx,
  esse número tem que subir — senão um `X-Forwarded-For` forjado volta a furar o rate limit.
- `AXES_LOCKOUT_PARAMETERS` deve continuar como lista aninhada (combinação IP+usuário), não
  lista plana (vira OR e bloqueia usuários legítimos pelo IP de terceiros).

**Transporte / cabeçalhos**
- `SECURE_SSL_REDIRECT=True` quando `DEBUG=False` (já é automático em `config/settings.py`).
- `CSRF_TRUSTED_ORIGINS` e `ALLOWED_HOSTS` batendo exatamente com os domínios reais em produção
  (ver `.env` do servidor, não o `.env.example`).

**Segredos**
- `SECRET_KEY`, `EMAIL_HOST_PASSWORD`, `DATABASE_URL` só existem em `.env` no servidor — nunca
  em commit, patch, log ou documento em `Claude outputs/` ou `docs/`.
- Se algum segredo já vazou no histórico do git (aconteceu antes, citado em
  `docs/HORACERTA_RELATORIO_INTERNO_STATUS_E_ROADMAP.md`), a correção é **rotacionar a
  credencial real**, não só remover o arquivo — reescrever histórico não invalida uma senha já
  exposta.

**Superfície admin**
- `ADMIN_URL_PATH` no `.env` de produção deve estar definido para algo não óbvio, não o padrão
  `admin/`.

**Dependências**
- `pip list --outdated` e, se disponível, `pip-audit` antes de qualquer sprint de segurança.
  `requirements.txt` é curto hoje — checar manualmente é viável.

## LGPD — dados pessoais tratados pelo sistema

Campos hoje coletados por vínculo/contrato (`accounts` — nome completo, CPF, telefone,
endereço, foto de perfil) são **por contrato**, não um perfil único — isso já é um ponto a favor
de minimização de dados (um cliente não vê dados cadastrados para outro). Antes de qualquer
feature nova que colete dado pessoal adicional (ex.: fotos de serviço, dados bancários,
assinatura):

- [ ] Documentar: que dado, para qual finalidade, base legal, prazo de retenção, quem acessa.
- [ ] Confirmar isolamento por prestador/contrato (mesmo padrão já usado em `mei_profile.html`).
- [ ] Definir o que pode aparecer em link público (portal do cliente) e o que não pode.
- [ ] Não apresentar nenhum recurso como "conforme LGPD" sem revisão jurídica real — o próprio
  roadmap já veta essa promessa (Bloco 5, critérios de aceite).

Pendências already tracked no roadmap (não implementar sem pedido explícito, só sinalizar
quando relevante): exportação de dados do usuário, solicitação de exclusão de conta, logout de
todas as sessões após troca de senha, histórico de login, 2FA.

## Fora de escopo hoje (decisão deliberada, não esquecimento)

HoraCerta **não** se posiciona como registrador oficial de ponto eletrônico CLT (Portaria
671/2021 do MTE) — isso exigiria REP-P registrado no INPI e recibos assinados com certificado
ICP-Brasil (Lei 14.063/2020), além de disponibilizar cada comprovante por pelo menos 48h. O
produto atual é gestão de horas/contratos de prestador MEI multi-cliente, não substituto de
ponto eletrônico obrigatório de empregador CLT com >20 funcionários. Se o usuário decidir migrar
para esse segmento no futuro, tratar como decisão estratégica separada (ver [[horacerta-product]])
antes de qualquer implementação — não assumir isso implicitamente.

## Quando rodar este skill

- Antes de publicizar o sistema para o público (marco "sistema disponível para pessoas usarem").
- Depois de qualquer mudança em `config/settings.py`, `accounts/axes_lockout.py`, nginx, ou
  topologia de rede (novo proxy/CDN).
- Antes de adicionar upload de arquivo, dado bancário ou qualquer dado sensível novo.
