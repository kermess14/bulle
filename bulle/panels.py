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

Version 6, mise au point sur 74 planches réelles de 52 albums de styles variés (franco-belge, manga, roman graphique,
comics, noir et blanc, aquarelle) :
- gouttière « barrée » par une bulle ou un cartouche à cheval sur deux cases : acceptée si ses bords sont ceux de cases
  (rectilignes, du dessin juste au-dessus et juste au-dessous) et si ce qui la barre est petit et au milieu (une grande
  case sur deux rangées qui la traverse n'est pas une bulle) ;
- cases « posées » sur le fond (bords nets avec le blanc sur les quatre côtés) : trouvées même quand une case voisine
  déborde jusqu'au bord de la page ; elles sont alors effacées et le reste est redécoupé, ce qui fait apparaître la
  grande image de fond (avec cases incrustées) comme une case à part entière ;
- une légende sous une case ou une ligne de crédits (bande mince et surtout claire) n'est pas une case.
"""
from __future__ import annotations

import re
from typing import Optional

from PIL import Image, ImageOps

PANELS_VERSION = 6        # à augmenter quand la détection change (les cases gardées en base sont alors recalculées)
FRAME_BUDGET = 150_000    # nombre maximal de tests de couverture pour chercher les cadres (borne le temps sur une page chargée)
WORK_WIDTH = 800          # largeur de travail (px) : assez fine pour les traits de cadre et les gouttières minces
GUTTER_FRACTION = 0.965   # part de pixels « fond » pour qu'une ligne soit une gouttière
PARTIAL_GUTTER = 0.55     # gouttière « barrée » (bulle, cartouche ou décor qui déborde dessus) : lignes candidates…
PARTIAL_MIN = 0.6         # … part de fond minimale sur toute l'épaisseur…
PARTIAL_MAX = 0.05        # … épaisseur maximale (fraction de la longueur coupée)…
EDGE_ALIGN = 0.8          # … et part de ses colonnes de fond bordées de dessin des deux côtés (bords de cases rectilignes)
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


def _edge_ratios(mask: Image.Image, box: tuple, axis: int, a: int, b: int, blockers: bool = False):
    """Bande [a, b) d'une zone (axis=0 : lignes) : part des colonnes entièrement « fond » dans la bande, et parmi elles,
    part de celles qui ont du dessin juste avant et juste après la bande (à 4 px près). Une vraie gouttière est bordée
    par les bords des cases sur toute sa longueur ; un blanc à l'intérieur d'une case (ciel, intérieur d'un cartouche)
    ne l'est pas."""
    region = mask.crop(box)
    if axis == 1:
        region = region.transpose(Image.Transpose.TRANSPOSE)
    w, h = region.size
    if w == 0 or b <= a:
        return 0.0, 0.0, 0.0
    data = region.tobytes()
    band = [255] * w
    for y in range(a, b):
        row = data[y * w:(y + 1) * w]
        band = [min(p, q) for p, q in zip(band, row)]
    def content(rows: range) -> list[bool]:
        out = [False] * w
        for y in rows:
            if 0 <= y < h:
                row = data[y * w:(y + 1) * w]
                out = [o or v == 0 for o, v in zip(out, row)]
        return out
    above, below = content(range(a - 4, a)), content(range(b, b + 4))
    cols = [i for i in range(w) if band[i] == 255]
    if not cols:
        return (0.0, 0.0, 0.0, False) if blockers else (0.0, 0.0, 0.0)
    ratios = (len(cols) / w, sum(above[i] for i in cols) / len(cols), sum(below[i] for i in cols) / len(cols))
    if not blockers:
        return ratios
    # ce qui barre la gouttière doit être une bulle ou un cartouche : au milieu, et court. Un obstacle qui touche un bout
    # de la bande est une case qui la traverse (grande case sur deux rangées) : alors ce n'est pas une gouttière.
    end = max(2, round(0.03 * w))
    ok, i = True, 0
    big = 0
    while i < w:
        if band[i] != 255:
            j = i
            while j < w and band[j] != 255:
                j += 1
            at_end = i < end or j > w - end
            big += (j - i) > 0.1 * w
            if j - i > (0.12 if at_end else 0.25) * w or big > 1:   # deux gros obstacles : des cases qui traversent
                ok = False
                break
            i = j
        else:
            i += 1
    return ratios + (ok,)


def _text_strip(mask: Image.Image, box: tuple, axis: int, a: int, b: int, length: int) -> bool:
    """La bande de part ou d'autre d'une gouttière barrée est-elle une ligne de texte (légende sous une case, crédits) ?
    Mince et surtout claire : alors ce n'est pas une case, on ne coupe pas."""
    from PIL import ImageStat
    x0, y0, x1, y1 = box
    thin = max(6, round(0.12 * length))
    for lo, hi in ((max(0, a - thin), a), (b, min(length, b + thin))):
        side = (x0, y0 + lo, x1, y0 + hi) if axis == 0 else (x0 + lo, y0, x0 + hi, y1)
        whole = (lo == 0 or hi == length)
        if whole and ImageStat.Stat(mask.crop(side)).mean[0] >= 0.55 * 255:
            return True
    return False


def _cut(mask: Image.Image, box: tuple, axis: int, min_gutter: int, min_side: int) -> list[tuple]:
    """Découpe la zone selon les gouttières traversantes (axis=0 : coupes horizontales). Une gouttière peut être
    « barrée » par une bulle ou un cartouche à cheval sur deux cases, si ses bords sont ceux de cases (rectilignes) ;
    une bande blanche bordée de blanc d'un côté (ciel) n'est pas une gouttière."""
    x0, y0, x1, y1 = box
    prof = _profile(mask, box, axis)
    length = len(prof)
    cuts = []
    runs, start = [], None
    for i, v in enumerate(prof + [0.0]):
        if v >= PARTIAL_GUTTER:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i)); start = None
    for a, b in runs:
        if b - a < min_gutter or a == 0 or b >= length:
            continue
        # la plus longue suite de lignes franches (≥ 96,5 % de fond) dans la bande
        sa = sb = None
        i = a
        while i < b:
            if prof[i] >= GUTTER_FRACTION:
                j = i
                while j < b and prof[j] >= GUTTER_FRACTION:
                    j += 1
                if sa is None or j - i > sb - sa:
                    sa, sb = i, j
                i = j
            else:
                i += 1
        if sa is not None and sb - sa >= min_gutter:
            cuts.append((sa, sb))
            continue
        if b - a > max(min_gutter, PARTIAL_MAX * length):
            continue
        frac, up, down, blocked_ok = _edge_ratios(mask, box, axis, a, b, blockers=True)
        if frac >= PARTIAL_MIN and up >= EDGE_ALIGN and down >= EDGE_ALIGN and blocked_ok:
            if _text_strip(mask, box, axis, a, b, length):
                continue
            cuts.append((a, b))
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


