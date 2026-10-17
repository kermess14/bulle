"""Détection des cases d'une planche, pour la lecture case par case.

Deux détecteurs complémentaires, sans réseau de neurones ni dépendance :

1. **Gouttières** (« X-Y cut ») : on cherche les bandes de fond uni (blanc ou noir) qui traversent la
   planche de part en part, horizontalement puis verticalement dans chaque bande, et ainsi de suite.
   C'est ce qui découpe les planches classiques (gaufrier, bandes, cases décalées).
2. **Cadres** : les traits noirs rectilignes des cadres de cases. Repérer les quatre côtés d'un
   rectangle permet de retrouver les cases *incrustées* sur une grande image (pas de gouttière autour),
   les cases posées sur un fond qui va jusqu'au bord de la page, etc.

Le résultat du premier est affiné par le second. Une pleine page, un fond sans gouttière ni cadre ou
une mise en page très libre donnent « pas de case » : le lecteur montre alors la page entière.
"""
from __future__ import annotations

import re
from typing import Optional

from PIL import Image, ImageOps

PANELS_VERSION = 3        # à augmenter quand la détection change (les cases gardées en base sont alors recalculées)
WORK_WIDTH = 800          # largeur de travail (px) : assez fine pour les traits de cadre et les gouttières minces
GUTTER_FRACTION = 0.965   # part de pixels « fond » pour qu'une ligne soit une gouttière
BG_TOLERANCE = 46         # écart de gris toléré autour de la couleur de fond
MIN_GUTTER = 0.003        # largeur minimale d'une gouttière (fraction du grand côté, au moins 2 px)
MIN_PANEL = 0.055         # côté minimal d'une case (fraction de la dimension de la page)
MIN_AREA = 0.012          # surface minimale d'une case (fraction de la page) — élimine numéros, titres
PAD = 0.012               # marge ajoutée autour de chaque case (fraction de la page)
MAX_DEPTH = 5
# cadres
INK = 90                  # gris en dessous duquel un pixel est « encre »
FRAME_MIN_LEN = 0.07      # longueur minimale d'un trait de cadre (fraction de la largeur de page)
FRAME_MAX_THICK = 9       # épaisseur maximale d'un trait (px, à la largeur de travail)
FRAME_TOL = 7             # tolérance d'alignement entre les côtés d'un rectangle (px)
FRAME_MIN_W = 0.07        # taille minimale d'un rectangle (fractions de la page)
FRAME_MIN_H = 0.05


# ----------------------------------------------------------------------------
# 1. Gouttières
# ----------------------------------------------------------------------------
def _background_value(gray: Image.Image) -> int:
    """Couleur de fond : la plus fréquente sur le pourtour de la planche, en préférant le blanc (papier) ou le noir
    au dessin qui déborde jusqu'au bord (pleine page)."""
    w, h = gray.size
    b = max(2, min(w, h) // 60)
    hist = [0] * 256
    for box in ((0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)):
        for i, n in enumerate(gray.crop(box).histogram()):
            hist[i] += n
    total = sum(hist) or 1
    whites, blacks = sum(hist[200:]), sum(hist[:56])
    if whites >= 0.12 * total:
        return max(range(200, 256), key=lambda i: hist[i])
    if blacks >= 0.12 * total:
        return max(range(0, 56), key=lambda i: hist[i])
    return max(range(256), key=lambda i: hist[i])


def _mask(gray: Image.Image, bg: int) -> Image.Image:
    lut = [255 if abs(i - bg) <= BG_TOLERANCE else 0 for i in range(256)]
    return gray.point(lut, "L")


def _profile(mask: Image.Image, box: tuple, axis: int) -> list[float]:
    """Part de fond sur chaque ligne (axis=0 : lignes horizontales) ou colonne (axis=1) de la zone."""
    region = mask.crop(box)
    w, h = region.size
    if w == 0 or h == 0:
        return []
    small = region.resize((1, h) if axis == 0 else (w, 1), Image.Resampling.BOX)
    return [v / 255.0 for v in small.getdata()]


def _runs(profile: list[float]) -> list[tuple[int, int]]:
    """Plages [début, fin) de lignes « fond »."""
    out, start = [], None
    for i, v in enumerate(profile):
        if v >= GUTTER_FRACTION:
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i)); start = None
    if start is not None:
        out.append((start, len(profile)))
    return out


