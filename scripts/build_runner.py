#!/usr/bin/env python3
"""Pixel-art game board for the profile.

A small white kitten runs across your GitHub contribution calendar, followed by
three mini kittens in a row. Every day it steps on is collected and added to
a score in the title bar; when the board is empty the loop starts again.

The calendar comes from the GitHub GraphQL API and the output is two animated
SVGs (dark and light) that follow the card palette used by build_assets.py.
Standard library only, so it runs in CI without installing anything.

    GITHUB_TOKEN=... python3 scripts/build_runner.py --user MrNicolass --out dist
    python3 scripts/build_runner.py --sample --out /tmp/preview     # fake data, no token
    python3 scripts/build_runner.py --data calendar.json --out dist # saved API response

Notes
- Text is drawn with a built-in 3x5 pixel font, so no font files are needed.
- Every animation shares one duration and starts at 0, so the whole board stays
  in lock-step. SMIL silently drops an animation whose first keyTime is not 0
  or whose lists differ in length; validate() rejects both.
- The four characters are pixel grids in LEADER / MINI below. Edit the rows to
  redraw them: W fur, e eyes, n nose, c collar; the outline is added automatically.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

NAME = "wonderland-run"
W = 880
BAR = 36  # title bar height

# ---------------------------------------------------------------- palette (same card colours as build_assets.py)
THEMES = {
    "dark": {
        "card": "#0a0d12",
        "line": "#232a34",
        "text": "#e6edf3",
        "text2": "#9da7b3",
        "muted": "#6e7681",
        "accent": "#a371f7",
        "bar": ["#43299b", "#8957e5", "#d6c2ff"],  # the three title-bar squares
        "levels": ["#151a21", "#33276f", "#5b3cc4", "#8957e5", "#d6c2ff"],  # empty .. busiest day
        "palette": {  # sprite colours: W fur, o outline, e eye, n nose, C/v/b/l collars
            "W": "#f4f6ff", "o": "#6b739f", "e": "#161a33", "n": "#ff8fb1",
            "C": "#f0883e", "v": "#8957e5", "b": "#388bfd", "l": "#d6c2ff",
        },
    },
    "light": {
        "card": "#f6f8fa",
        "line": "#d0d7de",
        "text": "#1f2328",
        "text2": "#4b5560",
        "muted": "#7a8490",
        "accent": "#8250df",
        "bar": ["#cbb2ff", "#a371f7", "#6a3fd1"],
        "levels": ["#e4e8ed", "#e0d3ff", "#c3a8ff", "#9a6df0", "#6a3fd1"],
        "palette": {
            "W": "#ffffff", "o": "#2f3556", "e": "#161a33", "n": "#ff7ea3",
            "C": "#f0883e", "v": "#8250df", "b": "#0969da", "l": "#c8a9ff",
        },
    },
}

# ---------------------------------------------------------------- characters (original pixel art)
# W fur, e eyes, n nose, c collar. The outline is added around the silhouette automatically.
LEADER = [
    "W.....W",
    "WWWWWWW",
    "WeWWWeW",
    "WWWnWWW",
    ".WWWWW.",
    ".ccccc.",
    ".WWWWW.",
]
LEADER_LEGS = [".W...W.", "..WWW.."]  # two walk frames, 1 row each
MINI = [
    "W...W",
    "WWWWW",
    "WeWeW",
    ".WnW.",
    ".ccc.",
]
MINI_LEGS = [".W.W.", ".WWW."]
LEADER_COLLAR = "C"  # ember
FOLLOWER_COLLARS = ["v", "b", "l"]  # violet, blue, lilac, in order behind the leader

# ---------------------------------------------------------------- timing and geometry
STEP = 0.075  # seconds to cross one day
INTRO = 1.4  # full board before the runner appears
OUTRO = 2.6  # empty board and the final score before the reset
LAG = 3  # steps between neighbours in the train
U = 2  # px per sprite pixel
CELL, PITCH = 12, 15
X0, Y0 = 52, 62  # top-left of the day grid

# ---------------------------------------------------------------- 3x5 pixel font
_FONT = {
    "A": ".X./X.X/XXX/X.X/X.X", "B": "XX./X.X/XX./X.X/XX.", "C": ".XX/X../X../X../.XX",
    "D": "XX./X.X/X.X/X.X/XX.", "E": "XXX/X../XX./X../XXX", "F": "XXX/X../XX./X../X..",
    "G": ".XX/X../X.X/X.X/.XX", "H": "X.X/X.X/XXX/X.X/X.X", "I": "XXX/.X./.X./.X./XXX",
    "J": "..X/..X/..X/X.X/.X.", "K": "X.X/X.X/XX./X.X/X.X", "L": "X../X../X../X../XXX",
    "M": "X.X/XXX/XXX/X.X/X.X", "N": "XX./X.X/X.X/X.X/X.X", "O": "XXX/X.X/X.X/X.X/XXX",
    "P": "XX./X.X/XX./X../X..", "Q": "XXX/X.X/X.X/XXX/..X", "R": "XX./X.X/XX./X.X/X.X",
    "S": ".XX/X../.X./..X/XX.", "T": "XXX/.X./.X./.X./.X.", "U": "X.X/X.X/X.X/X.X/XXX",
    "V": "X.X/X.X/X.X/X.X/.X.", "W": "X.X/X.X/XXX/XXX/X.X", "X": "X.X/X.X/.X./X.X/X.X",
    "Y": "X.X/X.X/.X./.X./.X.", "Z": "XXX/..X/.X./X../XXX",
    "0": "XXX/X.X/X.X/X.X/XXX", "1": ".X./XX./.X./.X./XXX", "2": "XX./..X/.X./X../XXX",
    "3": "XX./..X/.X./..X/XX.", "4": "X.X/X.X/XXX/..X/..X", "5": "XXX/X../XX./..X/XX.",
    "6": ".XX/X../XX./X.X/.X.", "7": "XXX/..X/.X./.X./.X.", "8": "XXX/X.X/XXX/X.X/XXX",
    "9": "XXX/X.X/XXX/..X/XX.",
    ".": ".../.../.../.../.X.", ":": ".../.X./.../.X./...",
    "/": "..X/..X/.X./X../X..", "-": ".../.../XXX/.../...", "+": ".../.X./XXX/.X./...",
    ">": "X../.X./..X/.X./X..", "'": ".X./.X./.../.../...",
}
FONT = {k: v.split("/") for k, v in _FONT.items()}
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fmt(v: float, places: int = 6) -> str:
    return f"{v:.{places}f}".rstrip("0").rstrip(".") or "0"


def runs(cells):
    """Merge a set of (x, y) pixels into horizontal runs (x, y, width)."""
    out = []
    for y in sorted({c[1] for c in cells}):
        xs = sorted(c[0] for c in cells if c[1] == y)
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is None or x != prev + 1:
                out.append((start, y, prev - start + 1))
                start = x
            prev = x
    return out


def path_d(cells, ox, oy, s):
    return "".join(f"M{ox + x * s} {oy + y * s}h{w * s}v{s}h-{w * s}z" for x, y, w in runs(cells)) if cells else ""


def text_cells(text):
    cells, x = set(), 0
    for ch in text.upper():
        if ch == " ":
            x += 3
            continue
        for y, row in enumerate(FONT[ch]):
            for dx, c in enumerate(row):
                if c == "X":
                    cells.add((x + dx, y))
        x += 4
    return cells, max(x - 1, 0)


def text_w(text, s):
    return text_cells(text)[1] * s


def text(txt, x, y, s, fill):
    cells, _ = text_cells(txt)
    return f'<path d="{path_d(cells, x, y, s)}" fill="{fill}"/>'


# ---------------------------------------------------------------- calendar data
QUERY = """query($login: String!) {
  user(login: $login) { contributionsCollection { contributionCalendar {
    totalContributions
    weeks { contributionDays { date weekday contributionCount contributionLevel } }
  } } }
}"""
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def fetch(login: str, token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": NAME},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors") or not (data.get("data") or {}).get("user"):
        raise SystemExit(f"GraphQL error: {data.get('errors') or 'user not found'}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def sample(seed: int = 7) -> dict:
    """Plausible fake calendar ending today, for previews without a token."""
    rng = random.Random(seed)
    today = dt.date.today()
    first = today - dt.timedelta(days=364)
    first -= dt.timedelta(days=(first.weekday() + 1) % 7)  # back to a Sunday
    days, d = [], first
    while d <= today:
        wd = (d.weekday() + 1) % 7
        busy = 0.15 if wd in (0, 6) else 0.62
        burst = 1.8 if (d.toordinal() // 17) % 3 == 0 else 0.7
        n = int(rng.random() ** 2 * 11 * burst) if rng.random() < busy * burst else 0
        days.append((d, wd, n))
        d += dt.timedelta(days=1)
    peak = max(n for *_, n in days) or 1
    weeks, week = [], []
    for d, wd, n in days:
        if wd == 0 and week:
            weeks.append({"contributionDays": week})
            week = []
        level = 0 if n == 0 else min(4, 1 + (n - 1) * 4 // peak)
        week.append({"date": d.isoformat(), "weekday": wd, "contributionCount": n,
                     "contributionLevel": list(LEVELS)[level]})
    weeks.append({"contributionDays": week})
    return {"totalContributions": sum(n for *_, n in days), "weeks": weeks}


def cells_of(cal: dict):
    """{(col, row): (date, count, level)} plus the column count."""
    cells = {}
    for c, week in enumerate(cal["weeks"]):
        for day in week["contributionDays"]:
            cells[(c, day["weekday"])] = (day["date"], day["contributionCount"], LEVELS[day["contributionLevel"]])
    return cells, len(cal["weeks"])


def route(cells, ncols):
    """Up the odd columns, down the even ones, one adjacent day at a time."""
    out = []
    for c in range(ncols):
        for r in (range(7) if c % 2 == 0 else range(6, -1, -1)):
            if (c, r) in cells:
                out.append((c, r))
    return out


# ---------------------------------------------------------------- sprites
def dilate(cells):
    return {(x + dx, y + dy) for x, y in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


def frame_cells(body, legs):
    """Body + one leg row as {(x, y): key}, wrapped in a 1-pixel outline and shifted to start at (0, 0)."""
    cells = {(x, y): ch for y, row in enumerate(body + [legs]) for x, ch in enumerate(row) if ch != "."}
    out = dict(cells)
    for x, y in cells:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            out.setdefault((x + dx, y + dy), "o")
    return {(x + 1, y + 1): k for (x, y), k in out.items()}


def sprite(body, legs, collar, t):
    """A kitten as SVG parts plus its size in px: a halo, then two walk frames that swap every 0.15 s."""
    pal = t["palette"]
    frames = [frame_cells(body, lg) for lg in legs]
    w = (max(x for f in frames for x, _ in f) + 1) * U
    h = (max(y for f in frames for _, y in f) + 1) * U
    parts = [f'<path d="{path_d(dilate(set(frames[0]) | set(frames[1])), 0, 0, U)}" fill="{t["card"]}"/>']
    for i, frame in enumerate(frames):
        paths = []
        for key in sorted(set(frame.values())):
            cells = {c for c, k in frame.items() if k == key}
            colour = pal[collar if key == "c" else key]
            paths.append(f'<path d="{path_d(cells, 0, 0, U)}" fill="{colour}"/>')
        values = "1;0" if i == 0 else "0;1"
        parts.append(
            f'<g opacity="{1 - i}"><animate attributeName="opacity" calcMode="discrete" values="{values}" '
            f'dur="0.3s" repeatCount="indefinite"/>{"".join(paths)}</g>'
        )
    return "".join(parts), w, h


# ---------------------------------------------------------------- board
def build(cal: dict, theme: str):
    t = THEMES[theme]
    cells, ncols = cells_of(cal)
    walk = route(cells, ncols)
    n = len(walk)
    steps = n + LAG * len(FOLLOWER_COLLARS)
    T = INTRO + steps * STEP + OUTRO
    dur = f"{T:.3f}s"

    def kt(seconds):
        return fmt(seconds / T)

    def at(i):  # time the leader enters the i-th day
        return INTRO + i * STEP

    total = cal["totalContributions"]
    ndigits = max(4, len(str(total)))
    height = Y0 + 7 * PITCH - (PITCH - CELL) + 42
    body = [f'<rect width="{W}" height="{height}" fill="{t["card"]}"/>']
    body.append(f'<rect x="0" y="{BAR - 0.5}" width="{W}" height="1" fill="{t["line"]}"/>')
    for i, col in enumerate(t["bar"]):
        body.append(f'<rect x="{16 + i * 14}" y="14" width="8" height="8" fill="{col}"/>')
    body.append(text("WONDERLAND/RUN", 78, 13, 2, t["muted"]))

    # score: one path per digit whose shape is swapped as days are collected
    digit_w = 4 * 3
    sx = W - 16 - (ndigits * digit_w - 3)
    body.append(text("SCORE", sx - 14 - text_w("SCORE", 2), 13, 2, t["text2"]))
    events, running = [], 0
    for i, pos in enumerate(walk):
        if cells[pos][1] > 0:
            running += cells[pos][1]
            events.append((at(i), running))
    for p in range(ndigits):
        px = sx + (ndigits - 1 - p) * digit_w
        seq = [(0.0, 0)]
        for sec, cum in events:
            d = cum // 10**p % 10
            if d != seq[-1][1]:
                seq.append((sec, d))
        shapes = [path_d(text_cells(str(d))[0], px, 11, 3) for _, d in seq]
        if len(seq) == 1:
            body.append(f'<path d="{shapes[0]}" fill="{t["accent"]}"/>')
        else:
            body.append(
                f'<path d="{shapes[0]}" fill="{t["accent"]}"><animate attributeName="d" calcMode="discrete" dur="{dur}" '
                f'repeatCount="indefinite" keyTimes="{";".join(kt(s) for s, _ in seq)}" values="{";".join(shapes)}"/></path>'
            )

    # month and weekday labels
    prev, marks = None, []
    for c in range(ncols):
        first = min((r for (cc, r) in cells if cc == c))
        month = int(cells[(c, first)][0][5:7]) - 1
        if month != prev:
            marks.append((c, month))
            prev = month
    if len(marks) > 1 and marks[1][0] - marks[0][0] < 3:
        marks.pop(0)
    for c, m in marks:
        body.append(text(MONTHS[m], X0 + c * PITCH, 44, 2, t["muted"]))
    for r, label in ((1, "MON"), (3, "WED"), (5, "FRI")):
        body.append(text(label, 20, Y0 + r * PITCH + 1, 2, t["muted"]))

    # the days: one empty square each, plus a coloured square on top that vanishes when collected
    body.append(f'<path d="{"".join(f"M{X0 + c * PITCH} {Y0 + r * PITCH}h{CELL}v{CELL}h-{CELL}z" for c, r in sorted(cells))}" fill="{t["levels"][0]}"/>')
    order = {pos: i for i, pos in enumerate(walk)}
    for (c, r), (_, count, level) in sorted(cells.items()):
        if level == 0:
            continue
        body.append(
            f'<rect x="{X0 + c * PITCH}" y="{Y0 + r * PITCH}" width="{CELL}" height="{CELL}" fill="{t["levels"][level]}">'
            f'<animate attributeName="opacity" calcMode="discrete" dur="{dur}" repeatCount="indefinite" '
            f'keyTimes="0;{kt(at(order[(c, r)]))}" values="1;0"/></rect>'
        )

    # the train: the same route for every character, delayed by LAG steps each
    def mover(index, art):
        content, sw, sh = art
        lead = index * LAG  # steps behind the leader
        ox, oy = (sw - CELL) // 2, (sh - CELL) // 2
        pts = [(X0 + c * PITCH - ox, Y0 + r * PITCH - oy) for c, r in walk]
        times = [0.0] + [at(lead + i) for i in range(1, n)]
        shown_from, shown_to = at(lead), at(lead + n)
        first = f"{pts[0][0]},{pts[0][1]}"
        return (
            f'<g transform="translate({first})" opacity="{1 if index == 0 else 0}">'
            f'<animateTransform attributeName="transform" type="translate" calcMode="discrete" dur="{dur}" repeatCount="indefinite" '
            f'keyTimes="{";".join(kt(s) for s in times)}" values="{";".join(f"{x},{y}" for x, y in pts)}"/>'
            f'<animate attributeName="opacity" calcMode="discrete" dur="{dur}" repeatCount="indefinite" '
            f'keyTimes="0;{kt(shown_from)};{kt(shown_to)}" values="0;1;0"/>'
            f"{content}</g>"
        )

    for k in range(len(FOLLOWER_COLLARS), 0, -1):
        body.append(mover(k, sprite(MINI, MINI_LEGS, FOLLOWER_COLLARS[k - 1], t)))
    body.append(mover(0, sprite(LEADER, LEADER_LEGS, LEADER_COLLAR, t)))

    # footer: total and the legend
    base = Y0 + 7 * PITCH - (PITCH - CELL) + 14
    body.append(text(f"{total:,} CONTRIBUTIONS IN THE LAST YEAR".replace(",", "."), X0, base, 2, t["muted"]))
    lx = X0 + 53 * PITCH - (PITCH - CELL)
    more_x = lx - text_w("MORE", 2)
    body.append(text("MORE", more_x, base, 2, t["muted"]))
    sq = 5 * CELL + 4 * 3
    for i, col in enumerate(t["levels"]):
        body.append(f'<rect x="{more_x - 8 - sq + i * (CELL + 3)}" y="{base - 1}" width="{CELL}" height="{CELL}" fill="{col}"/>')
    body.append(text("LESS", more_x - 8 - sq - 8 - text_w("LESS", 2), base, 2, t["muted"]))
    body.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" fill="none" stroke="{t["line"]}"/>')

    label = (f"A small white kitten runs across my GitHub contribution calendar followed by three mini kittens, "
             f"collecting {total} contributions.")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" '
           f'shape-rendering="crispEdges" role="img" aria-label="{label}">\n<title>{label}</title>\n' + "\n".join(body) + "\n</svg>\n")
    return svg, T


def validate(svg: str):
    """Reject the SMIL mistakes browsers silently ignore."""
    root = ET.fromstring(svg)
    checked = 0
    for el in root.iter():
        if not el.tag.endswith("}animate") and not el.tag.endswith("}animateTransform"):
            continue
        keys, vals = el.get("keyTimes"), el.get("values")
        if keys is None:
            continue
        ks = [float(k) for k in keys.split(";")]
        vs = vals.split(";")
        where = f"<{el.tag.split('}')[1]} {el.get('attributeName')}>"
        if len(ks) != len(vs):
            raise SystemExit(f"{where}: {len(ks)} keyTimes for {len(vs)} values")
        if ks[0] != 0:
            raise SystemExit(f"{where}: first keyTime must be 0")
        if any(b < a for a, b in zip(ks, ks[1:])) or ks[-1] > 1:
            raise SystemExit(f"{where}: keyTimes must be non-decreasing and <= 1")
        checked += 1
    return checked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "MrNicolass"))
    ap.add_argument("--out", default="dist")
    ap.add_argument("--data", help="JSON file with a contributionCalendar object instead of calling the API")
    ap.add_argument("--sample", action="store_true", help="use made-up data (preview only)")
    args = ap.parse_args()

    if args.sample:
        cal = sample()
    elif args.data:
        cal = json.loads(Path(args.data).read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set (or pass --sample / --data)")
        cal = fetch(args.user, token)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        svg, T = build(cal, theme)
        n = validate(svg)
        path = out / f"{NAME}-{theme}.svg"
        path.write_text(svg, encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size:,} bytes, loop {T:.1f}s, {n} animations validated)")


if __name__ == "__main__":
    main()
