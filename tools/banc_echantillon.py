"""Tire des planches au hasard dans votre bibliothèque de CBZ, pour agrandir le banc d'essai (rien n'est envoyé nulle part).

  python tools/banc_echantillon.py <dossier-des-BD> <dossier-sortie> [--n 250] [--graine 1]

Les planches sont enregistrées à 800 px de large (comme le serveur) dans <sortie>/pages/ (nom : s-<numéro d'album>-<page>.jpg),
et <sortie>/echantillon.json dit de quel album et de quelle page elles viennent. Elles restent chez vous : le dossier ne doit
jamais aller sur GitHub. Seuls les CBZ / ZIP sont lus (CBR, CB7, PDF sont ignorés). Les albums déjà dans le banc
(gt.json des dossiers donnés par --exclure) sont évités, pour que les nouvelles planches soient vraiment nouvelles ;
la couverture et la dernière page ne sont jamais tirées. Une planche par série par défaut (la série = le premier dossier sous
le dossier des BD ; --par-serie 2 pour en prendre jusqu'à 2)."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bulle import comics  # noqa: E402

IMG = (".jpg", ".jpeg", ".png", ".webp")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("library")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--graine", type=int, default=1)
    ap.add_argument("--par-serie", type=int, default=1)
    ap.add_argument("--exclure", nargs="*", default=[], help="dossiers de banc déjà utilisés (leur gt.json donne les albums à éviter)")
    a = ap.parse_args()
    used = set()
    for d in a.exclure:
        try:
            for e in json.load(open(os.path.join(d, "gt.json"), encoding="utf-8")).values():
                if isinstance(e, dict) and e.get("album"):
                    used.add(e["album"].lower())
        except OSError:
            print("gt.json introuvable dans", d)
    files = []
    for root, _dirs, names in os.walk(a.library):
        for n in names:
            if n.lower().endswith((".cbz", ".zip")):
                p = os.path.join(root, n)
                parts = [x.lower() for x in os.path.relpath(p, a.library).split(os.sep)]
                if any(u in x or x in u for u in used for x in parts[:-1]):
                    continue
                files.append(p)
    print(f"{len(files)} CBZ possibles (albums du banc exclus : {len(used)} séries)")
    rnd = random.Random(a.graine)
    rnd.shuffle(files)
    os.makedirs(os.path.join(a.out, "pages"), exist_ok=True)
    meta, per_series, k = {}, {}, 0
    for p in files:
        if len(meta) >= a.n:
            break
        series = os.path.relpath(p, a.library).split(os.sep)[0]
        if per_series.get(series, 0) >= a.par_serie:
            continue
        try:
            with zipfile.ZipFile(p) as zf:
                names = comics.sort_pages([n for n in zf.namelist() if n.lower().endswith(IMG)])
                if len(names) < 6:
                    continue
                for i in rnd.sample(range(2, len(names) - 1), 1):
                    key = f"s-{k:03d}-{i}"
                    open(os.path.join(a.out, "pages", key + ".jpg"), "wb").write(comics.resize_to_jpeg(zf.read(names[i]), 800))
                    meta[key] = {"album": os.path.splitext(os.path.basename(p))[0], "series": series, "page": i}
                    per_series[series] = per_series.get(series, 0) + 1
                    k += 1
        except (OSError, zipfile.BadZipFile, KeyError, ValueError) as e:
            print("ignoré :", os.path.basename(p), e)
        if len(meta) % 25 == 0 and meta:
            print(len(meta), "planches", flush=True)
    json.dump(meta, open(os.path.join(a.out, "echantillon.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(per_series)} séries différentes ; {len(meta)} planches dans {os.path.join(a.out, 'pages')}")


if __name__ == "__main__":
    main()
