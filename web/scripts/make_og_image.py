"""Render web/assets/og-image.png (1200x630) with counts read from web/data.

Run: uv run --with pillow python web/scripts/make_og_image.py
Fonts are system fonts (no network); candidates are tried in order.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WEB = Path(__file__).resolve().parent.parent
OUT = WEB / "assets" / "og-image.png"

BG, AMBER, WHITE, MUTED, RULE = "#0a0b0d", "#f5b02e", "#e8e9eb", "#7d828c", "#2a2d33"

SANS = ["segoeui.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf"]
SANS_BOLD = ["segoeuib.ttf", "NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
MONO = ["consola.ttf", "DejaVuSansMono.ttf"]
MONO_BOLD = ["consolab.ttf", "DejaVuSansMono-Bold.ttf"]


def font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise SystemExit(f"No font found among {names}")


def counts():
    tools = json.loads((WEB / "data/tool_signatures.json").read_text(encoding="utf-8"))
    themes = json.loads((WEB / "data/sources.json").read_text(encoding="utf-8"))
    institutions = [i for t in themes for i in t["institutions"]]
    n_sources = sum(len(i["sources"]) for i in institutions)
    return len(tools), n_sources, len(institutions)


def main():
    n_tools, n_sources, n_inst = counts()
    img = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(img)

    d.text((80, 100), "UNA CAPA DE CONTEXTO PARA DATOS ABIERTOS DE ECUADOR",
           font=font(MONO, 20), fill=AMBER, anchor="lm")
    big = font(SANS_BOLD, 66)
    d.text((80, 198), "Explora datos", font=big, fill=WHITE, anchor="lm")
    d.text((80, 281), "abiertos.", font=big, fill=AMBER, anchor="lm")
    sub = font(SANS, 28)
    d.text((80, 362), "Conecta tu asistente de IA a datasets, trámites,", font=sub, fill=MUTED, anchor="lm")
    d.text((80, 404), "contratos públicos, riesgos y compañías de Ecuador.", font=sub, fill=MUTED, anchor="lm")

    for x, y in [(1100, 50), (1020, 90), (1100, 130)]:
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=AMBER)

    stats = [(str(n_tools), "tools MCP"), (str(n_sources), "fuentes"),
             (str(n_inst), "instituciones"), ("0", "API keys")]
    num_f, lab_f = font(MONO_BOLD, 38), font(MONO, 22)
    x = 80
    for i, (num, label) in enumerate(stats):
        d.text((x, 478), num, font=num_f, fill=AMBER, anchor="lm")
        d.text((x, 522), label, font=lab_f, fill=MUTED, anchor="lm")
        w = max(d.textlength(num, font=num_f), d.textlength(label, font=lab_f))
        x += w + 28
        if i < len(stats) - 1:
            d.line((x, 465, x, 537), fill=RULE, width=2)
            x += 28
    img.save(OUT, optimize=True)
    print(f"wrote {OUT}: tools={n_tools} fuentes={n_sources} instituciones={n_inst}")


if __name__ == "__main__":
    main()
