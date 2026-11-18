#!/usr/bin/env python3
"""Generate the profile README panels: hero card, project tiles, headings, stack labels and buttons.

GitHub strips CSS from READMEs, so every styled panel is an SVG image. Each panel is
written twice (dark and light) and README.md picks one with <picture> and
prefers-color-scheme. The aurora and the tile art are ordered-dithered (Bayer 8x8)
pixel art embedded as PNG, and all text is converted to vector outlines, so the files
render the same everywhere and depend on no font or third-party host.

Setup (one time):
    pip install numpy pillow fonttools brotli
    npm install --no-save geist          # Geist Sans / Geist Mono, SIL OFL 1.1

Usage:
    python scripts/build_assets.py       # or: GEIST_DIR=/path/to/geist/dist/fonts python ...
    (it imports scripts/build_runner.py for the 3x5 pixel font, so run it from a normal checkout)

Edit the DATA section, run the script and commit the files in assets/.
"""

import base64
import io
import os
import sys
from pathlib import Path

import numpy as np
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_runner import text as pixel_text, text_w as pixel_text_w  # built-in 3x5 pixel font

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(os.environ.get("GEIST_DIR", ROOT / "node_modules" / "geist" / "dist" / "fonts"))

CELL = 5  # one dither pixel = 5x5 px, so every image width below is a multiple of 8 cells


# --------------------------------------------------------------------------- DATA

HANDLE = "MrNicolass"
NAME = "Nicolas Conte"
ROLE = "Full stack developer."
STATUS = "WELCOME TO MY WONDERLAND"

# Only what appears nowhere else on the page: the stack lives in the badge table, the projects in the tiles
# and the handle in the title bar, so the hero keeps just these lines.
HERO_LINES = [("Based in", "Brazil"), ("Stack", "React + Java"), ("Also", "desktop apps, local LLMs, games")]

TILES = [
    {
        "slug": "naji",
        "index": "1",
        "name": "naji",
        "kind": "desktop",
        "lines": ["Tray-first voice assistant for Windows", "and Linux, driven by a global hotkey."],
        "meta": [("Language", "Python"), ("UI", "PySide6"), ("Runs on", "Win · Linux")],
        "repo": "MrNicolass/naji",
        "art": "waveform",
        "ramp": "violet",
        "seed": 11,
    },
    {
        "slug": "react-portfolio",
        "index": "2",
        "name": "react-portfolio",
        "kind": "web",
        "lines": ["Personal portfolio on Next.js 16, React 19", "and Tailwind 4, with locale detection."],
        "meta": [("Language", "TypeScript"), ("Framework", "Next.js 16"), ("Styling", "Tailwind 4")],
        "repo": "MrNicolass/react-portfolio",
        "art": "site",
        "ramp": "blue",
        "seed": 23,
    },
]

# One pixel label per row of the stack section; the badges next to it are shields.io images in README.md.
STACK_ROWS = [("languages", "LANGUAGES", "code"), ("frontend", "FRONTEND", "window"), ("backend", "BACKEND", "server"),
              ("tools", "TOOLS", "prompt"), ("desktop-ai", "DESKTOP/AI", "chip")]

HEADINGS = [("projects", "PROJECTS"), ("stack", "STACK"), ("activity", "ACTIVITY"), ("contact", "CONTACT")]

# ------------------------------------------------------------------------- THEMES

THEMES = {
    "dark": {
        "card": "#0a0d12",
        "line": "#232a34",
        "text": "#e6edf3",
        "text2": "#9da7b3",
        "muted": "#6e7681",
        "accent": "#a371f7",
        "on_accent": "#0d1117",
        "ramps": {
            "violet": ["#0a0d12", "#1b1646", "#43299b", "#8957e5", "#d6c2ff"],
            "blue": ["#0a0d12", "#0f1f3f", "#173f7d", "#388bfd", "#cfe6ff"],
        },
    },
    "light": {
        "card": "#f6f8fa",
        "line": "#d0d7de",
        "text": "#1f2328",
        "text2": "#4b5560",
        "muted": "#7a8490",
        "accent": "#8250df",
        "on_accent": "#ffffff",
        "ramps": {
            "violet": ["#f6f8fa", "#e9dfff", "#cbb2ff", "#a371f7", "#6a3fd1"],
            "blue": ["#f6f8fa", "#dcebff", "#a9cdff", "#58a6ff", "#0b5fcf"],
        },
    },
}