def _trim(mask: Image.Image, box: tuple) -> Optional[tuple]:
    """Enlève les marges de fond autour d'une zone ; None si la zone est entièrement du fond."""
    x0, y0, x1, y1 = box
    rows = _profile(mask, box, 0)
    top = next((i for i, v in enumerate(rows) if v < GUTTER_FRACTION), None)
    if top is None:
        return None
    bottom = next(i for i in range(len(rows) - 1, -1, -1) if rows[i] < GUTTER_FRACTION) + 1
    box = (x0, y0 + top, x1, y0 + bottom)
    cols = _profile(mask, box, 1)
    left = next((i for i, v in enumerate(cols) if v < GUTTER_FRACTION), None)
    if left is None:
        return None
    right = next(i for i in range(len(cols) - 1, -1, -1) if cols[i] < GUTTER_FRACTION) + 1
    return (x0 + left, box[1], x0 + right, box[3])


def _cut(mask: Image.Image, box: tuple, axis: int, min_gutter: int, min_side: int) -> list[tuple]:
    """Découpe la zone selon les gouttières traversantes (axis=0 : coupes horizontales)."""
    x0, y0, x1, y1 = box
    prof = _profile(mask, box, axis)
    length = len(prof)
    cuts = [(a, b) for a, b in _runs(prof) if b - a >= min_gutter and a > 0 and b < length]
    if not cuts:
        return [box]
    parts, pos = [], 0
    for a, b in cuts:
        if a - pos >= min_side:
            parts.append((pos, a))
        pos = b
    if length - pos >= min_side:
        parts.append((pos, length))
    if len(parts) < 2:
        return [box]
    if axis == 0:
        return [(x0, y0 + a, x1, y0 + b) for a, b in parts]
    return [(x0 + a, y0, x0 + b, y1) for a, b in parts]


def _split(mask: Image.Image, box: tuple, axis: int, depth: int, min_gutter: int, min_side: int, rtl: bool) -> list[tuple]:
    box = _trim(mask, box)
    if box is None:
        return []
    parts = _cut(mask, box, axis, min_gutter, min_side)
    if len(parts) == 1:
        parts = _cut(mask, box, 1 - axis, min_gutter, min_side)   # rien dans ce sens : on essaie l'autre
        if len(parts) == 1:
            return [box]
        axis = 1 - axis
    if axis == 1 and rtl:
        parts = parts[::-1]
    if depth >= MAX_DEPTH:
        return [t for t in (_trim(mask, p) for p in parts) if t]
    out = []
    for p in parts:
        out.extend(_split(mask, p, 1 - axis, depth + 1, min_gutter, min_side, rtl))
    return out


# ----------------------------------------------------------------------------
# 2. Cadres (bords rectilignes de l'encre → rectangles)
# ----------------------------------------------------------------------------
_RUN_RE = re.compile(rb"\xff+(?:\x00{1,2}\xff+)*")   # trait continu, petits trous tolérés


def _edge_segments(edge: bytes, w: int, h: int, min_len: int) -> list[tuple[int, int, int]]:
    """Bords rectilignes : (y, x0, x1) — `edge` est un masque 255 = « ici l'encre commence/finit », ligne par ligne.
    Les bords de lignes consécutives aux extrémités proches sont fusionnés (un seul par bord)."""
    open_lines: list[list] = []   # [y0, y1, x0, x1]
    done: list[tuple[int, int, int]] = []
    for y in range(h):
        row = edge[y * w:(y + 1) * w]
        runs = [(m.start(), m.end()) for m in _RUN_RE.finditer(row) if m.end() - m.start() >= min_len]
        still, used = [], [False] * len(runs)
        for ln in open_lines:
            hit = next((i for i, (a, b) in enumerate(runs) if not used[i] and abs(a - ln[2]) <= FRAME_TOL and abs(b - ln[3]) <= FRAME_TOL), None)
            if hit is not None and ln[1] == y and y - ln[0] < 4:
                used[hit] = True
                ln[1] = y + 1; ln[2] = min(ln[2], runs[hit][0]); ln[3] = max(ln[3], runs[hit][1])
                still.append(ln)
            else:
                done.append((ln[0], ln[2], ln[3]))
        for i, (a, b) in enumerate(runs):
            if not used[i]:
                still.append([y, y + 1, a, b])
        open_lines = still
    done.extend((ln[0], ln[2], ln[3]) for ln in open_lines)
    return done


