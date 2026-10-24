"""Essai d'un modèle de vision (API Claude) pour trouver les cases, comparé au détecteur actuel, sur le banc.

C'est un OUTIL D'ESSAI : Bulle ne l'utilise pas et n'appelle jamais l'API. Il envoie les planches du banc à Anthropic
(les pages de vos BD quittent donc votre PC), uniquement si vous ajoutez --oui.

  python tools/banc_vision.py <dossier-banc>                 -> simulation : compte les planches, estime le coût, n'envoie rien
  python tools/banc_vision.py <dossier-banc> --oui           -> envoie vraiment (validation, 5 $ au plus)
  python tools/banc_vision.py <dossier> --annoter --oui      -> planches SANS annotation (tirées par banc_echantillon.py) : le
                                                                modèle propose des cases ; celles où il ne s'accorde pas avec
                                                                le détecteur actuel vont dans <dossier>/a-verifier/ (images à
                                                                regarder : vision en vert, détecteur en rouge)

Avant : la clé d'API dans la variable ANTHROPIC_API_KEY (voir le mode d'emploi donné avec ce script ; la clé ne s'écrit
jamais dans un fichier ni dans une commande qu'on partage).

Options : --set val|dev|tous (défaut val) ; --limit N (les N premières planches) ; --only A-18,B-45 (ces planches) ;
--budget 5 (dollars ; le script s'arrête de lui-même avant de le dépasser) ; --model nom ; --prix-entree 3 --prix-sortie 15
(dollars par million de jetons : À VÉRIFIER dans la console Anthropic, ils servent à l'estimation et au plafond) ;
--width 800 (largeur de la planche envoyée) ; --panels chemin/vers/panels.py (détecteur comparé ; défaut : celui du dépôt).

Chaque réponse est gardée dans <dossier-banc>/vision-<modèle>/ : relancer ne repaie pas les planches déjà faites.
Les mesures sont celles de banc_cases.py score (IoU 0,5 et 0,75, ordre de lecture). Le résultat complet est écrit dans
<dossier-banc>/vision-<modèle>.json."""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import banc_cases as bc  # noqa: E402
import banclib as B  # noqa: E402
from PIL import Image  # noqa: E402

API = "https://api.anthropic.com/v1/messages"
PROMPT = """Cette image est une page de bande dessinée, de {w} pixels de large sur {h} de haut.
Donne le rectangle de chaque CASE (chaque vignette dessinée, avec ou sans cadre), en pixels de CETTE image : [x0, y0, x1, y1],
(x0, y0) coin haut gauche, (x1, y1) coin bas droit. Ne compte pas les bulles, cartouches de texte ni numéros de page comme des
cases ; un texte posé sur le dessin fait partie de la case. Classe-les dans l'ordre de lecture ({sens}).
Si la page n'est pas découpée en cases (couverture, page de titre, page de texte, illustration pleine page), réponds une liste vide.
Réponds UNIQUEMENT par du JSON, sans aucun autre texte : {{"panels": [[x0, y0, x1, y1], ...]}}"""


def call_api(key: str, model: str, jpeg: bytes, w: int, h: int, manga: bool) -> tuple[list, int, int]:
    sens = "de droite à gauche puis de haut en bas" if manga else "de gauche à droite puis de haut en bas"
    body = {"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
        {"type": "text", "text": PROMPT.format(w=w, h=h, sens=sens)}]}]}
    req = urllib.request.Request(API, json.dumps(body).encode(), {"content-type": "application/json", "x-api-key": key,
                                                                    "anthropic-version": "2023-06-01"})
    err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            text = "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
            u = d.get("usage", {})
            return parse(text), int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code in (429, 500, 502, 503, 529):
                time.sleep(5 * (attempt + 1))
                continue
            break
        except Exception as e:  # noqa: BLE001
            err = str(e)
            time.sleep(3)
    raise RuntimeError(err)


def parse(text: str) -> list:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        return []
    try:
        d = json.loads(text[a:b + 1])
    except ValueError:
        return []
    out = []
    for r in d.get("panels", []) if isinstance(d, dict) else []:
        try:
            x0, y0, x1, y1 = (float(v) for v in r)
        except (TypeError, ValueError):
            continue
        out.append([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)])
    return out