# ---------------------------------------------------------------------------- TEXT


class Face:
    """A TrueType face that turns strings into SVG path outlines."""

    def __init__(self, filename):
        self.font = TTFont(FONT_DIR / filename)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]

    def _glyph(self, ch):
        name = self.cmap.get(ord(ch))
        assert name, f"missing glyph for {ch!r}"
        return name

    def width(self, text, size, tracking=0.0):
        s = size / self.upm
        return sum(self.hmtx[self._glyph(c)][0] * s + tracking for c in text)

    def path(self, text, x, y, size, fill, anchor="start", tracking=0.0):
        if anchor == "end":
            x -= self.width(text, size, tracking) - tracking
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        s = size / self.upm
        cursor = x
        for ch in text:
            g = self._glyph(ch)
            self.glyphs[g].draw(TransformPen(pen, (s, 0, 0, -s, cursor, y)))
            cursor += self.hmtx[g][0] * s + tracking
        return f'<path d="{pen.getCommands()}" fill="{fill}"/>'


def faces():
    return {
        "light": Face("geist-sans/Geist-Light.ttf"),
        "sans": Face("geist-sans/Geist-Regular.ttf"),
        "mono": Face("geist-mono/GeistMono-Regular.ttf"),
        "monob": Face("geist-mono/GeistMono-Medium.ttf"),
        "pixel": Face("geist-pixel/GeistPixel-Square.woff2"),
    }


# -------------------------------------------------------------------------- PIXELS


def bayer(n=8):
    m = np.array([[0]])
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n)


