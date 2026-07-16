# Estado público observado — 15/07/2026

## Disponibilidade

A página pública `https://horacertagestao.com.br/` está respondendo e exibindo a landing do HoraCerta.

Isso confirma disponibilidade da camada pública, mas não identifica a branch ou o commit ativo no EC2. O commit precisa ser confirmado no servidor com:

```bash
cd ~/horacerta
git branch --show-current
git rev-parse HEAD
```

## Posicionamento atualmente publicado

A landing observada apresenta o HoraCerta principalmente como:

- gestão de horas entre empresa e MEI;
- empresa cadastra o MEI;
- profissional registra horários;
- empresa acompanha em tempo real;
- apoio para RH, operação e financeiro.

Esse posicionamento representa o produto histórico empresa-first e não comunica o escopo mais recente do portal para prestadores de serviço, que inclui clientes, pedidos, serviços, propostas, folhas profissionais, materiais, execução e relatórios.

## Consequência para a próxima publicação

A release candidata contém uma landing revisada e uma nova área de empresa contratante. Antes de publicar, decidir qual posicionamento é oficial:

1. **Portal amplo para prestadores e empresas contratantes** — direção atual do produto e deste relatório; ou
2. **Gestão de horas empresa–MEI** — posicionamento da landing pública observada.

A recomendação é o primeiro posicionamento, sem apagar o módulo de horas. O controle de horas deve permanecer como um dos módulos centrais do portal, não como a definição completa do produto.

## Validação após a publicação

Após atualizar o servidor, conferir:

```bash
curl -sS -o /dev/null -w "landing: %{http_code}\n" https://horacertagestao.com.br/
curl -sS -o /dev/null -w "health: %{http_code}\n" https://horacertagestao.com.br/health/
curl -sS https://horacertagestao.com.br/health/
```

Também revisar no navegador:

- título e descrição da landing;
- botões de entrada e cadastro;
- ausência de promessas não implementadas;
- clareza entre Prestador de serviço e Empresa contratante;
- visual no computador e celular.
