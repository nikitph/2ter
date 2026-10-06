"""Render results/scale.json into two static SVG charts (no plotting deps).

    python experiments/plot.py
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "..", "results")

SERIES = [  # (condition, label, colour) - fixed categorical order, CVM first
    ("D_cvm", "D  CVM", "#2a78d6"),
    ("A_full", "A  full context", "#eb6834"),
    ("C_agent", "C  tool calling", "#1baf7a"),
    ("B2_graph_rag", "B2 graph-RAG", "#eda100"),
]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
W, H, L, R, T, B = 720, 360, 72, 150, 40, 48


def _x(n, lo, hi):
    return L + (math.log10(n) - lo) / (hi - lo) * (W - L - R)


def chart(path, title, ylabel, key, ylog, ymin, ymax, data, limit=None):
    sizes = [e["world_objects"] for e in data["sizes"]]
    lo, hi = math.log10(min(sizes)), math.log10(max(sizes))

    def y(v):
        if ylog:
            v = max(v, ymin)
            f = (math.log10(v) - math.log10(ymin)) / (math.log10(ymax) - math.log10(ymin))
        else:
            f = (v - ymin) / (ymax - ymin)
        return H - B - f * (H - T - B)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
           f'<text x="{L}" y="22" font-size="14" font-weight="600" fill="{INK}">{title}</text>']
    ticks = ([10 ** k for k in range(int(math.log10(ymin)), int(math.log10(ymax)) + 1)]
             if ylog else [ymin + i * (ymax - ymin) / 4 for i in range(5)])
    for t in ticks:
        lab = (f"{t:,.0f}" if t < 1e6 else f"{t / 1e6:.0f}M") if ylog else f"{t:.0%}"
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{L - 8}" y="{y(t) + 4:.1f}" text-anchor="end" fill="{INK2}">{lab}</text>')
    for n in sizes:
        out.append(f'<text x="{_x(n, lo, hi):.1f}" y="{H - B + 18}" text-anchor="middle" '
                   f'fill="{INK2}">10<tspan dy="-5" font-size="9">{round(math.log10(n))}</tspan></text>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 8}" text-anchor="middle" fill="{INK2}">'
               f'world size (objects in the address space)</text>')
    out.append(f'<text transform="translate(16 {(T + H - B) / 2}) rotate(-90)" '
               f'text-anchor="middle" fill="{INK2}">{ylabel}</text>')
    if limit:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(limit):.1f}" y2="{y(limit):.1f}" '
                   f'stroke="{INK2}" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{W - R - 4}" y="{y(limit) - 6:.1f}" text-anchor="end" fill="{INK2}">'
                   f'1M-token context window</text>')
    labels = []
    for cond, label, col in reversed(SERIES):  # CVM drawn last, on top
        rows = [e for e in data["sizes"] if cond in e["conditions"]]
        pts, hollow = [], []
        for e in rows:
            c = e["conditions"][cond]
            p = (_x(e["world_objects"], lo, hi), y(c[key]))
            # an infeasible run produced no answer: show it apart from the line
            (hollow if key == "accuracy" and c.get("infeasible") else pts).append(p)
        if not pts and not hollow:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2"/>')
        for px, py in pts:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{col}" '
                       f'stroke="{SURF}" stroke-width="2"/>')
        for px, py in hollow:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{SURF}" '
                       f'stroke="{col}" stroke-width="2"/>')
        if hollow:
            out.append(f'<text x="{hollow[0][0] - 8:.1f}" y="{hollow[0][1] - 10:.1f}" fill="{INK2}">'
                       f'A: prompt exceeds window, not runnable</text>')
        last = pts[-1] if pts else hollow[-1]
        labels.append([last[1], label, col])
    labels.sort()
    for i in range(1, len(labels)):  # de-collide direct labels
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 15)
    for ly, label, col in labels:
        out.append(f'<rect x="{W - R + 10}" y="{ly - 5:.1f}" width="10" height="3" fill="{col}"/>')
        out.append(f'<text x="{W - R + 24}" y="{ly + 4:.1f}" fill="{INK}">{label}</text>')
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(out))


def main():
    with open(os.path.join(RESULTS, "scale.json")) as f:
        data = json.load(f)
    chart(os.path.join(RESULTS, "context_vs_world_size.svg"),
          "Peak prompt size per task vs. world size", "peak prompt tokens (log)",
          "peak_prompt_tokens_mean", True, 100, 1e8, data, limit=1_000_000)
    chart(os.path.join(RESULTS, "accuracy_vs_world_size.svg"),
          "Task accuracy vs. world size", "accuracy", "accuracy", False, 0, 1, data)

    print("wrote SVGs to", RESULTS)


if __name__ == "__main__":
    main()