def _coverage(segments: list[tuple[int, int, int]], pos: int, a: int, b: int) -> float:
    """Part de [a, b) couverte par les bords situés à `pos` (± FRAME_TOL) : plusieurs morceaux (bulle qui coupe le trait,
    bord extérieur et bord intérieur d'un même trait) se complètent (union des intervalles)."""
    if b <= a:
        return 0.0
    parts = sorted((max(a, s0), min(b, s1)) for p, s0, s1 in segments if abs(p - pos) <= FRAME_TOL and s1 > a and s0 < b)
    covered, cur0, cur1 = 0, None, None
    for s0, s1 in parts:
        if cur1 is None or s0 > cur1:
            if cur1 is not None:
                covered += cur1 - cur0
            cur0, cur1 = s0, s1
        else:
            cur1 = max(cur1, s1)
    if cur1 is not None:
        covered += cur1 - cur0
    return min(1.0, covered / (b - a))


def _edges(ink: Image.Image) -> tuple[bytes, bytes]:
    """Masques des bords hauts (encre dont le pixel du dessus est clair) et bas (encre dont le pixel du dessous est clair)."""
    from PIL import ImageChops
    w, h = ink.size
    up = Image.new("L", (w, h), 0); up.paste(ink.crop((0, 0, w, h - 1)), (0, 1))      # ligne y-1 ramenée en y
    down = Image.new("L", (w, h), 0); down.paste(ink.crop((0, 1, w, h)), (0, 0))      # ligne y+1 ramenée en y
    top = ImageChops.subtract(ink, up)        # encre en y, pas en y-1
    bottom = ImageChops.subtract(ink, down)   # encre en y, pas en y+1
    return top.tobytes(), bottom.tobytes()


def _rects_from_edges(tops: list, bottoms: list, lefts: list, rights: list, w: int, h: int) -> list[tuple]:
    """Rectangles fermés : bord haut, bord bas, bord gauche, bord droit, chacun couvrant ≥ 85 % de son côté (à FRAME_TOL près).
    On part des paires de bords verticaux (gauche/droite), puis des paires horizontaux (haut/bas) : une bulle qui coupe un trait
    ne l'empêche pas d'être reconnu, ses morceaux s'additionnent."""
    min_w, min_h = FRAME_MIN_W * w, FRAME_MIN_H * h
    COV = 0.85
    found: list[tuple] = []

    def ys_near(segs: list, a: int, b: int) -> set[int]:
        """Positions (y ou x) des bords dont un morceau touche [a, b)."""
        return {p for p, s0, s1 in segs if s1 > a and s0 < b}

    # 1) paires gauche / droite
    for lx, ly0, ly1 in lefts:
        for rx, ry0, ry1 in rights:
            if rx - lx < min_w:
                continue
            y0, y1 = max(ly0, ry0), min(ly1, ry1)
            if y1 - y0 < min_h:
                continue
            for ty in sorted(ys_near(tops, lx, rx + 1)):
                if ty < y0 - FRAME_TOL or ty > y1 - min_h:
                    continue
                if _coverage(tops, ty, lx, rx + 1) < COV:
                    continue
                for by in sorted(ys_near(bottoms, lx, rx + 1)):
                    if by < ty + min_h or by > y1 + FRAME_TOL:
                        continue
                    if _coverage(bottoms, by, lx, rx + 1) < COV:
                        continue
                    if _coverage(lefts, lx, ty, by + 1) < COV or _coverage(rights, rx, ty, by + 1) < COV:
                        continue
                    found.append((lx, ty, rx + 1, by + 1))
    # 2) paires haut / bas
    for ty, tx0, tx1 in tops:
        for by, bx0, bx1 in bottoms:
            if by - ty < min_h:
                continue
            x0, x1 = max(tx0, bx0), min(tx1, bx1)
            if x1 - x0 < min_w:
                continue
            for lx in sorted(ys_near(lefts, ty, by + 1)):
                if lx < x0 - FRAME_TOL or lx > x1 - min_w or _coverage(lefts, lx, ty, by + 1) < COV:
                    continue
                for rx in sorted(ys_near(rights, ty, by + 1)):
                    if rx < lx + min_w or rx > x1 + FRAME_TOL or _coverage(rights, rx, ty, by + 1) < COV:
                        continue
                    if _coverage(tops, ty, lx, rx + 1) < COV or _coverage(bottoms, by, lx, rx + 1) < COV:
                        continue
                    found.append((lx, ty, rx + 1, by + 1))
    # un rectangle traversé par un bord vertical (ou horizontal) complet est en fait deux cases côte à côte : on le rejette
    def divided(r: tuple) -> bool:
        x0, y0, x1, y1 = r
        for segs, lo, hi, a, b in ((lefts, x0, x1, y0, y1), (rights, x0, x1, y0, y1)):
            for pos in {p for p, s0, s1 in segs if lo + 2 * FRAME_TOL < p < hi - 2 * FRAME_TOL and s1 > a and s0 < b}:
                if _coverage(segs, pos, a, b) >= COV:
                    return True
        for segs in (tops, bottoms):
            for pos in {p for p, s0, s1 in segs if y0 + 2 * FRAME_TOL < p < y1 - 2 * FRAME_TOL and s1 > x0 and s0 < x1}:
                if _coverage(segs, pos, x0, x1) >= COV:
                    return True
        return False
    found = [r for r in {tuple(r) for r in found} if not divided(r)]
    # dédoublonnage : bord extérieur / intérieur d'un même trait, rectangles quasi identiques → on garde le plus grand
    found.sort(key=lambda r: -(r[2] - r[0]) * (r[3] - r[1]))
    kept: list[tuple] = []
    for r in found:
        ra = (r[2] - r[0]) * (r[3] - r[1])
        if not any(_inter(r, k) >= 0.8 * ra for k in kept):
            kept.append(r)
    return kept


