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

from PIL import Image, ImageChops, ImageOps, ImageStat

PANELS_VERSION = 13       # à augmenter quand la détection change (les cases gardées en base sont alors recalculées)
FRAME_BUDGET = 150_000    # nombre maximal de tests de couverture pour chercher les cadres (borne le temps sur une page chargée)
WORK_WIDTH = 800          # largeur de travail (px) : assez fine pour les traits de cadre et les gouttières minces
GUTTER_FRACTION = 0.965   # part de pixels « fond » pour qu'une ligne soit une gouttière
PARTIAL_GUTTER = 0.55     # gouttière « barrée » (bulle, cartouche ou décor qui déborde dessus) : lignes candidates…
PARTIAL_MIN = 0.6         # … part de fond minimale sur toute l'épaisseur…
PARTIAL_MIN_PX = 4        # … épaisseur minimale en pixels (à la largeur de travail)
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
    # part de fond dans la bande, colonne par colonne : un cartouche (lettres sur du blanc) en garde beaucoup, une case
    # dessinée qui traverse presque pas
    mean = [0] * w
    for y in range(a, b):
        row = data[y * w:(y + 1) * w]
        mean = [m + (v == 255) for m, v in zip(mean, row)]
    ok, i = True, 0
    big = 0
    while i < w:
        if band[i] != 255:
            j = i
            while j < w and band[j] != 255:
                j += 1
            at_end = i < end or j > w - end
            caption = not at_end and sum(mean[i:j]) >= 0.5 * (j - i) * (b - a)
            big += (j - i) > 0.1 * w and not caption
            if j - i > (0.12 if at_end else 0.4 if caption else 0.25) * w or big > 1:   # deux gros obstacles : des cases qui traversent
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


def _walled(mask: Image.Image, box: tuple, axis: int, a: int, b: int) -> bool:
    """La bande blanche [a, b) est-elle fermée aux deux bouts par un trait continu (le cadre d'une case qui la traverse) ?
    C'est alors l'intérieur d'une bulle ou d'un ciel blanc, coupé par le cadre de la case, pas une gouttière : une vraie
    gouttière reste ouverte à ses bouts (elle rejoint la marge ou une autre gouttière)."""
    x0, y0, x1, y1 = box
    band = (x0, y0 + a, x1, y0 + b) if axis == 0 else (x0 + a, y0, x0 + b, y1)
    cols = _profile(mask, band, 1 - axis)   # part de fond dans chaque colonne de la bande (en travers)
    if len(cols) < 12:
        return False
    def wall(seq) -> bool:
        return any(v <= 0.2 for v in seq)
    # (au bord même de la page, un trait sombre est un défaut de numérisation, pas un cadre)
    lo_edge, hi_edge = (x0, x1) if axis == 0 else (y0, y1)
    size = mask.width if axis == 0 else mask.height
    if not (lo_edge > 1 and hi_edge < size - 1 and wall(cols[:4]) and wall(cols[-4:])):
        return False
    # une gouttière entre deux cases est bordée de leurs bords (du dessin juste au-dessus et juste au-dessous sur presque
    # toute sa longueur), même quand le cadre d'une case voisine la ferme à un bout ; le blanc d'une bulle non
    _, up, down = _edge_ratios(mask, box, axis, a, b)
    return min(up, down) < 0.5


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
            if not _walled(mask, box, axis, sa, sb):
                cuts.append((sa, sb))
            continue
        if b - a > max(min_gutter, PARTIAL_MAX * length) or b - a < PARTIAL_MIN_PX:
            continue   # (trop mince : un trait clair du décor, une ligne de plafond, pas une gouttière)
        frac, up, down, blocked_ok = _edge_ratios(mask, box, axis, a, b, blockers=True)
        if not blocked_ok:
            # les bords de la bande sont parfois mordus par le trait de cadre (anticrénelage) : on regarde son cœur
            core = [i for i in range(a, b) if prof[i] >= 0.9]
            if len(core) >= PARTIAL_MIN_PX - 1 and core[-1] - core[0] + 1 == len(core):
                f2, u2, d2, blocked_ok = _edge_ratios(mask, box, axis, core[0], core[-1] + 1, blockers=True)
            elif len(core) == 2 and core[1] == core[0] + 1:
                # gouttière de deux pixels entre deux cadres très rapprochés : acceptée seulement si elle est nette
                # (presque entièrement blanche) et bordée de dessin sur presque toute sa longueur
                f2, u2, d2, ok2 = _edge_ratios(mask, box, axis, core[0], core[1] + 1, blockers=True)
                if ok2 and f2 >= 0.95 and min(u2, d2) >= 0.85:
                    frac, up, down, blocked_ok = f2, u2, d2, True
        elif frac < PARTIAL_MIN:
            # une colonne d'anticrénelage au bord de la bande (moins claire que la gouttière) : la bande sans elle
            top = max(prof[a:b])
            core = [i for i in range(a, b) if prof[i] >= top - 0.08]
            if len(core) >= PARTIAL_MIN_PX and core[-1] - core[0] + 1 == len(core) and len(core) < b - a:
                frac, up, down, blocked_ok = _edge_ratios(mask, box, axis, core[0], core[-1] + 1, blockers=True)
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


def _dark_split(mask: Image.Image, box: tuple, depth: int, min_gutter: int, min_side: int, rtl: bool) -> list[tuple]:
    """Découpage par les gouttières d'un masque où le noir pur compte aussi pour du fond, mais prudent : une gouttière
    noire doit être mince et bordée de dessin (ni noir ni blanc) des deux côtés sur presque toute sa longueur ; une
    grande zone noire à l'intérieur d'une case (nuit, silhouette) ne coupe rien."""
    box = _trim(mask, box)
    if box is None:
        return []
    if depth >= 4:
        return [box]
    for axis in (0, 1):
        parts = _cut(mask, box, axis, min_gutter, min_side)
        if len(parts) < 2:
            continue
        length = (box[3] - box[1]) if axis == 0 else (box[2] - box[0])
        ok = True
        for p, q in zip(parts, parts[1:]):
            a = (p[3] - box[1]) if axis == 0 else (p[2] - box[0])
            b = (q[1] - box[1]) if axis == 0 else (q[0] - box[0])
            if b - a > max(12, 0.03 * length):
                ok = False
                break
            _, up, down = _edge_ratios(mask, box, axis, a, b)
            if min(up, down) < 0.8:
                ok = False
                break
        if not ok:
            continue
        if axis == 1 and rtl:
            parts = parts[::-1]
        out = []
        for p in parts:
            out.extend(_dark_split(mask, p, depth + 1, min_gutter, min_side, rtl))
        return out
    return [box]


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


