# Validação local segura — HoraCerta

Este roteiro serve para testar o HoraCerta no computador antes de qualquer integração ou publicação.

## Limite de segurança

Use este roteiro somente no ambiente local de desenvolvimento.

- Confirme que `DEBUG=True`.
- Use banco local de desenvolvimento.
- Não execute comandos de criação de demonstração no servidor.
- Não reutilize senha real em conta de teste.
- Não faça merge ou deploy apenas porque os testes locais passaram.

O comando de demonstração falha quando `DEBUG=False` justamente para evitar criação de dados de teste em produção.

## 1. Preparar a branch de demonstração

```bash
git fetch origin
git switch sprint-5-service-timeline
git pull --ff-only origin sprint-5-service-timeline
py manage.py migrate
py manage.py test accounts.test_local_demo_user_command
```

Resultado esperado: testes aprovados.

## 2. Criar a conta local de demonstração

Escolha uma senha temporária que não seja usada em nenhum outro lugar.

```bash
py manage.py create_local_demo_user --email demo.prestador@horacerta.test --password "troque-esta-senha"
```

O comando cria ou atualiza:

- prestador de demonstração;
- empresa cliente de demonstração;
- vínculo ativo;
- contrato com valor/hora.

Ele pode ser executado novamente sem duplicar esse ambiente básico.

## 3. Iniciar o projeto localmente

```bash
py manage.py runserver
```

Acesse o endereço exibido no terminal e entre com o e-mail usado no comando anterior e a senha temporária escolhida.

## 4. Fluxos para validar

### Meu Resumo e Horários

1. Abra **Meu Resumo**.
2. Confira se os totais iniciam sem erro.
3. Abra **Registrar horário**.
4. Selecione o cliente de demonstração e registre uma jornada de teste.
5. Retorne ao resumo e confira o reflexo nos totais.
6. Abra **Histórico** e confirme que o registro está no cliente correto.

### Clientes

1. Abra **Meus Clientes**.
2. Confira o contrato e o valor/hora.
3. Teste abrir e fechar detalhes.
4. Teste busca e filtros.
5. Verifique a ação de editar contrato e o fechamento rápido.

### Pedidos e Serviços

1. Abra **Serviços → Pedidos → Novo pedido**.
2. Crie um item de catálogo com um código interno, quando necessário.
3. Pesquise pelo código interno em **Itens rápidos**.
4. Confirme o preenchimento de nome, quantidade, observação e valor sugerido.
5. Salve o pedido e, em um segundo teste, transforme-o em serviço.
6. No serviço, valide dados, períodos trabalhados, itens previstos/usados e relatório final.

### Relatórios

1. Gere um relatório de horas ou de serviço em dados de demonstração.
2. Confira cliente, período, horas e valor antes de copiar ou abrir o link.
3. Teste a visualização pública em uma janela anônima apenas com dados de demonstração.
4. Não use dados reais para validar um link público.

### Segurança da conta

1. Abra **Meu Perfil → Segurança da conta**.
2. Teste a tela de troca de senha usando a senha temporária.
3. Teste primeiro com senha antiga incorreta.
4. Depois troque para outra senha temporária e confirme que a sessão atual continua ativa.

## 5. Registrar qualquer problema

Ao encontrar comportamento estranho, anote:

- tela e ação executada;
- resultado esperado;
- resultado observado;
- navegador e tamanho de tela;
- captura de tela, quando possível.

## 6. Antes de pensar em publicação

A versão candidata precisa passar por:

```bash
py manage.py test
py manage.py collectstatic --noinput
py manage.py check --deploy
```

E deve permanecer bloqueada até a senha do RDS ser rotacionada e a configuração do servidor ser revisada manualmente.