class _Segs:
    """Bords (position, début, fin) indexés par position : la couverture à une position se calcule sans parcourir la liste."""
    __slots__ = ("items", "by_pos", "calls")

    def __init__(self, items: list[tuple[int, int, int]]):
        self.items = items
        self.by_pos: dict[int, list[tuple[int, int]]] = {}
        for p, s0, s1 in items:
            self.by_pos.setdefault(p, []).append((s0, s1))
        self.calls = 0

    def near(self, pos: int):
        for p in range(pos - FRAME_TOL, pos + FRAME_TOL + 1):
            lst = self.by_pos.get(p)
            if lst:
                yield from lst

    def __iter__(self):
        return iter(self.items)


def _coverage(segments, pos: int, a: int, b: int) -> float:
    """Part de [a, b) couverte par les bords situés à `pos` (± FRAME_TOL) : plusieurs morceaux (bulle qui coupe le trait,
    bord extérieur et bord intérieur d'un même trait) se complètent (union des intervalles)."""
    if b <= a:
        return 0.0
    if isinstance(segments, _Segs):
        segments.calls += 1
        parts = sorted((max(a, s0), min(b, s1)) for s0, s1 in segments.near(pos) if s1 > a and s0 < b)
    else:
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
    tops, bottoms, lefts, rights = (x if isinstance(x, _Segs) else _Segs(x) for x in (tops, bottoms, lefts, rights))
    budget = [FRAME_BUDGET]

    def spent() -> bool:
        used = tops.calls + bottoms.calls + lefts.calls + rights.calls
        return used > budget[0]

    def ys_near(segs, a: int, b: int) -> set[int]:
        """Positions (y ou x) des bords dont un morceau touche [a, b)."""
        return {p for p, s0, s1 in segs if s1 > a and s0 < b}

    # 1) paires gauche / droite
    for lx, ly0, ly1 in lefts:
        if spent():
            break
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
        if spent():
            break
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
    """Traits rectilignes : (y, x0, x1), une entrée par ligne de pixels (un trait épais en donne plusieurs, voisines).
    `ink` : masque 255 = pixel du trait (encre, ou au contraire fond clair). Un trait doit avoir « autre chose »
    d'au moins un côté (sinon c'est l'intérieur d'un aplat)."""
    out = []
    for y in range(h):
        row = ink[y * w:(y + 1) * w]
        for m in _RUN_RE.finditer(row):
            a, b = m.start(), m.end()
            if b - a < min_len:
                continue
            span = b - a
            other = False
            for dy in (-3, -5, 3, 5):
                yy = y + dy
                if 0 <= yy < h and ink[yy * w + a:yy * w + b].count(b"\xff") <= 0.4 * span:
                    other = True
                    break
            if other:
                out.append((y, a, b))
    return out


