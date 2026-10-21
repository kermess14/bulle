"""Tests automatiques de la lecture simple (/simple) : python tools/test_simple.py [--vnu chemin/vnu.jar]

Construit une petite bibliothèque jetable (quelques CBZ fabriqués ici), lance l'application avec le client de test de Flask
et vérifie : toutes les routes répondent ; aucune balise <script>, aucun attribut on…, aucun lien javascript: ; aucune
ressource externe ; tout texte venu de la bibliothèque est échappé ; les images tiennent dans 1024 px, en JPEG de base,
avec des en-têtes de cache ; la progression est enregistrée et reprise ; les règles de sécurité (profil choisi, mots de
passe, code d'accès, comptes, rubrique Adulte, HTTPS imposé hors réseau local) s'appliquent aussi à /simple.
Si le validateur W3C (vnu.jar, Java) est disponible (--vnu ou variable VNU_JAR), chaque page est validée ; sinon on se
contente de html5lib en mode strict (s'il est installé).
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SCAN_ON_START", "0")
os.environ.setdefault("PRELOAD_COVERS", "0")

from PIL import Image, ImageDraw  # noqa: E402

from bulle.library import DEFAULT_PROFILE  # noqa: E402
from bulle.server import create_app, hash_pin  # noqa: E402

IPAD1_UA = ("Mozilla/5.0 (iPad; U; CPU OS 5_1 like Mac OS X; fr-fr) AppleWebKit/534.46 (KHTML, like Gecko) "
            "Version/5.1 Mobile/9B176 Safari/7534.48.3")
VNU = None
EVIL = '<b>x</b> & "q" \'z\''   # un titre piégé : doit ressortir échappé


FORM_RE = re.compile(r'<form method="get" action="([^"]*)" class="nav[^"]*">((?:<input type="hidden" name="[^"]*" value="[^"]*">)*)'
                     r'<button type="submit"(?: class="([^"]*)")?([^>]*)>')
HIDDEN_RE = re.compile(r'<input type="hidden" name="([^"]*)" value="([^"]*)">')


def nav_buttons(html):
    """Toute la navigation de /simple : [(adresse visitée, classe du bouton)]. En mode application (iPad), iOS rouvre Safari
    pour un <a href> touché : la navigation passe donc par des formulaires GET (action + champs cachés = l'adresse)."""
    import html as htmllib
    out = []
    for action, hidden, cls, _rest in FORM_RE.findall(html):
        fields = [(htmllib.unescape(k), htmllib.unescape(v)) for k, v in HIDDEN_RE.findall(hidden)]
        url = htmllib.unescape(action) + ("?" + "&".join(f"{k}={v}" for k, v in fields) if fields else "")
        out.append((url, cls or ""))
    return out


def targets(html):
    return [u for u, _ in nav_buttons(html)]


def button_target(html, cls):
    """L'adresse du bouton de classe `cls` (ex. « zone zl », « back »), ou None."""
    found = [u for u, c in nav_buttons(html) if c == cls]
    return found[0] if found else None


def make_cbz(path, sizes):
    """CBZ de pages JPEG dessinées (traits et texte, pour un poids réaliste)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for i, (w, h) in enumerate(sizes, 1):
            im = Image.new("RGB", (w, h), (250, 248, 240))
            d = ImageDraw.Draw(im)
            for k in range(0, h, max(20, h // 40)):
                d.line([(0, k), (w, (k * 7) % h)], fill=(30 + k % 90, 40, 60), width=3)
            d.rectangle([w // 8, h // 8, w * 7 // 8, h * 7 // 8], outline=(0, 0, 0), width=6)
            d.text((w // 3, h // 2), f"page {i}", fill=(0, 0, 0))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
            z.writestr(f"{i:03d}.jpg", buf.getvalue())


class SimpleTests(unittest.TestCase):
    pages_seen: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bulle-simple-")
        root = os.path.join(cls.tmp, "lib")
        make_cbz(os.path.join(root, "Astérix & Cie", "Tome 01.cbz"), [(900, 1300), (1400, 900), (2000, 2800)])
        make_cbz(os.path.join(root, "Astérix & Cie", "Tome 02.cbz"), [(400, 560), (400, 560)])
        make_cbz(os.path.join(root, "Zorro", "Sous-dossier", "Zorro T1.cbz"), [(600, 800), (600, 800)])
        make_cbz(os.path.join(root, "Adulte", "Secret.cbz"), [(500, 700)])
        make_cbz(os.path.join(root, "1000 bornes", "Un.cbz"), [(500, 700)])
        for i in range(1, 45):
            make_cbz(os.path.join(root, f"Série {i:02d}", "Un.cbz"), [(300, 420)])
        cls.app = create_app(root, os.path.join(cls.tmp, "data"))
        ext = cls.app.extensions["bulle"]
        cls.lib, cls.comics = ext["library"], ext["comics"]
        cls.lib.scan()
        # un titre piégé (les caractères < > " sont interdits dans les noms de fichiers Windows : on le pose en base)
        cls.t01 = cls.find("Tome 01")
        cls.t02 = cls.find("Tome 02")
        with cls.lib._write_lock:
            cls.lib.conn.execute("UPDATE nodes SET name=? WHERE id=?", (EVIL, cls.t01["id"]))
            cls.lib.conn.commit()
        cls.astx = cls.lib.node(cls.t01["parent_id"])
        cls.root = cls.lib.root_node()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def find(cls, name):
        row = cls.lib.conn.execute("SELECT * FROM nodes WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def setUp(self):
        # état de départ : un seul profil sans mot de passe, pas de code, pas de comptes, rien de caché
        self.lib.set_settings({"require_profile": False, "account_login": False, "force_https": False,
                               "access_pin_hash": "", "adult_paths": [], "adult_pin_hash": ""}, None)
        with self.lib._write_lock:
            self.lib.conn.execute("DELETE FROM profiles WHERE id<>?", (DEFAULT_PROFILE,))
            self.lib.conn.execute("UPDATE profiles SET pin_hash=NULL WHERE id=?", (DEFAULT_PROFILE,))
            self.lib.conn.execute("DELETE FROM progress")
            self.lib.conn.commit()
        self.app.config["TESTING"] = True
        self.c = self.app.test_client()
        self.c.environ_base["HTTP_USER_AGENT"] = IPAD1_UA
        self.c.environ_base["REMOTE_ADDR"] = "192.168.0.50"

    # ---- aides --------------------------------------------------------------------------
    def get(self, url, status=200, **kw):
        r = self.c.get(url, **kw)
        self.assertEqual(r.status_code, status, f"{url} → {r.status_code}")
        if r.mimetype == "text/html":
            self.check_html(r.get_data(as_text=True), url)
        return r

    def post(self, url, data, status=303):
        r = self.c.post(url, data=data)
        self.assertEqual(r.status_code, status, f"POST {url} → {r.status_code}")
        if r.mimetype == "text/html" and not 300 <= r.status_code < 400:   # (le corps d'une redirection n'est pas une page)
            self.check_html(r.get_data(as_text=True), "POST " + url)
        return r

    def check_html(self, html, where):
        low = html.lower()

        def absent(needle, what):   # (sans recopier toute la page dans le message d'échec)
            self.assertFalse(needle in low, f"{what} dans {where}")

        absent("<script", "balise script")
        absent("<noscript", "balise noscript")
        self.assertIsNone(re.search(r"<[^>]+\son[a-z]+\s*=", low), f"attribut on… dans {where}")
        absent("javascript:", "lien javascript:")
        for tag in ("<iframe", "<object", "<embed", '<form action="http', "@import"):
            absent(tag, tag)
        absent("http://", "adresse externe")
        absent("https://", "adresse externe")
        # en mode application (iPad), les liens doivent rester dans l'application : jamais de nouvelle fenêtre ni de
        # redirection par la page elle-même
        self.assertIsNone(re.search(r"\starget\s*=", low), f"target= dans {where}")
        # aucun <a> : en mode application iOS (avant 11.3) un lien touché rouvre Safari, avec sa barre d'adresse ; seuls
        # les formulaires restent dans l'application (navigation = formulaires GET, voir nav_buttons)
        self.assertIsNone(re.search(r"<a[\s>]", low), f"lien <a> dans {where}")
        for form in re.findall(r"<form\b[^>]*>", html):
            self.assertTrue(re.fullmatch(r'<form method="(get|post)" action="/simple[^"]*"( class="[^"]*")?>', form),
                            f"formulaire inattendu dans {where} : {form}")
        for m in re.finditer(r'<form method="get"[^>]*>', html):   # un formulaire GET est de navigation : classe « nav »
            self.assertIn('class="nav', m.group(0), f"formulaire GET sans classe nav dans {where}")
        self.assertIsNone(re.search(r'http-equiv\s*=\s*["\']?refresh', low), f"meta refresh dans {where}")
        # seuls <link> permis : les trois icônes de l'écran d'accueil
        links = re.findall(r"<link\b[^>]*>", html)
        self.assertEqual(len(links), 3, f"{len(links)} <link> dans {where}")
        for ln in links:
            self.assertTrue(re.fullmatch(r'<link rel="apple-touch-icon"( sizes="(72x72|144x144)")? href="/simple/icone-(72|144)\.png">', ln),
                            f"<link> inattendu dans {where} : {ln}")
        # balises Apple propres à iOS 5 (pas de manifest web avant iOS 11.3), dans TOUTES les pages /simple
        for tag in ('<meta name="apple-mobile-web-app-capable" content="yes">',
                    '<meta name="apple-mobile-web-app-status-bar-style" content="black">',
                    '<meta name="apple-mobile-web-app-title" content="Bulle">',
                    '<link rel="apple-touch-icon" href="/simple/icone-72.png">',
                    '<link rel="apple-touch-icon" sizes="144x144" href="/simple/icone-144.png">'):
            self.assertTrue(tag in html, f"{tag} manque dans {where}")
        for attr, val in re.findall(r'\b(src|href|action)="([^"]*)"', html):
            ok = (re.match(r"^/simple(/|\?|$)", val) or re.match(r"^/api/cover/\d+\?w=100$", val))
            self.assertTrue(ok, f"{attr}={val!r} sort de /simple dans {where}")
        for url in re.findall(r"url\(([^)]*)\)", html):   # la planche, image de fond de la page de lecture
            self.assertTrue(re.fullmatch(r"&#39;/simple/img/\d+/\d+\?v=\d+&#39;", url), f"url({url}) dans {where}")
        absent("<b>x</b>", "texte non échappé")
        for banned in ("/api/scan", "/api/settings", "admin", "reglages", "rescan"):
            absent(banned, banned)
        SimpleTests.pages_seen[where] = html

    def album(self, name="Tome 02"):
        return self.find(name)

    # ---- routes et contenu --------------------------------------------------------------
    def test_routes_repondent(self):
        r = self.get("/simple")
        self.assertIn("Toutes les séries", r.get_data(as_text=True))
        self.get("/simple/")
        s = self.get("/simple/series").get_data(as_text=True)
        self.assertIn("Astérix &amp; Cie", s)
        self.assertIn(f'/simple/serie/{self.astx["id"]}', s)
        self.get(f'/simple/serie/{self.astx["id"]}')
        sub = self.find("Sous-dossier")
        z = self.get(f'/simple/serie/{sub["id"]}').get_data(as_text=True)
        self.assertIn("Zorro T1", z)
        self.assertIn("Dossier au-dessus", z)
        r = self.c.get(f'/simple/lire/{self.t02["id"]}')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith(f'/simple/lire/{self.t02["id"]}?p=1'))
        self.get(f'/simple/lire/{self.t02["id"]}?p=1')
        self.get(f'/simple/lire/{self.t02["id"]}?p=2')
        self.get(f'/simple/lire/{self.t02["id"]}?p=99')   # borné à la dernière page
        self.get(f'/simple/lire/{self.t02["id"]}?p=abc')  # illisible → première page
        self.get("/simple/serie/999999", 404)
        self.get("/simple/lire/999999", 404)
        self.get(f'/simple/serie/{self.t02["id"]}', 404)  # un album n'est pas un dossier
        self.get("/simple/img/999999/0", 404)

    def test_pagination_et_index_alphabetique(self):
        s = self.get("/simple/series").get_data(as_text=True)
        self.assertIn("Page 1 / 3", s)       # 47 entrées, 20 par page
        self.assertIn('class="letters"', s)
        self.assertIn("/simple/series?l=S", targets(s))
        self.assertIn("/simple/series?l=0", targets(s))   # « # » : les noms qui commencent par un chiffre
        self.assertIn("/simple/series?p=2", targets(s))   # la page suivante : même adresse qu'avec un lien
        p3 = self.get("/simple/series?p=3").get_data(as_text=True)
        self.assertIn("Page 3 / 3", p3)
        z = self.get("/simple/series?l=Z").get_data(as_text=True)
        self.assertIn("Zorro", z)
        self.get("/simple/series?p=0")
        self.get("/simple/series?p=9999")
        self.get("/simple/series?l=%3Cscript%3E")

    def test_titres_echappes(self):
        s = self.get(f'/simple/serie/{self.astx["id"]}').get_data(as_text=True)
        self.assertIn("&lt;b&gt;x&lt;/b&gt; &amp; &quot;q&quot; &#x27;z&#x27;", s)
        r = self.get(f'/simple/lire/{self.t01["id"]}?p=1').get_data(as_text=True)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", r)
        pid = self.lib.add_profile('<i>Zoé</i> & "co"', None, None, "reader")["id"]
        ch = self.get("/simple?choix=1").get_data(as_text=True)
        self.assertIn("&lt;i&gt;Zoé&lt;/i&gt; &amp; &quot;co&quot;", ch)
        self.assertNotIn("<i>Zoé</i>", ch)

    def visible_text(self, html):
        """Le texte qu'une page affiche : sans <head>, ni balises. Les libellés des zones sont cachés hors de l'écran."""
        body = html.split("<body>", 1)[1]
        return [t.strip() for t in re.sub(r"<[^>]+>", "\n", body).split("\n") if t.strip()]

    def test_lecteur_plein_ecran_sans_texte(self):
        a = self.t01["id"]
        h = self.get(f"/simple/lire/{a}?p=2").get_data(as_text=True)
        # QUE la planche : aucun titre, aucun bouton « précédent / suivant », aucune barre, aucun tableau
        for word in ("<h1", "<table", 'class="btn', "crumb", "« Précédente", "Suivante »", "Album suivant", "Fin de l'album",
                     "page 2 / 3</div>"):
            self.assertFalse(word in h, f"{word!r} autour de la planche")
        # aucun texte à l'écran, sauf la flèche du petit bouton (les zones n'ont qu'un libellé pour les lecteurs d'écran)
        self.assertEqual(self.visible_text(h), ["‹"])
        # fond noir, plein écran, la planche entière centrée (image de fond « contain »), sans défilement
        self.assertIn("html,body{margin:0;padding:0;height:100%;background:#000;overflow:hidden}", h)
        self.assertIn("background-size:contain", h)
        self.assertIn("background-position:center center", h)
        self.assertIn("position:fixed;left:0;top:0;right:0;bottom:0", h)
        self.assertRegex(h, rf'class="screen"[^>]*style="background-image:url\(&#39;/simple/img/{a}/1\?v=\d+&#39;\)"')
        # ni zoom ni défilement (et pas de bogue de zoom à la rotation d'iOS)
        self.assertIn("maximum-scale=1", h)
        self.assertIn("user-scalable=no", h)
        # les deux grandes zones (moitié gauche / moitié droite de l'écran) : des boutons de formulaires GET, vides, étiquetés
        self.assertEqual(button_target(h, "zone zl"), f"/simple/lire/{a}?p=1")
        self.assertEqual(button_target(h, "zone zr"), f"/simple/lire/{a}?p=3")
        self.assertIn('class="zone zl" aria-label="Page précédente" title="Page précédente"></button>', h)
        self.assertIn("button.zone{position:fixed;top:0;height:100%;width:50%", h)
        # le petit bouton discret : en haut à gauche, 44 px, semi-transparent, vers la liste des albums
        self.assertEqual(button_target(h, "back"), f"/simple/serie/{self.astx['id']}?p=1")
        self.assertIn("button.back{position:fixed;left:6px;top:6px;width:44px;height:44px", h)
        self.assertRegex(h, r"button\.back\{[^}]*opacity:\.\d+")
        self.assertEqual(sorted(c for _, c in nav_buttons(h)), ["back", "zone zl", "zone zr"])   # et rien d'autre
        self.assertIn(f'class="pre" src="/simple/img/{a}/2?v=', h)   # la suivante, préchargée
        # première page : rien avant ; dernière page : la zone de droite ouvre l'album suivant du dossier, ou ramène à la liste
        first = self.get(f"/simple/lire/{a}?p=1").get_data(as_text=True)
        self.assertIsNone(button_target(first, "zone zl"))
        self.assertEqual(self.visible_text(first), ["‹"])
        last = self.get(f"/simple/lire/{a}?p=3").get_data(as_text=True)
        self.assertEqual(button_target(last, "zone zr"), f"/simple/lire/{self.t02['id']}")
        self.assertNotIn('class="pre"', last)
        end = self.get(f"/simple/lire/{self.t02['id']}?p=2").get_data(as_text=True)
        self.assertEqual(button_target(end, "zone zr"), f"/simple/serie/{self.astx['id']}?p=1")

    def test_navigation_par_formulaires_sans_lien(self):
        """Application de l'écran d'accueil sur iOS (avant 11.3) : un <a href> touché rouvre Safari avec sa barre d'adresse ;
        seul un formulaire reste dans l'application. Toute la navigation est donc faite de formulaires GET."""
        for url in ("/simple", "/simple/series", f'/simple/serie/{self.astx["id"]}', f'/simple/lire/{self.t01["id"]}?p=2',
                    "/simple/serie/999999"):
            html = self.c.get(url).get_data(as_text=True)
            self.assertNotRegex(html, r"<a[\s>]", f"lien <a> sur {url}")
            self.assertTrue(nav_buttons(html), f"aucun bouton de navigation sur {url}")
            for u in targets(html):
                self.assertTrue(u.startswith("/simple"), f"{u} sur {url}")
        # une ligne de liste : la couverture ET le titre mènent au même endroit, comme avec un lien
        s = self.get(f'/simple/serie/{self.astx["id"]}').get_data(as_text=True)
        row = [(u, c) for u, c in nav_buttons(s) if c in ("cvbtn", "rowbtn")]
        self.assertEqual(sorted(row), sorted([(f'/simple/lire/{self.t01["id"]}', "cvbtn"), (f'/simple/lire/{self.t01["id"]}', "rowbtn"),
                                              (f'/simple/lire/{self.t02["id"]}', "cvbtn"), (f'/simple/lire/{self.t02["id"]}', "rowbtn")]))
        # les paramètres de l'adresse deviennent des champs cachés : l'adresse visitée est la même qu'avec un lien
        self.assertIn('<form method="get" action="/simple/series" class="nav "><input type="hidden" name="p" value="2">',
                      self.get("/simple/series").get_data(as_text=True))
        self.assertIn('<form method="get" action="/simple" class="nav "><input type="hidden" name="choix" value="1">',
                      self.get("/simple").get_data(as_text=True)) if len(self.lib.profiles()) > 1 else None

    # ---- application sur l'écran d'accueil de l'iPad (iOS 5 : balises Apple, pas de manifest) ---------------------
    def test_icones_de_l_ecran_d_accueil(self):
        for size in (72, 144):
            r = self.get(f"/simple/icone-{size}.png")
            self.assertEqual(r.mimetype, "image/png")
            self.assertIn("max-age=", r.headers["Cache-Control"])
            im = Image.open(io.BytesIO(r.data))
            self.assertEqual(im.format, "PNG")
            self.assertEqual(im.size, (size, size), "l'icône est carrée")
            self.assertEqual(im.mode, "RGB", "pas de transparence (iOS la remplacerait par du noir)")
            bg = im.getpixel((size // 2, 1))
            for corner in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
                self.assertEqual(im.getpixel(corner), bg, "coins pleins, pas arrondis : iOS les arrondit lui-même")
        self.get("/simple/icone-100.png", 404)
        self.assertEqual(self.c.get("/simple/icone-72.png", headers={"If-None-Match": "x"}).status_code, 200)
        r = self.get("/simple/icone-72.png")
        r2 = self.c.get("/simple/icone-72.png", headers={"If-None-Match": r.headers["ETag"]})
        self.assertEqual(r2.status_code, 304)

    def test_icones_sans_authentification(self):
        """L'iPad demande l'icône en ajoutant l'application, avant toute connexion : jamais de code ni de profil exigé."""
        self.lib.add_profile("Bob", hash_pin("secret1"), None, "reader")
        self.lib.set_settings({"access_pin_hash": hash_pin("sesame"), "require_profile": True}, None)
        fresh = self.app.test_client()
        fresh.environ_base["REMOTE_ADDR"] = "192.168.0.51"
        self.assertEqual(fresh.get("/simple/series").status_code, 302)        # le reste est bien protégé
        for size in (72, 144):
            r = fresh.get(f"/simple/icone-{size}.png")
            self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.lib.set_settings({"access_pin_hash": "", "require_profile": False, "account_login": True}, None)
        for size in (72, 144):
            self.assertEqual(fresh.get(f"/simple/icone-{size}.png").status_code, 200)   # même en mode comptes
        # la page de connexion elle-même porte déjà les balises (l'icône s'ajoute depuis n'importe quelle page /simple)
        self.assertIn("apple-touch-icon", fresh.get("/simple").get_data(as_text=True))

    def test_aucune_impasse_en_mode_application(self):
        """En mode application il n'y a pas de bouton « retour » du navigateur : chaque page doit offrir un bouton pour sortir."""
        home = self.get("/simple").get_data(as_text=True)
        self.assertIn("/simple/series", targets(home))
        for url in ("/simple/series", f'/simple/serie/{self.astx["id"]}', "/simple/serie/999999", "/simple/lire/999999"):
            html = self.c.get(url).get_data(as_text=True)
            self.assertIn("/simple", targets(html), f"pas de bouton vers l'accueil sur {url}")
        reader = self.get(f'/simple/lire/{self.t02["id"]}?p=1').get_data(as_text=True)
        self.assertTrue(button_target(reader, "back").startswith("/simple/serie/"))

    def test_cookies_persistants_session_gardee(self):
        """En mode application l'appli est quittée et relancée : la session doit tenir dans des cookies PERSISTANTS (une
        date d'expiration), valables pour tout le site (Path=/), sans « Secure » en http (le réseau local n'a pas de TLS)."""
        self.lib.set_settings({"require_profile": True}, None)
        bob = self.lib.add_profile("Bob", None, None, "reader")["id"]
        r = self.post("/simple/profil", {"id": bob}, 303)
        ck = r.headers["Set-Cookie"]
        self.assertIn("bulle_profile=", ck)
        self.assertIn("Max-Age=315360000", ck)                       # 10 ans : pas un cookie de session
        self.assertIn("Expires=", ck)
        self.assertIn("Path=/", ck)
        self.assertIn("HttpOnly", ck)
        self.assertNotIn("Secure", ck)
        # « relance de l'application » : un tout nouveau client qui n'a QUE ce cookie est toujours Bob
        value = ck.split("bulle_profile=", 1)[1].split(";", 1)[0]
        relaunch = self.app.test_client()
        relaunch.environ_base["REMOTE_ADDR"] = "192.168.0.52"
        relaunch.set_cookie("bulle_profile", value)
        h = relaunch.get("/simple").get_data(as_text=True)
        self.assertIn("Bonjour <b>Bob</b>", h)
        self.assertEqual(relaunch.get("/simple/series").status_code, 200)
        # idem pour le code d'accès (10 ans) et la session d'un compte (30 jours)
        self.lib.set_settings({"require_profile": False, "access_pin_hash": hash_pin("sesame")}, None)
        r = self.post("/simple/connexion", {"pin": "sesame"}, 303)
        self.assertIn("Max-Age=315360000", r.headers["Set-Cookie"])
        self.lib.set_settings({"access_pin_hash": "", "account_login": True}, None)
        ann = self.lib.add_profile("Ann", hash_pin("motdepasse1"), None, "reader")["id"]
        cookies = self.post("/simple/connexion", {"name": "Ann", "password": "motdepasse1"}, 303).headers.getlist("Set-Cookie")
        sess = [c for c in cookies if c.startswith("bulle_session=")][0]
        self.assertIn("Max-Age=2592000", sess)                       # 30 jours
        self.assertNotIn("Secure", sess)

    def test_liens_internes_seulement(self):
        """Toute la navigation de toutes les pages reste dans /simple (pas de nouvelle fenêtre en mode application)."""
        for url in ("/simple", "/simple/series", f'/simple/serie/{self.astx["id"]}', f'/simple/lire/{self.t01["id"]}?p=2'):
            html = self.get(url).get_data(as_text=True)
            self.assertNotRegex(html, r"<a[\s>]")
            for u in targets(html):
                self.assertTrue(u.startswith("/simple"), f"{u} sur {url}")
    def test_images_1024_jpeg_de_base_avec_cache(self):
        v = int(self.t01.get("mtime") or 0)
        seen = []
        for idx, (w, h) in enumerate([(900, 1300), (1400, 900), (2000, 2800)]):
            r = self.get(f'/simple/img/{self.t01["id"]}/{idx}?v={v}')
            self.assertEqual(r.mimetype, "image/jpeg")
            im = Image.open(io.BytesIO(r.data))
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 1024, f"page {idx}: {im.size}")
            self.assertAlmostEqual(im.size[0] / im.size[1], w / h, delta=0.01)   # proportions gardées
            self.assertFalse(im.info.get("progressive"), "JPEG progressif : trop gourmand pour un iPad 1")
            self.assertLess(len(r.data), 400_000, f"page {idx} : {len(r.data)} octets")
            seen.append((im.size, len(r.data)))
            cc = r.headers["Cache-Control"]
            self.assertIn("max-age=31536000", cc)
            self.assertIn("immutable", cc)
        small = Image.open(io.BytesIO(self.get(f'/simple/img/{self.t02["id"]}/0').data))
        self.assertEqual(small.size, (400, 560), "une petite page n'est jamais agrandie")
        self.assertIn("max-age=600", self.get(f'/simple/img/{self.t02["id"]}/0').headers["Cache-Control"])
        cached = os.path.join(self.comics.pages_dir, str(self.t01["id"]))
        self.assertTrue(any(n.endswith("-simple1024.jpg") for n in os.listdir(cached)), "pas de fichier en cache")
        r1 = self.get(f'/simple/img/{self.t01["id"]}/0?v={v}')
        r2 = self.c.get(f'/simple/img/{self.t01["id"]}/0?v={v}', headers={"If-None-Match": r1.headers.get("ETag", "")})
        self.assertEqual(r2.status_code, 304)
        self.get(f'/simple/img/{self.t01["id"]}/3', 404)   # il n'y a que 3 pages (0, 1, 2)
        print("  images :", ", ".join(f"{s[0][0]}x{s[0][1]} {s[1] // 1024} Ko" for s in seen))

    # ---- progression ----------------------------------------------------------------------
    def test_progression_et_reprise(self):
        a = self.t01["id"]
        self.get(f"/simple/lire/{a}?p=2")
        prog = self.lib.progress(a, DEFAULT_PROFILE)
        self.assertEqual(prog["page"], 1)
        self.assertFalse(prog["completed"])
        r = self.c.get(f"/simple/lire/{a}")   # reprise
        self.assertTrue(r.headers["Location"].endswith(f"/simple/lire/{a}?p=2"))
        self.get(f"/simple/lire/{a}?p=3")     # dernière page : lu
        self.assertTrue(self.lib.progress(a, DEFAULT_PROFILE)["completed"])
        r = self.c.get(f"/simple/lire/{a}")   # un album terminé repart du début
        self.assertTrue(r.headers["Location"].endswith(f"/simple/lire/{a}?p=1"))
        home = self.get("/simple").get_data(as_text=True)
        self.assertNotIn("Reprendre la lecture", home)   # terminé : plus « en cours »
        self.get(f"/simple/lire/{self.t02['id']}?p=1")
        home = self.get("/simple").get_data(as_text=True)
        self.assertIn("Reprendre la lecture", home)
        self.assertIn("page 1 / 2", home)
        s = self.get(f'/simple/serie/{self.astx["id"]}').get_data(as_text=True)
        self.assertIn("Lu", s)

    # ---- profils, mots de passe ------------------------------------------------------------
    def test_profils_et_mots_de_passe(self):
        self.lib.set_settings({"require_profile": True}, None)
        bob = self.lib.add_profile("Bob", hash_pin("secret1"), None, "reader")["id"]
        ch = self.get("/simple").get_data(as_text=True)
        self.assertIn("Qui lit ?", ch)
        self.assertIn("Mot de passe de Bob", ch)
        self.assertNotIn("Toutes les séries", ch)
        for url in ("/simple/series", f'/simple/serie/{self.astx["id"]}', f'/simple/lire/{self.t02["id"]}?p=1'):
            r = self.c.get(url)
            self.assertEqual((r.status_code, r.headers["Location"].rstrip("/").endswith("/simple")), (302, True), url)
        self.assertEqual(self.c.get(f'/simple/img/{self.t02["id"]}/0').status_code, 403)   # pas d'image sans profil
        self.assertEqual(self.lib.progress(self.t02["id"], bob), None)
        r = self.post("/simple/profil", {"id": bob, "pin": "faux"}, 403)
        self.assertIn("Mot de passe incorrect", r.get_data(as_text=True))
        self.assertNotIn("bulle_profile", r.headers.get("Set-Cookie", ""))
        r = self.post("/simple/profil", {"id": bob, "pin": "secret1"}, 303)
        self.assertIn("bulle_profile", r.headers.get("Set-Cookie", ""))
        self.assertIn("HttpOnly", r.headers.get("Set-Cookie", ""))
        self.assertEqual(self.get("/simple").get_data(as_text=True).count("Bonjour <b>Bob</b>"), 1)
        self.get(f'/simple/lire/{self.t02["id"]}?p=2')
        self.assertEqual(self.lib.progress(self.t02["id"], bob)["page"], 1)       # la progression est celle de Bob
        self.assertIsNone(self.lib.progress(self.t02["id"], DEFAULT_PROFILE))
        self.get(f'/simple/img/{self.t02["id"]}/0')
        self.post("/simple/profil", {"id": 9999, "pin": ""}, 404)
        self.get("/simple?choix=1")   # « changer de profil » rouvre le choix
        self.post("/simple/deconnexion", {}, 303)
        self.assertIn("Qui lit ?", self.get("/simple").get_data(as_text=True))

    def test_aucune_fonction_admin(self):
        paths = ("/simple", "/simple/series", f'/simple/serie/{self.astx["id"]}', f'/simple/lire/{self.t02["id"]}?p=1')
        for url in paths:
            html = self.get(url).get_data(as_text=True)
            self.assertNotRegex(html, r'(?i)(rescan|scanner|param[eè]tres|r[eé]glages|supprimer|ignorer)')
        # les routes /simple n'acceptent pas d'autre méthode que celles prévues
        self.assertEqual(self.c.post("/simple/series").status_code, 405)
        self.assertEqual(self.c.post(f'/simple/lire/{self.t02["id"]}').status_code, 405)
        self.assertEqual(self.c.put("/simple").status_code, 405)

    # ---- code d'accès, comptes ---------------------------------------------------------------
    def test_code_d_acces(self):
        self.lib.set_settings({"access_pin_hash": hash_pin("sesame")}, None)
        h = self.get("/simple").get_data(as_text=True)
        self.assertIn("Code d'accès", h)
        self.assertNotIn("Toutes les séries", h)
        for url in ("/simple/series", f'/simple/lire/{self.t02["id"]}?p=1'):
            self.assertEqual(self.c.get(url).status_code, 302)
        self.assertEqual(self.c.get(f'/simple/img/{self.t02["id"]}/0').status_code, 403)
        r = self.post("/simple/connexion", {"pin": "mauvais"}, 403)
        self.assertIn("incorrect", r.get_data(as_text=True))
        r = self.post("/simple/connexion", {"pin": "sesame"}, 303)
        self.assertIn("bulle_auth", r.headers.get("Set-Cookie", ""))
        self.get("/simple/series")
        self.get(f'/simple/img/{self.t02["id"]}/0')

    def test_comptes(self):
        ann = self.lib.add_profile("Ann", hash_pin("motdepasse1"), None, "reader")["id"]
        self.lib.set_settings({"account_login": True}, None)
        h = self.get("/simple").get_data(as_text=True)
        self.assertIn('name="name"', h)
        self.assertIn('type="password"', h)
        self.assertEqual(self.c.get("/simple/series").status_code, 302)
        self.assertEqual(self.c.get(f'/simple/img/{self.t02["id"]}/0').status_code, 403)
        self.post("/simple/connexion", {"name": "Ann", "password": "faux"}, 403)
        r = self.post("/simple/connexion", {"name": "ann", "password": "motdepasse1"}, 303)   # sans tenir compte des majuscules
        self.assertIn("bulle_session", r.get_data(as_text=True) + r.headers.get("Set-Cookie", ""))
        home = self.get("/simple").get_data(as_text=True)
        self.assertIn("Bonjour <b>Ann</b>", home)
        self.assertIn("Se déconnecter", home)
        self.assertNotIn("Changer de profil", home)   # en mode comptes on ne change pas de compte sans se déconnecter
        self.get(f'/simple/lire/{self.t02["id"]}?p=2')
        self.assertEqual(self.lib.progress(self.t02["id"], ann)["page"], 1)
        self.post("/simple/profil", {"id": DEFAULT_PROFILE, "pin": ""}, 303)   # sans effet : redirige vers /simple
        self.assertIn("Bonjour <b>Ann</b>", self.get("/simple").get_data(as_text=True))
        self.post("/simple/deconnexion", {}, 303)
        self.assertEqual(self.c.get("/simple/series").status_code, 302)

    def test_essais_ratés_bloques(self):
        self.lib.set_settings({"access_pin_hash": hash_pin("sesame")}, None)
        self.c.environ_base["REMOTE_ADDR"] = "192.168.0.77"   # une adresse pour ce seul test
        for _ in range(5):
            self.c.post("/simple/connexion", data={"pin": "non"})
        r = self.post("/simple/connexion", {"pin": "sesame"}, 429)   # même avec le bon code : bloqué 15 minutes
        self.assertIn("Trop d", r.get_data(as_text=True))

    # ---- rubrique Adulte, HTTPS ---------------------------------------------------------------
    def test_rubrique_adulte_cachee(self):
        self.lib.set_settings({"adult_paths": ["Adulte"], "adult_pin_hash": hash_pin("1234")}, None)
        secret = self.find("Secret")
        s = self.get("/simple/series").get_data(as_text=True)
        self.assertNotIn(">Adulte<", s)
        folder = self.find("Adulte")
        self.get(f'/simple/serie/{folder["id"]}', 403)
        self.get(f'/simple/lire/{secret["id"]}?p=1', 403)
        self.get(f'/simple/img/{secret["id"]}/0', 403)
        self.assertEqual(self.lib.progress(secret["id"], DEFAULT_PROFILE), None)

    def test_https_impose_hors_reseau_local(self):
        self.lib.set_settings({"force_https": True}, None)
        for host in ("192.168.0.213:2205", "localhost:2205", "nas:2205", "bulle.local:2205"):
            r = self.c.get("/simple", base_url=f"http://{host}")
            self.assertEqual(r.status_code, 200, f"{host} doit rester accessible en http")
            self.assertEqual(self.c.get("/simple/series", base_url=f"http://{host}").status_code, 200)
            self.assertIn("image/jpeg", self.c.get(f'/simple/img/{self.t02["id"]}/0', base_url=f"http://{host}").mimetype)
        r = self.c.get("/simple", base_url="http://exemple.org")
        self.assertEqual(r.status_code, 308)
        self.assertTrue(r.headers["Location"].startswith("https://exemple.org/simple"))
        # et le cookie de profil n'est « Secure » qu'en HTTPS (sinon l'iPad en http ne le garderait pas)
        self.lib.set_settings({"require_profile": True}, None)
        bob = self.lib.add_profile("Bob", None, None, "reader")["id"]
        r = self.c.post("/simple/profil", data={"id": bob}, base_url="http://192.168.0.213:2205")
        self.assertEqual(r.status_code, 303)
        self.assertNotIn("Secure", r.headers.get("Set-Cookie", ""))

    def test_zz_html_valide(self):
        """Toutes les pages vues par les tests ci-dessus : validées par le W3C (vnu.jar) ou, à défaut, html5lib strict."""
        pages = SimpleTests.pages_seen
        self.assertGreater(len(pages), 10, "lancer toute la suite (les pages sont collectées par les autres tests)")
        if VNU and os.path.isfile(VNU):
            d = tempfile.mkdtemp(prefix="bulle-vnu-")
            try:
                files = []
                for i, (where, html) in enumerate(pages.items()):
                    f = os.path.join(d, f"{i:03d}.html")
                    with open(f, "w", encoding="utf-8") as fh:
                        fh.write(html)
                    files.append(f)
                p = subprocess.run(["java", "-jar", VNU, "--errors-only", "--format", "text", *files],
                                   capture_output=True, text=True, timeout=300)
                out = (p.stdout + p.stderr).strip()
                self.assertEqual(p.returncode, 0, "validateur W3C :\n" + out)
                print(f"  W3C (vnu {VNU}) : {len(files)} pages sans erreur")
            finally:
                shutil.rmtree(d, ignore_errors=True)
        else:
            try:
                import html5lib
            except ImportError:
                self.skipTest("ni vnu.jar ni html5lib")
            for where, html in pages.items():
                try:
                    html5lib.HTMLParser(strict=True).parse(html)
                except Exception as e:  # noqa: BLE001
                    self.fail(f"HTML invalide ({where}) : {e}")
            print(f"  html5lib strict : {len(pages)} pages sans erreur")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--vnu" in args:
        i = args.index("--vnu")
        VNU = args[i + 1]
        del args[i:i + 2]
    VNU = VNU or os.environ.get("VNU_JAR")
    unittest.main(argv=[sys.argv[0]] + args, verbosity=2)
