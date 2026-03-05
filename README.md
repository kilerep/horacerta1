# HoraCerta

## Configuracao de e-mail (reset de senha)

O envio de e-mail usa a variavel `USE_CONSOLE_EMAIL`.

- Se `USE_CONSOLE_EMAIL=True`, usa backend de console.
- Se `USE_CONSOLE_EMAIL=False`, usa SMTP real.
- Se `USE_CONSOLE_EMAIL` nao existir no `.env`, o sistema usa o valor de `DEBUG` como padrao.

Assim, mesmo com `DEBUG=True`, basta definir `USE_CONSOLE_EMAIL=False` para forcar SMTP.

## Gmail: como gerar Senha de App (resumo)

1. Entre na Conta Google e ative a verificacao em duas etapas.
2. Acesse Seguranca > Senhas de app.
3. Gere uma senha para "Mail".
4. Use essa senha gerada em `EMAIL_HOST_PASSWORD`.

Nao use a senha normal da conta Google no Django.

## .env (campos principais)

```env
DEBUG=True
USE_CONSOLE_EMAIL=False
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=seu_email@gmail.com
EMAIL_HOST_PASSWORD=sua_senha_de_app
DEFAULT_FROM_EMAIL=HoraCerta <seu_email@gmail.com>
```

- `EMAIL_HOST_USER`: seu e-mail Gmail completo.
- `EMAIL_HOST_PASSWORD`: Senha de App gerada no Google.

## Testar envio por comando

```bash
python manage.py test_email destino@email.com
```

- Se funcionar, o comando imprime: `OK`
- Se falhar, imprime o erro completo (traceback).
