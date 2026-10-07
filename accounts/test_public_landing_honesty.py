import re

from django.test import SimpleTestCase
from django.urls import reverse


class PublicLandingHonestyTests(SimpleTestCase):
    """A landing page tinha varias afirmacoes falsas/exageradas (avaliacao
    fabricada, conformidade legal nao revisada, integracoes inexistentes,
    "comunidade ativa" que nao existe). Trava aqui pra essas nao voltarem.
    """

    def test_landing_page_has_no_fabricated_rating_or_false_compliance_claims(self):
        response = self.client.get(reverse("landing"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "aggregateRating")
        self.assertNotContains(response, "ratingValue")
        self.assertNotContains(response, "Conforme CLT")
        self.assertNotContains(response, "NFS-e Integrado")
        self.assertNotContains(response, "Comunidade ativa")
        self.assertNotContains(response, "Webmania")
        self.assertNotContains(response, "NotaAS")
        self.assertNotContains(response, "instagram.com/horacerta")
        self.assertNotContains(response, "facebook.com/horacerta")
        body = response.content.decode()
        for phrase in ("ponta a ponta", "planos profissionais"):
            self.assertNotRegex(body, re.compile(re.escape(phrase), re.IGNORECASE))

    def test_landing_page_faq_reflects_real_product_state(self):
        response = self.client.get(reverse("landing"), secure=True)

        self.assertEqual(response.status_code, 200)
        # Nota fiscal: nunca prometer emissao ou integracao que nao existe.
        self.assertNotContains(response, "HoraCerta não emite nota fiscal diretamente")
        self.assertContains(response, "continua sendo responsabilidade do prestador")
        # Exportacao/exclusao de dados (Bloco 5) ainda nao existe - nao prometer.
        self.assertNotContains(response, "pode exportar seus dados a qualquer momento")
        self.assertContains(response, "em desenvolvimento")
        # Troca de senha ja existe hoje; nao dizer que "sera implementada em breve".
        self.assertContains(response, "já está disponível em Meu Perfil")
        # Offline: nunca declarar "completamente offline" antes de validar sincronizacao.
        self.assertContains(response, "exige conexão para confirmar a gravação")
