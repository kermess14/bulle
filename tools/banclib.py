"""Mesures du banc d'essai de la détection des cases (sans image : rien que des rectangles et des listes).

Vocabulaire
  - une « annotation » : les cases attendues d'une planche, corrigées à la main, en pixels de l'image, dans l'ordre
    de lecture ; soit une liste de rectangles [x0, y0, x1, y1], soit un dictionnaire {"boxes": [...], "manga": bool,
    "album": "…", "set": "dev" | "val"} (voir `normalize_gt`) ;
  - une « détection » : ce que `detect_panels` renvoie ({"panels", "rtl", "join", "grow"}) ; `reading` en tire les
    cases telles que le lecteur les montre, `raw` les cases brutes ;
  - l'appariement est un-à-un : une case détectée ne peut « valider » qu'une seule case attendue, et réciproquement.
    Deux cases attendues couvertes par une seule détection comptent donc 1 juste + 1 manquante (une fusion), et une
    case attendue coupée en deux compte 1 juste + 1 en trop (une coupe) ;
  - à partir des appariements : TP (justes), FP (en trop), FN (manquantes), précision = TP/(TP+FP),
    rappel = TP/(TP+FN), F1 = moyenne harmonique ; chaque mesure est donnée à plusieurs seuils d'IoU
    (part commune / union des deux rectangles) ;
  - l'ordre : part des cases attendues consécutives (toutes deux appariées) dont les détections se suivent dans le
    même sens ; 1.0 = ordre de lecture entièrement respecté ;
  - le score historique (`legacy_score`) : la mesure de l'ancien banc (case attendue « juste » si une détection la
    recouvre à 60 %, détection « en trop » si elle ne recouvre aucune case attendue), gardée pour comparer avec les
    anciens relevés : elle ne voit pas les fusions.

Pas de division par zéro : une planche sans case attendue et sans case détectée est parfaite (P = R = F1 = 1).
"""
from __future__ import annotations

import hashlib
import statistics

IOU_THRESHOLDS = (0.5, 0.6, 0.75)
DUP_IOU = 0.95


# -- rectangles ---------------------------------------------------------------------------------------------------
def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def to_pixels(frac_boxes, w: int, h: int) -> list:
    """Rectangles en fractions de la page (sortie de detect_panels) → pixels de l'image de taille w × h."""
    return [[r[0] * w, r[1] * h, r[2] * w, r[3] * h] for r in frac_boxes]


def dedupe(boxes, thr: float = DUP_IOU):
    """Retire les rectangles en double (IoU ≥ thr avec un précédent) ; renvoie (liste nettoyée, nombre retiré)."""
    out, dropped = [], 0
    for b in boxes:
        if any(iou(b, o) >= thr for o in out):
            dropped += 1
        else:
            out.append(list(b))
    return out, dropped


# -- cases d'une détection ----------------------------------------------------------------------------------------
def raw(d: dict, manga: bool = False) -> list:
    """Cases brutes de la détection, dans l'ordre de lecture demandé (ordre manga = permutation « rtl »)."""
    pan = [list(r) for r in d.get("panels") or []]
    return [pan[i] for i in _order(d, len(pan), manga)]


def reading(d: dict, manga: bool = False) -> list:
    """Cases telles que le lecteur les montre : « grow » (case élargie pour une bulle) et « join » (cases montrées
    ensemble, fusionnées en leur enveloppe), dans l'ordre de lecture demandé."""
    pan = [list(r) for r in d.get("panels") or []]
    for k, r in (d.get("grow") or {}).items():
        if 0 <= int(k) < len(pan):
            pan[int(k)] = list(r)
    par = list(range(len(pan)))

    def f(i):
        while par[i] != i:
            i = par[i]
        return i

    for a, b in d.get("join") or []:
        if 0 <= a < len(pan) and 0 <= b < len(pan):
            par[f(a)] = f(b)
    un, out, seen = {}, [], set()
    for i, r in enumerate(pan):
        g = f(i)
        u = un.get(g)
        un[g] = r if u is None else [min(u[0], r[0]), min(u[1], r[1]), max(u[2], r[2]), max(u[3], r[3])]
    for i in _order(d, len(pan), manga):
        g = f(i)
        if g not in seen:
            seen.add(g)
            out.append(un[g])
    return out


def _order(d: dict, n: int, manga: bool) -> list:
    if manga:
        rtl = d.get("rtl")
        if rtl and sorted(rtl) == list(range(n)):
            return list(rtl)
    return list(range(n))


# -- appariement et mesures ---------------------------------------------------------------------------------------
def match(gt: list, det: list, thr: float) -> dict:
    """Appariement un-à-un, glouton par IoU décroissant (déterministe). Renvoie
    {"pairs": [(i_gt, i_det, iou), …], "fp": [i_det, …], "fn": [i_gt, …]}."""
    cands = sorted(((iou(g, x), gi, di) for gi, g in enumerate(gt) for di, x in enumerate(det) if iou(g, x) >= thr),
                   key=lambda t: (-t[0], t[1], t[2]))
    used_g, used_d, pairs = set(), set(), []
    for v, gi, di in cands:
        if gi in used_g or di in used_d:
            continue
        used_g.add(gi)
        used_d.add(di)
        pairs.append((gi, di, v))
    pairs.sort()
    return {"pairs": pairs, "fp": [i for i in range(len(det)) if i not in used_d],
            "fn": [i for i in range(len(gt)) if i not in used_g]}


