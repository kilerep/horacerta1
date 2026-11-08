"""Checagem de contraste dos temas (static/css/design_tokens.css), usada pelo teste
accounts/test_theme_contrast.py. Le cada bloco [data-theme="..."], resolve var(...) e
mistura cores com transparencia sobre o fundo do cartao, como o navegador faria."""

import re
from pathlib import Path

from django.conf import settings

TOKENS = Path(settings.BASE_DIR) / "static/css/design_tokens.css"

# (texto, fundo, minimo WCAG). Fundo com alfa e misturado sobre --color-card.
PAIRS = [
    ("--color-text", "--color-bg", 7.0),
    ("--color-text", "--color-card", 4.5),
    ("--color-text", "--surface-soft", 4.5),
    ("--color-text-muted", "--color-card", 4.5),
    ("--color-text-muted", "--color-bg", 4.5),
    ("--color-primary", "--color-card", 4.5),          # links e destaques em texto
    ("--text-inverse", "--color-primary", 4.5),         # texto do botao principal
    ("--text-inverse", "--color-primary-strong", 4.5),
    ("--btn-text", "--btn-bg", 4.5),
    ("--menu-active-text", "--color-card", 4.5),
    ("--badge-solid-text", "--badge-solid-bg", 4.5),
    ("--badge-text", "--badge-bg", 4.5),
    ("--success-text", "--success-bg", 4.5),
    ("--warning-text", "--warning-bg", 4.5),
    ("--danger-text", "--danger-bg", 4.5),
    ("--field-placeholder", "--field-bg", 3.0),
]


def parse_themes():
    css = TOKENS.read_text(encoding="utf-8")
    themes = {}
    for name, body in re.findall(r'\[data-theme="([^"]+)"\]\s*\{(.*?)\n\}', css, flags=re.S):
        themes[name] = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body))
    return themes


def resolve(tokens, value, depth=0):
    value = value.strip()
    match = re.fullmatch(r"var\((--[\w-]+)(?:\s*,\s*(.+))?\)", value)
    if match and depth < 10:
        ref, fallback = match.groups()
        if ref in tokens:
            return resolve(tokens, tokens[ref], depth + 1)
        return resolve(tokens, fallback or "", depth + 1)
    return value


def to_rgba(value):
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    match = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)", value)
    if match:
        r, g, b, a = match.groups()
        return float(r), float(g), float(b), float(a) if a is not None else 1.0
    return None


def blend(top, bottom):
    a = top[3]
    return tuple(top[i] * a + bottom[i] * (1 - a) for i in range(3)) + (1.0,)


def luminance(rgb):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def report():
    """[(tema, texto, fundo, razao, minimo)] dos pares abaixo do minimo."""
    failures = []
    for theme, tokens in parse_themes().items():
        card = to_rgba(resolve(tokens, tokens.get("--color-card", "#ffffff"))) or (255, 255, 255, 1.0)
        for fg_name, bg_name, minimum in PAIRS:
            if fg_name not in tokens or bg_name not in tokens:
                continue
            fg = to_rgba(resolve(tokens, tokens[fg_name]))
            bg = to_rgba(resolve(tokens, tokens[bg_name]))
            if fg is None or bg is None:
                continue  # gradiente ou valor nao comparavel
            bg = blend(bg, card) if bg[3] < 1 else bg
            fg = blend(fg, bg) if fg[3] < 1 else fg
            ratio = contrast(fg, bg)
            if ratio < minimum:
                failures.append((theme, fg_name, bg_name, round(ratio, 2), minimum))
        # Botao principal usa gradiente: o texto precisa ler bem sobre cada parada de cor.
        gradient, text = tokens.get("--gradient-button"), tokens.get("--text-inverse")
        if gradient and text:
            fg = to_rgba(resolve(tokens, text))
            for stop in re.findall(r"var\(--[\w-]+\)|#[0-9a-fA-F]{3,6}\b", gradient):
                bg = to_rgba(resolve(tokens, stop))
                if fg and bg:
                    ratio = contrast(fg, bg)
                    if ratio < 4.5:
                        failures.append((theme, "--text-inverse", f"--gradient-button {stop}", round(ratio, 2), 4.5))
    return failures
