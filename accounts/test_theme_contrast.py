from django.test import SimpleTestCase

from accounts.theme_contrast import parse_themes, report


class ThemeContrastTests(SimpleTestCase):
    """Todo tema precisa manter texto legivel (WCAG AA) em fundo, cartao, botao e etiquetas."""

    def test_all_themes_are_parsed(self):
        themes = parse_themes()

        for name in ("graphite-premium", "professional-neutral", "brazil-corporate",
                     "claro-operacional", "rubro-professional", "areia-terracota", "oceano-noturno"):
            self.assertIn(name, themes)
            self.assertIn("--color-primary", themes[name])

    def test_no_contrast_failures(self):
        self.assertEqual(report(), [])