def _ink_lines(ink: bytes, w: int, h: int, min_len: int) -> list[tuple[int, int, int]]:
    """Traits d'encre rectilignes : (y, x0, x1), une entrée par ligne de pixels (un trait épais en donne plusieurs,
    voisines). Un trait doit avoir du clair d'au moins un côté (sinon c'est l'intérieur d'un aplat sombre)."""
    out = []
    for y in range(h):
        row = ink[y * w:(y + 1) * w]
        for m in _RUN_RE.finditer(row):
            a, b = m.start(), m.end()
            if b - a < min_len:
                continue
            span = b - a
            light = False
            for dy in (-3, -5, 3, 5):
                yy = y + dy
                if 0 <= yy < h and ink[yy * w + a:yy * w + b].count(b"\xff") <= 0.4 * span:
                    light = True
                    break
            if light:
                out.append((y, a, b))
    return out


def detect_frames(gray: Image.Image) -> list[tuple]:
    """Rectangles dessinés par des traits d'encre (cadres de cases), en pixels de l'image donnée."""
    w, h = gray.size
    ink_img = gray.point([255 if i < INK else 0 for i in range(256)], "L")
    hl = _ink_lines(ink_img.tobytes(), w, h, max(8, int(FRAME_MIN_LEN * w)))
    vl = _ink_lines(ink_img.transpose(Image.Transpose.TRANSPOSE).tobytes(), h, w, max(8, int(FRAME_MIN_LEN * h * 0.7)))  # (x, y0, y1)
    return _rects_from_edges(hl, hl, vl, vl, w, h)


# ----------------------------------------------------------------------------
# 3. Combinaison
# ----------------------------------------------------------------------------
def _area(b: tuple) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _inter(a: tuple, b: tuple) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _reading_order(rects: list[tuple], rtl: bool) -> list[tuple]:
    """Lignes de cases (chevauchement vertical), de haut en bas ; dans une ligne de gauche à droite (ou l'inverse)."""
    rows: list[list[tuple]] = []
    for r in sorted(rects, key=lambda r: (r[1], r[0])):
        placed = False
        for row in rows:
            ref = row[0]
            overlap = min(r[3], ref[3]) - max(r[1], ref[1])
            if overlap > 0.5 * min(r[3] - r[1], ref[3] - ref[1]):
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])
    rows.sort(key=lambda row: min(r[1] for r in row))
    out = []
    for row in rows:
        row.sort(key=lambda r: r[0], reverse=rtl)
        out.extend(row)
    return out


