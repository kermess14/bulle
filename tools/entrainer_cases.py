"""Apprentissage du modèle de cases de Bulle (moteur « model », bulle/models/cases-yolo11n.onnx), sur un PC à carte
graphique, à partir des planches corrigées à la main (gt.json des bancs ; ces planches ne vont jamais dans le dépôt).
Bulle lui-même n'en a pas besoin : il n'utilise que le fichier .onnx produit. Prérequis sur le PC : torch (CUDA) et
ultralytics (pip install ultralytics). Dossiers : les bancs sont cherchés dans BULLE_BANCS (défaut : le dossier qui
contient le dépôt) ; tout ce qui est produit va dans <BULLE_BANCS>/ia-test.
Usage :  python tools/entrainer_cases.py <essai> [--modele yolo11n.pt]
  essai = "A" : apprend sur bulle-banc-nouveau + bulle-banc-essai, teste sur bulle-banc-lots
  essai = "B" : apprend sur bulle-banc-lots + bulle-banc-essai, teste sur bulle-banc-nouveau
  essai = "final" : apprend sur tout (pour Bulle, une fois les essais A et B jugés bons)
Pour reprendre un apprentissage interrompu (fenêtre fermée, Ctrl+C) : python tools/entrainer_cases.py A --reprendre
Option : --modele yolo11n.pt (celui de Bulle, 5 Mo, rapide sans carte graphique), yolo11s.pt, ou best.pt (gros modèle
de cases « best-comic-panel-detection », à télécharger dans ia-test). Le fichier .onnx du modèle final « final » se copie
ensuite dans bulle/models/cases-yolo11n.onnx (et MODEL_VERSION de panels_model.py est augmenté de 1).
Mesure : tools/banc_cases.py score <banc> --engine model (sur des planches que le modèle n'a pas apprises).
Les planches ne quittent pas ce PC. Résultat : predictions-<essai>-<modele>.json et le modèle appris (.pt)."""
import json, os, shutil, sys, time
TRAVAIL = os.environ.get("BULLE_BANCS") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICI = os.path.join(TRAVAIL, "ia-test")
os.makedirs(ICI, exist_ok=True)
SPLITS = {"A": (["bulle-banc-nouveau", "bulle-banc-essai"], ["bulle-banc-lots"]),
          "B": (["bulle-banc-lots", "bulle-banc-essai"], ["bulle-banc-nouveau"]),
          "final": (["bulle-banc-nouveau", "bulle-banc-essai", "bulle-banc-lots"], ["bulle-banc-lots"])}
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def pages_annotees(banc):
    d = os.path.join(TRAVAIL, banc)
    gt = json.load(open(os.path.join(d, "gt.json"), encoding="utf-8"))
    fichiers = {os.path.splitext(f)[0]: os.path.join(d, "pages", f) for f in os.listdir(os.path.join(d, "pages")) if f.lower().endswith(EXTS)}
    for k, e in gt.items():
        boxes = e.get("boxes") if isinstance(e, dict) else e
        if k in fichiers and boxes is not None:
            yield k, fichiers[k], [[min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])] for b in boxes]


def construire(essai):
    from PIL import Image
    racine = os.path.join(ICI, "donnees-" + essai)
    if os.path.isdir(racine):
        shutil.rmtree(racine)
    train, test = SPLITS[essai]
    for part, bancs in (("train", train), ("val", test)):
        os.makedirs(os.path.join(racine, "images", part)); os.makedirs(os.path.join(racine, "labels", part))
        n = 0
        for banc in bancs:
            for k, f, boxes in pages_annotees(banc):
                W, H = Image.open(f).size
                nom = banc + "__" + k
                shutil.copy(f, os.path.join(racine, "images", part, nom + os.path.splitext(f)[1].lower()))
                with open(os.path.join(racine, "labels", part, nom + ".txt"), "w") as out:
                    for x0, y0, x1, y1 in boxes:
                        x0, x1 = max(0, x0), min(W, x1); y0, y1 = max(0, y0), min(H, y1)
                        if x1 > x0 and y1 > y0:
                            out.write(f"0 {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}\n")
                n += 1
        print(f"{part} : {n} planches ({', '.join(bancs)})")
    yaml = os.path.join(racine, "data.yaml")
    with open(yaml, "w") as f:
        f.write(f"path: {racine}\ntrain: images/train\nval: images/val\nnames:\n  0: panel\n")
    return yaml, test


