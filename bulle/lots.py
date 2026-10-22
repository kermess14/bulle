"""Deux lots de planches à corriger à la main (pour le banc d'essai de la détection des cases).

Un lot = 50 planches : 10 de « Watchmen » (si l'album est dans la bibliothèque) et des planches d'albums tous différents,
tirés au hasard dans toute la bibliothèque (donc de tous les styles). Aucune planche n'est dans les deux lots.
Chaque planche existe en deux versions : `avant/NN.png` (cases détectées, avec leur numéro) et `pages/NN.jpg` (la page seule).
Le ZIP contient un dossier par lot (à donner tel quel) et, à la racine, `index.json` : la correspondance numéro → album,
à garder pour soi (elle sert à ranger les corrections dans le banc d'essai).

Rien ici ne touche aux fichiers de la bibliothèque : les pages sont lues, jamais écrites.
"""
from __future__ import annotations

import io
import json
import os
import random
import zipfile
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

COLS = [(230, 0, 0), (0, 110, 230), (0, 150, 0), (240, 120, 0), (180, 0, 180), (0, 160, 160)]
PER_LOT, WATCH_PER_LOT, WATCH_WORD = 50, 10, "watchmen"
LOTS = ("lot-A", "lot-B")

README = """50 planches à corriger.

avant/   : chaque planche avec les cases que Bulle a trouvées, entourées et numérotées (rectangles de couleur).
pages/   : la même planche, sans aucun dessin.

Pour chaque planche, dire si c'est juste. Sinon, écrire ce qui ne va pas, par exemple :
  « planche 07 : la 3 et la 4 forment une seule case » ; « planche 12 : il manque la case en bas à droite » ;
  « planche 31 : la 2 déborde sur la 1 » ; « planche 40 : pleine page, c'est une seule case ».
Les numéros ne sont que des étiquettes pour désigner un rectangle : ils ne disent pas l'ordre de lecture.

Une case = ce qu'on veut voir plein écran quand on lit case par case. Une bulle ou un cartouche qui déborde de la case
appartient à cette case. Une planche sans cases (pleine page, couverture) : « pleine page ».
"""


class Stopped(Exception):
    """Préparation arrêtée à la demande."""


def page_range(n: int) -> range:
    """Pages possibles d'un album de n pages : ni la couverture et ses premières pages, ni la fin."""
    lo = min(4, n // 8)
    hi = n - max(2, n // 16)
    return range(lo, max(lo + 1, hi))


def pick(cands: list[dict], seed: int = 22, per_lot: int = PER_LOT, watch_per_lot: int = WATCH_PER_LOT,
         watch_word: str = WATCH_WORD) -> list[list[tuple[dict, int]]]:
    """Choisit les planches des deux lots. `cands` : albums {id, path, pages}. Renvoie deux listes de (album, page 0-based)."""
    rnd = random.Random(seed)
    watch = [c for c in cands if watch_word in c["path"].lower()]
    watch.sort(key=lambda c: -c["pages"])
    others = sorted((c for c in cands if c not in watch), key=lambda c: c["id"])
    rnd.shuffle(others)
    picks_w: list[tuple[dict, int]] = []
    if watch:
        a = watch[0]
        rng = list(page_range(a["pages"]))
        need = min(2 * watch_per_lot, len(rng))
        step = len(rng) / need
        chosen = [rng[min(len(rng) - 1, int(i * step + rnd.random() * step))] for i in range(need)]
        rnd.shuffle(chosen)
        picks_w = [(a, p) for p in chosen]
    need_o = 2 * per_lot - len(picks_w)
    picks_o: list[tuple[dict, int]] = []
    used: set[tuple[int, int]] = set()
    rounds = 0
    while len(picks_o) < need_o and others and rounds < 20:
        for a in others:
            if len(picks_o) >= need_o:
                break
            rng = [p for p in page_range(a["pages"]) if (a["id"], p) not in used]
            if rng:
                p = rnd.choice(rng)
                used.add((a["id"], p))
                picks_o.append((a, p))
        rounds += 1
    rnd.shuffle(picks_o)
    half_w, half_o = len(picks_w) // 2, len(picks_o) // 2
    lots = [picks_w[:half_w] + picks_o[:half_o], picks_w[half_w:] + picks_o[half_o:]]
    for lot in lots:
        rnd.shuffle(lot)
    return lots


def reading(d: dict) -> list[list[float]]:
    """Cases telles que le lecteur les montre : « grow » (case élargie) et « join » (cases montrées ensemble)."""
    pan = [list(r) for r in d["panels"]]
    for k, r in (d.get("grow") or {}).items():
        if int(k) < len(pan):
            pan[int(k)] = list(r)
    par = list(range(len(pan)))

    def find(i: int) -> int:
        while par[i] != i:
            i = par[i]
        return i

    for a, b in d.get("join") or []:
        if a < len(pan) and b < len(pan):
            par[find(a)] = find(b)
    merged: dict[int, list[float]] = {}
    out: list[list[float]] = []
    seen: set[int] = set()
    for i, r in enumerate(pan):
        g = find(i)
        u = merged.get(g)
        merged[g] = r if u is None else [min(u[0], r[0]), min(u[1], r[1]), max(u[2], r[2]), max(u[3], r[3])]
    for i in range(len(pan)):
        g = find(i)
        if g not in seen:
            seen.add(g)
            out.append(merged[g])
    return out


def draw_cases(im: Image.Image, cases: list[list[float]], label: str) -> Image.Image:
    im = im.convert("RGB")
    w, h = im.size
    dr = ImageDraw.Draw(im)
    try:
        big, small = ImageFont.load_default(size=64), ImageFont.load_default(size=28)
    except TypeError:   # Pillow ancien : police minuscule, mais ça marche
        big = small = ImageFont.load_default()
    for i, r in enumerate(cases):
        c = COLS[i % 6]
        x0, y0, x1, y1 = r[0] * w, r[1] * h, r[2] * w, r[3] * h
        dr.rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], outline=c, width=6)
        dr.rectangle([x0 + 6, y0 + 6, x0 + 86, y0 + 84], fill=c)
        dr.text((x0 + 18, y0 + 6), str(i + 1), fill="white", font=big)
    dr.rectangle([0, h - 40, 360, h], fill=(0, 0, 0))
    dr.text((8, h - 38), label, fill=(255, 230, 0), font=small)
    return im


