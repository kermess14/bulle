"""Tests du banc d'essai (tools/banclib.py), sans image : python tools/test_banc.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banclib as B  # noqa: E402

A = [0, 0, 100, 100]
Bx = [100, 0, 200, 100]
C = [0, 100, 100, 200]
D = [100, 100, 200, 200]


class Rect(unittest.TestCase):
    def test_iou(self):
        self.assertEqual(B.iou(A, A), 1.0)
        self.assertEqual(B.iou(A, Bx), 0.0)
        self.assertAlmostEqual(B.iou(A, [50, 0, 150, 100]), 50 * 100 / (100 * 100 * 2 - 50 * 100))
        self.assertEqual(B.iou([0, 0, 0, 0], [0, 0, 0, 0]), 0.0)   # pas de division par zéro

    def test_to_pixels(self):
        self.assertEqual(B.to_pixels([[0, 0.5, 1, 1]], 200, 100), [[0, 50, 200, 100]])

    def test_dedupe(self):
        out, n = B.dedupe([A, [1, 0, 100, 100], Bx, Bx])
        self.assertEqual((len(out), n), (2, 2))


class Reading(unittest.TestCase):
    def test_raw_and_reading(self):
        d = {"panels": [[0, 0, .5, .5], [.5, 0, 1, .5], [0, .5, 1, 1]], "rtl": [1, 0, 2]}
        self.assertEqual(B.raw(d), d["panels"])
        self.assertEqual(B.raw(d, manga=True), [d["panels"][1], d["panels"][0], d["panels"][2]])
        self.assertEqual(B.reading(d), d["panels"])

    def test_grow_join(self):
        d = {"panels": [[0, 0, .5, .5], [.5, 0, 1, .5], [0, .5, 1, 1]], "rtl": [0, 1, 2],
             "join": [[0, 1]], "grow": {"2": [0, .45, 1, 1]}}
        self.assertEqual(B.reading(d), [[0, 0, 1, .5], [0, .45, 1, 1]])
        self.assertEqual(B.raw(d), d["panels"])                       # brut : ni grow ni join

    def test_bad_rtl_ignored(self):
        d = {"panels": [[0, 0, 1, 1]], "rtl": [0, 0]}
        self.assertEqual(B.raw(d, manga=True), d["panels"])

    def test_empty(self):
        self.assertEqual(B.reading({"panels": []}), [])
        self.assertEqual(B.reading({}), [])


class Matching(unittest.TestCase):
    def test_one_to_one_fusion(self):
        # une seule détection couvre deux cases attendues : 1 juste + 1 manquante, pas 2 justes
        m = B.match([A, Bx], [[0, 0, 200, 100]], 0.5)
        self.assertEqual(len(m["pairs"]), 1)
        self.assertEqual(m["fn"], [1])
        self.assertEqual(m["fp"], [])
        # l'ancien score, lui, en voit 2 de justes (c'est pour ça qu'il est seulement « historique »)
        self.assertEqual(B.legacy_score([A, Bx], [[0, 0, 200, 100]]), (0, 1))
        self.assertEqual(B.legacy_score([[0, 0, 200, 100]], [A, Bx]), (0, 2))

    def test_one_to_one_split(self):
        # une case attendue coupée en deux : 1 juste + 1 en trop (le seuil est inclusif : IoU 0.5 pile passe à 0.5)
        m = B.match([[0, 0, 200, 100]], [A, Bx], 0.5)
        self.assertEqual((len(m["pairs"]), m["fp"]), (1, [1]))
        m = B.match([[0, 0, 200, 100]], [A, Bx], 0.6)
        self.assertEqual((m["pairs"], m["fp"], m["fn"]), ([], [0, 1], [0]))
        m = B.match([[0, 0, 200, 100]], [[0, 0, 120, 100], Bx], 0.5)
        self.assertEqual(len(m["pairs"]), 1)
        self.assertEqual(m["fp"], [1])

    def test_best_pairs_first(self):
        det = [[2, 2, 98, 98], [0, 0, 100, 100]]
        m = B.match([A], det, 0.5)
        self.assertEqual(m["pairs"][0][1], 1)                         # la meilleure IoU gagne
        self.assertEqual(m["fp"], [0])

    def test_prf(self):
        self.assertEqual(B.prf(0, 0, 0), (1.0, 1.0, 1.0))
        self.assertEqual(B.prf(0, 3, 0), (0.0, 0.0, 0.0))
        p, r, f = B.prf(2, 1, 2)
        self.assertAlmostEqual(p, 2 / 3)
        self.assertAlmostEqual(r, 0.5)
        self.assertAlmostEqual(f, 2 * p * r / (p + r))

    def test_order(self):
        self.assertEqual(B.order_score([(0, 0, 1), (1, 1, 1), (2, 2, 1)], 3), 1.0)
        self.assertEqual(B.order_score([(0, 1, 1), (1, 0, 1), (2, 2, 1)], 3), 0.5)
        self.assertIsNone(B.order_score([(0, 0, 1)], 1))
        self.assertIsNone(B.order_score([], 0))
        self.assertEqual(B.order_score([(0, 0, 1), (2, 1, 1)], 3), None)   # la case 1 manque : aucun pas mesurable

    def test_page_metrics_perfect_and_empty(self):
        pm = B.page_metrics([A, Bx, C, D], [A, Bx, C, D])
        for thr in B.IOU_THRESHOLDS:
            self.assertTrue(pm[thr]["perfect"])
            self.assertEqual(pm[thr]["f1"], 1.0)
        pm = B.page_metrics([], [])
        self.assertTrue(pm[0.5]["perfect"])
        self.assertEqual((pm[0.5]["p"], pm[0.5]["r"]), (1.0, 1.0))
        pm = B.page_metrics([], [A])
        self.assertEqual((pm[0.5]["fp"], pm[0.5]["p"]), (1, 0.0))
        pm = B.page_metrics([A], [])
        self.assertEqual((pm[0.5]["fn"], pm[0.5]["r"]), (1, 0.0))

    def test_thresholds(self):
        pm = B.page_metrics([A], [[0, 0, 100, 80]], (0.5, 0.9))
        self.assertEqual(pm[0.5]["tp"], 1)
        self.assertEqual(pm[0.9]["tp"], 0)

    def test_aggregate(self):
        per = {"p1": B.page_metrics([A, Bx], [A, Bx]), "p2": B.page_metrics([A, Bx], [[0, 0, 200, 100]])}
        agg = B.aggregate(per)
        t = agg[0.5]
        self.assertEqual((agg["pages"], t["tp"], t["fp"], t["fn"], t["perfect"]), (2, 3, 0, 1, 1))
        self.assertAlmostEqual(t["r"], 0.75)
        self.assertAlmostEqual(t["f1_macro"], (1.0 + 2 / 3) / 2)
        self.assertEqual(B.aggregate({})[0.5]["f1_macro"], 1.0)


class Annotations(unittest.TestCase):
    def test_normalize(self):
        a = B.normalize_gt([[100, 100, 0, 0], A])
        self.assertEqual(a["boxes"], [A])                               # remis d'équerre, doublon retiré
        self.assertEqual(a["dups"], 1)
        self.assertFalse(a["manga"])
        a = B.normalize_gt({"boxes": [A], "manga": True, "album": "X", "set": "val"})
        self.assertEqual((a["manga"], a["album"], a["set"]), (True, "X", "val"))
        self.assertEqual(B.normalize_gt(None)["boxes"], [])
        with self.assertRaises(ValueError):
            B.normalize_gt({"boxes": [], "set": "test"})

    def test_sets_by_album(self):
        self.assertEqual(B.assign_set("k", "Album", "val"), "val")
        self.assertEqual(B.assign_set("k", None), "dev")
        same = {B.assign_set(f"p{i}", "Même album") for i in range(10)}
        self.assertEqual(len(same), 1)                                  # un album = un seul jeu
        seen = {B.assign_set("k", f"album-{i}") for i in range(200)}
        self.assertEqual(seen, {"dev", "val"})                          # les deux jeux sont servis


class Misc(unittest.TestCase):
    def test_timing(self):
        s = B.timing_stats({})
        self.assertEqual(s["n"], 0)
        s = B.timing_stats({f"p{i}": i / 10 for i in range(1, 21)})
        self.assertEqual(s["n"], 20)
        self.assertAlmostEqual(s["median"], 1.05)
        self.assertAlmostEqual(s["p95"], 1.9)
        self.assertEqual((s["max"], s["worst"]), (2.0, "p20"))

    def test_compare(self):
        base = {"a": {"panels": [A]}, "b": {"panels": [A]}, "z": {"panels": []}}
        res = {"a": {"panels": [A]}, "b": {"panels": [Bx]}, "n": {"panels": []}}
        self.assertEqual(B.compare(base, res), {"changed": ["b"], "added": ["n"], "removed": ["z"]})


if __name__ == "__main__":
    unittest.main(verbosity=1)