def _group_lines(lines: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Un trait de plusieurs pixels d'épaisseur donne une entrée par ligne : on les fusionne (position = milieu).
    Trop épais (> FRAME_MAX_THICK), ce n'est pas un trait mais une surface : on l'écarte."""
    lines.sort()
    out: list[tuple[int, int, int]] = []
    groups: list[list] = []   # [y0, y1, a, b]
    for y, a, b in lines:
        g = next((g for g in groups if g[1] == y and abs(g[2] - a) <= FRAME_TOL and abs(g[3] - b) <= FRAME_TOL), None)
        if g is not None:
            g[1] = y + 1; g[2] = min(g[2], a); g[3] = max(g[3], b)
        else:
            groups.append([y, y + 1, a, b])
        # les groupes terminés (dernière ligne < y) sortent de la liste active
        if len(groups) > 64:
            done, groups = [g for g in groups if g[1] < y], [g for g in groups if g[1] >= y]
            out.extend((g[0] + (g[1] - g[0]) // 2, g[2], g[3]) for g in done if g[1] - g[0] <= FRAME_MAX_THICK)
    out.extend((g[0] + (g[1] - g[0]) // 2, g[2], g[3]) for g in groups if g[1] - g[0] <= FRAME_MAX_THICK)
    return out


def _lines_of(mask_img: Image.Image) -> tuple[list, list]:
    w, h = mask_img.size
    hl = _group_lines(_ink_lines(mask_img.tobytes(), w, h, max(8, int(FRAME_MIN_LEN * w))))
    vl = _group_lines(_ink_lines(mask_img.transpose(Image.Transpose.TRANSPOSE).tobytes(), h, w, max(8, int(FRAME_MIN_LEN * h * 0.7))))  # (x, y0, y1)
    return hl, vl


def detect_frames(gray: Image.Image, bg_mask: Optional[Image.Image] = None) -> list[tuple]:
    """Rectangles dessinés par des traits : d'encre (cadres noirs), ou de fond clair (liserés et gouttières blancs
    autour de cases posées sur une grande image). Les deux familles de traits se combinent : un rectangle peut avoir
    un cadre noir sur trois côtés et une gouttière blanche sur le quatrième. En pixels de l'image donnée."""
    w, h = gray.size
    ink_img = gray.point([255 if i < INK else 0 for i in range(256)], "L")
    hl, vl = _lines_of(ink_img)
    if bg_mask is not None:
        hb, vb = _lines_of(bg_mask)
        hl, vl = hl + hb, vl + vb
    return _rects_from_edges(hl, hl, vl, vl, w, h)


def detect_boxes(mask: Image.Image) -> list[tuple]:
    """Cases « posées » sur le fond : rectangles de dessin dont les quatre côtés sont des bords nets avec le fond (blanc ou
    noir). Contrairement aux gouttières, ça ne demande pas que la séparation traverse toute la planche : une case bien
    entourée de blanc est trouvée même si sa voisine déborde jusqu'au bord de la page ou chevauche une autre case."""
    content = mask.point([255 if i < 128 else 0 for i in range(256)], "L")
    w, h = content.size
    top, bottom = _edges(content)
    left, right = _edges(content.transpose(Image.Transpose.TRANSPOSE))
    min_h, min_v = max(8, int(FRAME_MIN_LEN * w)), max(8, int(FRAME_MIN_LEN * h * 0.7))
    rects = _rects_from_edges(_edge_segments(top, w, h, min_h), _edge_segments(bottom, w, h, min_h),
                              _edge_segments(left, h, w, min_v), _edge_segments(right, h, w, min_v), w, h)
    # une case est surtout du dessin ; un cartouche ou une bulle (intérieur clair, couleur du fond) n'en est pas une
    from PIL import ImageStat
    return [r for r in rects if ImageStat.Stat(mask.crop(r)).mean[0] <= 0.45 * 255]


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


