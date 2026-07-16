from django.core.management.base import BaseCommand
from django.utils import timezone

from editorial.models import EditorialArticle, EditorialCategory


STARTER_ARTICLES = [
    {
        "category": "gestao",
        "content_type": EditorialArticle.ContentType.GUIDE,
        "title": "Como organizar um pedido de serviço antes de começar",
        "summary": "Um roteiro simples para registrar cliente, escopo, local, prazo e próximos passos sem transformar a primeira conversa em burocracia.",
        "body": """Um pedido de serviço bem registrado reduz retrabalho e evita que informações importantes fiquem espalhadas em mensagens, áudios e anotações.

Comece pelo básico: quem solicitou, qual é a necessidade, onde o atendimento será realizado e qual data foi mencionada. Neste momento, não é necessário inventar preço, material ou prazo que ainda não foram confirmados.

Depois, transforme a conversa em um escopo inicial. Registre o que o cliente espera, quais informações ainda faltam e qual será o próximo passo: visita técnica, envio de proposta, cotação de itens ou início do serviço.

Quando o serviço estiver combinado, revise endereço, agenda, forma de cobrança, materiais previstos e responsabilidades. O pedido deixa de ser apenas uma mensagem e passa a funcionar como ponto de partida do histórico profissional.

No HoraCerta, o fluxo recomendado é: registrar o pedido, confirmar os detalhes, transformar em serviço, preparar a folha ou proposta, registrar a execução e finalizar com relatório.""",
        "is_featured": True,
    },
    {
        "category": "financas",
        "content_type": EditorialArticle.ContentType.GUIDE,
        "title": "Prestação de contas: separe horas, materiais e despesas",
        "summary": "Apresente ao cliente o que foi trabalhado, o que foi consumido e quais despesas fizeram parte do atendimento.",
        "body": """Uma prestação de contas clara não precisa ser complicada. O primeiro passo é separar três grupos: horas e atividades, materiais utilizados e despesas relacionadas ao atendimento.

Horas devem mostrar data, início, fim e uma descrição breve do que foi realizado. Materiais devem indicar quantidade, valor e situação de uso. Despesas como pedágio, estacionamento, combustível ou alimentação precisam estar ligadas ao serviço correto.

Evite misturar estimativa com valor realizado. A proposta apresenta o que estava previsto; o relatório final apresenta o que realmente aconteceu. Quando houver diferença, explique o motivo de forma objetiva.

Com essa separação, o cliente consegue conferir o documento e o prestador mantém um histórico útil para novos orçamentos, visitas futuras e análise de custos.""",
        "is_featured": True,
    },
    {
        "category": "tecnologia",
        "content_type": EditorialArticle.ContentType.ANALYSIS,
        "title": "Onde a inteligência artificial pode ajudar o prestador",
        "summary": "A IA pode reduzir trabalho administrativo, mas preços, segurança, diagnóstico e decisões técnicas continuam exigindo revisão humana.",
        "body": """A inteligência artificial é mais útil quando assume tarefas repetitivas e de baixo risco. Exemplos incluem organizar anotações, criar uma primeira versão de mensagem, resumir um pedido, sugerir um checklist e estruturar um relatório.

Ela também pode ajudar a localizar informações em históricos, comparar previsto e realizado e preparar perguntas que ainda precisam ser respondidas antes do serviço.

O limite é importante: a IA não deve inventar preço, confirmar uma obrigação legal, substituir uma avaliação técnica ou decidir sozinha sobre segurança. Todo conteúdo gerado precisa ser revisado pelo prestador responsável.

A melhor aplicação é simples: usar a tecnologia como assistente de organização, sem entregar a ela decisões que afetam o cliente, o custo ou a execução do trabalho.""",
        "is_featured": True,
    },
    {
        "category": "marketing",
        "content_type": EditorialArticle.ContentType.GUIDE,
        "title": "O que revisar antes de enviar uma proposta de serviço",
        "summary": "Cliente, escopo, prazo, itens, cobrança e limites precisam estar claros antes do compartilhamento.",
        "body": """Antes de enviar uma proposta, confira se o documento responde às dúvidas principais do cliente.

Identifique corretamente as partes, descreva o serviço em linguagem simples, informe local e previsão de atendimento e separe mão de obra de materiais quando isso fizer sentido.

Registre também o que não está incluído, quais informações dependem de confirmação e como alterações serão tratadas. Uma proposta profissional não precisa parecer um contrato complexo, mas deve reduzir interpretações diferentes sobre o combinado.

Por fim, revise números, datas, telefone e endereço. O documento deve ser compreensível no celular e indicar claramente qual é o próximo passo: confirmar recebimento, solicitar alteração ou continuar a negociação.""",
        "is_featured": False,
    },
]


class Command(BaseCommand):
    help = "Cria conteúdos editoriais iniciais do HoraCerta sem duplicar publicações."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for item in STARTER_ARTICLES:
            category = EditorialCategory.objects.get(slug=item["category"])
            defaults = {
                "category": category,
                "content_type": item["content_type"],
                "summary": item["summary"],
                "body": item["body"],
                "author_name": "Equipe HoraCerta",
                "status": EditorialArticle.Status.PUBLISHED,
                "is_featured": item["is_featured"],
                "published_at": timezone.now(),
            }
            article, was_created = EditorialArticle.objects.update_or_create(
                title=item["title"],
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Conteúdos editoriais: {created} criados, {updated} atualizados."))
