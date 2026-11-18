#!/usr/bin/env python3
"""Pixel-art stats cards for the profile.

Two cards, each in a dark and a light theme, drawn with the same palette and 3x5
pixel font as the contribution game (build_runner.py):

    stats-{dark,light}.svg   stars, commits, pull requests, issues, repos contributed to
                             and a pixel ring with the rank letter
    langs-{dark,light}.svg   the six most used languages as segmented bars

The numbers and the rank follow github-readme-stats, so the cards say the same
thing as the ones they replace: all-time commits (search API), stars on your own
non-fork repositories, language share by bytes over the top six languages, and the
same rank formula and thresholds.

    GITHUB_TOKEN=... python3 scripts/build_stats.py --user MrNicolass --out dist
    python3 scripts/build_stats.py --sample --out /tmp/preview      # made-up numbers, no token
    python3 scripts/build_stats.py --data stats.json --out dist     # saved numbers

A STATS_TOKEN (personal access token) is used instead of GITHUB_TOKEN when set, which is
the way to count private repositories. Standard library only; run it with plain python3
because it imports build_runner.py from the same folder.

Notes
- On load the ring sweeps clockwise and the bars grow, once. Everything is already in its
  final state in the file, so a viewer without SMIL (or a static renderer) shows the finished card.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
from pathlib import Path

import build_runner as R

W, H, BAR = 440, 196, 36
THEMES = R.THEMES
LANG_COLORS = {
    "dark": ["#8957e5", "#388bfd", "#d6c2ff", "#f0883e", "#ff8fb1", "#56d4a8"],
    "light": ["#8250df", "#0969da", "#c8a9ff", "#f0883e", "#ff7ea3", "#1a9e75"],
}
T = 1.8  # one duration for every animation, so keyTimes are plain fractions of it

# ---------------------------------------------------------------- icons (7x7, drawn at 2px)
ICONS = {
    "star": ["...X...", "...X...", "XXXXXXX", ".XXXXX.", "..XXX..", ".XX.XX.", ".X...X."],
    "commit": [".......", ".......", "..XXX..", "XXX.XXX", "..XXX..", ".......", "......."],
    "pr": ["XX...XX", ".XX.XX.", "..XXX..", "...X...", "...X...", "...X...", "...X..."],
    "issue": ["..XXX..", ".X...X.", "X.....X", "X..X..X", "X.....X", ".X...X.", "..XXX.."],
    "repo": ["XXXXXX.", "X....X.", "X.XXXX.", "X....X.", "X.XXXX.", "XXXXXX.", ".X...X."],
}
ROWS = [
    ("STARS EARNED", "stars", "star"),
    ("COMMITS", "commits", "commit"),
    ("PULL REQUESTS", "prs", "pr"),
    ("ISSUES", "issues", "issue"),
    ("CONTRIBUTED TO (LAST YEAR)", "contrib", "repo"),
]

# ---------------------------------------------------------------- data
REPOS_QUERY = """query($login: String!, $after: String) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $after) {
      nodes {
        stargazers { totalCount }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""
USER_QUERY = """query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests(first: 1) { totalCount }
    openIssues: issues(states: OPEN) { totalCount }
    closedIssues: issues(states: CLOSED) { totalCount }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) { totalCount }
    contributionsCollection { totalCommitContributions restrictedContributionsCount totalPullRequestReviewContributions }
  }
}"""


def call(token, url, body=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "pixel-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def graphql(token, query, **variables):
    """The user object. Fields the token may not read (private repositories seen through
    GITHUB_TOKEN, for one) come back as null with an error; those count as 0 instead of failing."""
    data = call(token, "https://api.github.com/graphql", {"query": query, "variables": variables})
    user = (data.get("data") or {}).get("user")
    if not user:
        raise SystemExit(f"GraphQL error: {data.get('errors') or 'user not found'}")
    if data.get("errors"):
        print(f"note: {len(data['errors'])} fields are not readable with this token and count as 0 "
              f"({data['errors'][0].get('message')})")
    return user


def count(obj, key):
    return ((obj or {}).get(key) or {}).get("totalCount", 0)


def fetch(login: str, token: str, top: int = 6) -> dict:
    u = graphql(token, USER_QUERY, login=login)
    cc = u.get("contributionsCollection") or {}

    stars, sizes, repos, after = 0, {}, 0, None
    for _ in range(10):  # up to 1000 repositories
        page = graphql(token, REPOS_QUERY, login=login, after=after)["repositories"]
        for repo in page["nodes"]:
            if not repo:
                continue
            repos += 1
            stars += count(repo, "stargazers")
            for edge in (repo.get("languages") or {}).get("edges") or []:
                sizes[edge["node"]["name"]] = sizes.get(edge["node"]["name"], 0) + edge["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    print(f"{repos} repositories read, {len(sizes)} languages found")
    best = sorted(sizes.items(), key=lambda kv: -kv[1])[:top]
    total = sum(s for _, s in best) or 1

    try:  # all-time commits, the way include_all_commits does it
        commits = call(token, f"https://api.github.com/search/commits?q=author:{login}&per_page=1")["total_count"]
    except Exception as err:  # rate limit or search outage: fall back to the last year
        print(f"commit search failed ({err}); using last year's commits")
        commits = cc.get("totalCommitContributions", 0) + cc.get("restrictedContributionsCount", 0)

    return {
        "stars": stars,
        "commits": commits,
        "prs": count(u, "pullRequests"),
        "issues": count(u, "openIssues") + count(u, "closedIssues"),
        "contrib": count(u, "repositoriesContributedTo"),
        "reviews": cc.get("totalPullRequestReviewContributions", 0),
        "followers": count(u, "followers"),
        "langs": [[name, round(size * 100 / total, 2)] for name, size in best],
    }


def sample() -> dict:
    """The numbers on the cards this replaces (reviews and followers are guesses)."""
    return {"stars": 6, "commits": 375, "prs": 46, "issues": 1, "contrib": 1, "reviews": 0, "followers": 3,
            "langs": [["Java", 28.08], ["TypeScript", 26.31], ["Jupyter Notebook", 23.45],
                      ["Python", 18.10], ["Dart", 2.03], ["Game Maker Language", 2.03]]}


# ---------------------------------------------------------------- rank (github-readme-stats)
def rank(d: dict):
    def exp_cdf(x):
        return 1 - 2 ** -x

    def log_cdf(x):
        return x / (1 + x)

    parts = (2 * exp_cdf(d["commits"] / 1000) + 3 * exp_cdf(d["prs"] / 50) + 1 * exp_cdf(d["issues"] / 25)
             + 1 * exp_cdf(d["reviews"] / 2) + 4 * log_cdf(d["stars"] / 50) + 1 * log_cdf(d["followers"] / 10))
    percentile = (1 - parts / 12) * 100
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    cuts = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    return levels[next(i for i, c in enumerate(cuts) if percentile <= c)], percentile


# ---------------------------------------------------------------- drawing helpers
def clean(s: str, limit: int | None = None) -> str:
    s = "".join(c if c.upper() in R.FONT or c == " " else "?" for c in s).upper()
    while limit and R.text_w(s, 2) > limit:
        s = s[:-2] + "."
    return s


def num(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def right(txt, edge, y, s, fill):
    return R.text(txt, edge - R.text_w(txt, s), y, s, fill)


def icon(name, x, y, fill):
    cells = {(cx, cy) for cy, row in enumerate(ICONS[name]) for cx, ch in enumerate(row) if ch == "X"}
    return f'<path d="{R.path_d(cells, x, y, 2)}" fill="{fill}"/>'


def rects(cells, ox, oy, w, h):
    return "".join(f"M{ox + x} {oy + y}h{w}v{h}h-{w}z" for x, y in cells)


def frame(t, title, tag):
    body = [f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>',
            f'<rect x="0" y="{BAR - 0.5}" width="{W}" height="1" fill="{t["line"]}"/>']
    for i, col in enumerate(t["bar"]):
        body.append(f'<rect x="{16 + i * 14}" y="14" width="8" height="8" fill="{col}"/>')
    body.append(R.text(title, 78, 13, 2, t["muted"]))
    body.append(right(tag, W - 16, 13, 2, t["accent"]))
    return body


def wrap(body, label, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{label}">\n<title>{label}</title>\n'
            + (f"<defs>{defs}</defs>\n" if defs else "") + "\n".join(body)
            + f'\n<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="none" stroke="THEME_LINE"/>\n</svg>\n')


# ---------------------------------------------------------------- stats card
RING_CELL, RING_N, RING_IN, RING_OUT = 6, 18, 6.5, 8.75
RING_X, RING_Y = 308, 62  # top-left of the ring grid


def ring(progress):
    """Cells of the ring in clockwise order from the top, and how many of them are lit."""
    c = RING_N / 2
    cells = []
    for gy in range(RING_N):
        for gx in range(RING_N):
            dx, dy = gx + 0.5 - c, gy + 0.5 - c
            if RING_IN <= math.hypot(dx, dy) <= RING_OUT:
                cells.append((math.atan2(dx, -dy) % (2 * math.pi) / (2 * math.pi), gx, gy))
    cells.sort()
    lit = sum(1 for a, *_ in cells if a * 100 < progress)
    return [(gx, gy) for _, gx, gy in cells], lit


def stats_card(d, theme):
    t = THEMES[theme]
    level, pct = rank(d)
    progress = 100 - pct
    body = frame(t, "GITHUB/STATS", "MRNICOLASS")

    top, pitch, edge = 56, 26, 288
    for i, (label, key, ic) in enumerate(ROWS):
        y = top + i * pitch
        value = num(d[key])
        body.append(icon(ic, 16, y + 1, t["accent"]))
        body.append(R.text(label, 40, y + 5, 2, t["text2"]))
        body.append(right(value, edge, y, 3, t["text"]))
        x0 = 40 + R.text_w(label, 2) + 8
        x1 = edge - R.text_w(value, 3) - 8
        dots = [(x, 0) for x in range(x0, x1 - 1, 6)]
        if dots:
            body.append(f'<path d="{rects(dots, 0, y + 13, 2, 2)}" fill="{t["line"]}"/>')

    cells, lit = ring(progress)
    body.append(f'<path d="{R.path_d(set(cells), RING_X, RING_Y, RING_CELL)}" fill="{t["levels"][0]}"/>')
    for k, (gx, gy) in enumerate(cells[:lit]):
        when = (0.2 + 1.0 * k / max(lit, 1)) / T
        body.append(
            f'<rect x="{RING_X + gx * RING_CELL}" y="{RING_Y + gy * RING_CELL}" width="{RING_CELL}" height="{RING_CELL}" '
            f'fill="{t["accent"]}"><animate attributeName="opacity" calcMode="discrete" dur="{T}s" fill="freeze" '
            f'keyTimes="0;{R.fmt(when)}" values="0;1"/></rect>')
    cx, cy = RING_X + RING_N * RING_CELL // 2, RING_Y + RING_N * RING_CELL // 2
    s = 6 if len(level) == 1 else 5
    body.append(R.text(level, cx - R.text_w(level, s) // 2, cy - 22, s, t["accent"]))
    body.append(R.text("RANK", cx - R.text_w("RANK", 2) // 2, cy + 12, 2, t["muted"]))

    label = (f"GitHub stats: {d['stars']} stars earned, {d['commits']} commits, {d['prs']} pull requests, "
             f"{d['issues']} issues, contributed to {d['contrib']} repositories in the last year, rank {level}.")
    return wrap(body, label).replace("THEME_LINE", t["line"])


# ---------------------------------------------------------------- languages card
BAR_X, BAR_CELLS, BAR_PITCH, BAR_H = 196, 28, 6, 10


def langs_card(d, theme):
    t = THEMES[theme]
    colors = LANG_COLORS[theme]
    body = frame(t, "TOP/LANGUAGES", "BY SIZE")
    defs, top, pitch = [], 56, 22
    peak = max((p for _, p in d["langs"]), default=1) or 1
    for i, (name, pct) in enumerate(d["langs"]):
        y = top + i * pitch
        col = colors[i % len(colors)]
        body.append(f'<rect x="16" y="{y + 1}" width="8" height="8" fill="{col}"/>')
        body.append(R.text(clean(name, 150), 32, y, 2, t["text"]))
        body.append(right(f"{pct:.2f}%", W - 16, y, 2, t["text2"]))

        track = [(j * BAR_PITCH, 0) for j in range(BAR_CELLS)]
        body.append(f'<path d="{rects(track, BAR_X, y, BAR_PITCH - 1, BAR_H)}" fill="{t["levels"][0]}"/>')
        n = max(1, min(BAR_CELLS, round(pct / peak * BAR_CELLS)))
        start = 0.15 + 0.1 * i
        times = [0.0] + [(start + 0.7 * j / n) / T for j in range(1, n + 1)]
        widths = [0] + [j * BAR_PITCH for j in range(1, n + 1)]
        defs.append(
            f'<clipPath id="c{i}"><rect x="{BAR_X}" y="{y}" width="{n * BAR_PITCH}" height="{BAR_H}">'
            f'<animate attributeName="width" calcMode="discrete" dur="{T}s" fill="freeze" '
            f'keyTimes="{";".join(R.fmt(k) for k in times)}" values="{";".join(map(str, widths))}"/></rect></clipPath>')
        fill = [(j * BAR_PITCH, 0) for j in range(n)]
        body.append(f'<path clip-path="url(#c{i})" d="{rects(fill, BAR_X, y, BAR_PITCH - 1, BAR_H)}" fill="{col}"/>')

    names = ", ".join(f"{n} {p:.0f}%" for n, p in d["langs"])
    return wrap(body, f"Most used languages by code size: {names}.", "".join(defs)).replace("THEME_LINE", t["line"])


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "MrNicolass"))
    ap.add_argument("--out", default="dist")
    ap.add_argument("--data", help="JSON file with the numbers instead of calling the API")
    ap.add_argument("--sample", action="store_true", help="use the numbers of the old cards (preview only)")
    args = ap.parse_args()

    if args.sample:
        data = sample()
    elif args.data:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    else:
        token = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set (or pass --sample / --data)")
        data = fetch(args.user, token)

    level, pct = rank(data)
    print(f"rank {level} (percentile {pct:.1f}); " + ", ".join(f"{k}={data[k]}" for k in ("stars", "commits", "prs", "issues", "contrib")))
    print("langs: " + ", ".join(f"{n} {p}%" for n, p in data["langs"]))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for name, build in (("stats", stats_card), ("langs", langs_card)):
            svg = build(data, theme)
            n = R.validate(svg)
            path = out / f"{name}-{theme}.svg"
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path} ({path.stat().st_size:,} bytes, {n} animations validated)")


if __name__ == "__main__":
    main()