def _refine_leaf(leaf: tuple, frames: list[tuple], w: int, h: int, rtl: bool) -> list[tuple]:
    """Une zone issue des gouttières, redécoupée d'après les cadres qu'elle contient (cases incrustées)."""
    la = _area(leaf)
    if la < 0.3 * w * h:
        return [leaf]   # une case ordinaire : un rectangle dessiné dedans (tableau, fenêtre) n'est pas une case
    inside = [f for f in frames if _area(f) and _inter(f, leaf) >= 0.9 * _area(f) and _area(f) < 0.92 * la]
    if not inside:
        return [leaf]
    # cadre unique couvrant presque toute la zone = la zone elle-même
    if len(inside) == 1 and _area(inside[0]) >= 0.7 * la:
        return [leaf]
    ordered = _reading_order(inside, rtl)
    bx0, by0 = min(f[0] for f in inside), min(f[1] for f in inside)
    bx1, by1 = max(f[2] for f in inside), max(f[3] for f in inside)
    # la partie de l'image qui reste visible autour des cadres : au-dessus, en dessous, à gauche, à droite
    bands = {
        "top": (leaf[0], leaf[1], leaf[2], by0), "bottom": (leaf[0], by1, leaf[2], leaf[3]),
        "left": (leaf[0], leaf[1], bx0, leaf[3]), "right": (bx1, leaf[1], leaf[2], leaf[3]),
    }
    name, band = max(bands.items(), key=lambda kv: _area(kv[1]))
    out = list(ordered)
    if _area(band) >= 0.2 * la and (band[2] - band[0]) >= MIN_PANEL * w and (band[3] - band[1]) >= MIN_PANEL * h:
        if name == "top" or (name == "left" and not rtl) or (name == "right" and rtl):
            out = [band] + out
        else:
            out = out + [band]
    return out


def detect_panels(img: Image.Image) -> dict:
    """Cases d'une planche : {"panels": [[x0, y0, x1, y1], …] (fractions, ordre occidental), "rtl": [indices, ordre manga]}."""
    gray = ImageOps.grayscale(img)
    if gray.width > WORK_WIDTH:
        gray = gray.resize((WORK_WIDTH, max(1, round(gray.height * WORK_WIDTH / gray.width))), Image.Resampling.BOX)
    w, h = gray.size
    bg = _background_value(gray)
    mask = _mask(gray, bg)
    min_gutter = max(2, int(max(w, h) * MIN_GUTTER))
    min_side = max(6, round(min(w, h) * MIN_PANEL))
    full = (0, 0, w, h)
    page_area = w * h
    try:
        frames = detect_frames(gray)
    except Exception:  # noqa: BLE001
        frames = []

    def leaves(rtl: bool) -> list[tuple]:
        # fond ni blanc ni noir (dessin jusqu'aux bords) : les gouttières n'ont pas de sens, seuls les cadres comptent
        res = (_split(mask, full, 0, 0, min_gutter, min_side, rtl) if (bg >= 200 or bg <= 55) else [full]) or [full]
        out: list[tuple] = []
        for leaf in res:
            out.extend(_refine_leaf(leaf, frames, w, h, rtl))
        return [b for b in out if _area(b) >= MIN_AREA * page_area]

    ltr = leaves(False)
    empty = {"panels": [], "rtl": [], "v": PANELS_VERSION}
    if len(ltr) < 2:
        return empty
    if max(_area(b) for b in ltr) > 0.85 * page_area:
        return empty
    rtl = leaves(True)
    pad_x, pad_y = PAD * w, PAD * h

    def rel(b: tuple) -> list[float]:
        return [round(max(0.0, (b[0] - pad_x) / w), 4), round(max(0.0, (b[1] - pad_y) / h), 4),
                round(min(1.0, (b[2] + pad_x) / w), 4), round(min(1.0, (b[3] + pad_y) / h), 4)]

    panels = [rel(b) for b in ltr]
    index = {tuple(rel(b)): i for i, b in enumerate(ltr)}
    order = [index.get(tuple(rel(b)), i) for i, b in enumerate(rtl)]
    if sorted(order) != list(range(len(panels))):
        order = list(range(len(panels)))
    return {"panels": panels, "rtl": order, "v": PANELS_VERSION}
