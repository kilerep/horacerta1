# HoraCerta — Cadastro e equipe da empresa contratante

## Entrega desta Sprint

A empresa contratante passa a ter um ambiente próprio em `/contratante/` para:

- cadastrar a organização;
- criar automaticamente o primeiro administrador;
- abrir um painel inicial;
- consultar membros;
- convidar contas empresariais existentes;
- aceitar convites recebidos;
- registrar os eventos principais em auditoria.

## Regras de acesso

- somente contas do perfil **Empresa contratante** acessam a área;
- o primeiro usuário da organização recebe o papel **Administrador**;
- somente administradores convidam membros;
- o convite é vinculado ao e-mail exato da conta;
- cada usuário possui apenas um vínculo por organização;
- uma empresa não acessa o painel de outra;
- contas de prestador não podem ser convidadas como membros empresariais.

## Papéis

- **Administrador:** gerencia empresa e membros;
- **Gestor de serviços:** acompanha a operação;
- **Financeiro:** acompanha horas, fechamentos e valores compartilhados;
- **Consulta:** acesso somente para leitura.

## Limite atual

Nesta etapa, a pessoa convidada precisa possuir uma conta de Empresa contratante. O envio automático de e-mail e o cadastro por link serão tratados em uma Sprint posterior.

A área ainda não exibe pedidos, serviços, horas ou relatórios. Esses módulos serão conectados somente após a validação dos vínculos e das permissões.

## Validação manual

1. Acessar `/contratante/` com conta empresarial sem organização.
2. Cadastrar uma empresa.
3. Conferir o primeiro administrador.
4. Abrir Membros.
5. Convidar outra conta empresarial.
6. Entrar com a conta convidada.
7. Aceitar o convite.
8. Confirmar que a conta convidada abre apenas a organização correspondente.
9. Confirmar que uma conta de prestador recebe acesso negado.
