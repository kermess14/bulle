"""Tests du lecteur dans un vrai navigateur (Playwright + Chromium) : paliers de largeur, sens manga changé pendant une
réponse en route, mémoire du défilement continu. Facultatif : ignoré si Playwright ou Chromium manquent (le workflow
« Tests » ne l'exécute pas ; à lancer à la main : python tools/test_reader_browser.py).
Non testé sur appareil réel (tablette, téléphone) : seulement un Chromium de bureau."""
from __future__ import annotations

import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import zipfile

os.environ.setdefault("SCAN_ON_START", "0")
os.environ.setdefault("PRELOAD_COVERS", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image, ImageDraw  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except Exception:  # noqa: BLE001
    sync_playwright = None

from bulle.server import create_app  # noqa: E402


def grid_jpeg(w=800, h=1200):
    """Planche de 2 colonnes × 3 rangées : cadres noirs, gouttières blanches, un peu de dessin dedans."""
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for r in range(3):
        for c in range(2):
            x0, y0 = 30 + c * 375, 40 + r * 385
            d.rectangle([x0, y0, x0 + 350, y0 + 360], fill=(200 + c * 20, 190 + r * 20, 150), outline="black", width=5)
            d.ellipse([x0 + 60, y0 + 60, x0 + 280, y0 + 300], fill=(60, 80 + r * 40, 120 + c * 40))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


@unittest.skipIf(sync_playwright is None, "Playwright absent")
class ReaderBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bulle-browser-")
        root = os.path.join(cls.tmp, "lib", "Série")
        os.makedirs(root)
        jpg = grid_jpeg()
        for name, n in (("Court", 4), ("Long", 80)):
            with zipfile.ZipFile(os.path.join(root, f"{name}.cbz"), "w") as z:
                for i in range(n):
                    z.writestr(f"{i + 1:03d}.jpg", jpg)
        cls.app = create_app(os.path.join(cls.tmp, "lib"), os.path.join(cls.tmp, "data"))
        cls.lib = cls.app.extensions["bulle"]["library"]
        cls.lib.scan()
        row = lambda name: dict(cls.lib.conn.execute("SELECT * FROM nodes WHERE name=?", (name,)).fetchone())["id"]  # noqa: E731
        cls.short, cls.long = row("Court"), row("Long")
        from werkzeug.serving import make_server
        cls.srv = make_server("127.0.0.1", 0, cls.app, threaded=True)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            cls.srv.shutdown()
            raise unittest.SkipTest(f"Chromium indisponible : {e}")

    @classmethod
    def tearDownClass(cls):
        for f in (getattr(cls, "browser", None) and cls.browser.close, getattr(cls, "pw", None) and cls.pw.stop,
                  getattr(cls, "srv", None) and cls.srv.shutdown):
            try:
                f and f()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def page(self, init=None):
        ctx = self.browser.new_context(viewport={"width": 1280, "height": 800})
        if init:
            ctx.add_init_script(init)
        pg = ctx.new_page()
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        self.addCleanup(ctx.close)
        return pg

    def test_widths_follow_server_steps(self):
        asked = set()
        pg = self.page()
        pg.on("request", lambda r: asked.add(int(m.group(1))) if (m := re.search(r"/api/page/\d+/\d+\?w=(\d+)", r.url)) else None)
        pg.goto(f"{self.base}/read/{self.short}?page=0")
        pg.wait_for_timeout(800)
        if not pg.is_visible("#pedit"):
            pg.keyboard.press("c")
        pg.wait_for_timeout(2000)
        for _ in range(4):
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(400)
        self.assertTrue(asked)
        self.assertTrue(all(w % 100 == 0 and 300 <= w <= 3000 for w in asked), sorted(asked))
        self.assertEqual(self.errors, [])

    def test_scroll_mode_frees_far_pages(self):
        pg = self.page()
        pg.goto(f"{self.base}/read/{self.long}?page=0")
        pg.wait_for_timeout(1000)
        for _ in range(6):
            if pg.evaluate("document.body.classList.contains('mode-scroll')"):
                break
            pg.keyboard.press("d")
            pg.wait_for_timeout(300)
        self.assertTrue(pg.evaluate("document.body.classList.contains('mode-scroll')"))
        for _ in range(40):
            pg.evaluate("document.querySelector('#stage').scrollBy(0, 1400)")
            pg.wait_for_timeout(120)
        pg.wait_for_timeout(600)
        loaded = pg.evaluate("[...document.querySelectorAll('#scroll img')].filter(i => i.getAttribute('src')).length")
        self.assertLessEqual(loaded, 14, "les pages lointaines doivent être libérées")
        pg.evaluate("document.querySelector('#stage').scrollTo(0, 0)")
        pg.wait_for_timeout(1500)
        back = pg.evaluate("[...document.querySelectorAll('#scroll img')].filter(i => i.complete && i.naturalWidth > 0).length")
        self.assertGreaterEqual(back, 1, "elles reviennent quand on remonte")
        self.assertEqual(self.errors, [])

    def test_manga_switch_during_request(self):
        """La réponse « occidentale » arrive après la bascule en manga : elle ne doit pas écraser l'ordre manga."""
        init = """
        const _f = window.fetch;
        window.fetch = (u, o) => {
          const url = String(u);
          if (url.includes('/api/panels/') && !url.includes('rtl=1') && !url.includes('/manual'))
            return _f(u, o).then(r => new Promise(res => setTimeout(() => res(r), 1800)));
          return _f(u, o);
        };"""
        with sqlite3.connect(os.path.join(self.tmp, "data", "bulle.sqlite")) as c:
            c.execute("DELETE FROM panels")
        pg = self.page(init)
        pg.goto(f"{self.base}/read/{self.short}?page=0")
        pg.wait_for_timeout(600)
        pg.evaluate("localStorage.clear()")
        if pg.evaluate("document.querySelector('#manga').classList.contains('on')"):
            pg.keyboard.press("m")
            pg.wait_for_timeout(300)
        if not pg.is_visible("#pedit"):
            pg.keyboard.press("c")
        pg.wait_for_timeout(300)
        pg.keyboard.press("m")            # manga, pendant que la requête occidentale est en route
        pg.wait_for_timeout(5000)
        for _ in range(2):
            pg.keyboard.press(" ")
            pg.wait_for_timeout(900)
        raced = pg.evaluate("document.querySelector('#page').getBoundingClientRect().left")
        pg.reload()
        pg.wait_for_timeout(4500)
        for _ in range(2):
            pg.keyboard.press(" ")
            pg.wait_for_timeout(900)
        clean = pg.evaluate("document.querySelector('#page').getBoundingClientRect().left")
        self.assertAlmostEqual(raced, clean, delta=3)
        self.assertEqual(self.errors, [])

    def test_resume_at_panel(self):
        pg = self.page()
        pg.goto(f"{self.base}/read/{self.short}?page=1")
        pg.wait_for_timeout(800)
        if not pg.is_visible("#pedit"):
            pg.keyboard.press("c")
        pg.wait_for_timeout(2000)
        for _ in range(3):
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(500)
        before = pg.inner_text("#rcount")
        pg.wait_for_timeout(900)
        with sqlite3.connect(os.path.join(self.tmp, "data", "bulle.sqlite")) as c:
            row = c.execute("SELECT page, panel, panel_count FROM progress WHERE node_id=?", (self.short,)).fetchone()
        self.assertEqual(row[0], 1)
        self.assertIsNotNone(row[1])
        pg.goto(f"{self.base}/read/{self.short}")
        pg.wait_for_timeout(2500)
        after = pg.inner_text("#rcount")
        self.assertEqual(before, after)
        self.assertIn("case", after)
        self.assertEqual(self.errors, [])

    def test_editor_order_and_full_page(self):
        pg = self.page()
        pg.goto(f"{self.base}/read/{self.short}?page=2")
        pg.wait_for_timeout(800)
        if not pg.is_visible("#pedit"):
            pg.keyboard.press("c")
        pg.wait_for_timeout(2000)
        pg.keyboard.press("e")
        pg.wait_for_timeout(800)
        self.assertTrue(pg.is_visible(".pe"))
        n = pg.locator(".pe-r").count()
        self.assertGreaterEqual(n, 4)
        pg.locator(".pe-r").first.click()
        pg.keyboard.press("]")
        pg.wait_for_timeout(200)
        self.assertIn("fixé", pg.inner_text('[data-a="order"]'))
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(1200)
        with sqlite3.connect(os.path.join(self.tmp, "data", "bulle.sqlite")) as c:
            import json as _j
            d = _j.loads(c.execute("SELECT data FROM panels WHERE node_id=? AND page=2", (self.short,)).fetchone()[0])
        self.assertTrue(d["manual"] and d["custom_order"])
        self.assertEqual(len(d["panels"]), n)
        pg.keyboard.press("e")
        pg.wait_for_timeout(800)
        pg.click('[data-a="full"]')
        pg.wait_for_timeout(1200)
        with sqlite3.connect(os.path.join(self.tmp, "data", "bulle.sqlite")) as c:
            d = _j.loads(c.execute("SELECT data FROM panels WHERE node_id=? AND page=2", (self.short,)).fetchone()[0])
        self.assertEqual((d["manual"], d["panels"]), (True, []))
        self.assertEqual(self.errors, [])

    def test_diag_screen(self):
        pg = self.page()
        pg.goto(f"{self.base}/read/{self.short}?page=0")
        pg.wait_for_timeout(800)
        if not pg.is_visible("#pedit"):
            pg.keyboard.press("c")
        pg.wait_for_timeout(2000)
        pg.keyboard.press("g")
        pg.wait_for_timeout(600)
        self.assertTrue(pg.is_visible(".pd"))
        self.assertGreaterEqual(pg.locator(".pd-panel").count(), 4)
        self.assertIn("Version du détecteur", pg.inner_text(".pd-info"))
        pg.click("[data-a=measure]")
        pg.wait_for_timeout(2500)
        txt = pg.inner_text(".pd-info")
        self.assertIn("Dimensions analysées", txt)
        self.assertIn("Budget des cadres épuisé", txt)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        self.assertFalse(pg.is_visible(".pd"))
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