class _Tee:
    """Tout ce qui s'affiche est aussi écrit dans journal-<essai>.txt (pour relire une erreur)."""
    def __init__(self, a, b): self.a, self.b = a, b
    def write(self, s): self.a.write(s); self.b.write(s); self.b.flush()
    def flush(self): self.a.flush(); self.b.flush()
    def __getattr__(self, n): return getattr(self.a, n)


def main():
    essai = sys.argv[1] if len(sys.argv) > 1 else "A"
    journal = open(os.path.join(ICI, f"journal-{essai}.txt"), "a", encoding="utf-8")
    sys.stdout, sys.stderr = _Tee(sys.stdout, journal), _Tee(sys.stderr, journal)
    modele = sys.argv[sys.argv.index("--modele") + 1] if "--modele" in sys.argv else "yolo11n.pt"
    epochs = int(sys.argv[sys.argv.index("--epochs") + 1]) if "--epochs" in sys.argv else 40
    import torch
    from ultralytics import YOLO
    print("Carte graphique :", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "AUCUNE")
    if "--reprendre" in sys.argv and os.path.isdir(os.path.join(ICI, "donnees-" + essai)):
        test = SPLITS[essai][1]
    else:
        yaml, test = construire(essai)
    nom = f"{essai}-{os.path.splitext(os.path.basename(modele))[0]}"
    base = os.path.join(ICI, modele) if os.path.exists(os.path.join(ICI, modele)) else modele
    t0 = time.time()
    dernier = os.path.join(ICI, "runs", nom, "weights", "last.pt")
    if "--reprendre" in sys.argv and os.path.exists(dernier):
        print("Reprise là où l'apprentissage s'était arrêté…")
        YOLO(dernier).train(resume=True)
    else:
      m = YOLO(base)
      m.train(data=yaml, epochs=epochs, imgsz=640, batch=4 if "best" in modele or "x" in modele else 16, device=0,
            project=os.path.join(ICI, "runs"), name=nom, exist_ok=True, workers=0, patience=25, plots=False,
            fliplr=0.0, mosaic=0.5, verbose=False)
    print(f"Apprentissage fini en {time.time() - t0:.0f} s")
    poids = os.path.join(ICI, "runs", nom, "weights", "best.pt")
    m = YOLO(poids)
    out = {"model": nom, "pages": {}}
    t1 = time.time(); n = 0
    for banc in ["bulle-banc-nouveau", "bulle-banc-lots", "bulle-banc-essai"]:
        for k, f, _ in pages_annotees(banc):
            r = m.predict(f, imgsz=640, conf=0.05, device=0, verbose=False)[0]
            H, W = r.orig_shape
            out["pages"][banc + "/" + k] = [[round(a / W, 4), round(b / H, 4), round(c / W, 4), round(d / H, 4), round(s, 3), 0]
                                             for (a, b, c, d), s in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
            n += 1
    out["test"] = test
    out["secondes_par_planche"] = round((time.time() - t1) / max(1, n), 4)
    dest = os.path.join(ICI, f"predictions-{nom}.json")
    json.dump(out, open(dest, "w"), indent=0)
    shutil.copy(poids, os.path.join(ICI, f"modele-{nom}.pt"))
    try:   # copie ONNX : le format que Bulle saura lire (sans PyTorch)
        onnx = YOLO(poids).export(format="onnx", imgsz=640, simplify=True)
        shutil.copy(onnx, os.path.join(ICI, f"modele-{nom}.onnx"))
        print(f"Modèle ONNX -> modele-{nom}.onnx")
    except Exception as e:
        print("Conversion ONNX impossible :", e)
    print(f"Fini -> {os.path.basename(dest)} (test sur {', '.join(test)})")


if __name__ == "__main__":
    main()
