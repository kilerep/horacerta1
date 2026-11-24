# Validação manual — Sprint 1

Este roteiro confirma apenas as melhorias da branch `sprint-1-clientes-acabamento`.

## 1. Atualizar a branch no computador

No terminal aberto na pasta do HoraCerta:

```bash
git fetch origin
git switch sprint-1-clientes-acabamento
git pull --ff-only origin sprint-1-clientes-acabamento
```

Não execute merge e não atualize o servidor nesta etapa.

## 2. Rodar os testes focados

No Windows, dentro do ambiente virtual já usado pelo projeto:

```bash
py manage.py test accounts.test_mei_clients services.test_service_request_catalog
```

Resultado esperado: todos os testes aprovados.

## 3. Conferir Meus Clientes

Entre com uma conta de teste de prestador e abra **Meus clientes**.

1. Sem selecionar um cliente por link, a lista deve iniciar recolhida.
2. Clique em **Ver detalhes** de um cliente: apenas aquele card deve abrir.
3. Clique em outro cliente: o primeiro precisa fechar automaticamente.
4. Clique em **Fechar detalhes**: o card deve recolher.
5. Busque parte do nome de um cliente.
6. Teste os filtros: ativos, inativos/encerrados e sem valor por hora.
7. Aplique uma busca que não exista: deve aparecer o estado “Nenhum cliente encontrado”.
8. Limpe os filtros e confirme que todos voltaram.
9. No card, confirme que o texto de próximo passo faz sentido para o contrato.

## 4. Conferir item rápido por código interno no Pedido

Antes, tenha pelo menos um item ativo no Catálogo com código interno.

1. Abra **Serviços → Pedidos**.
2. Abra um pedido existente ou crie um pedido simples e salve-o.
3. Dentro do pedido, em **Itens rápidos**, digite o código interno ou parte do nome do catálogo.
4. Selecione um resultado.
5. Confirme que nome, quantidade, observação e valor estimado foram preenchidos.
6. Clique em **Adicionar item rápido**.
7. Confirme que o item aparece na lista e que pertence apenas ao seu pedido.
8. Transforme o pedido em serviço somente se quiser confirmar que o item foi levado como previsto.

## 5. O que registrar para revisão

Ao encontrar algo estranho, envie uma captura com:

- tela e botão usado;
- o que esperava acontecer;
- o que aconteceu de fato;
- se era no computador ou celular.

Não publicar em produção antes de a Sprint 0 ser liberada, porque a Sprint 1 depende dela.