def _join_segments(items: list[tuple[int, int, int]], gap: int) -> list[tuple[int, int, int]]:
    """Bords d'un même trait coupés en morceaux (une bulle posée sur le cadre, une lettre qui le touche) : les morceaux
    alignés (à 2 px près) et séparés de moins de `gap` sont réunis en un seul bord, pour chercher les rectangles. La
    couverture de chaque côté reste mesurée sur les vrais morceaux."""
    out: list[tuple[int, int, int]] = []
    for p, s0, s1 in sorted(items, key=lambda t: (t[1], t[0])):
        for i, (q, a, b) in enumerate(out):
            if abs(q - p) <= 2 and s0 <= b + gap and s1 >= a - gap:
                out[i] = (q, min(a, s0), max(b, s1))
                break
        else:
            out.append((p, s0, s1))
    return out + list(items)


def _rects_from_edges(tops: list, bottoms: list, lefts: list, rights: list, w: int, h: int, cov: float = 0.85,
                      join: int = 0) -> list[tuple]:
    """Rectangles fermés : bord haut, bord bas, bord gauche, bord droit, chacun couvrant ≥ 85 % de son côté (à FRAME_TOL près).
    On part des paires de bords verticaux (gauche/droite), puis des paires horizontaux (haut/bas) : une bulle qui coupe un trait
    ne l'empêche pas d'être reconnu, ses morceaux s'additionnent."""
    min_w, min_h = FRAME_MIN_W * w, FRAME_MIN_H * h
    COV = cov
    found: list[tuple] = []
    if join:
        pairs_src = [_join_segments(list(x), join) for x in (tops, bottoms, lefts, rights)]
    tops, bottoms, lefts, rights = (x if isinstance(x, _Segs) else _Segs(x) for x in (tops, bottoms, lefts, rights))
    if join:
        p_tops, p_bottoms, p_lefts, p_rights = pairs_src
    else:
        p_tops, p_bottoms, p_lefts, p_rights = tops, bottoms, lefts, rights
    budget = [FRAME_BUDGET]

    def spent() -> bool:
        used = tops.calls + bottoms.calls + lefts.calls + rights.calls
        return used > budget[0]

    def ys_near(segs, a: int, b: int) -> set[int]:
        """Positions (y ou x) des bords dont un morceau touche [a, b)."""
        return {p for p, s0, s1 in segs if s1 > a and s0 < b}

    # 1) paires gauche / droite
    for lx, ly0, ly1 in p_lefts:
        if spent():
            break
        for rx, ry0, ry1 in p_rights:
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
    for ty, tx0, tx1 in p_tops:
        if spent():
            break
        for by, bx0, bx1 in p_bottoms:
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
                              _edge_segments(left, h, w, min_v), _edge_segments(right, h, w, min_v), w, h,
                              join=max(20, w // 20))
    # une case est surtout du dessin ; un cartouche ou une bulle (intérieur clair, couleur du fond) n'en est pas une
    from PIL import ImageStat
    return [r for r in rects if ImageStat.Stat(mask.crop(r)).mean[0] <= 0.45 * 255]


def detect_blobs(mask: Image.Image, leaf: tuple) -> list[tuple]:
    """Cases aux bords dessinés à main levée (traits qui ondulent, cases de biais) : aucune gouttière n'est droite, mais
    chaque case reste un bloc de dessin séparé des autres par le fond. On cherche ces blocs (taches connexes), après avoir
    rompu les ponts d'un ou deux pixels (deux cadres qui se frôlent). Liste vide si la zone ne se découpe pas ainsi."""
    from collections import deque
    from PIL import ImageFilter
    x0, y0, x1, y1 = leaf
    lw, lh = x1 - x0, y1 - y0
    if lw < 40 or lh < 40:
        return []
    sw, sh = max(1, lw // 2), max(1, lh // 2)
    content = mask.crop(leaf).point([255 if i < 128 else 0 for i in range(256)], "L")
    # réduit de moitié en gardant les traits fins (un cadre tracé à la plume fait un ou deux pixels)
    content = content.resize((sw, sh), Image.Resampling.BOX).point([255 if i >= 64 else 0 for i in range(256)], "L")
    data = bytearray(content.tobytes())
    seen = bytearray(len(data))
    comps = []
    for start in range(len(data)):
        if not data[start] or seen[start]:
            continue
        seen[start] = 1
        q = deque([start])
        n = 0
        bx0, by0, bx1, by1 = sw, sh, 0, 0
        while q:
            i = q.popleft()
            n += 1
            y, x = divmod(i, sw)
            if x < bx0: bx0 = x
            if x > bx1: bx1 = x
            if y < by0: by0 = y
            if y > by1: by1 = y
            for j in ((i - 1) if x > 0 else -1, (i + 1) if x < sw - 1 else -1, i - sw, i + sw):
                if 0 <= j < len(data) and data[j] and not seen[j]:
                    seen[j] = 1
                    q.append(j)
        comps.append((n, (bx0, by0, bx1 + 1, by1 + 1), start))
    page = mask.size[0] * mask.size[1]
    W, H = mask.size
    big = []
    for n, (a, b, c, d), seed in sorted(comps, reverse=True):
        box = (x0 + 2 * a - 2, y0 + 2 * b - 2, x0 + 2 * c + 2, y0 + 2 * d + 2)
        box = (max(x0, box[0]), max(y0, box[1]), min(x1, box[2]), min(y1, box[3]))
        if _area(box) < MIN_AREA * page or (box[2] - box[0]) < MIN_PANEL * W or (box[3] - box[1]) < MIN_PANEL * H:
            continue
        if 4 * n < 0.35 * _area(box):
            continue   # trop creux : un trait isolé, pas une case
        if any(_inter(box, o) >= 0.5 * _area(box) for o in big):
            continue   # détail à l'intérieur d'une case déjà trouvée
        # un bloc en L (plusieurs cases qui se touchent par un coin, une bulle) : on le redécoupe par ses propres
        # gouttières, les autres blocs effacés
        pieces = [box]
        crowded = any(_inter(box, o) > 0.1 * min(_area(box), _area(o)) for o in big) or any(
            _inter(box, (x0 + 2 * a2, y0 + 2 * b2, x0 + 2 * c2, y0 + 2 * d2)) > 0.1 * min(_area(box), 4 * (c2 - a2) * (d2 - b2))
            for n2, (a2, b2, c2, d2), _ in comps if n2 != n and 4 * n2 >= MIN_AREA * page and (a2, b2, c2, d2) != (a, b, c, d))
        if crowded and n < 0.8 * (c - a) * (d - b):
            only = bytearray(len(data))
            q = deque([seed])
            only[seed] = 255
            while q:
                i = q.popleft()
                y, x = divmod(i, sw)
                for j in ((i - 1) if x > 0 else -1, (i + 1) if x < sw - 1 else -1, i - sw, i + sw):
                    if 0 <= j < len(data) and data[j] and not only[j]:
                        only[j] = 255
                        q.append(j)
            blob = Image.frombytes("L", (sw, sh), bytes(only)).resize((lw, lh), Image.Resampling.NEAREST)
            blob = blob.filter(ImageFilter.MaxFilter(3))
            sub = mask.copy()
            # le fond partout, sauf le dessin de ce bloc
            sub.paste(255, (0, 0, W, H))
            sub.paste(mask.crop(leaf), (x0, y0), blob.point([255 if v else 0 for v in range(256)]))
            min_g = max(2, int(max(W, H) * MIN_GUTTER))
            min_s = max(6, round(min(W, H) * MIN_PANEL))
            parts = [r for r in _split(sub, box, 0, 0, min_g, min_s, False)
                     if _area(r) >= MIN_AREA * page and (r[2] - r[0]) >= MIN_PANEL * W and (r[3] - r[1]) >= MIN_PANEL * H]
            if len(parts) >= 2:
                pieces = parts
        big.extend(pieces)
    if len(big) < 2:
        return []
    # les blocs doivent être des cases côte à côte (peu de chevauchement) et couvrir l'essentiel de la zone dessinée
    for i, a in enumerate(big):
        for b in big[i + 1:]:
            if _inter(a, b) > 0.25 * min(_area(a), _area(b)):   # (cases de biais : leurs rectangles se recouvrent un peu)
                return []
    ux0, uy0 = min(b[0] for b in big), min(b[1] for b in big)
    ux1, uy1 = max(b[2] for b in big), max(b[3] for b in big)
    if sum(_area(b) for b in big) < 0.6 * _area((ux0, uy0, ux1, uy1)):
        return []
    return big


LINE_EDGE = 32            # écart de gris entre deux pixels de part et d'autre d'un bord net
LINE_COVER = 0.6          # part de la longueur de la zone que le bord doit couvrir (marges, bulles et cartouches tolérés)


def _edge_rows(gray: Image.Image, box: tuple, axis: int) -> list[float]:
    """Pour chaque ligne (axis=0) ou colonne (axis=1) de la zone : part de sa longueur où l'image change nettement de
    part et d'autre (un bord de case, quelle que soit sa couleur)."""
    region = gray.crop(box)
    if axis == 1:
        region = region.transpose(Image.Transpose.TRANSPOSE)
    w, h = region.size
    if w < 10 or h < 10:
        return []
    up = Image.new("L", (w, h), 0); up.paste(region.crop((0, 0, w, h - 2)), (0, 2))
    diff = ImageChops.difference(region, up).point([255 if i >= LINE_EDGE else 0 for i in range(256)], "L")
    return [v / 255.0 for v in diff.resize((1, h), Image.Resampling.BOX).getdata()]


def _line_cuts(gray: Image.Image, box: tuple, axis: int, min_side: int) -> list[tuple]:
    """Coupe une zone le long des bords de case rectilignes qui la traversent de part en part : deux bords parallèles
    rapprochés (le bas d'une case, le haut de la suivante), même quand la gouttière entre les deux n'est pas du fond
    (décor peint, couleur qui change en cours de page) et même si un cartouche la chevauche."""
    prof = _edge_rows(gray, box, axis)
    n = len(prof)
    rows = [i for i, v in enumerate(prof) if v >= LINE_COVER and i >= 3]
    # bords regroupés (un trait donne deux ou trois lignes voisines)
    edges, cur = [], []
    for i in rows:
        if cur and i - cur[-1] > 2:
            edges.append((cur[0], cur[-1] + 1)); cur = []
        cur.append(i)
    if cur:
        edges.append((cur[0], cur[-1] + 1))
    region = gray.crop(box)
    if axis == 1:
        region = region.transpose(Image.Transpose.TRANSPOSE)
    rw = region.size[0]
    cuts = []
    for (a0, a1), (b0, b1) in zip(edges, edges[1:]):
        gap = b0 - a1
        strong = max(max(prof[a0:a1]), max(prof[b0:b1])) >= 0.67   # au moins un des deux bords bien net
        if strong and 2 <= gap <= max(30, round(0.035 * n)) and a0 >= min_side and n - b1 >= min_side:
            # entre les deux bords, une gouttière : une bande unie sur l'essentiel de sa longueur (un cartouche peut la
            # chevaucher) ; deux traits d'un décor (plancher, poutre) ont du dessin entre eux
            band = region.crop((0, a1, rw, b0)).resize((rw, 1), Image.Resampling.BOX)
            vals = list(band.getdata())
            med = sorted(vals)[len(vals) // 2]
            if sum(1 for v in vals if abs(v - med) <= 28) >= 0.45 * len(vals):
                cuts.append((a0, b1))
    if not cuts:
        return [box]
    x0, y0, x1, y1 = box
    parts, pos = [], 0
    for a, b in cuts:
        if a - pos >= min_side:
            parts.append((pos, a))
            pos = b
    if n - pos >= min_side:
        parts.append((pos, n))
    if len(parts) < 2:
        return [box]
    if axis == 0:
        return [(x0, y0 + a, x1, y0 + b) for a, b in parts]
    return [(x0 + a, y0, x0 + b, y1) for a, b in parts]


def split_lines(gray: Image.Image, box: tuple, min_side: int, rtl: bool, depth: int = 0) -> list[tuple]:
    """Découpage récursif le long des bords rectilignes (rangées, puis cases de chaque rangée)."""
    if depth > 4:
        return [box]
    for axis in ((0, 1) if depth % 2 == 0 else (1, 0)):
        parts = _line_cuts(gray, box, axis, min_side)
        if len(parts) >= 2:
            if axis == 1 and rtl:
                parts = parts[::-1]
            out = []
            for p in parts:
                out.extend(split_lines(gray, p, min_side, rtl, depth + 1))
            return out
    return [box]


# ----------------------------------------------------------------------------
# 3. Combinaison
# ----------------------------------------------------------------------------
def _area(b: tuple) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _inter(a: tuple, b: tuple) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


ORDER_TOL = 0.2           # une case peut déborder de 20 % de sa taille au-delà d'une coupe (cases de biais)


def _reading_order(rects: list[tuple], rtl: bool) -> list[tuple]:
    """Ordre de lecture par coupes successives : d'abord une coupe horizontale que presque aucune case ne traverse (le
    haut avant le bas), sinon une coupe verticale (la gauche avant la droite, l'inverse en manga). Une grande case haute
    à droite de deux cases empilées est ainsi lue après elles. Sans coupe possible : lignes de cases."""
    if len(rects) <= 2:
        return _row_order(rects, rtl)
    for axis in (1, 0):   # 1 : coupe horizontale (y), 0 : verticale (x)
        lo, hi = (1, 3) if axis == 1 else (0, 2)
        for cut in sorted({r[hi] for r in rects}):
            above = [r for r in rects if r[hi] <= cut + ORDER_TOL * (r[hi] - r[lo])]
            below = [r for r in rects if r not in above]
            if not above or not below:
                continue
            if all(r[lo] >= cut - ORDER_TOL * (r[hi] - r[lo]) for r in below):
                first, second = (below, above) if (axis == 0 and rtl) else (above, below)
                return _reading_order(first, rtl) + _reading_order(second, rtl)
    return _row_order(rects, rtl)


def _row_order(rects: list[tuple], rtl: bool) -> list[tuple]:
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
    if mask is not None:
        # une rangée de cases posée sur une grande image (sans gouttière entre les deux) : une case de la rangée est
        # trouvée comme cadre, collée au bord haut (ou bas) de la zone ; sa hauteur donne celle de la rangée, que les
        # gouttières verticales découpent ; le reste de la zone est la grande image
        best: list[tuple] = []
        for f in inside:
            if _area(f) < 0.02 * w * h:
                continue
            for edge in ("top", "bottom"):
                if edge == "top" and abs(f[1] - leaf[1]) <= 10 and leaf[3] - f[3] >= min_side:
                    strip, rest_box = (leaf[0], leaf[1], leaf[2], f[3]), (leaf[0], f[3], leaf[2], leaf[3])
                elif edge == "bottom" and abs(f[3] - leaf[3]) <= 10 and f[1] - leaf[1] >= min_side:
                    strip, rest_box = (leaf[0], f[1], leaf[2], leaf[3]), (leaf[0], leaf[1], leaf[2], f[1])
                else:
                    continue
                pieces = [t for t in (_trim(mask, b) for b in _cut(mask, strip, 1, min_gutter, min_side)) if t]
                pieces = [b for b in pieces if _area(b) >= MIN_AREA * w * h and (b[2] - b[0]) >= MIN_PANEL * w]
                if len(pieces) >= 2 and len(pieces) > len(best) - 1:
                    rest_t = _trim(mask, rest_box)
                    rest_parts = []
                    if rest_t and _area(rest_t) >= MIN_AREA * w * h:
                        # le reste peut contenir d'autres cases (une autre rangée posée sur l'image) : même traitement
                        rest_parts = _refine_leaf(rest_t, inside, w, h, rtl, mask, min_gutter, min_side) \
                            if _area(rest_t) < la else [rest_t]
                    # le reste doit être une grande image : s'il contient lui-même plusieurs cadres de case qu'on n'a
                    # pas su séparer, c'est une planche ordinaire aux gouttières barrées, pas une rangée sur une image
                    framed = [g for g in inside if _area(g) >= 0.02 * w * h and _inter(g, rest_box) >= 0.8 * _area(g)]
                    if len(rest_parts) == 1 and len(framed) >= 2:
                        continue
                    cand = pieces + rest_parts
                    if len(cand) > len(best):
                        best = cand
        if best:
            return _reading_order(best, rtl)
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


# ----------------------------------------------------------------------------
# 4. Texte à cheval sur deux cases
# ----------------------------------------------------------------------------
BRIDGE_GAP = 0.08         # écart maximal entre deux cases voisines (fraction de la page)
BRIDGE_MIN = 0.012        # hauteur minimale de ce qui traverse la gouttière (fraction de la page) : une ligne de texte
BRIDGE_SIDE = 0.025       # profondeur regardée de chaque côté de la gouttière (fraction de la page)
BRIDGE_JOIN = 0.2         # le texte entre d'au moins 20 % dans chacune des deux cases : on les réunit ; sinon on élargit
                          # seulement la case qui porte le texte, pour qu'il ne soit plus coupé


def _paper_ink(img: Image.Image, size: tuple) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Masques à la taille de travail : « papier » (clair et presque sans couleur : fond d'une bulle, d'un cartouche),
    « encre » (lettres, traits) et « neutre » (sans couleur : papier, encre et leurs gris intermédiaires)."""
    small = img.convert("RGB").resize(size, Image.Resampling.BOX)
    r, g, b = small.split()
    lo = ImageChops.darker(ImageChops.darker(r, g), b)
    hi = ImageChops.lighter(ImageChops.lighter(r, g), b)
    chroma = ImageChops.subtract(hi, lo)
    neutral = chroma.point(lambda v: 255 if v <= 45 else 0)
    paper = ImageChops.multiply(lo.point(lambda v: 255 if v >= 190 else 0), neutral)
    ink = ImageOps.grayscale(small).point(lambda v: 255 if v < 110 else 0)
    # « neutre » : papier, encre et gris d'anticrénelage des lettres (pas de couleur de décor)
    return paper, ink, ImageChops.lighter(neutral, ink)


def _cols(img: Image.Image, box: tuple) -> list[float]:
    """Part de blanc (255) dans chaque colonne de la zone."""
    c = img.crop(box)
    if c.width == 0 or c.height == 0:
        return []
    return [v / 255.0 for v in c.resize((c.width, 1), Image.Resampling.BOX).getdata()]


def _rows(img: Image.Image, box: tuple) -> list[float]:
    c = img.crop(box)
    if c.width == 0 or c.height == 0:
        return []
    return [v / 255.0 for v in c.resize((1, c.height), Image.Resampling.BOX).getdata()]


def _text_lines(neutral: Image.Image, ink: Image.Image, box: tuple, anchor: int) -> int:
    """Nombre de lignes de lettres dans la bulle qui passe par la colonne `anchor` (le milieu de la gouttière) : des
    bandes de pixels où l'encre alterne souvent avec le papier (une lettre après l'autre), séparées par des interlignes
    de papier. Chaque ligne de pixels n'est lue que sur le morceau de papier continu qui traverse la gouttière (le
    décor autour est ignoré). Des hachures, de l'herbe ou des traits de vitesse ne laissent pas d'interligne propre."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w < 10 or h < 6 or not x0 <= anchor < x1:
        return 0
    idata, pdata = ink.crop(box).tobytes(), neutral.crop(box).tobytes()
    ax = anchor - x0
    texty, quiet = [], []
    for y in range(h):
        row, prow = idata[y * w:(y + 1) * w], pdata[y * w:(y + 1) * w]
        ok = [bool(row[x] or prow[x]) for x in range(w)]
        lo = hi = ax
        miss = 0
        while lo > 0 and miss <= 3:
            lo -= 1
            miss = 0 if ok[lo] else miss + 1
        lo += miss
        miss = 0
        while hi < w - 1 and miss <= 3:
            hi += 1
            miss = 0 if ok[hi] else miss + 1
        hi -= miss
        seg = hi - lo + 1
        if seg < 30:
            texty.append(False); quiet.append(False)
            continue
        spans, x = [], lo
        while x <= hi:
            if row[x]:
                e = x
                while e + 1 <= hi and row[e + 1]:
                    e += 1
                spans.append((x, e))
                x = e + 1
            else:
                x += 1
        # les traits qui touchent les bouts du morceau sont les bords de la bulle (ou le décor contre elle)
        inside = [(u, v) for u, v in spans if u > lo + 1 and v < hi - 1]
        texty.append(len(spans) >= max(4, seg // 24))
        quiet.append(len(inside) <= 1 and sum(v - u + 1 for u, v in inside) <= 0.05 * seg)   # interligne
    lines, y = 0, 0
    while y < h:
        if not texty[y]:
            y += 1
            continue
        a = y
        while y < h and not quiet[y]:
            y += 1
        if (a == 0 or quiet[a - 1]) and (y == h or quiet[y]) and 3 <= y - a <= 18 and sum(texty[a:y]) >= 0.4 * (y - a):
            lines += 1
    return lines


def _bridge(gray: Image.Image, mask: Image.Image, paper: Image.Image, ink: Image.Image, neutral: Image.Image,
            a: tuple, b: tuple, axis: int, bw: bool = False) -> Optional[dict]:
    """`a` puis `b`, voisines (axis=1 : côte à côte, a à gauche ; axis=0 : l'une sous l'autre, a en haut). Un cartouche
    ou une bulle passe-t-il de l'une à l'autre par-dessus la gouttière ? Renvoie None, ou {"grow": 0|1, "edge": x} :
    la case qui porte le texte (0 : a, 1 : b) et la coordonnée jusqu'où l'élargir pour qu'il ne soit plus coupé, avec
    "join": True si le texte est vraiment sur les deux cases (on les montre alors ensemble)."""
    W, H = gray.size
    neutral0, ink0 = neutral, ink   # sens d'origine : le texte se lit toujours en lignes horizontales
    valid0 = ImageChops.lighter(paper, ink)
    if axis == 0:   # on se ramène au cas « côte à côte » en transposant tout
        T = Image.Transpose.TRANSPOSE
        gray, mask, paper, ink, neutral = (im.transpose(T) for im in (gray, mask, paper, ink, neutral))
        a, b = (a[1], a[0], a[3], a[2]), (b[1], b[0], b[3], b[2])
        W, H = H, W
    g0, g1 = a[2], b[0]
    o0, o1 = max(a[1], b[1]), min(a[3], b[3])
    if g1 - g0 > BRIDGE_GAP * W or g1 - g0 < -2 or o1 - o0 < 0.25 * min(a[3] - a[1], b[3] - b[1]):
        return None
    # cœur de la gouttière : les colonnes les plus « fond » entre les deux cases (les traits de cadre exclus)
    lo, hi = max(0, g0 - 8), min(W, g1 + 8)
    cols = _cols(mask, (lo, o0, hi, o1))
    if not cols:
        return None
    best = max(cols)
    if best < 0.5:
        return None   # pas de vraie gouttière ici (cases séparées par leurs cadres seulement)
    core = [i for i, v in enumerate(cols) if v >= best - 0.05]
    c0, c1 = lo + core[0], lo + core[-1] + 1
    side = max(6, round(BRIDGE_SIDE * W))
    n = o1 - o0

    def frame_col(x_from: int, x_to: int) -> Optional[int]:
        """Trait de cadre vertical le long de la gouttière (colonne la plus encrée), s'il y en a un."""
        if x_to <= x_from:
            return None
        inks = _cols(ink, (x_from, o0, x_to, o1))
        k = max(range(len(inks)), key=lambda t: inks[t])
        return x_from + k if inks[k] >= 0.35 else None   # (en partie caché par la bulle elle-même)

    def crossing(fx: Optional[int], x_from: int, x_to: int) -> list[bool]:
        """Lignes où le côté est « recouvert » : le trait de cadre y disparaît sous du papier (bulle, cartouche posé
        dessus) ; sans cadre, le papier continue sur toute la bande regardée."""
        if fx is not None:
            inks = _rows(ink, (max(0, fx - 1), o0, min(W, fx + 2), o1))
            papers = _rows(paper, (fx, o0, fx + 1, o1))
            # une lettre posée sur l'emplacement du cadre : du papier juste avant et juste après
            before = _rows(paper, (max(0, fx - 3), o0, max(1, fx - 2), o1))
            after = _rows(paper, (min(W - 1, fx + 3), o0, min(W, fx + 4), o1))
            return [(iv == 0 and pv >= 1.0) or (bv >= 1.0 and av >= 1.0)
                    for iv, pv, bv, av in zip(inks, papers, before, after)]
        pv = _rows(paper, (max(0, x_from), o0, min(W, x_to), o1))
        nv = _rows(neutral, (max(0, x_from), o0, min(W, x_to), o1))
        return [p >= 0.4 and q >= 0.9 for p, q in zip(pv, nv)]   # papier et lettres seulement, pas de décor

    fa = frame_col(max(a[0], c0 - 10), c0)
    fb = frame_col(c1, min(b[2], c1 + 10))
    if bw and (fa is None or fb is None):
        return None   # noir et blanc : tout y est « papier et encre », seule une bulle qui cache un cadre est sûre
    ca = crossing(fa, c0 - side, c0)
    cb = crossing(fb, c1, c1 + side)
    inner = [x and y for x, y in zip(ca, cb)]

    valid = ImageChops.lighter(paper, ink)   # papier ou encre : l'intérieur d'une bulle, lettres comprises

    def reach(ya: int, yb: int, direction: int) -> int:
        """Jusqu'où va le papier (avec ses lettres) de ce côté-ci, ligne par ligne : la largeur du cartouche dans la case
        (une bulle ovale est plus étroite en haut et en bas : on garde les lignes les plus larges)."""
        if direction < 0:
            x_lo, x_hi = max(0, a[0]), c0
        else:
            x_lo, x_hi = c1, min(W, b[2])
        if x_hi <= x_lo:
            return 0
        reg = valid.crop((x_lo, o0 + ya, x_hi, o0 + yb))
        rw, rh = reg.size
        data = reg.tobytes()
        ext = []
        for yy in range(rh):
            if not inner[ya + yy]:
                continue   # seulement les lignes où la bulle passe par-dessus la gouttière
            row = data[yy * rw:(yy + 1) * rw]
            seq = row[::-1] if direction < 0 else row   # depuis la gouttière vers le fond de la case
            last, miss = 0, 0
            for k, v in enumerate(seq):
                if v:
                    last, miss = k + 1, 0
                else:
                    miss += 1
                    if miss > 3:
                        break
            if last < 0.95 * rw:   # une ligne qui va jusqu'au fond de la case : trait de cadre, pas une bulle
                ext.append(last)
        if len(ext) < 3:
            return rw   # pas de bout trouvé : rejeté plus bas (papier jusqu'au fond de la case)
        ext.sort()
        return ext[len(ext) // 2]

    found = None
    y = 0
    while y < n:
        if not inner[y]:
            y += 1
            continue
        # des lettres posées sur le trait de cadre le font réapparaître sur une ligne de texte : trous tolérés
        ya, holes, gap = y, 0, max(4, round(0.012 * H))
        while y < n and (inner[y] or holes < gap):
            holes = 0 if inner[y] else holes + 1
            y += 1
        yb = y - holes
        if yb - ya < BRIDGE_MIN * H or yb - ya > 0.6 * n or sum(inner[ya:yb]) < 0.3 * (yb - ya):
            continue
        # le cartouche passe vraiment par-dessus la gouttière : son contour (haut, bas) ou ses lettres la traversent.
        # Deux cartouches face à face, chacun dans sa case, laissent la gouttière vide.
        core_ink = _rows(ink, (c0, o0 + ya, c1, o0 + yb))
        if sum(1 for v in core_ink if v > 0) < 2:
            continue
        ra, rb = reach(ya, yb, -1), reach(ya, yb, 1)
        if ra < 2 or rb < 2:
            continue
        # une bulle a un bout : du papier jusqu'au fond de la case, c'est un dessin au trait sur fond blanc, pas un cartouche
        if ra >= 0.85 * (c0 - a[0]) or rb >= 0.85 * (b[2] - c1):
            continue
        if axis == 1:
            tbox, anchor = (max(0, c0 - ra - 4), o0 + ya, min(W, c1 + rb + 4), o0 + yb), (c0 + c1) // 2
        else:   # gouttière horizontale : on lit les lignes au-dessus et au-dessous, depuis le milieu du passage
            tbox, anchor = (o0 + ya, max(0, c0 - ra - 4), o0 + yb, min(W, c1 + rb + 4)), o0 + (ya + yb) // 2
        # lettres nettes (papier + encre) ou adoucies par la réduction (gris neutres) : l'une ou l'autre lecture
        lines = max(_text_lines(valid0, ink0, tbox, anchor), _text_lines(neutral0, ink0, tbox, anchor))
        if lines < 1:
            continue
        wa, wb = max(1, a[2] - a[0]), max(1, b[2] - b[0])
        in_a, in_b = max(0, ra - (c0 - a[2])), max(0, rb - (b[0] - c1))   # part dans chaque case, depuis son bord
        share = in_b / wb if in_b / wb >= in_a / wa else in_a / wa
        if in_b / wb >= in_a / wa:   # surtout dans b : b s'élargit jusqu'au bout du cartouche, côté a
            r = {"grow": 1, "edge": c0 - ra - 2, "share": share}
        else:
            r = {"grow": 0, "edge": c1 + rb + 2, "share": share}
        # réunir seulement si les lettres elles-mêmes passent par la gouttière (le texte serait coupé en deux) :
        # au moins deux lignes d'encre distinctes dans la gouttière, en plus du contour
        inked_rows = [v > 0 for v in core_ink]
        bands = sum(1 for t in range(len(inked_rows)) if inked_rows[t] and (t == 0 or not inked_rows[t - 1]))
        if in_a >= BRIDGE_JOIN * wa and in_b >= BRIDGE_JOIN * wb and bands >= 3:
            r["join"] = True   # (l'élargissement sert de repli si la réunion déborderait sur d'autres cases)
            return r
        if found is None or share > found["share"]:
            found = r
    return found


def text_bridges(img: Image.Image, gray: Image.Image, mask: Image.Image, boxes: list[tuple]) -> tuple[list, dict]:
    """Cases reliées par un texte à cheval sur la gouttière. Renvoie (paires à réunir, {indice: case élargie})."""
    w, h = gray.size
    pairs = []
    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes):
            if i != j and a[2] <= b[0] + 2 and min(a[3], b[3]) - max(a[1], b[1]) > 0:
                pairs.append((i, j, 1))
            elif i != j and a[3] <= b[1] + 2 and min(a[2], b[2]) - max(a[0], b[0]) > 0:
                pairs.append((i, j, 0))
    if not pairs:
        return [], {}
    paper, ink, neutral = _paper_ink(img, (w, h))
    bw = ImageStat.Stat(neutral).mean[0] >= 0.85 * 255   # planche en noir et blanc (ou presque)
    join, grown = [], {}
    for i, j, axis in pairs:
        r = _bridge(gray, mask, paper, ink, neutral, boxes[i], boxes[j], axis, bw)
        if not r:
            continue
        if r.get("join"):
            u = (min(boxes[i][0], boxes[j][0]), min(boxes[i][1], boxes[j][1]),
                 max(boxes[i][2], boxes[j][2]), max(boxes[i][3], boxes[j][3]))
            # les deux cases réunies ne doivent pas en recouvrir une troisième (sinon : élargir seulement)
            if _area(u) <= 0.5 * w * h and not any(k not in (i, j) and _inter(u, c) > 0.1 * _area(c) for k, c in enumerate(boxes)):
                if [i, j] not in join:
                    join.append([i, j])
                continue
        k = i if r["grow"] == 0 else j
        box = list(grown.get(k, boxes[k]))
        size = (box[2] - box[0]) if axis == 1 else (box[3] - box[1])
        lo_side, hi_side = (box[0], box[2]) if axis == 1 else (box[1], box[3])
        reach = (lo_side - r["edge"]) if k == j else (r["edge"] - hi_side)
        if reach > 0.4 * size:
            continue   # une bulle qui déborde d'un peu, pas une moitié de case voisine
        if axis == 1:
            if k == j:
                box[0] = min(box[0], r["edge"])
            else:
                box[2] = max(box[2], r["edge"])
        else:
            if k == j:
                box[1] = min(box[1], r["edge"])
            else:
                box[3] = max(box[3], r["edge"])
        grown[k] = tuple(box)
    return join, grown


BUBBLE_REACH = 0.3        # une bulle qui dépasse du cadre : on élargit la case d'au plus 30 % de sa taille…
BUBBLE_PAGE = 0.06        # … et d'au plus 6 % de la page


def overflow_grow(mask: Image.Image, boxes: list[tuple], grown: dict) -> dict:
    """Élargit une case pour montrer en entier une bulle (ou un cartouche) qui dépasse un peu de son cadre dans la
    gouttière : la vue se dézoome juste ce qu'il faut. On cherche, le long de chaque côté, ce qui traverse le bord ;
    ce morceau doit s'arrêter dans la gouttière (sinon c'est la case voisine) et être surtout clair (l'intérieur blanc
    d'une bulle, pas du dessin)."""
    w, h = mask.size
    out = dict(grown)
    for k, b in enumerate(boxes):
        cur = list(out.get(k, b))
        changed = False
        for side in range(4):
            horiz = side in (1, 3)              # 1 : haut, 3 : bas (des lignes) ; 0 : gauche, 2 : droite (des colonnes)
            dim = (b[3] - b[1]) if horiz else (b[2] - b[0])
            limit = round(min(BUBBLE_REACH * dim, BUBBLE_PAGE * (h if horiz else w)))
            if limit < 4:
                continue
            x0, y0, x1, y1 = cur
            strip = {0: (x0 - limit, y0, x0, y1), 1: (x0, y0 - limit, x1, y0),
                     2: (x1, y0, x1 + limit, y1), 3: (x0, y1, x1, y1 + limit)}[side]
            if strip[0] < 0 or strip[1] < 0 or strip[2] > w or strip[3] > h:
                continue
            reg = mask.crop(strip)
            # ligne 0 = la plus proche du cadre, colonnes = le long du bord
            reg = {0: lambda r: r.transpose(Image.Transpose.ROTATE_90), 1: lambda r: r.transpose(Image.Transpose.FLIP_TOP_BOTTOM),
                   2: lambda r: r.transpose(Image.Transpose.ROTATE_270), 3: lambda r: r}[side](reg)
            n, L = reg.size
            d = reg.tobytes()
            cross = [c for c in range(n) if not d[c] or not d[n + c]]
            segs, cs = [], []
            for c in cross:
                if cs and c - cs[-1] > 3:
                    segs.append((cs[0], cs[-1] + 1)); cs = []
                cs.append(c)
            if cs:
                segs.append((cs[0], cs[-1] + 1))
            reach = 0
            for s0, s1 in segs:
                if s1 - s0 < 6 or s1 - s0 > 0.6 * n:
                    continue
                m = max(3, (s1 - s0) // 4)
                lo, hi = max(0, s0 - m), min(n, s1 + m)
                depth = None
                for r in range(L):
                    if all(d[r * n + c] for c in range(lo, hi)):
                        depth = r
                        break
                if depth is None or depth < 3:
                    continue   # ne s'arrête pas avant la case voisine, ou trop peu pour compter
                light = sum(1 for r in range(depth) for c in range(s0, s1) if d[r * n + c]) / (depth * (s1 - s0))
                if light >= 0.45:
                    reach = max(reach, depth)
            if not reach:
                continue
            new = list(cur)
            new[side] = cur[side] - reach if side in (0, 1) else cur[side] + reach
            if any(j != k and _inter(tuple(new), o) > _inter(tuple(cur), o) + 0.02 * _area(o) for j, o in enumerate(boxes)):
                continue
            cur, changed = new, True
        if changed:
            out[k] = tuple(cur)
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

    dark = ImageChops.lighter(mask, gray.point([255 if i <= 24 else 0 for i in range(256)], "L")) if bg >= 200 else mask

    def leaves(rtl: bool) -> list[tuple]:
        # fond ni blanc ni noir (dessin jusqu'aux bords) : les gouttières n'ont pas de sens, seuls les cadres comptent
        res = (_split(mask, full, 0, 0, min_gutter, min_side, rtl) if (bg >= 200 or bg <= 55) else [full]) or [full]
        out: list[tuple] = []
        for leaf in res:
            parts = _refine_leaf(leaf, frames, w, h, rtl, mask if (bg >= 200 or bg <= 55) else None, min_gutter, min_side)
            if parts == [leaf] and (bg >= 200 or bg <= 55) and _area(leaf) >= 0.3 * page_area:
                # grande zone indécoupable : peut-être des cases aux bords tracés à main levée, séparées par le fond
                blobs = detect_blobs(mask, leaf)
                if blobs:
                    parts = _reading_order(blobs, rtl)
            if _area(leaf) >= 0.3 * page_area:
                # ou des rangées aux bords bien droits, mais séparées par autre chose que du fond (décor peint, couleur
                # qui change, cartouche à cheval) : on coupe le long des bords eux-mêmes, puis chaque rangée est
                # découpée normalement
                rows = _line_cuts(gray, leaf, 0, 2 * min_side)   # des rangées franches, pas une bande de texte
                # seulement si le découpage trouvé contredit ces bords (une case trouvée les enjambe) ou s'il n'y en a pas
                crossed = parts == [leaf] or any(p[1] < r[1] - min_side and p[3] > r[1] + min_side for p in parts for r in rows[1:])
                if len(rows) >= 2 and crossed:
                    parts = []
                    for row in rows:
                        sub = (_split(mask, row, 1, 1, min_gutter, min_side, rtl) if (bg >= 200 or bg <= 55) else [row]) or [row]
                        for r in sub:
                            parts.extend(_refine_leaf(r, frames, w, h, rtl, mask if (bg >= 200 or bg <= 55) else None,
                                                      min_gutter, min_side))
            if bg >= 200:
                # gouttières noires sur une page blanche (une colonne de cases encadrée de noir, une rangée posée sur
                # un bandeau noir) : chaque grande case encore entière est redécoupée en prenant aussi le noir pur
                # pour du fond ; seulement si les morceaux couvrent presque toute la case
                again = []
                for p_ in parts:
                    if _area(p_) >= 0.1 * page_area:
                        sub = [r for r in _dark_split(dark, p_, 0, min_gutter, min_side, rtl)
                               if _area(r) >= MIN_AREA * page_area and (r[2] - r[0]) >= MIN_PANEL * w and (r[3] - r[1]) >= MIN_PANEL * h]
                        if len(sub) >= 2 and sum(_area(r) for r in sub) >= 0.8 * _area(p_):
                            again.extend(sub)
                            continue
                    again.append(p_)
                parts = again
            out.extend(parts)
        return [b for b in out if _area(b) >= MIN_AREA * page_area and (b[2] - b[0]) >= MIN_PANEL * w and (b[3] - b[1]) >= MIN_PANEL * h]

    def flat_sliver(b: tuple) -> bool:
        """Bande étroite collée au bord de la page : le fond de la planche qui dépasse à côté d'une case, pas une case."""
        bw_, bh_ = b[2] - b[0], b[3] - b[1]
        narrow = (bw_ < 0.15 * w and (b[0] <= 3 or b[2] >= w - 3)) or (bh_ < 0.08 * h and (b[1] <= 3 or b[3] >= h - 3))
        # d'une seule teinte, ou surtout du fond (marge de la page prise avec un bout de décor)
        return narrow and (ImageStat.Stat(gray.crop(b)).stddev[0] < 14 or ImageStat.Stat(mask.crop(b)).mean[0] >= 0.7 * 255)

    ltr = [b for b in leaves(False) if not flat_sliver(b)]
    empty = {"panels": [], "rtl": [], "v": PANELS_VERSION}
    if len(ltr) < 2:
        return empty
    if max(_area(b) for b in ltr) > 0.85 * page_area:
        return empty
    if sum(_area(b) for b in ltr) < 0.35 * page_area:
        return empty   # couverture, page de titre, crédits : quelques blocs isolés sur du vide, pas des cases
    rtl = [b for b in leaves(True) if not flat_sliver(b)]
    pad_x, pad_y = PAD * w, PAD * h

    def rel(b: tuple) -> list[float]:
        return [round(max(0.0, (b[0] - pad_x) / w), 4), round(max(0.0, (b[1] - pad_y) / h), 4),
                round(min(1.0, (b[2] + pad_x) / w), 4), round(min(1.0, (b[3] + pad_y) / h), 4)]

    panels = [rel(b) for b in ltr]
    index = {tuple(rel(b)): i for i, b in enumerate(ltr)}
    order = [index.get(tuple(rel(b)), i) for i, b in enumerate(rtl)]
    if sorted(order) != list(range(len(panels))):
        order = list(range(len(panels)))
    out = {"panels": panels, "rtl": order, "v": PANELS_VERSION}
    if bg >= 200 or bg <= 55:
        try:
            join, grown = text_bridges(img, gray, mask, ltr)
        except Exception:  # noqa: BLE001
            join, grown = [], {}
        try:
            grown = overflow_grow(mask, ltr, grown)
        except Exception:  # noqa: BLE001
            pass
        if join:
            out["join"] = join
        if grown:   # cases élargies pour ne pas couper une bulle qui déborde (même ordre, mêmes indices)
            out["grow"] = {str(k): rel(v) for k, v in grown.items()}
    return out