def prf(tp: int, fp: int, fn: int) -> tuple:
    """(précision, rappel, F1) ; sans rien à trouver ni rien trouvé : (1, 1, 1)."""
    if tp == fp == fn == 0:
        return 1.0, 1.0, 1.0
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def order_score(pairs: list, n_gt: int):
    """Part des paires de cases attendues consécutives (toutes deux appariées) dont les détections se suivent dans le
    bon sens. None quand moins de deux cases sont appariées (rien à ordonner)."""
    pos = {gi: di for gi, di, _ in pairs}
    steps = [(pos[i], pos[i + 1]) for i in range(n_gt - 1) if i in pos and i + 1 in pos]
    if not steps:
        return None
    return sum(1 for a, b in steps if b > a) / len(steps)


def page_metrics(gt: list, det: list, thresholds=IOU_THRESHOLDS) -> dict:
    """Mesures d'une planche : par seuil {"tp", "fp", "fn", "p", "r", "f1", "order", "perfect"}."""
    out = {}
    for thr in thresholds:
        m = match(gt, det, thr)
        tp, fp, fn = len(m["pairs"]), len(m["fp"]), len(m["fn"])
        p, r, f = prf(tp, fp, fn)
        o = order_score(m["pairs"], len(gt))
        out[thr] = {"tp": tp, "fp": fp, "fn": fn, "p": p, "r": r, "f1": f, "order": o,
                    "perfect": fp == 0 and fn == 0 and (o is None or o == 1.0), "pairs": m["pairs"]}
    return out


def legacy_score(gt: list, det: list, thr: float = 0.6) -> tuple:
    """Score de l'ancien banc : (justes, en trop). Une détection peut valider plusieurs cases attendues."""
    m = sum(1 for g in gt if det and max(iou(g, x) for x in det) >= thr)
    e = sum(1 for x in det if not gt or max(iou(g, x) for g in gt) < thr)
    return m, e


def aggregate(per_page: dict, thresholds=IOU_THRESHOLDS) -> dict:
    """Totaux sur un ensemble de planches ({clé: page_metrics}) : par seuil, TP/FP/FN cumulés, P/R/F1 globaux
    (micro), F1 moyen par planche (macro), ordre moyen et nombre de planches parfaites."""
    out = {"pages": len(per_page)}
    for thr in thresholds:
        rows = [pm[thr] for pm in per_page.values()]
        tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
        p, r, f = prf(tp, fp, fn)
        orders = [r_["order"] for r_ in rows if r_["order"] is not None]
        out[thr] = {"tp": tp, "fp": fp, "fn": fn, "p": p, "r": r, "f1": f,
                    "f1_macro": sum(r_["f1"] for r_ in rows) / len(rows) if rows else 1.0,
                    "order": sum(orders) / len(orders) if orders else None,
                    "perfect": sum(1 for r_ in rows if r_["perfect"])}
    return out


# -- annotations --------------------------------------------------------------------------------------------------
def normalize_gt(entry) -> dict:
    """Une annotation sous sa forme complète : {"boxes", "manga", "album", "set"} (liste nue = boxes seules).
    Les rectangles sont remis d'équerre (x0 < x1, y0 < y1) ; les doublons sont retirés (compte dans "dups")."""
    if isinstance(entry, dict):
        boxes = entry.get("boxes") or []
        manga = bool(entry.get("manga", False))
        album = entry.get("album")
        subset = entry.get("set")
    else:
        boxes, manga, album, subset = list(entry or []), False, None, None
    fixed = [[min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])] for b in boxes]
    fixed, dups = dedupe(fixed)
    if subset not in (None, "dev", "val"):
        raise ValueError(f"set inconnu : {subset!r} (dev ou val)")
    return {"boxes": fixed, "manga": manga, "album": album, "set": subset, "dups": dups}


def assign_set(key: str, album, explicit=None, val_share: int = 30) -> str:
    """Jeu d'une planche : « set » explicite, sinon par album (toutes les planches d'un même album vont ensemble,
    tirage stable par empreinte du nom), sinon « dev ». val_share : part visée des albums en validation (%)."""
    if explicit in ("dev", "val"):
        return explicit
    if not album:
        return "dev"
    h = int(hashlib.sha1(album.encode("utf-8")).hexdigest()[:8], 16) % 100
    return "val" if h < val_share else "dev"


# -- temps et comparaison -----------------------------------------------------------------------------------------
def timing_stats(times: dict) -> dict:
    """{"n", "median", "p95", "max", "worst"} en secondes ; vide si rien."""
    if not times:
        return {"n": 0, "median": 0.0, "p95": 0.0, "max": 0.0, "worst": None}
    ts = sorted(times.values())
    p95 = ts[min(len(ts) - 1, max(0, int(round(0.95 * len(ts))) - 1))]
    return {"n": len(ts), "median": statistics.median(ts), "p95": p95, "max": ts[-1], "worst": max(times, key=times.get)}


def compare(base: dict, res: dict, fields=("panels", "rtl", "join", "grow")) -> dict:
    """Planches changées entre deux relevés (mêmes clés, champs différents), ajoutées (dans res seulement) et
    retirées (dans base seulement)."""
    changed = sorted(k for k in res if k in base and any(base[k].get(f) != res[k].get(f) for f in fields))
    return {"changed": changed, "added": sorted(k for k in res if k not in base),
            "removed": sorted(k for k in base if k not in res)}
