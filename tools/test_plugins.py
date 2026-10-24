"""Tests automatiques des plugins (laboratoire) : python tools/test_plugins.py

Fabrique le paquet du plugin d'exemple (examples/plugins/bonjour), l'installe dans un Bulle jetable (client de test de
Flask) et vérifie : paquet propre (rien de personnel ni de jetable), refus des paquets dangereux (« ../ », liens
symboliques, fiche invalide), démarrage, relais des pages avec réécriture des adresses, flux en direct, écriture dans
le dossier de sortie, accès réservé à l'administrateur, arrêt à la demande, arrêt automatique après inactivité (sauf
si le plugin dit qu'il travaille), mise à jour qui garde les fichiers « keep », désinstallation qui garde la sortie.
Aucun accès à Internet.
"""
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SCAN_ON_START", "0")
os.environ.setdefault("PRELOAD_COVERS", "0")

from bulle import plugins as pm  # noqa: E402
from bulle.server import create_app  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "plugins", "bonjour")


def make_zip(files: dict, symlink: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


MANIFEST = {"id": "essai", "name": "Essai", "version": "1", "command": ["{python}", "app.py"]}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_paquet_propre(self):
        src = os.path.join(self.tmp, "bonjour")
        shutil.copytree(EXAMPLE, src)
        for junk in ("__pycache__/app.cpython-312.pyc", ".git/config", ".venv/bin/python", "compteur.txt", "vieux.zip"):
            os.makedirs(os.path.dirname(os.path.join(src, junk)), exist_ok=True)
            with open(os.path.join(src, junk), "w") as f:
                f.write("x")
        path, manifest, count = pm.build_package(src)
        self.assertEqual(os.path.basename(path), "bonjour-1.0.zip")
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
        self.assertEqual(names, {"app.py", "icone.svg", "plugin.json"})   # « exclude » + exclusions par défaut
        self.assertEqual(count, 3)

    def check_refused(self, data: bytes, fragment: str):
        p = os.path.join(self.tmp, "p.zip")
        with open(p, "wb") as f:
            f.write(data)
        with self.assertRaises(pm.PluginError) as cm:
            pm.read_package(p)
        self.assertIn(fragment, str(cm.exception))

    def test_paquets_refuses(self):
        good = json.dumps(MANIFEST)
        self.check_refused(b"pas un zip", "pas un .zip")
        self.check_refused(make_zip({"app.py": ""}), "plugin.json")
        self.check_refused(make_zip({"plugin.json": "{"}), "JSON")
        self.check_refused(make_zip({"plugin.json": json.dumps(dict(MANIFEST, id="Pas Bon"))}), "id")
        self.check_refused(make_zip({"plugin.json": json.dumps(dict(MANIFEST, command="python app.py"))}), "command")
        self.check_refused(make_zip({"plugin.json": json.dumps(dict(MANIFEST, port=80))}), "port")
        self.check_refused(make_zip({"plugin.json": json.dumps(dict(MANIFEST, busy_url="/abs"))}), "busy_url")
        self.check_refused(make_zip({"plugin.json": good, "../evade.py": ""}), "interdit")
        self.check_refused(make_zip({"plugin.json": good, "a/../../evade.py": ""}), "interdit")
        self.check_refused(make_zip({"plugin.json": good}, symlink="lien"), "lien symbolique")

    def test_dossier_englobant_accepte(self):
        p = os.path.join(self.tmp, "p.zip")
        with open(p, "wb") as f:
            f.write(make_zip({"essai/plugin.json": json.dumps(MANIFEST), "essai/app.py": "print(1)"}))
        dest = os.path.join(self.tmp, "out")
        m = pm.extract_package(p, dest)
        self.assertEqual(m["id"], "essai")
        self.assertTrue(os.path.isfile(os.path.join(dest, "app.py")))

    def test_reecriture(self):
        html = ('<html><head><link href="/static/a.css"></head><body><a href="/api/x">x</a><img src="//cdn/y.png">'
                '<a href="https://ailleurs/z">z</a><a href="/plugins/p/deja">d</a><div style="background:url(/img/b.png)">'
                '</div></body></html>')
        out = pm.rewrite_html(html, "/plugins/p/")
        self.assertIn('href="/plugins/p/static/a.css"', out)
        self.assertIn('href="/plugins/p/api/x"', out)
        self.assertIn('src="//cdn/y.png"', out)
        self.assertIn('href="https://ailleurs/z"', out)
        self.assertIn('href="/plugins/p/deja"', out)
        self.assertNotIn("/plugins/p/plugins/p/", out)
        self.assertIn("url(/plugins/p/img/b.png)", out)
        # images créées en JavaScript (img.src, setAttribute, innerHTML…) : relayées aussi par /plugins/<id>/ (v0.44.1)
        for hook in ("HTMLImageElement", "Element.prototype.setAttribute", "innerHTML", "insertAdjacentHTML",
                     "MutationObserver"):
            self.assertIn(hook, out)
        self.assertLess(out.index("<script>"), out.index("<link"))   # le script d'adaptation passe avant tout le reste
        self.assertEqual(pm._fix_set_cookie("sid=1; Path=/; HttpOnly", "/plugins/p/"), "sid=1; Path=/plugins/p/; HttpOnly")
        self.assertEqual(pm._strip_bulle_cookies("bulle_session=s; sid=1; bulle_auth=a"), "sid=1")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        lib = os.path.join(cls.tmp, "lib")
        os.makedirs(os.path.join(lib, "Série"))
        cls.out = os.path.join(cls.tmp, "sortie")
        os.makedirs(cls.out)
        os.environ["PLUGINS_OUT"] = cls.out
        cls.app = create_app(lib, os.path.join(cls.tmp, "data"))
        cls.lib = cls.app.extensions["bulle"]["library"]
        cls.mgr = cls.app.extensions["bulle"]["plugins"]
        cls.pkg, _m, _n = pm.build_package(EXAMPLE, os.path.join(cls.tmp, "bonjour.zip"))

    @classmethod
    def tearDownClass(cls):
        cls.mgr.stop_all()
        os.environ.pop("PLUGINS_OUT", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.c = self.app.test_client()

    def install(self, path=None):
        with open(path or self.pkg, "rb") as f:
            r = self.c.post("/api/plugins", data={"file": (f, "bonjour.zip")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()["plugin"]

    def test_1_parcours_complet(self):
        info = self.install()
        self.assertEqual(info["state"], "stopped")
        self.assertEqual(info["output"], os.path.join(self.out, "bonjour"))
        # arrêté : page d'explication, pas d'erreur obscure
        self.assertEqual(self.c.get("/plugins/bonjour/").status_code, 503)
        r = self.c.post("/api/plugins/bonjour/start")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["plugin"]["state"], "running")
        page = self.c.get("/plugins/bonjour/")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('href="/plugins/bonjour/static/style.css"', html)
        self.assertIn("window.fetch", html)
        self.assertEqual(self.c.get("/plugins/bonjour/static/style.css").status_code, 200)
        self.assertEqual(self.c.get("/plugins/bonjour").status_code, 308)
        # écriture dans le dossier de sortie, puis téléchargement par le relais
        name = self.c.post("/plugins/bonjour/api/write").get_json()["written"]
        self.assertTrue(os.path.isfile(os.path.join(self.out, "bonjour", name)))
        dl = self.c.get("/plugins/bonjour/api/download/" + name)
        self.assertEqual(dl.data, "Bonjour depuis un plugin de Bulle !\n".encode())
        # tâche : le flux de progression arrive en entier ; pendant la tâche le plugin se dit occupé
        self.c.post("/plugins/bonjour/api/task")
        p = self.mgr.plugins["bonjour"]
        self.assertTrue(self.mgr.busy(p))
        stream = self.c.get("/plugins/bonjour/api/stream")
        events = [json.loads(line[6:]) for line in stream.get_data(as_text=True).splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["done"], 10)
        self.assertFalse(events[-1]["running"])
        self.assertEqual(p.streams, 0)
        # la tâche apparaît dans Réglages › Tâches et s'arrête de là
        tasks = {t["id"]: t for t in self.c.get("/api/tasks").get_json()["tasks"]}
        self.assertEqual(tasks["plugin:bonjour"]["state"], "running")
        self.assertTrue(self.c.post("/api/tasks/plugin:bonjour/stop").get_json()["stopped"])
        self.assertEqual(self.c.get("/plugins/bonjour/").status_code, 503)
        self.assertIn("démarrage", self.c.get("/api/plugins/bonjour/log").get_data(as_text=True))
        self.assertEqual(self.c.get("/api/plugins/bonjour/icon").mimetype, "image/svg+xml")

    def test_2_arret_automatique(self):
        self.install()
        self.c.post("/api/plugins/bonjour/start")
        p = self.mgr.plugins["bonjour"]
        later = time.time() + 21 * 60
        self.c.post("/plugins/bonjour/api/task")        # occupé : pas arrêté malgré 21 min « sans activité »
        self.assertEqual(self.mgr.idle_check(now=later), [])
        self.assertTrue(p.alive())
        time.sleep(10.5)                                # la tâche d'exemple dure 10 s
        self.assertEqual(self.mgr.idle_check(now=later + 21 * 60), ["bonjour"])   # occupé = activité notée à « later »
        self.assertFalse(p.alive())
        self.assertIn("sans activité", self.c.get("/api/plugins").get_json()["plugins"][0]["stop_reason"])

    def test_3_mise_a_jour_garde_keep(self):
        self.install()
        self.c.post("/api/plugins/bonjour/start")
        self.c.get("/plugins/bonjour/")                 # compteur.txt (« keep ») = 1
        app_dir = self.mgr.plugins["bonjour"].app_dir
        read = lambda: open(os.path.join(app_dir, "compteur.txt")).read()  # noqa: E731,SIM115
        before = read()
        info = self.install()                           # même id : mise à jour (le plugin est arrêté au passage)
        self.assertEqual(info["state"], "stopped")
        self.assertEqual(read(), before)

    def test_8_reseau_local_seulement(self):
        """v0.44.2 : ouverts par le nom de domaine public ou depuis une adresse d'Internet, les plugins n'existent pas."""
        self.install()
        lan = {"base_url": "http://192.168.0.213:2205"}
        pub = {"base_url": "https://bdbulle.exemple.duckdns.org"}
        self.assertEqual(self.c.get("/api/plugins", **lan).status_code, 200)
        self.assertTrue(self.c.get("/api/settings", **lan).get_json()["plugins"])
        for path in ("/api/plugins", "/api/plugins/bonjour/log", "/plugins/bonjour/", "/plugins/bonjour/api/x"):
            self.assertEqual(self.c.get(path, **pub).status_code, 404, path)
        self.assertEqual(self.c.post("/api/plugins/bonjour/start", **pub).status_code, 404)
        self.assertFalse(self.c.get("/api/settings", **pub).get_json()["plugins"])
        # proxy de la maison qui transmet l'adresse réelle d'un visiteur d'Internet, même avec un Host « local »
        self.assertEqual(self.c.get("/api/plugins", headers={"X-Real-IP": "82.64.10.20"}, **lan).status_code, 404)
        # visiteur d'Internet arrivé directement (redirection de port) en se faisant passer pour une adresse locale
        self.assertEqual(self.c.get("/api/plugins", environ_base={"REMOTE_ADDR": "82.64.10.20"}, **lan).status_code, 404)
        self.assertEqual(self.c.get("/api/plugins", headers={"X-Real-IP": "192.168.0.20"}, **lan).status_code, 200)

    def test_4_lecteur_refuse(self):
        self.install()
        self.c.post("/api/plugins/bonjour/start")
        bob = self.lib.add_profile("Bob", None, None, "reader")["id"]
        reader = self.app.test_client()
        self.assertEqual(reader.post("/api/profiles/select", json={"id": bob}).status_code, 200)
        self.assertEqual(reader.get("/api/plugins").status_code, 403)
        self.assertEqual(reader.get("/plugins/bonjour/").status_code, 403)
        self.assertEqual(reader.post("/plugins/bonjour/api/write").status_code, 403)
        self.assertEqual(reader.post("/api/plugins/bonjour/start").status_code, 403)
        self.c.post("/api/plugins/bonjour/stop")

    def test_5_dependances_en_echec(self):
        """Un requirements.txt impossible à installer (ici : paquet inexistant, sans Internet) met le plugin en erreur,
        sans bloquer Bulle, et il refuse de démarrer."""
        src = os.path.join(self.tmp, "deps")
        os.makedirs(src)
        with open(os.path.join(src, "plugin.json"), "w") as f:
            json.dump(dict(MANIFEST, id="deps"), f)
        with open(os.path.join(src, "app.py"), "w") as f:
            f.write("print('ok')\n")
        with open(os.path.join(src, "requirements.txt"), "w") as f:
            f.write("ce-paquet-n-existe-pas-bulle==9.9\n")
        path, _m, _n = pm.build_package(src)
        info = self.install(path)
        self.assertEqual(info["state"], "installing")
        for _ in range(300):
            if self.mgr.plugins["deps"].state != "installing":
                break
            time.sleep(0.2)
        self.assertEqual(self.mgr.plugins["deps"].state, "error")
        self.assertEqual(self.c.post("/api/plugins/deps/start").status_code, 409)
        self.c.delete("/api/plugins/deps")

    def test_6_programme_qui_plante(self):
        src = os.path.join(self.tmp, "plante")
        os.makedirs(src)
        with open(os.path.join(src, "plugin.json"), "w") as f:
            json.dump(dict(MANIFEST, id="plante", start_timeout=5), f)
        with open(os.path.join(src, "app.py"), "w") as f:
            f.write("import sys\nprint('boum')\nsys.exit(3)\n")
        path, _m, _n = pm.build_package(src)
        self.install(path)
        r = self.c.post("/api/plugins/plante/start")
        self.assertEqual(r.status_code, 409)
        self.assertIn("code 3", r.get_json()["error"])
        self.assertIn("boum", self.c.get("/api/plugins/plante/log").get_data(as_text=True))
        self.c.delete("/api/plugins/plante")

    def test_7_desinstallation_garde_la_sortie(self):
        self.install()
        self.c.post("/api/plugins/bonjour/start")
        self.c.post("/plugins/bonjour/api/write")
        r = self.c.delete("/api/plugins/bonjour")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("bonjour", self.mgr.plugins)
        self.assertTrue(os.listdir(os.path.join(self.out, "bonjour")))
        self.assertEqual(self.c.get("/plugins/bonjour/").status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
