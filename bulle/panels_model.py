"""Détection des cases par un modèle appris (moteur « model »), hors ligne.

Un petit réseau de détection d'objets (YOLO11n, environ 10 Mo au format ONNX) a appris à reconnaître les cases sur
380 planches corrigées à la main (banc privé, jamais publié). Il tourne ici, dans Bulle, sur le processeur du
serveur, avec onnxruntime : pas de réseau, pas d'API, rien n'est envoyé nulle part, et le même fichier donne
toujours le même résultat pour la même planche (il ne réapprend pas).

Mesures (lot 103, IoU 0,5, planches que le modèle n'avait pas vues pendant son apprentissage) :
- banc de validation, 100 planches : F1 96,9 % (détecteur à règles : 94,9 %), 79 planches parfaites (75) ;
- banc difficile, 240 planches : F1 93,7 % (89,1 %), 149 planches parfaites (141) ;
- environ 0,1 s par planche sur un cœur de processeur récent (0,2 à 0,4 s sur un vieux Xeon).

Le résultat suit le contrat des cases (voir panels.valid_result) ; le serveur garde le détecteur à règles en secours
(onnxruntime absent, fichier du modèle manquant ou illisible). Licence : le modèle de départ (Ultralytics YOLO11n)
est sous AGPL-3.0, le modèle appris aussi ; seul le fichier .onnx est utilisé (pas la bibliothèque Ultralytics).
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from PIL import Image

MODEL_VERSION = 1001          # version des cases de ce moteur (à augmenter à chaque nouveau modèle)
MODEL_FILE = os.environ.get("PANELS_MODEL", os.path.join(os.path.dirname(__file__), "models", "cases-yolo11n.onnx"))
MODEL_SIZE = 640              # côté de l'image donnée au modèle (celle de l'apprentissage)
MODEL_CONF = 0.6              # confiance minimale d'une case (réglée sur le banc : moins de fausses cases, peu de manquées)
MODEL_NMS = 0.5               # deux boîtes qui se recouvrent à plus de 50 % : on garde la plus sûre
MODEL_MIN = 0.03              # côté minimal d'une case (fraction de la page) : numéros de page, petites bulles
MODEL_THREADS = max(1, int(os.environ.get("PANELS_MODEL_THREADS", "2") or 2))

_lock = threading.Lock()
_session = None
_error: Optional[str] = None


def available() -> bool:
    """Le moteur peut-il tourner ici (onnxruntime installé, fichier du modèle lisible) ?"""
    return _load() is not None


def status() -> dict:
    _load()
    return {"file": MODEL_FILE, "loaded": _session is not None, "error": _error, "version": MODEL_VERSION}


def _load():
    global _session, _error
    if _session is not None or _error is not None:
        return _session
    with _lock:
        if _session is not None or _error is not None:
            return _session
        try:
            import onnxruntime as ort   # noqa: WPS433 (import paresseux : Bulle démarre sans)
            if not os.path.exists(MODEL_FILE):
                raise FileNotFoundError(MODEL_FILE)
            so = ort.SessionOptions()
            so.intra_op_num_threads = MODEL_THREADS
            so.inter_op_num_threads = 1
            _session = ort.InferenceSession(MODEL_FILE, so, providers=["CPUExecutionProvider"])
        except Exception as e:  # noqa: BLE001
            _error = f"{type(e).__name__}: {e}"
    return _session


def raw_boxes(img: Image.Image) -> list[tuple]:
    """Boîtes trouvées par le modèle : [(x0, y0, x1, y1, confiance)], en fractions de la page, sans ordre."""
    import numpy as np
    sess = _load()
    if sess is None:
        raise RuntimeError(_error or "modèle indisponible")
    im = img.convert("RGB")
    W, H = im.size
    r = MODEL_SIZE / max(W, H)
    nw, nh = max(1, round(W * r)), max(1, round(H * r))
    canvas = Image.new("RGB", (MODEL_SIZE, MODEL_SIZE), (114, 114, 114))
    px, py = (MODEL_SIZE - nw) // 2, (MODEL_SIZE - nh) // 2
    canvas.paste(im.resize((nw, nh), Image.Resampling.BILINEAR), (px, py))
    x = (np.asarray(canvas, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
    out = np.asarray(sess.run(None, {sess.get_inputs()[0].name: x})[0])[0]   # (5, N) : cx, cy, w, h, confiance
    if out.shape[0] > out.shape[1]:
        out = out.T
    keep = out[4] >= MODEL_CONF
    cx, cy, bw, bh, sc = (out[i][keep] for i in range(5))
    boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
    order = sc.argsort()[::-1]
    kept: list[int] = []
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = int(order[0])
        kept.append(i)
        rest = order[1:]
        iw = np.clip(np.minimum(boxes[i, 2], boxes[rest, 2]) - np.maximum(boxes[i, 0], boxes[rest, 0]), 0, None)
        ih = np.clip(np.minimum(boxes[i, 3], boxes[rest, 3]) - np.maximum(boxes[i, 1], boxes[rest, 1]), 0, None)
        inter = iw * ih
        order = rest[inter / (area[i] + area[rest] - inter + 1e-9) < MODEL_NMS]
    res = []
    for i in kept:
        x0, y0, x1, y1 = boxes[i]
        x0, x1 = (x0 - px) / nw, (x1 - px) / nw
        y0, y1 = (y0 - py) / nh, (y1 - py) / nh
        x0, y0, x1, y1 = max(0.0, float(x0)), max(0.0, float(y0)), min(1.0, float(x1)), min(1.0, float(y1))
        if x1 - x0 >= MODEL_MIN and y1 - y0 >= MODEL_MIN:
            res.append((x0, y0, x1, y1, float(sc[i])))
    return res


def detect(img: Image.Image, reading_order, manga: bool = True, diag: Optional[dict] = None, **_ignored) -> dict:
    """Cases d'une planche, au contrat de panels.detect_panels ; moins de deux cases : pleine page (liste vide)."""
    import time
    t0 = time.perf_counter()
    boxes = raw_boxes(img)
    empty = {"panels": [], "rtl": [], "v": MODEL_VERSION, "engine": "model"}
    if diag is not None:
        diag.update({"engine": "model", "model_file": os.path.basename(MODEL_FILE), "found": len(boxes)})
    if len(boxes) < 2:
        if diag is not None:
            diag["ms_total"] = round(1000 * (time.perf_counter() - t0), 1)
        return empty
    S = 10000   # ordre de lecture calculé en entiers (la même fonction que le détecteur à règles)
    px = [(round(a * S), round(b * S), round(c * S), round(d * S)) for a, b, c, d, _ in boxes]
    ltr = reading_order(px, False)
    panels = [[round(v / S, 4) for v in t] for t in ltr]
    order = list(range(len(panels)))
    if manga:
        index = {t: i for i, t in enumerate(ltr)}
        order = [index[t] for t in reading_order(px, True)]
        if sorted(order) != list(range(len(panels))):
            order = list(range(len(panels)))
    out = {"panels": panels, "rtl": order, "v": MODEL_VERSION, "engine": "model"}
    if not manga:
        out["rtl_full"] = False
    if diag is not None:
        diag["ms_total"] = round(1000 * (time.perf_counter() - t0), 1)
    return out
