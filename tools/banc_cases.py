"""Banc d'essai de la détection des cases (bulle/panels.py), sans les planches : on lui donne le dossier des pages.

  python tools/banc_cases.py base    <dossier>   -> enregistre la référence (<dossier>/base.json)
  python tools/banc_cases.py compare <dossier>   -> planches changées par rapport à base.json (cases, ordre manga,
                                                    « join », « grow »), planches ajoutées ou retirées depuis la
                                                    référence, montages AVANT/APRÈS dans <dossier>/diff/, temps
                                                    (médiane, p95, pire planche)
  python tools/banc_cases.py score   <dossier>   -> mesures sur les planches corrigées à la main (<dossier>/gt.json) :
                                                    justes / en trop / manquantes, précision, rappel, F1 à plusieurs
                                                    seuils d'IoU, ordre de lecture, planches parfaites, par jeu
                                                    (dev / val) ; plus le score historique de l'ancien banc

Options : --panels chemin/vers/panels.py (par défaut celui du dépôt) ; --width N (réduire les pages à N px de large
avant la détection, comme le serveur ; par défaut : telles quelles) ; --iou 0.5,0.6,0.75 (seuils) ; --set dev|val
(ne mesurer qu'un jeu) ; --raw (mesurer les cases brutes plutôt que celles que le lecteur montre, « grow » et
« join » compris) ; --json fichier (enregistrer le relevé complet, pour comparer deux versions) ; --quiet (totaux
seulement).

Le dossier contient les planches (*.jpg, *.png, *.webp — directement, ou dans un sous-dossier pages/) et, pour
« score », un gt.json : { "nom-sans-extension": annotation }, où l'annotation est soit la liste des cases
[[x0, y0, x1, y1], ...] en pixels de l'image, dans l'ordre de lecture, soit {"boxes": [...], "manga": true/false,
"album": "…", "set": "dev"/"val"}. Le jeu d'une planche vient de « set », sinon de son album (toutes les planches
d'un album vont dans le même jeu), sinon « dev ». Les mesures sont expliquées dans tools/banclib.py.
Les planches viennent d'une bibliothèque personnelle : elles ne vont jamais dans le dépôt.
"""
import argparse
import glob
import importlib.util
import json
import os
import sys
import time

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banclib as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def load(path):
    spec = importlib.util.spec_from_file_location("panels_under_test", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pages(folder):
    """Planches du dossier, ou de son sous-dossier pages/ (base.json, gt.json et diff/ restent dans le dossier)."""
    sub = os.path.join(folder, "pages")
    where = sub if os.path.isdir(sub) else folder
    return sorted(f for f in glob.glob(os.path.join(where, "*")) if f.lower().endswith(EXTS))


def key(f):
    return os.path.splitext(os.path.basename(f))[0]


def open_page(f, width):
    im = Image.open(f).convert("RGB")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
    return im


def detect(P, f, width, manga):
    im = open_page(f, width)
    t = time.perf_counter()
    d = P.detect_panels(im, manga=manga) if manga is not None else P.detect_panels(im)
    return {"panels": d["panels"], "rtl": d.get("rtl"), "join": d.get("join"), "grow": d.get("grow"),
            "v": d.get("v")}, time.perf_counter() - t


def run(P, folder, width):
    out, times = {}, {}
    for f in pages(folder):
        out[key(f)], times[key(f)] = detect(P, f, width, None)
    return out, times


def draw(im, panels, label):
    im = im.copy()
    W, H = im.size
    dr = ImageDraw.Draw(im)
    cols = [(255, 0, 0), (0, 140, 255), (0, 190, 0), (255, 140, 0), (200, 0, 200), (0, 190, 190)]
    for i, r in enumerate(panels):
        c = cols[i % 6]
        dr.rectangle([r[0] * W + 3, r[1] * H + 3, r[2] * W - 3, r[3] * H - 3], outline=c, width=5)
        dr.rectangle([r[0] * W + 6, r[1] * H + 6, r[0] * W + 40, r[1] * H + 36], fill=c)
        dr.text((r[0] * W + 14, r[1] * H + 12), str(i + 1), fill=(255, 255, 255))
    dr.rectangle([0, 0, 260, 24], fill=(0, 0, 0))
    dr.text((6, 6), label, fill=(255, 230, 0))
    return im


def fmt_times(times):
    s = B.timing_stats(times)
    return (f"{s['n']} planches, médiane {1000 * s['median']:.0f} ms, p95 {1000 * s['p95']:.0f} ms, "
            f"pire {1000 * s['max']:.0f} ms ({s['worst']})")


def score(P, folder, args):
    gtf = os.path.join(folder, "gt.json")
    if not os.path.exists(gtf):
        sys.exit(f"pas de gt.json dans {folder}")
    gt = json.load(open(gtf, encoding="utf-8"))
    thresholds = tuple(float(x) for x in args.iou.split(","))
    byk = {key(f): f for f in pages(folder)}
    per = {}
    missing, dups_gt, dups_det, times = [], 0, 0, {}
    legacy = [0, 0, 0]
    for k, entry in gt.items():
        a = B.normalize_gt(entry)
        subset = B.assign_set(k, a["album"], a["set"])
        if args.set and subset != args.set:
            continue
        if k not in byk:
            missing.append(k)
            continue
        dups_gt += a["dups"]
        im = Image.open(byk[k])
        W, H = im.size
        d, times[k] = detect(P, byk[k], args.width, True)
        boxes = B.raw(d, a["manga"]) if args.raw else B.reading(d, a["manga"])
        det, dd = B.dedupe(B.to_pixels(boxes, W, H))
        dups_det += dd
        pm = B.page_metrics(a["boxes"], det, thresholds)
        per[k] = {"set": subset, "album": a["album"], "manga": a["manga"], "n_gt": len(a["boxes"]), "n_det": len(det),
                  "metrics": pm, "legacy": B.legacy_score(a["boxes"], det), "v": d.get("v")}
        legacy[0] += per[k]["legacy"][0]
        legacy[1] += len(a["boxes"])
        legacy[2] += per[k]["legacy"][1]
        if not args.quiet:
            m = pm[thresholds[0]]
            o = "" if m["order"] is None else f" ordre {100 * m['order']:.0f} %"
            print(f"{k:28s} {subset:3s} {m['tp']:2d}/{len(a['boxes']):2d} justes, {m['fp']:2d} en trop, "
                  f"{m['fn']:2d} manquantes{o}{'  PARFAITE' if m['perfect'] else ''}")
    if missing:
        print(f"{len(missing)} annotation(s) sans planche (ignorées) :", ", ".join(missing))
    if dups_gt or dups_det:
        print(f"doublons retirés : {dups_gt} dans les annotations, {dups_det} dans les détections")
    if not per:
        sys.exit("aucune planche mesurée")
    sets = sorted({v["set"] for v in per.values()})
    report = {"folder": folder, "panels": os.path.abspath(args.panels),
              "version": sorted({v["v"] for v in per.values() if v["v"] is not None}), "width": args.width, "raw": bool(args.raw), "thresholds": list(thresholds), "pages": per,
              "totals": {}, "times": B.timing_stats(times), "legacy": {"ok": legacy[0], "total": legacy[1], "extra": legacy[2]}}
    print()
    print(f"{'jeu':6s} {'IoU':>5s} {'pl.':>4s} {'justes':>6s} {'trop':>5s} {'manq.':>5s} {'préc.':>6s} {'rappel':>6s} "
          f"{'F1':>6s} {'F1moy':>6s} {'ordre':>6s} {'parf.':>5s}")
    for name in sets + (["tous"] if len(sets) > 1 else []):
        sub = {k: v["metrics"] for k, v in per.items() if name == "tous" or v["set"] == name}
        agg = B.aggregate(sub, thresholds)
        report["totals"][name] = agg
        for thr in thresholds:
            t = agg[thr]
            o = "   -  " if t["order"] is None else f"{100 * t['order']:5.0f} %"
            print(f"{name:6s} {thr:5.2f} {agg['pages']:4d} {t['tp']:6d} {t['fp']:5d} {t['fn']:5d} {100 * t['p']:5.1f}% "
                  f"{100 * t['r']:5.1f}% {100 * t['f1']:5.1f}% {100 * t['f1_macro']:5.1f}% {o} {t['perfect']:4d}")
    print()
    print(f"score historique (ancien banc) : {legacy[0]} / {legacy[1]} justes, {legacy[2]} en trop")
    print("temps :", fmt_times(times))
    if args.json:
        report["pages"] = {k: {**v, "metrics": {str(t): {kk: vv for kk, vv in m.items() if kk != "pairs"}
                                                 for t, m in v["metrics"].items()}} for k, v in per.items()}
        report["totals"] = {n: {str(t): v for t, v in agg.items()} for n, agg in report["totals"].items()}
        json.dump(report, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("relevé enregistré :", args.json)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("base", "compare", "score"))
    ap.add_argument("folder", help="dossier des planches")
    ap.add_argument("--panels", default=os.path.join(ROOT, "bulle", "panels.py"))
    ap.add_argument("--width", type=int, default=0, help="réduire les pages à cette largeur avant la détection")
    ap.add_argument("--iou", default=",".join(str(t) for t in B.IOU_THRESHOLDS), help="seuils d'IoU, séparés par des virgules")
    ap.add_argument("--set", choices=("dev", "val"), default=None, help="ne mesurer que ce jeu")
    ap.add_argument("--raw", action="store_true", help="cases brutes (sans grow ni join)")
    ap.add_argument("--json", default=None, help="enregistrer le relevé (score) dans ce fichier")
    ap.add_argument("--quiet", action="store_true", help="totaux seulement")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)
    P = load(args.panels)
    if args.mode == "score":
        score(P, folder, args)
        return
    res, times = run(P, folder, args.width)
    if not res:
        sys.exit(f"aucune planche dans {folder}")
    print(fmt_times(times))
    basef = os.path.join(folder, "base.json")
    if args.mode == "base":
        json.dump(res, open(basef, "w"))
        print("référence enregistrée :", basef)
        return
    if not os.path.exists(basef):
        sys.exit("pas de base.json : lancer d'abord « base »")
    base = json.load(open(basef))
    cmp = B.compare(base, res)
    dd = os.path.join(folder, "diff")
    os.makedirs(dd, exist_ok=True)
    for x in glob.glob(os.path.join(dd, "*.jpg")):
        try:
            os.remove(x)
        except OSError:   # dossier sans droit de suppression : les anciens montages restent, les nouveaux les recouvrent
            pass
    byk = {key(f): f for f in pages(folder)}
    for k in cmp["changed"]:
        im = Image.open(byk[k]).convert("RGB")
        a = draw(im, B.reading(base[k]), k + " AVANT")
        b = draw(im, B.reading(res[k]), "APRÈS")
        t = Image.new("RGB", (a.width * 2 + 10, a.height), (30, 30, 30))
        t.paste(a, (0, 0))
        t.paste(b, (a.width + 10, 0))
        t.save(os.path.join(dd, k + ".jpg"), quality=80)
    print(len(cmp["changed"]), "planches changées :", cmp["changed"])
    if cmp["added"]:
        print(len(cmp["added"]), "planches nouvelles (pas dans la référence) :", cmp["added"])
    if cmp["removed"]:
        print(len(cmp["removed"]), "planches de la référence absentes du dossier :", cmp["removed"])


if __name__ == "__main__":
    main()
