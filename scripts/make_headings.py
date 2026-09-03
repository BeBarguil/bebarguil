#!/usr/bin/env python3
"""
Gera os títulos de seção como SVG: label minúscula em mono + linha fina até a borda direita.

Uso:
    python3 scripts/make_headings.py about stack stats
    -> hd-about.svg, hd-stack.svg, hd-stats.svg
"""
import base64
import os
import sys

COLOR = "#8b949e"
RULE = "#30363d"
FONT_SIZE = 12.9
CHAR_W = 7.74
FAMILY = "'JetBrains Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace"
FONT_FILE = os.environ.get("STATS_FONT")   # .woff2 opcional (Part 4)
W, H = 460, 24


def font_css():
    if not FONT_FILE:
        return ""
    with open(FONT_FILE, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return ("@font-face{font-family:'JetBrains Mono';src:url(data:font/woff2;base64,"
            + b64 + ") format('woff2');}")


def heading(label: str) -> str:
    label = label.lower()
    text_w = len(label) * CHAR_W
    x_rule = round(text_w + 12, 1)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
        f"<style>{font_css()}"
        f"text{{font-family:{FAMILY};font-size:{FONT_SIZE}px;fill:{COLOR};}}</style>"
        f'<text x="0" y="16">{label}</text>'
        f'<line x1="{x_rule}" y1="12" x2="{W}" y2="12" stroke="{RULE}" stroke-width="1"/>'
        "</svg>\n"
    )


def main():
    labels = sys.argv[1:] or ["about", "stack", "stats"]
    for label in labels:
        name = f"hd-{label.lower()}.svg"
        with open(name, "w") as f:
            f.write(heading(label))
        print("ok", name)


if __name__ == "__main__":
    main()