def annoter(a, byk: dict, key: str, fake: bool) -> None:
    """Planches sans annotation : propositions du modèle + détecteur actuel ; les désaccords sont à regarder."""
    from PIL import ImageDraw
    keys = sorted(byk)[:a.limit] if a.limit else sorted(byk)
    est = len(keys) * (1500 * a.prix_entree + 300 * a.prix_sortie) / 1e6
    print(f"{len(keys)} planches à annoter, modèle {a.model}, estimation ≈ {est:.2f} $ (plafond {a.budget:.2f} $)")
    if not a.oui and not fake:
        print("Simulation : rien n'est envoyé. Ajoutez --oui pour envoyer ces planches à l'API Anthropic.")
        return
    cache = os.path.join(a.folder, "vision-" + ("fake" if fake else a.model.replace("/", "_")))
    os.makedirs(cache, exist_ok=True)
    os.makedirs(os.path.join(a.folder, "a-verifier"), exist_ok=True)
    P = bc.load(a.panels)
    spent, res = 0.0, {}
    for k in keys:
        f = byk[k]
        W, H = Image.open(f).size
        im = bc.open_page(f, a.width)
        cf = os.path.join(cache, k + ".json")
        if os.path.exists(cf) and not fake:
            panels = json.load(open(cf, encoding="utf-8"))["panels"]
        else:
            if spent >= a.budget:
                print(f"Plafond de {a.budget:.2f} $ atteint : arrêt avant {k}.")
                break
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
            try:
                if fake:   # essai du script sans réseau : le détecteur, avec une case retirée une fois sur deux
                    d0, _ = bc.detect(P, f, a.width, True)
                    panels = [[v * (im.width if j % 2 == 0 else im.height) for j, v in enumerate(r)] for r in B.reading(d0, False)]
                    panels = panels[1:] if len(k) and k[-1] in "13579" else panels
                    tin = tout = 0
                else:
                    panels, tin, tout = call_api(key, a.model, buf.getvalue(), im.width, im.height, False)
            except RuntimeError as e:
                print(f"{k} : échec ({e}) ; on arrête pour ne pas gaspiller.")
                break
            spent += (tin * a.prix_entree + tout * a.prix_sortie) / 1e6
            json.dump({"panels": panels}, open(cf, "w", encoding="utf-8"))
        s = W / im.width
        vis, _ = B.dedupe([[b[0] * s, b[1] * s, b[2] * s, b[3] * s] for b in panels])
        d, _ = bc.detect(P, f, 0, True)
        cls, _ = B.dedupe(B.to_pixels(B.reading(d, False), W, H))
        m = B.match(vis, cls, 0.7)
        agree = not m["fp"] and not m["fn"]
        res[k] = {"vision": vis, "classique": cls, "accord": agree, "size": [W, H]}
        if not agree:
            tiles = []
            for boxes, col in ((vis, "lime"), (cls, "red")):
                t = Image.open(f).convert("RGB")
                dr = ImageDraw.Draw(t)
                for i, b in enumerate(boxes):
                    dr.rectangle(list(b), outline=col, width=6)
                    dr.text((b[0] + 8, b[1] + 8), str(i + 1), fill=col)
                tiles.append(t.resize((W * 640 // H, 640)))
            sheet = Image.new("RGB", (tiles[0].width + tiles[1].width + 10, 640), "white")
            sheet.paste(tiles[0], (0, 0))
            sheet.paste(tiles[1], (tiles[0].width + 10, 0))
            sheet.save(os.path.join(a.folder, "a-verifier", k + ".jpg"), quality=85)
        print(f"{k:12} vision {len(vis):2}  détecteur {len(cls):2}  {'accord' if agree else 'A VÉRIFIER'}  dépensé {spent:.2f} $", flush=True)
    out = os.path.join(a.folder, "annotations-vision.json")
    json.dump(res, open(out, "w", encoding="utf-8"))
    n_dis = sum(1 for r in res.values() if not r["accord"])
    print(f"\n{len(res)} planches, dépensé ≈ {spent:.2f} $ : {len(res) - n_dis} en accord, {n_dis} à vérifier (images dans a-verifier/).")
    print("Détail écrit dans", out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--oui", action="store_true", help="envoyer vraiment les planches à l'API")
    ap.add_argument("--annoter", action="store_true", help="planches sans gt.json : proposer des cases et trier celles à vérifier")
    ap.add_argument("--set", default="val", choices=("val", "dev", "tous"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--budget", type=float, default=5.0)
    ap.add_argument("--model", default=os.environ.get("BULLE_VISION_MODEL", "claude-sonnet-5-5"))
    ap.add_argument("--prix-entree", type=float, default=3.0)
    ap.add_argument("--prix-sortie", type=float, default=15.0)
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--panels", default=os.path.join(HERE, "..", "bulle", "panels.py"))
    a = ap.parse_args()
    fake = os.environ.get("BULLE_VISION_FAKE") == "1"   # essai du script lui-même, sans réseau
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if a.oui and not key and not fake:
        sys.exit("La variable ANTHROPIC_API_KEY est vide : voir le mode d'emploi (la clé ne se passe pas en argument).")
    byk = {bc.key(f): f for f in bc.pages(a.folder)}
    if a.annoter:
        return annoter(a, byk, key, fake)
    gt = json.load(open(os.path.join(a.folder, "gt.json"), encoding="utf-8"))
    only = {s.strip() for s in a.only.split(",") if s.strip()}
    todo = []
    for k, entry in gt.items():
        g = B.normalize_gt(entry)
        subset = B.assign_set(k, g["album"], g["set"])
        if (a.set != "tous" and subset != a.set) or k not in byk or (only and k not in only):
            continue
        todo.append((k, g))
    todo.sort(key=lambda t: t[0])
    if a.limit:
        todo = todo[:a.limit]
    est_in, est_out = 1500, 300   # par planche (ordre de grandeur) pour la simulation
    est = len(todo) * (est_in * a.prix_entree + est_out * a.prix_sortie) / 1e6
    print(f"{len(todo)} planches ({a.set}), modèle {a.model}, estimation ≈ {est:.2f} $ (plafond {a.budget:.2f} $)")
    if not a.oui and not fake:
        print("Simulation : rien n'est envoyé. Ajoutez --oui pour envoyer ces planches à l'API Anthropic.")
        return
    tag = "fake" if fake else a.model.replace("/", "_")   # l'essai sans réseau n'écrit jamais dans le cache réel
    cache = os.path.join(a.folder, "vision-" + tag)
    os.makedirs(cache, exist_ok=True)
    P = bc.load(a.panels)
    spent, calls = 0.0, 0
    per_v, per_c, rows = {}, {}, {}
    for k, g in todo:
        f = byk[k]
        W, H = Image.open(f).size
        cf = os.path.join(cache, k + ".json")
        im = bc.open_page(f, a.width)
        if os.path.exists(cf):
            panels = json.load(open(cf, encoding="utf-8"))["panels"]
        else:
            if spent >= a.budget:
                print(f"Plafond de {a.budget:.2f} $ atteint : arrêt avant {k}.")
                break
            if fake:
                panels = [[b[0] * im.width / W, b[1] * im.width / W, b[2] * im.width / W, b[3] * im.width / W] for b in g["boxes"]]
                tin = tout = 0
            else:
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=90)
                try:
                    panels, tin, tout = call_api(key, a.model, buf.getvalue(), im.width, im.height, g["manga"])
                except RuntimeError as e:
                    print(f"{k} : échec ({e}) ; on arrête pour ne pas gaspiller.")
                    break
                calls += 1
            spent += (tin * a.prix_entree + tout * a.prix_sortie) / 1e6
            json.dump({"panels": panels}, open(cf, "w", encoding="utf-8"))
        s = W / im.width
        vis, _ = B.dedupe([[b[0] * s, b[1] * s, b[2] * s, b[3] * s] for b in panels])
        d, _ = bc.detect(P, f, 0, True)
        cls, _ = B.dedupe(B.to_pixels(B.reading(d, g["manga"]), W, H))
        per_v[k] = B.page_metrics(g["boxes"], vis, (0.5, 0.75))
        per_c[k] = B.page_metrics(g["boxes"], cls, (0.5, 0.75))
        rows[k] = {"gt": len(g["boxes"]), "vision": len(vis), "classique": len(cls), "album": g["album"]}
        print(f"{k:6} attendues {len(g['boxes']):2}  vision {len(vis):2} (justes {per_v[k][0.5]['tp']:2}, en trop {per_v[k][0.5]['fp']:2})"
              f"  classique {len(cls):2} (justes {per_c[k][0.5]['tp']:2}, en trop {per_c[k][0.5]['fp']:2})  dépensé {spent:.2f} $", flush=True)
    if not per_v:
        return
    av, ac = B.aggregate(per_v, (0.5, 0.75)), B.aggregate(per_c, (0.5, 0.75))
    print(f"\n{len(per_v)} planches. Appels : {calls}, dépensé ≈ {spent:.2f} $.\n")
    print("                    justes  en trop  manq.   préc.  rappel     F1   parfaites")
    for name, ag, per in (("classique", ac, per_c), ("vision", av, per_v)):
        for thr in (0.5, 0.75):
            r = ag[thr]
            perfect = sum(1 for m in per.values() if m[thr]["perfect"])
            print(f"{name:10} IoU {thr:<4} {r['tp']:6} {r['fp']:8} {r['fn']:6} {r['p']*100:6.1f}% {r['r']*100:6.1f}% {r['f1']*100:6.1f}% {perfect:6}")
    fail_c = [k for k, m in per_c.items() if not m[0.5]["perfect"]]
    win = [k for k in fail_c if per_v[k][0.5]["perfect"]]
    lose = [k for k, m in per_c.items() if m[0.5]["perfect"] and not per_v[k][0.5]["perfect"]]
    print(f"\nPlanches où le détecteur actuel échoue : {len(fail_c)} ; la vision les réussit toutes : {len(win)} ({', '.join(win)})")
    print(f"Planches où le détecteur actuel est parfait et la vision non : {len(lose)}")
    out = os.path.join(a.folder, "vision-" + tag + ".json")
    json.dump({"model": a.model, "spent": round(spent, 3), "rows": rows,
               "classique": {str(t): {kk: {x: per_c[kk][t][x] for x in ("tp", "fp", "fn")} for kk in per_c} for t in (0.5, 0.75)},
               "vision": {str(t): {kk: {x: per_v[kk][t][x] for x in ("tp", "fp", "fn")} for kk in per_v} for t in (0.5, 0.75)}},
              open(out, "w", encoding="utf-8"), indent=1)
    print("Détail écrit dans", out)


if __name__ == "__main__":
    main()
