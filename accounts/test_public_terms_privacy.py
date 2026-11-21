from django.test import SimpleTestCase
from django.urls import reverse


class PublicTermsPageTests(SimpleTestCase):
    """Os termos antigos descreviam o modelo "empresa cadastra o
    profissional" que o produto abandonou no pivo MEI-first (mesmo
    problema ja corrigido na Central de Ajuda). Trava a versao corrigida.
    """

    def test_terms_page_describes_current_signup_model_not_the_outdated_one(self):
        response = self.client.get(reverse("terms"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "A empresa e responsavel pelo cadastro de profissionais")
        self.assertNotContains(response, "A empresa é responsável pelo cadastro de profissionais")
        self.assertContains(response, "prestador (MEI/autônomo)")

    def test_terms_page_has_a_real_contact_channel(self):
        response = self.client.get(reverse("terms"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mailto:kilerepp@gmail.com")

    def test_terms_page_does_not_overpromise_availability(self):
        response = self.client.get(reverse("terms"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não garantimos disponibilidade ininterrupta")


class PublicPrivacyPageTests(SimpleTestCase):
    def test_privacy_page_has_a_real_contact_channel(self):
        response = self.client.get(reverse("privacy"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mailto:kilerepp@gmail.com")
        self.assertNotContains(response, "canais oficiais informados pela empresa responsavel")
        self.assertNotContains(response, "canais oficiais informados pela empresa responsável")

    def test_privacy_page_frames_export_and_deletion_as_request_based_not_self_service(self):
        response = self.client.get(reverse("privacy"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mediante pedido pelo canal de contato")

    def test_privacy_page_mentions_security_telemetry_it_actually_collects(self):
        response = self.client.get(reverse("privacy"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "endereço IP")