def build(lots: list[list[tuple[dict, int]]], render: Callable[[dict, int], bytes],
          detect: Callable[[Image.Image, dict, int], dict], out_path: str,
          progress: Optional[Callable[[int, int], None]] = None, should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Fabrique le ZIP. `render(album, page)` : JPEG de la page à 800 px ; `detect(image, album, page)` : résultat de
    detect_panels. Écrit d'abord dans un fichier temporaire, remplacé à la fin. Renvoie le nombre de planches."""
    total = sum(len(lot) for lot in lots)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".part"
    index: list[dict] = []
    done = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        for name, items in zip(LOTS, lots):
            thumbs = []
            for n, (album, page) in enumerate(items, 1):
                if should_stop and should_stop():
                    raise Stopped()
                key = f"{n:02d}"
                jpg = render(album, page)
                im = Image.open(io.BytesIO(jpg)).convert("RGB")
                try:
                    d = detect(im, album, page)
                    cases = reading(d)
                except Exception:   # noqa: BLE001  (une planche qui plante est livrée sans cases, pas perdue)
                    d, cases = {"panels": []}, []
                zf.writestr(f"{name}/pages/{key}.jpg", jpg)
                shown = draw_cases(im, cases, f"planche {key} - {len(cases)} cases")
                buf = io.BytesIO()
                shown.save(buf, "PNG", optimize=False)
                zf.writestr(f"{name}/avant/{key}.png", buf.getvalue())
                th = shown.copy()
                th.thumbnail((400, 560))
                thumbs.append(th)
                index.append({"lot": name, "planche": key, "album_id": album["id"], "album": album["path"], "page": page + 1,
                              "cases": len(cases), "panels": d.get("panels"), "rtl": d.get("rtl"), "join": d.get("join"),
                              "grow": d.get("grow")})
                done += 1
                if progress:
                    progress(done, total)
            if thumbs:
                tw, th_ = max(t.width for t in thumbs), max(t.height for t in thumbs)
                cols = 5
                rows = (len(thumbs) + cols - 1) // cols
                sheet = Image.new("RGB", (tw * cols + 10 * (cols - 1), th_ * rows + 10 * (rows - 1)), (40, 40, 40))
                for i, t in enumerate(thumbs):
                    sheet.paste(t, ((i % cols) * (tw + 10), (i // cols) * (th_ + 10)))
                buf = io.BytesIO()
                sheet.save(buf, "JPEG", quality=80)
                zf.writestr(f"{name}/planche-contact.jpg", buf.getvalue())
            zf.writestr(f"{name}/LISEZ-MOI.txt", README)
        zf.writestr("index.json", json.dumps(index, ensure_ascii=False))
        zf.writestr("LISEZ-MOI-prive.txt", "index.json : numéro de planche → album et page (et cases détectées). À garder pour soi : "
                                          "ne donner que les dossiers lot-A ou lot-B.\n")
    os.replace(tmp, out_path)
    return total
