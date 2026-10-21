"""Banc d'essai de la détection des cases (bulle/panels.py), sans les planches : on lui donne le dossier des pages.

  python tools/banc_cases.py base    <dossier>   -> enregistre la référence (<dossier>/base.json)
  python tools/banc_cases.py compare <dossier>   -> planches changées par rapport à base.json (cases, ordre manga,
                                                    « join », « grow »), montages AVANT/APRÈS dans <dossier>/diff/,
                                                    temps moyen et pire planche
  python tools/banc_cases.py score   <dossier>   -> score sur les planches corrigées à la main (<dossier>/gt.json)

Options : --panels chemin/vers/panels.py (par défaut celui du dépôt), --width N (réduire les pages à N px de large
avant la détection, comme le serveur ; par défaut : telles quelles).

Le dossier contient les planches (*.jpg, *.png, *.webp — directement, ou dans un sous-dossier pages/) et, pour
« score », un gt.json : { "nom-sans-extension": [[x0, y0, x1, y1], ...] } en pixels de l'image, dans l'ordre de
lecture. Les planches viennent d'une bibliothèque personnelle : elles ne vont jamais dans le dépôt.
"""
import argparse, glob, json, os, sys, time, importlib.util

from PIL import Image, ImageDraw

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


def run(P, folder, width):
    out, times = {}, {}
    for f in pages(folder):
        k = key(f)
        im = open_page(f, width)
        t = time.perf_counter()
        d = P.detect_panels(im)
        times[k] = time.perf_counter() - t
        out[k] = {"panels": d["panels"], "rtl": d.get("rtl"), "join": d.get("join"), "grow": d.get("grow")}
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


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u else 0


def reading(d):
    """Cases telles que le lecteur les montre : « grow » (case élargie pour une bulle) et « join » (cases montrées ensemble)."""
    pan = [list(r) for r in d["panels"]]
    for k, r in (d.get("grow") or {}).items():
        pan[int(k)] = list(r)
    par = list(range(len(pan)))

    def f(i):
        while par[i] != i:
            i = par[i]
        return i

    for a, b in d.get("join") or []:
        par[f(a)] = f(b)
    un, out, seen = {}, [], set()
    for i, r in enumerate(pan):
        g = f(i)
        u = un.get(g)
        un[g] = r if u is None else [min(u[0], r[0]), min(u[1], r[1]), max(u[2], r[2]), max(u[3], r[3])]
    for i in range(len(pan)):
        g = f(i)
        if g not in seen:
            seen.add(g)
            out.append(un[g])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("base", "compare", "score"))
    ap.add_argument("folder", help="dossier des planches")
    ap.add_argument("--panels", default=os.path.join(ROOT, "bulle", "panels.py"))
    ap.add_argument("--width", type=int, default=0, help="réduire les pages à cette largeur avant la détection")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)
    P = load(args.panels)
    if args.mode == "score":
        gtf = os.path.join(folder, "gt.json")
        if not os.path.exists(gtf):
            sys.exit(f"pas de gt.json dans {folder}")
        gt = json.load(open(gtf, encoding="utf-8"))
        tot = ok = extra = 0
        for k, g in gt.items():
            f = next((x for x in pages(folder) if key(x) == k), None)
            if not f:
                print(f"{k:28s} planche absente")
                continue
            im = Image.open(f)
            W, H = im.size
            d = P.detect_panels(open_page(f, args.width))
            det = [[r[0] * W, r[1] * H, r[2] * W, r[3] * H] for r in reading(d)]
            m = sum(1 for gb in g if det and max(iou(gb, x) for x in det) >= 0.6)
            e = sum(1 for x in det if max(iou(gb, x) for gb in g) < 0.6)
            tot += len(g)
            ok += m
            extra += e
            print(f"{k:28s} {m}/{len(g)} justes, {e} en trop")
        print("TOTAL", ok, "/", tot, "justes,", extra, "en trop")
        return
    res, times = run(P, folder, args.width)
    if not res:
        sys.exit(f"aucune planche dans {folder}")
    ts = sorted(times.values())
    print(f"{len(res)} planches, moyenne {1000 * sum(ts) / len(ts):.0f} ms, pire {1000 * ts[-1]:.0f} ms "
          f"({max(times, key=times.get)})")
    basef = os.path.join(folder, "base.json")
    if args.mode == "base":
        json.dump(res, open(basef, "w"))
        print("référence enregistrée :", basef)
        return
    if not os.path.exists(basef):
        sys.exit("pas de base.json : lancer d'abord « base »")
    base = json.load(open(basef))
    changed = [k for k in res if any(base.get(k, {}).get(f) != res[k][f] for f in ("panels", "rtl", "join", "grow"))]
    dd = os.path.join(folder, "diff")
    os.makedirs(dd, exist_ok=True)
    for x in glob.glob(os.path.join(dd, "*.jpg")):
        os.remove(x)
    byk = {key(f): f for f in pages(folder)}
    for k in changed:
        im = Image.open(byk[k]).convert("RGB")
        a = draw(im, reading(base[k]), k + " AVANT")
        b = draw(im, reading(res[k]), "APRÈS")
        t = Image.new("RGB", (a.width * 2 + 10, a.height), (30, 30, 30))
        t.paste(a, (0, 0))
        t.paste(b, (a.width + 10, 0))
        t.save(os.path.join(dd, k + ".jpg"), quality=80)
    print(len(changed), "planches changées :", changed)


if __name__ == "__main__":
    main()