def dither(intensity, ramp, cell=CELL):
    """Quantize a 0..1 field to len(ramp) colors with an 8x8 Bayer matrix; returns PNG data URI."""
    rows, cols = intensity.shape
    thr = np.tile(bayer(8), (rows // 8 + 1, cols // 8 + 1))[:rows, :cols]
    level = np.clip(np.floor(np.clip(intensity, 0, 1) * (len(ramp) - 1) + thr), 0, len(ramp) - 1)
    img = Image.fromarray(level.astype("uint8"), "P")
    img.putpalette([int(c[i : i + 2], 16) for c in ramp for i in (1, 3, 5)])
    img = img.resize((cols * cell, rows * cell), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def periodic_noise(rng, cols, lo, hi, decay):
    """Smooth noise that tiles seamlessly across `cols` (integer harmonics only)."""
    x = np.arange(cols) / cols
    out = np.zeros(cols)
    for k in range(lo, hi + 1):
        out += rng.uniform(0.4, 1.0) / (k**decay) * np.sin(2 * np.pi * (k * x + rng.random()))
    out -= out.min()
    return out / out.max()


def aurora_field(cols, rows, seed, base=0.64):
    """Curtains of light: a wavy bright core with rays of random height rising above it."""
    rng = np.random.default_rng(seed)
    y = (np.arange(rows)[:, None] + 0.5) / rows
    center = base + 0.09 * (periodic_noise(rng, cols, 1, 3, 1.0) - 0.5) * 2
    rays = periodic_noise(rng, cols, 6, 40, 0.55) ** 1.4
    glow = 0.45 + 0.55 * periodic_noise(rng, cols, 2, 9, 0.8)
    height = 0.16 + 0.50 * rays
    d = center[None, :] - y
    above = (np.exp(-np.clip(d, 0, None) / height[None, :]) * glow[None, :]) ** 0.7
    below = np.exp(-np.clip(-d, 0, None) / 0.045) * 0.85
    core = 0.5 * np.exp(-((d / 0.035) ** 2))
    field = np.where(d >= 0, above, below) + core
    field *= np.clip(y / 0.18, 0, 1) ** 0.8  # keep the very top dark
    return np.clip(field, 0, 1)


def waveform_field(cols, rows, seed):
    """A voice waveform: mirrored bars that swell in the middle, over a soft glow."""
    rng = np.random.default_rng(seed)
    x = (np.arange(cols)[None, :] + 0.5) / cols
    y = (np.arange(rows)[:, None] + 0.5) / rows
    field = 0.06 + 0.26 * np.exp(-(((x - 0.5) / 0.5) ** 2 + ((y - 0.5) / 0.6) ** 2))
    mid = rows / 2
    for c in range(8, cols - 8):
        if c % 3 == 2:  # one blank column between bars
            continue
        xx = (c + 0.5) / cols
        env = np.exp(-(((xx - 0.5) / 0.27) ** 2)) * (0.45 + 0.55 * rng.random())
        half = 1.5 + env * (rows * 0.36)
        for r in range(rows):
            off = abs(r + 0.5 - mid)
            if off <= half:
                field[r, c] = 0.55 + 0.45 * (1 - off / half)
    return np.clip(field, 0, 1)


def site_field(cols, rows, seed):
    """A tiny website wireframe: nav, hero text, a glowing sphere and project cards."""
    y = (np.arange(rows)[:, None] + 0.5) / rows
    field = np.tile(0.05 + 0.10 * y, (1, cols))

    def block(c0, c1, r0, r1, v):
        field[r0:r1, c0:c1] = np.maximum(field[r0:r1, c0:c1], v)

    block(4, cols - 4, 2, 5, 0.26)  # nav bar
    block(6, 14, 3, 4, 0.85)  # logo
    for c in (56, 64, 72):
        block(c, c + 5, 3, 4, 0.5)  # menu items
    block(6, 44, 9, 13, 0.82)  # title
    block(6, 34, 15, 17, 0.42)  # subtitle
    block(6, 18, 20, 23, 1.0)  # call to action
    yy, xx = np.mgrid[0:rows, 0:cols]
    r = np.sqrt(((xx - 66) / 13.0) ** 2 + ((yy - 14) / 7.5) ** 2)
    field = np.maximum(field, np.clip(1.05 - r, 0, 1) * 0.95)  # glowing sphere
    for c0 in (6, 33, 60):
        block(c0, c0 + 22, 25, rows, 0.5)  # project cards
        block(c0, c0 + 22, 25, 26, 0.8)  # card highlight
    return np.clip(field, 0, 1)


ART = {"waveform": waveform_field, "site": site_field}

# ----------------------------------------------------------------------------- SVG


def svg(w, h, defs, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{title}">\n<title>{title}</title>\n<defs>{defs}</defs>\n{body}\n</svg>\n'
    )


def line(x1, y1, x2, y2, t):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{t["line"]}" stroke-width="1" shape-rendering="crispEdges"/>'


def border(w, h, t, edges="tlbr"):
    parts = []
    if "t" in edges:
        parts.append(line(0, 0.5, w, 0.5, t))
    if "b" in edges:
        parts.append(line(0, h - 0.5, w, h - 0.5, t))
    if "l" in edges:
        parts.append(line(0.5, 0, 0.5, h, t))
    if "r" in edges:
        parts.append(line(w - 0.5, 0, w - 0.5, h, t))
    return "".join(parts)


def arrow(x, y, s, color):
    """Small north-east arrow with its top-left corner at (x, y)."""
    return (
        f'<path d="M{x} {y + s} L{x + s} {y} M{x + s * 0.2} {y} H{x + s} V{y + s * 0.8}" fill="none" '
        f'stroke="{color}" stroke-width="1.4" stroke-linecap="square"/>'
    )


def style(shift=896, steps=112):
    return (
        "<style>"
        f"@keyframes drift{{to{{transform:translateX(-{shift}px)}}}}"
        f".drift{{animation:drift 120s steps({steps}) infinite}}"
        "@keyframes blink{0%,60%{opacity:1}61%,100%{opacity:.25}}"
        ".blink{animation:blink 1.6s steps(1) infinite}"
        "@media (prefers-reduced-motion:reduce){.drift,.blink{animation:none}}"
        "</style>"
    )


# -------------------------------------------------------------------------- PANELS


# The white kitten. Only the fill is drawn here: shading (right and bottom edges) and the outline are added by cat_cells().
# W fur, p inner ear, e eye, n nose, c collar.
CAT = [
    "..W........W..",
    ".WpW......WpW.",
    ".WWWWWWWWWWWW.",
    ".WWWWWWWWWWWW.",
    ".WWeeWWWWeeWW.",
    ".WWeeWWWWeeWW.",
    ".WWWWWnnWWWWW.",
    "..WWWWWWWWWW..",
    "..cccccccccc..",
    ".WWWWWWWWWWW.W",
    ".WWWWWWWWWWW.W",
    ".WWWWWWWWWWW.W",
    ".WWWWWWWWWWWWW",
    ".WWWW..WWWWWWW",
]
assert {len(r) for r in CAT} == {14}
CAT_COLORS = {
    "dark": {"W": "#f4f6ff", "w": "#b9c1e6", "o": "#5a6391", "e": "#161a33", "n": "#ff8fb1", "p": "#ffb3c8", "c": "#f0883e"},
    "light": {"W": "#ffffff", "w": "#cdd3ea", "o": "#2f3556", "e": "#161a33", "n": "#ff7ea3", "p": "#ffb3c8", "c": "#f0883e"},
}
BANNER = (110, 25, 8)  # cols, rows, px per cell: an 880 x 200 scene
CAT_AT = (80, 8)  # column and row of the kitten's top-left fill cell


def rgb(colour):
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))


def cat_cells():
    cells = {(x, y): ch for y, row in enumerate(CAT) for x, ch in enumerate(row) if ch != "."}
    out = dict(cells)
    for (x, y), k in cells.items():
        if k == "W" and ((x + 1, y) not in cells or (x, y + 1) not in cells):
            out[(x, y)] = "w"
    for x, y in cells:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            out.setdefault((x + dx, y + dy), "o")
    return out


def banner_foreground(theme):
    """Everything in front of the drifting aurora, as one transparent PNG: moon, two hills and the kitten."""
    t, pal = THEMES[theme], CAT_COLORS[theme]
    cols, rows, cell = BANNER
    thr = bayer(8)
    rgba = np.zeros((rows, cols, 4), "uint8")
    xs = np.arange(cols)
    yy, xx = np.mgrid[0:rows, 0:cols] + 0.5

    moon = (np.hypot(xx - 13, yy - 7) < 4.2) & (np.hypot(xx - 15.3, yy - 6.1) > 3.6)
    rgba[moon] = (*rgb(t["ramps"]["violet"][4]), 255)

    ramp = t["ramps"]["blue"]
    far_v, near_v = (0.40, 0.22) if theme == "dark" else (0.44, 0.72)
    far = 17.2 + 1.8 * np.sin(xs / 9 + 1) + 0.9 * np.sin(xs / 3.7)
    near = 21.2 + 1.0 * np.sin(xs / 6.5 + 2.2) + 0.6 * np.sin(xs / 2.9)
    for top, v in ((far, far_v), (near, near_v)):
        for x in xs:
            for y in range(int(np.ceil(top[x])), rows):
                lvl = int(np.clip(np.floor(v * (len(ramp) - 1) + thr[y % 8, x % 8]), 0, len(ramp) - 1))
                rgba[y, x] = (*rgb(ramp[lvl]), 255)

    ox, oy = CAT_AT
    oy = int(round(near[ox + 6])) - 13  # paws rest on the near hill
    for (x, y), key in cat_cells().items():
        rgba[oy + y, ox + x] = (*rgb(pal[key]), 255)

    img = Image.fromarray(rgba, "RGBA").resize((cols * cell, rows * cell), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), (ox, oy)


def stars(theme, cat_at):
    """Small square stars as separate rects so a few of them can blink."""
    cols, rows, cell = BANNER
    rng = np.random.default_rng(3)
    colour, opacity = ("#e6edf3", 0.9) if theme == "dark" else ("#8250df", 0.55)
    out, n = [], 0
    while len(out) < 30:
        c, r = int(rng.integers(1, cols - 1)), int(rng.integers(0, 15))
        if np.hypot(c - 13, r - 7) < 6 or (cat_at[0] - 3 <= c <= cat_at[0] + 17 and r >= cat_at[1] - 3):
            continue
        big = len(out) % 6 == 0  # every sixth star is a small plus that blinks
        blink = f' class="blink" style="animation-delay:-{(n * 0.37) % 1.6:.2f}s"' if big else ""
        if big:
            n += 1
            x, y = c * cell, r * cell
            out.append(
                f'<path d="M{x + 2} {y}h4v2h2v4h-2v2h-4v-2h-2v-4h2z" fill="{colour}" fill-opacity="{opacity}"{blink}/>'
            )
        else:
            out.append(f'<rect x="{c * cell + 2}" y="{r * cell + 2}" width="4" height="4" fill="{colour}" fill-opacity="{opacity}"/>')
    return "".join(out)


def hero(theme, f):
    """One card: title bar, a pixel-art banner (aurora, moon, hills, white kitten), the name and a few lines."""
    t = THEMES[theme]
    w, top, band, body_h = 880, 36, 200, 150
    grid = top + band
    h = grid + body_h
    au = dither(aurora_field(896 // 8, band // 8, seed=7, base=0.60), t["ramps"]["violet"], cell=8)
    fg, cat_at = banner_foreground(theme)
    defs = (
        style()
        + f'<image id="au" href="{au}" width="896" height="{band}" style="image-rendering:pixelated"/>'
        + f'<clipPath id="band"><rect width="{w}" height="{band}"/></clipPath>'
    )
    px = 5
    icon = (  # four pixels, one of them blinking
        f'<rect x="92" y="12" width="{px}" height="{px}" fill="{t["accent"]}"/>'
        f'<rect x="{92 + px + 2}" y="12" width="{px}" height="{px}" fill="{t["accent"]}" fill-opacity=".55"/>'
        f'<rect x="92" y="{12 + px + 2}" width="{px}" height="{px}" fill="{t["accent"]}" fill-opacity=".55"/>'
        f'<rect class="blink" x="{92 + px + 2}" y="{12 + px + 2}" width="{px}" height="{px}" fill="{t["accent"]}"/>'
    )
    body = [
        f'<rect width="{w}" height="{h}" fill="{t["card"]}"/>',
        f["monob"].path("nicolas", 16, 23, 13, t["text"]),
        icon,
        f["mono"].path(STATUS, 114, 23, 12, t["text2"], tracking=1.0),
        f["mono"].path(f"github.com/{HANDLE}", w - 16, 23, 12.5, t["muted"], anchor="end"),
        line(0, top - 0.5, w, top - 0.5, t),
        f'<g transform="translate(0 {top})"><g clip-path="url(#band)"><g class="drift">'
        f'<use href="#au"/><use href="#au" x="896"/></g></g>'
        f'{stars(theme, cat_at)}<image href="{fg}" width="{w}" height="{band}" style="image-rendering:pixelated"/></g>',
        line(0, grid - 0.5, w, grid - 0.5, t),
        f["pixel"].path(NAME, 24, grid + 84, 58, t["text"]),
        f["sans"].path(ROLE, 26, grid + 120, 17, t["text2"]),
        line(476.5, grid, 476.5, h, t),
    ]

    x0, x_end = 508, w - 28
    mono = f["mono"]
    adv = mono.width(".", 13)
    for i, (key, value) in enumerate(HERO_LINES):
        y = grid + 44 + i * 28
        head = f".{key}:"
        dots = int(round((x_end - x0 - mono.width(head, 13) - mono.width(value, 13)) / adv))
        body += [
            mono.path(".", x0, y, 13, t["muted"]),
            mono.path(f"{key}:", x0 + adv, y, 13, t["accent"]),
            mono.path("." * dots, x0 + mono.width(head, 13), y, 13, t["muted"]),
            mono.path(value, x_end, y, 13, t["text"], anchor="end"),
        ]
    y = grid + 44 + len(HERO_LINES) * 28 + 6
    body += [
        f["monob"].path("›", x0, y + 4, 15, t["accent"]),
        f'<rect class="blink" x="{x0 + 14}" y="{y - 9}" width="8" height="15" fill="{t["accent"]}"/>',
        border(w, h, t),
    ]
    alt = (
        f"{NAME}, {ROLE} {STATUS.title()}. Pixel-art banner of a white kitten wearing an orange collar, sitting on a hill "
        "under an aurora and a crescent moon. " + ". ".join(f"{a}: {b}" for a, b in HERO_LINES) + "."
    )
    return svg(w, h, defs, "".join(body), alt)


def tile(spec, theme, edges, f):
    t = THEMES[theme]
    w, h, bar, art_h = 440, 370, 32, 170
    ramp = t["ramps"][spec["ramp"]]
    art = dither(ART[spec["art"]](w // CELL, art_h // CELL, spec["seed"]), ramp)
    y_art, y_desc, y_meta, y_cta = bar, bar + art_h, bar + art_h + 72, bar + art_h + 72 + 52
    defs = f'<image id="art" href="{art}" width="{w}" height="{art_h}" style="image-rendering:pixelated"/>'
    body = [
        f'<rect width="{w}" height="{h}" fill="{t["card"]}"/>',
        f'<use href="#art" y="{y_art}"/>',
        line(bar - 0.5, 0, bar - 0.5, bar, t),
        f["monob"].path(spec["index"], 12.5, 21, 13, t["accent"]),
        f["monob"].path(spec["name"], 46, 21, 13, t["text"]),
        f["mono"].path(spec["kind"], w - 16, 21, 12, t["muted"], anchor="end"),
        line(0, bar - 0.5, w, bar - 0.5, t),
        line(0, y_desc - 0.5, w, y_desc - 0.5, t),
    ]
    for i, text in enumerate(spec["lines"]):
        body.append(f["sans"].path(text, 16, y_desc + 31 + i * 23, 15, t["text"] if i == 0 else t["text2"]))
    body += [line(0, y_meta - 0.5, w, y_meta - 0.5, t), line(0, y_cta - 0.5, w, y_cta - 0.5, t)]
    cell = w / 3
    for i, (label, value) in enumerate(spec["meta"]):
        x = i * cell + 16
        if i:
            body.append(line(round(i * cell) - 0.5, y_meta, round(i * cell) - 0.5, y_cta, t))
        body.append(f["mono"].path(label, x, y_meta + 21, 11, t["muted"]))
        body.append(f["mono"].path(value, x, y_meta + 41, 13.5, t["text"]))
    bw, bh = 118, 28
    bx, by = w - 16 - bw, y_cta + (h - y_cta - bh) / 2
    body += [
        f["mono"].path(f"github.com/{spec['repo']}", 16, y_cta + 27, 12, t["muted"]),
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{t["accent"]}"/>',
        f["monob"].path("view repo", bx + 14, by + 18.5, 12.5, t["on_accent"]),
        arrow(bx + bw - 24, by + 9, 9, t["on_accent"]),
        border(w, h, t, edges),
    ]
    alt = f'{spec["name"]} ({spec["kind"]}): ' + " ".join(spec["lines"]) + " " + ", ".join(f"{a} {b}" for a, b in spec["meta"]) + "."
    return svg(w, h, defs, "".join(body), alt)


def rects(cells, px, ox, oy, fill):
    """Merge pixel cells into horizontal runs and emit one path for the whole icon."""
    d = []
    for y in sorted({c[1] for c in cells}):
        xs = sorted(c[0] for c in cells if c[1] == y)
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is None or x != prev + 1:
                d.append(f"M{ox + start * px} {oy + y * px}h{(prev - start + 1) * px}v{px}h-{(prev - start + 1) * px}z")
                start = x
            prev = x
    return f'<path d="{"".join(d)}" fill="{fill}"/>'


def icon_cells(kind, n=13):
    c, r = (n - 1) / 2, (n - 1) / 2
    cells = set()
    for y in range(n):
        for x in range(n):
            dx, dy = x - c, y - c
            if kind == "globe":
                ring = abs(np.hypot(dx, dy) - r) < 0.6
                meridian = abs((dx / 3.0) ** 2 + (dy / r) ** 2 - 1) < 0.35 and np.hypot(dx, dy) < r
                equator = y == n // 2 and np.hypot(dx, dy) < r
                if ring or meridian or equator:
                    cells.add((x, y))
            elif kind == "mail":
                if 2 <= y <= 10 and 0 <= x <= 12:
                    edge = y in (2, 10) or x in (0, 12)
                    flap = y <= 2 + min(x, 12 - x) and y >= 3 and y <= 7 and abs(y - 2 - min(x, 12 - x)) < 0.5
                    if edge or flap:
                        cells.add((x, y))
    return cells


STACK_ICONS = {  # 9 x 7 pixels, original generic glyphs
    "code": [".....X...", "..X..XX..", ".X..X..X.", "X...X...X", ".X..X..X.", "..XX..X..", "...X....."],
    "window": ["XXXXXXXXX", "X.......X", "XXXXXXXXX", "X.......X", "X.XXX...X", "X.......X", "XXXXXXXXX"],
    "server": ["XXXXXXXXX", "X.....X.X", "XXXXXXXXX", ".........", "XXXXXXXXX", "X.....X.X", "XXXXXXXXX"],
    "prompt": [".........", "X........", ".X.......", "..X......", ".X.......", "X..XXXXX.", "........."],
    "chip": [".X.X.X.X.", "XXXXXXXXX", "X.......X", "X..XXX..X", "X.......X", "XXXXXXXXX", ".X.X.X.X."],
}


def stack_chip(label, icon, theme):
    """A 20px tall pixel tag (same height as a flat-square badge) that sits at the start of a badge row."""
    t = THEMES[theme]
    w, h, n = 132, 20, 2
    shade = t["ramps"]["violet"][2] if theme == "dark" else "#5a32a3"

    def shape(height):
        return f"M{n} 0H{w - n}V{n}H{w}V{height - n}H{w - n}V{height}H{n}V{height - n}H0V{n}H{n}Z"

    cells = {(x, y) for y, row in enumerate(STACK_ICONS[icon]) for x, ch in enumerate(row) if ch == "X"}
    body = (
        f'<path d="{shape(h)}" fill="{shade}"/><path d="{shape(h - 2)}" fill="{t["accent"]}"/>'
        + rects(cells, 2, 9, 2, t["on_accent"])
        + pixel_text(label, 36, 4, 2, t["on_accent"])
    )
    return svg(w, h, "", body, label.title())


def heading(label, index, theme, f):
    t = THEMES[theme]
    w, h = 880, 44
    body = [
        f["pixel"].path(index, 2, 29, 20, t["accent"]),
        f["pixel"].path(label, 48, 29, 24, t["text"], tracking=1.0),
    ]
    x = 48 + f["pixel"].width(label, 24, 1.0) + 18
    n = int((w - 28 - x) // 10)
    for i in range(n):  # dotted rule that fades to the right
        op = 0.9 - 0.75 * i / max(n - 1, 1)
        body.append(f'<rect x="{x + i * 10:.0f}" y="21" width="4" height="4" fill="{t["muted"]}" fill-opacity="{op:.2f}"/>')
    body.append(rects({(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}, 4, w - 14, 15, t["accent"]))  # tiny pixel star
    return svg(w, h, "", "".join(body), label)


BUTTONS = [  # (slug, label, value, icon, accent dark, accent light)
    ("website", "WEBSITE", "imconte.com", "globe", "#a371f7", "#8250df"),
    ("linkedin", "LINKEDIN", "in/nicolasgconteti", "in", "#58a6ff", "#0969da"),
    ("email", "EMAIL", "say hello", "mail", "#f0883e", "#bc4c00"),
]


def button(spec, theme, f):
    slug, label, value, icon, ad, al = spec
    t = THEMES[theme]
    accent = ad if theme == "dark" else al
    w, h, n = 294, 66, 4  # n = notch size of the pixel corners
    shape = f"M{n} 0H{w - n}V{n}H{w}V{h - n}H{w - n}V{h}H{n}V{h - n}H0V{n}H{n}Z"
    ox, oy, px = 24, 15, 3
    if icon == "in":
        glyph = [
            f'<rect x="{ox}" y="{oy}" width="39" height="39" fill="{accent}"/>',
            f["pixel"].path("in", ox + (39 - f["pixel"].width("in", 26)) / 2, oy + 29, 26, t["card"]),
        ]
    else:
        glyph = [rects(icon_cells(icon), px, ox, oy, accent)]
    body = [
        f'<path d="{shape}" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="2"/>',
        f'<rect x="{n}" y="{h - 7}" width="{w - 2 * n}" height="4" fill="{accent}"/>',
        f'<rect x="{n}" y="3" width="{w - 2 * n}" height="2" fill="{t["text"]}" fill-opacity=".08"/>',
        *glyph,
        f["pixel"].path(label, 78, 30, 18, t["text"], tracking=1.0),
        f["mono"].path(value, 78, 48, 12, t["muted"]),
    ]
    return svg(w, h, "", "".join(body), f"{label.title()}: {value}")


# --------------------------------------------------------------------------- MAIN


def main():
    ASSETS.mkdir(exist_ok=True)
    f = faces()
    count = 0
    for theme in THEMES:
        out = {f"hero-{theme}.svg": hero(theme, f)}
        for i, spec in enumerate(TILES):
            edges = "tlb" if i < len(TILES) - 1 else "tlbr"
            out[f"tile-{spec['slug']}-{theme}.svg"] = tile(spec, theme, edges, f)
        for i, (slug, label) in enumerate(HEADINGS):
            out[f"heading-{slug}-{theme}.svg"] = heading(label, f"{i + 1:02d}", theme, f)
        for slug, label, icon in STACK_ROWS:
            out[f"stack-{slug}-{theme}.svg"] = stack_chip(label, icon, theme)
        for spec in BUTTONS:
            out[f"btn-{spec[0]}-{theme}.svg"] = button(spec, theme, f)
        for name, content in out.items():
            (ASSETS / name).write_text(content, encoding="utf-8")
            count += 1
    print(f"wrote {count} files to {ASSETS}")


if __name__ == "__main__":
    main()