def _refine_leaf(leaf: tuple, frames, w: int, h: int, rtl: bool, mask: Optional[Image.Image] = None,
                 min_gutter: int = 2, min_side: int = 6) -> list[tuple]:
    """Une zone issue des gouttières, redécoupée d'après les cadres qu'elle contient (cases incrustées, cases bien
    entourées de fond dans une mise en page sans gouttière traversante). Quand les cadres sont sûrs, ils sont « effacés »
    et le reste de la zone est redécoupé par les gouttières : la grande case qui déborde jusqu'au bord de la page devient
    une case à part entière. `frames` : liste de cadres, ou fonction qui la calcule (appelée seulement pour une grande
    zone)."""
    la = _area(leaf)
    if la < 0.3 * w * h:
        return [leaf]   # une case ordinaire : un rectangle dessiné dedans (tableau, fenêtre) n'est pas une case
    if callable(frames):
        frames = frames()
    inside = [f for f in frames if _area(f) and _inter(f, leaf) >= 0.9 * _area(f) and _area(f) < 0.92 * la]
    if not inside:
        return [leaf]
    # cadre unique couvrant presque toute la zone = la zone elle-même
    if len(inside) == 1 and _area(inside[0]) >= 0.7 * la:
        return [leaf]
    if mask is not None:
        # cadres sûrs : assez grands, surtout du dessin (pas un cartouche ni une bulle), pas l'un dans l'autre
        from PIL import ImageStat
        sure = sorted((f for f in inside if _area(f) >= 0.025 * w * h and ImageStat.Stat(mask.crop(f)).mean[0] <= 0.7 * 255),
                      key=_area, reverse=True)
        outer: list[tuple] = []
        for f in sure:
            if not any(_inter(f, o) >= 0.6 * _area(f) for o in outer):
                outer.append(f)
        if outer and not (len(outer) == 1 and _area(outer[0]) >= 0.7 * la):
            rest_mask = mask.copy()
            for f in outer:
                rest_mask.paste(255, f)
            rest = [r for r in _split(rest_mask, leaf, 0, 0, min_gutter, min_side, rtl)
                    if _area(r) >= MIN_AREA * w * h and (r[2] - r[0]) >= MIN_PANEL * w and (r[3] - r[1]) >= MIN_PANEL * h]
            # le reste ne vaut que s'il se découpe en morceaux propres, à côté des cadres ; un morceau qui les englobe
            # (le reste n'est pas séparable) : on revient au découpage simple ci-dessous
            if all(sum(_inter(r, f) for f in outer) <= 0.25 * _area(r) and not any(_inter(r, f) >= 0.8 * _area(f) for f in outer)
                   for r in rest):
                return _reading_order(outer + rest, rtl)
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
    frames_cache: list = []

    def frames() -> list[tuple]:
        """Cadres dessinés : calcul coûteux, fait une seule fois et seulement si une grande zone (planche sans gouttières,
        grande image avec des cases incrustées) en a besoin ; une planche classique n'en a pas besoin."""
        if not frames_cache:
            found: list[tuple] = []
            try:
                found = detect_frames(gray, mask if (bg >= 200 or bg <= 55) else None)
            except Exception:  # noqa: BLE001
                pass
            if bg >= 200 or bg <= 55:
                try:
                    found = found + [b for b in detect_boxes(mask) if not any(_inter(b, f) >= 0.8 * max(_area(b), _area(f)) for f in found)]
                except Exception:  # noqa: BLE001
                    pass
            frames_cache.append(found)
        return frames_cache[0]

    def leaves(rtl: bool) -> list[tuple]:
        # fond ni blanc ni noir (dessin jusqu'aux bords) : les gouttières n'ont pas de sens, seuls les cadres comptent
        res = (_split(mask, full, 0, 0, min_gutter, min_side, rtl) if (bg >= 200 or bg <= 55) else [full]) or [full]
        out: list[tuple] = []
        for leaf in res:
            out.extend(_refine_leaf(leaf, frames, w, h, rtl, mask if (bg >= 200 or bg <= 55) else None, min_gutter, min_side))
        return [b for b in out if _area(b) >= MIN_AREA * page_area and (b[2] - b[0]) >= MIN_PANEL * w and (b[3] - b[1]) >= MIN_PANEL * h]

    ltr = leaves(False)
    empty = {"panels": [], "rtl": [], "v": PANELS_VERSION}
    if len(ltr) < 2:
        return empty
    if max(_area(b) for b in ltr) > 0.85 * page_area:
        return empty
    if sum(_area(b) for b in ltr) < 0.35 * page_area:
        return empty   # couverture, page de titre, crédits : quelques blocs isolés sur du vide, pas des cases
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
