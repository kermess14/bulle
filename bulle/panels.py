"""Détection des cases d'une planche, pour la lecture case par case.

Méthode « X-Y cut » : on cherche les gouttières (bandes de fond uni, blanches ou noires) qui traversent
la planche de part en part, d'abord horizontalement (lignes de cases), puis verticalement dans chaque
bande, et ainsi de suite. Pas de réseau de neurones : c'est rapide, sans dépendance, et ça marche bien
sur les planches classiques (gaufrier, bandes de hauteurs variables, cases décalées). Les pleines pages,
les fonds noirs sans gouttière ou les mises en page très libres donnent « pas de case » : le lecteur
montre alors la page entière.
"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageOps

WORK_WIDTH = 480          # largeur de travail (px) : suffisant pour voir les gouttières, rapide
GUTTER_FRACTION = 0.965   # part de pixels « fond » pour qu'une ligne soit une gouttière
BG_TOLERANCE = 46         # écart de gris toléré autour de la couleur de fond
MIN_GUTTER = 0.006        # largeur minimale d'une gouttière (fraction du grand côté)
MIN_PANEL = 0.055         # côté minimal d'une case (fraction de la dimension de la page)
MIN_AREA = 0.012          # surface minimale d'une case (fraction de la page) — élimine numéros, titres
PAD = 0.012               # marge ajoutée autour de chaque case (fraction de la page)
MAX_DEPTH = 5


def _background_value(gray: Image.Image) -> int:
    """Couleur de fond : la plus fréquente sur le pourtour de la planche (blanc le plus souvent, noir parfois)."""
    w, h = gray.size
    b = max(2, min(w, h) // 60)
    hist = [0] * 256
    for box in ((0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)):
        for i, n in enumerate(gray.crop(box).histogram()):
            hist[i] += n
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


def detect_panels(img: Image.Image) -> dict:
    """Cases d'une planche : {"panels": [[x0, y0, x1, y1], …] (fractions, ordre occidental), "rtl": [indices, ordre manga]}."""
    gray = ImageOps.grayscale(img)
    if gray.width > WORK_WIDTH:
        gray = gray.resize((WORK_WIDTH, max(1, round(gray.height * WORK_WIDTH / gray.width))), Image.Resampling.BOX)
    w, h = gray.size
    bg = _background_value(gray)
    mask = _mask(gray, bg)
    min_gutter = max(2, round(max(w, h) * MIN_GUTTER))
    min_side = max(6, round(min(w, h) * MIN_PANEL))
    full = (0, 0, w, h)

    def leaves(rtl: bool) -> list[tuple]:
        res = _split(mask, full, 0, 0, min_gutter, min_side, rtl)
        return [b for b in res if (b[2] - b[0]) * (b[3] - b[1]) >= MIN_AREA * w * h]

    ltr = leaves(False)
    if len(ltr) < 2:
        return {"panels": [], "rtl": []}
    page_area = w * h
    if len(ltr) == 1 or max((b[2] - b[0]) * (b[3] - b[1]) for b in ltr) > 0.85 * page_area:
        return {"panels": [], "rtl": []}
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
    return {"panels": panels, "rtl": order}
