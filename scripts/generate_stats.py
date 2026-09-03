#!/usr/bin/env python3
"""
Gera stats.svg, streak.svg, langs.svg e year.svg a partir da API GraphQL do GitHub.
Só biblioteca padrão. Roda no GitHub Actions com o GITHUB_TOKEN embutido.

Env:
    GITHUB_TOKEN  token (no Actions: secrets.GITHUB_TOKEN; local: gh auth token)
    GH_LOGIN      usuário (default: BeBarguil)

Uso local:
    GITHUB_TOKEN=$(gh auth token) python3 scripts/generate_stats.py
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.request

LOGIN = os.environ.get("GH_LOGIN", "BeBarguil")
TOKEN = os.environ.get("GITHUB_TOKEN")
EXCLUDE_REPOS = {"dotfiles"}          # repos que não entram no gráfico de linguagens
SKIP_FORKS = True

# --- mesma linguagem visual do retrato ---------------------------------------
RAMP = " .`:-=+*cs#%@"
COLOR = "#8b949e"
DIM = "#484f58"
FONT_SIZE = 12.9
CHAR_W = 7.74
LINE_H = CHAR_W / 0.48
FAMILY = "'JetBrains Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace"
FONT_FILE = os.environ.get("STATS_FONT")   # .woff2 opcional (Part 4)

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        isFork
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


# --- API ----------------------------------------------------------------------
def fetch():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN não definido")
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=364)
    variables = {
        "login": LOGIN,
        "from": f"{start.isoformat()}T00:00:00Z",   # janela em dias UTC inteiros
        "to": f"{today.isoformat()}T23:59:59Z",
    }
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(json.dumps(data["errors"], indent=2))
    return data["data"]["user"]


# --- cálculo ------------------------------------------------------------------
def daily(user):
    days = []
    for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            days.append((dt.date.fromisoformat(d["date"]), d["contributionCount"]))
    days.sort()
    return days


def weekly(days):
    out, acc = [], 0
    for i, (_, c) in enumerate(days, 1):
        acc += c
        if i % 7 == 0:
            out.append(acc)
            acc = 0
    if acc:
        out.append(acc)
    return out


def streaks(days):
    """Devolve (atual, (ini, fim)), (maior, (ini, fim))."""
    longest, cur = 0, 0
    l_range = c_range = (None, None)
    run_start = None
    for d, c in days:
        if c > 0:
            if cur == 0:
                run_start = d
            cur += 1
            if cur > longest:
                longest, l_range = cur, (run_start, d)
        else:
            cur = 0
    # streak atual: conta de trás pra frente; hoje sem commit ainda não quebra
    cur, end = 0, None
    for i in range(len(days) - 1, -1, -1):
        d, c = days[i]
        if c > 0:
            if end is None:
                end = d
            cur += 1
        elif i == len(days) - 1:
            continue          # hoje vazio: pula
        else:
            break
    c_range = (days[len(days) - cur][0] if cur else None, end)
    return (cur, c_range), (longest, l_range)


def languages(user):
    by_bytes, by_repo = {}, {}
    for repo in user["repositories"]["nodes"]:
        if repo["name"] in EXCLUDE_REPOS or (SKIP_FORKS and repo["isFork"]):
            continue
        seen = set()
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            by_bytes[name] = by_bytes.get(name, 0) + e["size"]
            if name not in seen:
                by_repo[name] = by_repo.get(name, 0) + 1
                seen.add(name)
    return by_bytes, by_repo


# --- SVG ----------------------------------------------------------------------
def font_css():
    if not FONT_FILE:
        return ""
    with open(FONT_FILE, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return ("@font-face{font-family:'JetBrains Mono';src:url(data:font/woff2;base64,"
            + b64 + ") format('woff2');}")


def svg_open(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"<style>{font_css()}"
            f"text{{font-family:{FAMILY};font-size:{FONT_SIZE}px;fill:{COLOR};white-space:pre;}}"
            f".dim{{fill:{DIM};}}.big{{font-size:{FONT_SIZE * 2.6:.1f}px;}}"
            f"rect,polyline,path{{fill:{COLOR};}}polyline{{fill:none;stroke:{COLOR};stroke-width:1.5;}}"
            "</style>")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<text x="{x:.1f}" y="{y:.1f}"{c} xml:space="preserve">{esc(s)}</text>'


def fmt(d):
    return d.strftime("%d %b").lower() if d else "—"


def write(name, body):
    with open(name, "w") as f:
        f.write(body + "\n")
    print("ok", name)


def stats_svg(total, weeks):
    W, H = 460, 110
    out = [svg_open(W, H)]
    out.append(text(10, 46, f"{total:,}".replace(",", "."), "big"))
    out.append(text(10, 66, "contributions, last 365 days", "dim"))
    # sparkline semanal (agregado -> linha é honesta)
    x0, x1, y0, y1 = 10, W - 10, 80, 100
    mx = max(weeks) or 1
    n = len(weeks)
    pts = []
    for i, v in enumerate(weeks):
        x = x0 + (x1 - x0) * i / max(n - 1, 1)
        y = y1 - (y1 - y0) * v / mx
        pts.append(f"{x:.1f},{y:.1f}")
    out.append(f'<polyline points="{" ".join(pts)}"/>')
    out.append("</svg>")
    write("stats.svg", "\n".join(out))


def streak_svg(current, longest):
    W, H = 460, 110
    (c, (cs, ce)), (l, (ls, le)) = current, longest
    out = [svg_open(W, H)]
    out.append(text(10, 46, str(c), "big"))
    out.append(text(10, 66, "day current streak", "dim"))
    out.append(text(10, 86, f"{fmt(cs)} → {fmt(ce)}" if c else "no commits yet", "dim"))
    out.append(text(240, 46, str(l), "big"))
    out.append(text(240, 66, "day longest streak", "dim"))
    out.append(text(240, 86, f"{fmt(ls)} → {fmt(le)}" if l else "—", "dim"))
    out.append("</svg>")
    write("streak.svg", "\n".join(out))


def langs_svg(by_bytes, by_repo, top=6):
    ranked = sorted(by_bytes.items(), key=lambda kv: -kv[1])[:top]
    W = 460
    H = 30 + LINE_H * (len(ranked) + 1) + 10
    tot = sum(by_bytes.values()) or 1
    out = [svg_open(W, H)]
    out.append(text(10, 20, "top languages   bytes    repos", "dim"))
    bar_x, bar_w = 165, 150
    for i, (name, size) in enumerate(ranked):
        y = 20 + LINE_H * (i + 1)
        pct = size / tot
        out.append(text(10, y, name[:15]))
        out.append(f'<rect x="{bar_x}" y="{y - 10}" width="{bar_w * pct:.1f}" height="9"/>')
        out.append(text(bar_x + bar_w + 10, y, f"{pct * 100:4.0f}%    {by_repo.get(name, 0):2d}", "dim"))
    out.append("</svg>")
    write("langs.svg", "\n".join(out))


def year_svg(days):
    """Um caractere por dia, 7 linhas (dom→sáb) x 52/53 colunas, usando a rampa."""
    mx = max(c for _, c in days) or 1
    n = len(RAMP) - 1
    first = days[0][0]
    ncols = (len(days) + first.weekday() + 1) // 7 + 1
    grid = [[" "] * ncols for _ in range(7)]
    for d, c in days:
        col = ((d - first).days + (first.weekday() + 1) % 7) // 7
        row = (d.weekday() + 1) % 7                     # domingo = 0
        lvl = 0 if c == 0 else max(1, round(n * (c / mx) ** 0.5))
        grid[row][col] = RAMP[lvl]
    pad = 10
    W = pad * 2 + ncols * CHAR_W + 4 * CHAR_W
    H = pad * 2 + 8 * LINE_H
    out = [svg_open(round(W), round(H))]
    for r, label in enumerate(["", "mon", "", "wed", "", "fri", ""]):
        y = pad + (r + 1) * LINE_H
        out.append(text(pad, y, label, "dim"))
        out.append(text(pad + 4 * CHAR_W, y, "".join(grid[r])))
    out.append("</svg>")
    write("year.svg", "\n".join(out))


def main():
    user = fetch()
    days = daily(user)
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    stats_svg(total, weekly(days))
    cur, lon = streaks(days)
    streak_svg(cur, lon)
    langs_svg(*languages(user))
    year_svg(days)


if __name__ == "__main__":
    main()
