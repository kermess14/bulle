"""Contrats de la détection des cases (bulle/panels.py), sur des planches fabriquées ici : python tools/test_panels_contracts.py

Ce que `detect_panels(img, retry=True, _bg=None, manga=True)` promet :
  - un dictionnaire avec "panels" (rectangles [x0, y0, x1, y1] en fractions de la page, 0 ≤ x0 < x1 ≤ 1, ordre de
    lecture occidental), "rtl" (une permutation des indices de "panels" : l'ordre de lecture manga) et
    "v" (= PANELS_VERSION, la version de la détection, pour savoir si une case gardée en base est encore valable) ;
  - "panels" vide = la page entière est une seule case (page blanche, illustration, page de texte) ;
  - manga=False : "rtl" est l'ordre occidental et "rtl_full" vaut False (les cases sont les mêmes) ;
  - facultatifs : "join" (paires [a, b] d'indices de cases montrées ensemble, parce qu'un texte les chevauche) et
    "grow" ({"indice": rectangle} : case élargie pour ne pas couper une bulle qui déborde) ; les indices renvoient à
    "panels" et les rectangles de "grow" contiennent la case d'origine ;
  - l'appel ne lève pas d'exception sur une image quelconque (les étapes facultatives sont protégées) ; une image
    en couleur, en niveaux de gris ou avec transparence est acceptée.
Ces tests fixent le contrat, pas la qualité : ils ne mesurent pas si les cases sont justes (c'est le banc d'essai).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from bulle import panels as P  # noqa: E402


def grid_page(w=800, h=1100, rows=3, cols=2, gutter=24, margin=40, bg=(255, 255, 255)):
    """Planche synthétique : cases à cadre noir, intérieur gris clair, séparées par des gouttières blanches."""
    im = Image.new("RGB", (w, h), bg)
    dr = ImageDraw.Draw(im)
    cw = (w - 2 * margin - (cols - 1) * gutter) / cols
    ch = (h - 2 * margin - (rows - 1) * gutter) / rows
    boxes = []
    for r in range(rows):
        for c in range(cols):
            x0 = margin + c * (cw + gutter)
            y0 = margin + r * (ch + gutter)
            x1, y1 = x0 + cw, y0 + ch
            dr.rectangle([x0, y0, x1, y1], fill=(200, 200, 200), outline=(0, 0, 0), width=4)
            # un peu de dessin dedans, pour que la case ne soit pas prise pour du fond
            dr.ellipse([x0 + 20, y0 + 20, x1 - 20, y1 - 20], outline=(30, 30, 30), width=3)
            boxes.append((x0 / w, y0 / h, x1 / w, y1 / h))
    return im, boxes


def check_shape(t, d, n_expected=None):
    t.assertIsInstance(d, dict)
    t.assertIn("panels", d)
    t.assertIn("rtl", d)
    t.assertEqual(d.get("v"), P.PANELS_VERSION)
    pans = d["panels"]
    for r in pans:
        t.assertEqual(len(r), 4)
        t.assertTrue(0 <= r[0] < r[2] <= 1, r)
        t.assertTrue(0 <= r[1] < r[3] <= 1, r)
    t.assertEqual(sorted(d["rtl"]), list(range(len(pans))), "rtl doit être une permutation des cases")
    for a, b in d.get("join") or []:
        t.assertTrue(0 <= a < len(pans) and 0 <= b < len(pans) and a != b, (a, b))
    for k, r in (d.get("grow") or {}).items():
        i = int(k)
        t.assertTrue(0 <= i < len(pans))
        o = pans[i]
        t.assertTrue(r[0] <= o[0] + 1e-6 and r[1] <= o[1] + 1e-6 and r[2] >= o[2] - 1e-6 and r[3] >= o[3] - 1e-6,
                     "grow contient la case d'origine")
    if n_expected is not None:
        t.assertEqual(len(pans), n_expected)


class Contracts(unittest.TestCase):
    def test_grid(self):
        im, boxes = grid_page()
        d = P.detect_panels(im)
        check_shape(self, d, len(boxes))
        # ordre occidental : de gauche à droite puis de haut en bas (centres)
        centers = [((r[0] + r[2]) / 2, (r[1] + r[3]) / 2) for r in d["panels"]]
        for (x0, y0), (x1, y1) in zip(centers, centers[1:]):
            self.assertTrue(y1 > y0 + 0.05 or (abs(y1 - y0) < 0.05 and x1 > x0), (centers,))
        # chaque case attendue est retrouvée (IoU large)
        for b in boxes:
            best = max(_iou(b, r) for r in d["panels"])
            self.assertGreater(best, 0.7, (b, d["panels"]))

    def test_manga_order_and_flag(self):
        im, _ = grid_page()
        d = P.detect_panels(im, manga=True)
        check_shape(self, d)
        self.assertNotIn("rtl_full", d)
        # en manga, la première case lue est celle en haut à droite
        first = d["panels"][d["rtl"][0]]
        self.assertGreater((first[0] + first[2]) / 2, 0.5)
        d2 = P.detect_panels(im, manga=False)
        check_shape(self, d2)
        self.assertEqual(d2["panels"], d["panels"], "les cases ne dépendent pas de l'ordre demandé")
        self.assertEqual(d2["rtl"], list(range(len(d2["panels"]))))
        self.assertIs(d2.get("rtl_full"), False)

    def test_blank_and_full_page(self):
        for bg in ((255, 255, 255), (0, 0, 0)):
            d = P.detect_panels(Image.new("RGB", (600, 900), bg))
            check_shape(self, d, 0)
            self.assertEqual(d["rtl"], [])
        # une illustration pleine page (gradient sans gouttière) : une seule case, ou rien (= page entière)
        im = Image.new("RGB", (600, 900))
        px = im.load()
        for y in range(900):
            for x in range(600):
                px[x, y] = ((x * 255) // 600, (y * 255) // 900, 128)
        d = P.detect_panels(im)
        check_shape(self, d)
        self.assertLessEqual(len(d["panels"]), 1)

    def test_modes_and_sizes(self):
        im, boxes = grid_page()
        for conv in ("L", "RGBA", "P"):
            d = P.detect_panels(im.convert(conv))
            check_shape(self, d, len(boxes))
        small = im.resize((200, 275))
        check_shape(self, P.detect_panels(small))
        big = im.resize((2400, 3300))
        d = P.detect_panels(big)
        check_shape(self, d, len(boxes))
        check_shape(self, P.detect_panels(Image.new("RGB", (1, 1), (255, 255, 255))), 0)

    def test_retry_off(self):
        im, boxes = grid_page()
        check_shape(self, P.detect_panels(im, retry=False), len(boxes))

    def test_edge_ratios_shape(self):
        # une bande vide (b <= a) doit renvoyer autant de valeurs que la forme demandée : 3, ou 4 avec `blockers`
        mask = Image.new("L", (50, 50), 255)
        self.assertEqual(len(P._edge_ratios(mask, (0, 0, 50, 50), 0, 10, 10)), 3)
        self.assertEqual(len(P._edge_ratios(mask, (0, 0, 50, 50), 0, 10, 10, blockers=True)), 4)
        self.assertEqual(len(P._edge_ratios(mask, (0, 0, 0, 50), 0, 0, 10, blockers=True)), 4)
        self.assertEqual(len(P._edge_ratios(mask, (0, 0, 50, 50), 1, 5, 15, blockers=True)), 4)

    def test_version_is_int(self):
        self.assertIsInstance(P.PANELS_VERSION, int)
        self.assertGreaterEqual(P.PANELS_VERSION, 18)


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u else 0


if __name__ == "__main__":
    unittest.main(verbosity=1)
