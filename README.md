# HoraCerta

## Fluxo "Esqueci minha senha": configuracao de e-mail

O projeto agora usa `USE_CONSOLE_EMAIL` para alternar entre envio em console e SMTP real, sem depender diretamente de `DEBUG`.

### Variaveis de ambiente

- `USE_CONSOLE_EMAIL`: `True` usa backend de console; `False` usa SMTP.
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `DEFAULT_FROM_EMAIL`

## Como testar em console (dev)

1. Configure no `.env`:

```env
DEBUG=True
USE_CONSOLE_EMAIL=True
DEFAULT_FROM_EMAIL=HoraCerta <no-reply@horacerta.local>
```

2. Execute o fluxo de "Esqueci minha senha" na tela de login.
3. O conteudo do e-mail (incluindo link de reset) sera exibido no terminal do servidor Django.

Opcional: teste direto por comando:

```bash
python manage.py test_email seu_email@exemplo.com
```

## Como testar com SMTP real (dev/prod)

1. Configure no `.env`:

```env
DEBUG=False
USE_CONSOLE_EMAIL=False
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=seu_email@gmail.com
EMAIL_HOST_PASSWORD=sua_senha_de_app
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=HoraCerta <seu_email@gmail.com>
```

2. Envie um teste manual:

```bash
python manage.py test_email destino@exemplo.com --subject "Teste SMTP HoraCerta"
```

3. Se houver falha de autenticacao/conexao, o comando retorna erro detalhado SMTP no terminal.

### Gmail (App Password)

1. Ative verificacao em duas etapas na conta Google.
2. Gere uma App Password para "Mail".
3. Use essa senha em `EMAIL_HOST_PASSWORD` (nao use a senha normal da conta).

## Exemplo completo de `.env`

```env
SECRET_KEY=django-insecure-troque-esta-chave-em-producao
DEBUG=True
APP_BASE_URL=http://localhost:8000
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

USE_CONSOLE_EMAIL=True
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=seu_email@gmail.com
EMAIL_HOST_PASSWORD=sua_senha_de_app
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=HoraCerta <no-reply@horacerta.com>
```
