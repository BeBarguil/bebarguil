#!/usr/bin/env python3
"""
Foto -> retrato ASCII animado (SVG), seguindo o pipeline do Part 1:
rembg -> bilateral -> CLAHE -> curva de escurecimento -> rampa -> SVG com "digitação".

Uso:
    python3 scripts/make_portrait.py foto.jpg -o portrait.svg
    python3 scripts/make_portrait.py foto.jpg -o portrait.svg --cols 90 --gamma 1.7
    python3 scripts/make_portrait.py foto.jpg -o portrait.svg --font ramp.woff2   # Part 4
"""
import argparse
import base64
import io
import sys

import cv2
import numpy as np
from PIL import Image
from rembg import remove

# 13 níveis, do branco (espaço) ao preto (@)
RAMP = " .`:-=+*cs#%@"

FONT_SIZE = 12.9
CHAR_W = 7.74                 # 0.600 em  -> geometria que o guia assume
LINE_H = CHAR_W / 0.48        # ~16.1 px; caractere mono é ~2x mais alto que largo


def load_gray(path: str, use_rembg: bool) -> np.ndarray:
    """Abre a foto, tira o fundo (branco) e devolve em tons de cinza."""
    img = Image.open(path).convert("RGBA")
    if use_rembg:
        img = remove(img)  # RGBA com fundo transparente
    # compõe sobre branco -> fundo vira 255 -> índice 0 da rampa (espaço)
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    return np.array(bg.convert("L"))


def process(gray: np.ndarray, cols: int, gamma: float, clip: float) -> np.ndarray:
    """bilateral -> CLAHE -> resize -> curva. Devolve matriz (rows x cols) em 0..255."""
    g = cv2.bilateralFilter(gray, d=9, sigmaColor=40, sigmaSpace=9)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    g = clahe.apply(g)

    h, w = g.shape
    rows = max(1, round(cols * (h / w) * 0.48))
    g = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)

    # a "correção" do guia: escurece os meios-tons pra sobrancelha/óculos/lábio sobreviverem
    v = (g.astype(np.float32) / 255.0) ** gamma
    return (v * 255).astype(np.uint8)


def to_ascii(mat: np.ndarray) -> list[str]:
    n = len(RAMP) - 1
    idx = np.round((1.0 - mat / 255.0) * n).astype(int)
    lines = ["".join(RAMP[i] for i in row) for row in idx]
    # tira colunas/linhas totalmente vazias nas bordas pra não desperdiçar espaço
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return lines


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(lines: list[str], color: str, stagger: float, dur: float,
              font_b64: str | None) -> str:
    cols = max(len(l) for l in lines)
    rows = len(lines)
    W = round(cols * CHAR_W, 2)
    H = round(rows * LINE_H, 2)
    pad = 6

    if font_b64:
        font_css = (
            "@font-face{font-family:'Ramp';src:url(data:font/woff2;base64,"
            + font_b64 + ") format('woff2');}"
        )
        family = "'Ramp', 'JetBrains Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace"
    else:
        font_css = ""
        family = "'JetBrains Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace"

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {W + 2 * pad} {H + 2 * pad}" width="{W + 2 * pad}" height="{H + 2 * pad}">'
    )
    out.append("<style>")
    out.append(font_css)
    out.append(
        f"text{{font-family:{family};font-size:{FONT_SIZE}px;fill:{color};"
        "white-space:pre;dominant-baseline:hanging;}"
        f".cur{{fill:{color};}}"
    )
    out.append("</style>")
    out.append("<defs>")
    for i, line in enumerate(lines):
        begin = round(i * stagger, 3)
        y = round(pad + i * LINE_H, 2)
        out.append(
            f'<clipPath id="c{i}"><rect x="{pad}" y="{y}" width="0" height="{round(LINE_H, 2)}">'
            f'<animate attributeName="width" from="0" to="{W}" begin="{begin}s" dur="{dur}s" fill="freeze"/>'
            "</rect></clipPath>"
        )
    out.append("</defs>")

    for i, line in enumerate(lines):
        begin = round(i * stagger, 3)
        y = round(pad + i * LINE_H, 2)
        out.append(
            f'<text x="{pad}" y="{y + 2}" xml:space="preserve" clip-path="url(#c{i})">'
            f"{xml_escape(line)}</text>"
        )
        # cursor: um bloquinho que corre na frente da "digitação" e some no fim
        out.append(
            f'<rect class="cur" x="{pad}" y="{y + 1}" width="{CHAR_W}" height="{round(LINE_H - 2, 2)}" opacity="0">'
            f'<set attributeName="opacity" to="1" begin="{begin}s"/>'
            f'<animate attributeName="x" from="{pad}" to="{round(pad + W, 2)}" begin="{begin}s" dur="{dur}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0" begin="{round(begin + dur, 3)}s" fill="freeze"/>'
            "</rect>"
        )
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Foto -> retrato ASCII animado em SVG")
    ap.add_argument("photo")
    ap.add_argument("-o", "--out", default="portrait.svg")
    ap.add_argument("--cols", type=int, default=90)
    ap.add_argument("--gamma", type=float, default=1.7, help="curva de escurecimento (v/255)^gamma")
    ap.add_argument("--clip", type=float, default=3.0, help="clipLimit do CLAHE")
    ap.add_argument("--color", default="#8b949e", help="uma cor só (dica do guia)")
    ap.add_argument("--stagger", type=float, default=0.09, help="atraso entre linhas (s)")
    ap.add_argument("--dur", type=float, default=0.5, help="duração da digitação de cada linha (s)")
    ap.add_argument("--no-rembg", action="store_true", help="pula a remoção de fundo")
    ap.add_argument("--font", help="arquivo .woff2 pra embutir (Part 4)")
    ap.add_argument("--txt", help="também salva o ASCII puro num .txt pra conferir")
    args = ap.parse_args()

    gray = load_gray(args.photo, use_rembg=not args.no_rembg)
    mat = process(gray, args.cols, args.gamma, args.clip)
    lines = to_ascii(mat)
    if not lines:
        sys.exit("saiu tudo em branco — a foto está clara demais ou o rembg apagou o rosto")

    if args.txt:
        with open(args.txt, "w") as f:
            f.write("\n".join(lines))

    font_b64 = None
    if args.font:
        with open(args.font, "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode()

    svg = build_svg(lines, args.color, args.stagger, args.dur, font_b64)
    with open(args.out, "w") as f:
        f.write(svg)

    print(f"{args.out}: {len(lines)} linhas x {max(len(l) for l in lines)} colunas "
          f"(~{round(len(lines) * args.stagger + args.dur, 1)}s de animação)")


if __name__ == "__main__":
    main()
