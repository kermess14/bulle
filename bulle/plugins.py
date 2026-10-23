"""Plugins de Bulle : de petits programmes empaquetés (un fichier .zip) que Bulle installe, lance à la demande, affiche
dans le panneau du laboratoire et arrête tout seul après un moment sans activité.

Un plugin est un programme web ordinaire (Flask, http.server…) qui écoute sur 127.0.0.1, à l'intérieur du conteneur de
Bulle. Il n'est jamais exposé directement : on y accède par Bulle, à l'adresse /plugins/<id>/, et seulement en étant
administrateur. Bulle relaie les requêtes (proxy) et réécrit au passage les adresses « /… » des pages HTML pour qu'un
programme écrit pour être servi à la racine fonctionne quand même sous /plugins/<id>/.

Le paquet contient le programme et un fichier plugin.json (voir PLUGINS.md à la racine du dépôt) :

    {"id": "mon-outil", "name": "Mon outil", "version": "1.0", "command": ["{python}", "app.py"], "port": 5000}

Sur le disque (volume /data de Bulle) :
    plugins/<id>/app/       le programme décompressé (son dossier de travail)
    plugins/<id>/deps/      ses dépendances Python (pip --target), si le paquet a un requirements.txt
    plugins/<id>/data/      un dossier à lui, gardé lors des mises à jour (variable PLUGIN_DATA)
    plugins/<id>/plugin.log son journal (sortie du programme), refait à chaque démarrage
et le dossier de sortie, en écriture : /plugins-out/<id>/ (variable PLUGIN_OUTPUT) — c'est là qu'un plugin dépose ce
qu'il fabrique ; la bibliothèque, elle, reste en lecture seule.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import zipfile
from typing import Any, Callable, Optional

log = logging.getLogger("bulle.plugins")

MANIFEST = "plugin.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MAX_PACKAGE = 300 * 1024 * 1024          # taille du .zip envoyé
MAX_UNPACKED = 1024 * 1024 * 1024        # taille totale une fois décompressé
MAX_MEMBERS = 20000
DEFAULT_IDLE_MINUTES = 20
LOG_MAX = 2 * 1024 * 1024                # journal : on garde la fin
ICON_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
# toujours laissés de côté à l'empaquetage (tools/make_plugin.py) : rien de personnel ni de jetable dans un paquet
DEFAULT_EXCLUDE = ["__pycache__", "*.pyc", "*.pyo", ".git", ".venv", "venv", "node_modules", ".env", ".DS_Store",
                   "Thumbs.db", "*.zip"]


class PluginError(ValueError):
    """Paquet ou action refusés : le message est affiché tel quel à l'administrateur."""


# ------------------------------------------------------------------------------------------------ manifeste
def validate_manifest(raw: Any) -> dict:
    """Vérifie plugin.json et renvoie une version propre (valeurs par défaut comprises)."""
    if not isinstance(raw, dict):
        raise PluginError("plugin.json doit contenir un objet JSON { … }")

    def text(key: str, required: bool = True, limit: int = 200) -> str:
        v = raw.get(key)
        if v is None and not required:
            return ""
        if not isinstance(v, str) or not v.strip():
            raise PluginError(f"plugin.json : « {key} » manquant ou vide")
        if len(v) > limit:
            raise PluginError(f"plugin.json : « {key} » trop long")
        return v.strip()

    pid = text("id", limit=40)
    if not ID_RE.match(pid):
        raise PluginError("plugin.json : « id » en minuscules, chiffres et tirets seulement (ex. data-reaper)")
    m: dict[str, Any] = {"id": pid, "name": text("name", limit=80), "version": text("version", limit=40),
                         "description": text("description", required=False, limit=500)}
    cmd = raw.get("command")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) and c for c in cmd) or len(cmd) > 50:
        raise PluginError('plugin.json : « command » doit être une liste, ex. ["{python}", "app.py"]')
    m["command"] = list(cmd)
    port = raw.get("port")
    if port is not None and (isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535):
        raise PluginError("plugin.json : « port » doit être un nombre entre 1024 et 65535 (ou absent)")
    m["port"] = port
    idle = raw.get("idle_minutes", DEFAULT_IDLE_MINUTES)
    if isinstance(idle, bool) or not isinstance(idle, (int, float)) or not 0 <= idle <= 1440:
        raise PluginError("plugin.json : « idle_minutes » entre 0 (jamais d'arrêt automatique) et 1440")
    m["idle_minutes"] = float(idle)
    timeout = raw.get("start_timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 300:
        raise PluginError("plugin.json : « start_timeout » entre 1 et 300 secondes")
    m["start_timeout"] = float(timeout)
    busy = raw.get("busy_url")
    if busy is not None and (not isinstance(busy, str) or not busy or busy.startswith(("/", "http:", "https:")) or ".." in busy):
        raise PluginError("plugin.json : « busy_url » est une adresse relative au plugin, ex. api/status")
    m["busy_url"] = busy
    env = raw.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and re.match(r"^[A-Z_][A-Z0-9_]*$", k) and isinstance(v, str)
                                            for k, v in env.items()):
        raise PluginError("plugin.json : « env » est un objet {\"NOM\": \"valeur\"} (noms en majuscules)")
    m["env"] = dict(env)
    for key in ("keep", "exclude"):
        val = raw.get(key, [])
        if not isinstance(val, list) or not all(isinstance(x, str) and x.strip() for x in val) or len(val) > 200:
            raise PluginError(f"plugin.json : « {key} » est une liste de noms de fichiers ou de dossiers")
        m[key] = [x.strip().strip("/") for x in val]
    for k in m["keep"]:
        if k.startswith("/") or ".." in k.split("/") or not k:
            raise PluginError("plugin.json : « keep » contient un chemin invalide")
    req = raw.get("requirements", "requirements.txt")
    if not isinstance(req, str) or "/" in req or "\\" in req or ".." in req:
        raise PluginError("plugin.json : « requirements » est un nom de fichier du paquet")
    m["requirements"] = req
    icon = raw.get("icon")
    if icon is not None and (not isinstance(icon, str) or "/" in icon or "\\" in icon
                             or os.path.splitext(icon)[1].lower() not in ICON_TYPES):
        raise PluginError("plugin.json : « icon » est une image du paquet (png, svg, jpg, webp)")
    m["icon"] = icon
    return m


def excluded(rel: str, patterns: list[str]) -> bool:
    """`rel` (chemin relatif avec des /) est-il écarté par un des motifs (nom ou chemin, jokers * ?) ?"""
    parts = rel.split("/")
    for pat in patterns:
        pat = pat.strip("/")
        if "/" in pat:
            if fnmatch.fnmatch(rel, pat) or rel.startswith(pat + "/"):
                return True
        elif any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
    return False


# ------------------------------------------------------------------------------------------------ paquet (.zip)
def read_package(path: str) -> tuple[dict, str, list[zipfile.ZipInfo]]:
    """Ouvre un paquet sans rien écrire : (manifeste, préfixe à retirer, fichiers à extraire). Refuse ce qui sort du
    dossier (« ../ », chemins absolus), les liens symboliques, les archives démesurées."""
    if os.path.getsize(path) > MAX_PACKAGE:
        raise PluginError(f"Paquet trop gros (plus de {MAX_PACKAGE // (1024 * 1024)} Mo)")
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PluginError("Ce fichier n'est pas un .zip valide") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise PluginError("Paquet refusé : trop de fichiers")
        names = [i.filename.replace("\\", "/") for i in infos]
        prefix = ""
        if MANIFEST not in names:
            # paquet fait en compressant le dossier lui-même : tout est dans « mon-outil/ »
            tops = {n.split("/", 1)[0] for n in names if n.strip("/")}
            if len(tops) == 1 and (next(iter(tops)) + "/" + MANIFEST) in names:
                prefix = next(iter(tops)) + "/"
            else:
                raise PluginError(f"Paquet refusé : pas de {MANIFEST} (la fiche du plugin) à la racine du .zip")
        try:
            manifest = validate_manifest(json.loads(zf.read(prefix + MANIFEST).decode("utf-8-sig")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginError(f"{MANIFEST} n'est pas un JSON valide : {exc}") from exc
        total = 0
        keep: list[zipfile.ZipInfo] = []
        for info, name in zip(infos, names):
            if not name.startswith(prefix):
                raise PluginError("Paquet refusé : des fichiers sont hors du dossier du plugin")
            rel = name[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            parts = rel.split("/")
            if rel.startswith("/") or ":" in parts[0] or any(p in ("", ".", "..") for p in parts):
                raise PluginError(f"Paquet refusé : chemin interdit « {name} »")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PluginError(f"Paquet refusé : lien symbolique « {name} »")
            total += info.file_size
            if total > MAX_UNPACKED:
                raise PluginError("Paquet refusé : trop gros une fois décompressé")
            keep.append(info)
        return manifest, prefix, keep


def extract_package(path: str, dest: str) -> dict:
    manifest, prefix, members = read_package(path)
    os.makedirs(dest, exist_ok=True)
    root = os.path.realpath(dest)
    with zipfile.ZipFile(path) as zf:
        for info in members:
            rel = info.filename.replace("\\", "/")[len(prefix):]
            target = os.path.realpath(os.path.join(dest, *rel.split("/")))
            if not target.startswith(root + os.sep):
                raise PluginError(f"Paquet refusé : chemin interdit « {rel} »")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            mode = (info.external_attr >> 16) & 0o777
            if mode & 0o100:
                os.chmod(target, 0o755)
    return manifest


def build_package(folder: str, out_path: Optional[str] = None) -> tuple[str, dict, int]:
    """Fabrique le .zip d'un plugin à partir de son dossier (utilisé par tools/make_plugin.py) : vérifie plugin.json,
    laisse de côté les fichiers jetables ou personnels (DEFAULT_EXCLUDE + « exclude » du manifeste)."""
    folder = os.path.abspath(folder)
    mpath = os.path.join(folder, MANIFEST)
    if not os.path.isfile(mpath):
        raise PluginError(f"Pas de {MANIFEST} dans {folder}")
    try:
        with open(mpath, encoding="utf-8-sig") as f:
            manifest = validate_manifest(json.load(f))
    except json.JSONDecodeError as exc:
        raise PluginError(f"{MANIFEST} n'est pas un JSON valide : {exc}") from exc
    patterns = DEFAULT_EXCLUDE + manifest["exclude"]
    out_path = os.path.abspath(out_path or os.path.join(os.path.dirname(folder),
                                                        f"{manifest['id']}-{manifest['version']}.zip"))
    count = 0
    with zipfile.ZipFile(out_path + ".tmp", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(folder):
            rel_base = os.path.relpath(base, folder).replace(os.sep, "/")
            rel_base = "" if rel_base == "." else rel_base + "/"
            dirs[:] = sorted(d for d in dirs if not excluded(rel_base + d, patterns)
                             and not os.path.islink(os.path.join(base, d)))
            for name in sorted(files):
                rel = rel_base + name
                full = os.path.join(base, name)
                if os.path.islink(full) or excluded(rel, patterns) or os.path.abspath(full) in (out_path, out_path + ".tmp"):
                    continue
                zf.write(full, rel)
                count += 1
    os.replace(out_path + ".tmp", out_path)
    return out_path, manifest, count


# ------------------------------------------------------------------------------------------------ gestionnaire
def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


class Plugin:
    def __init__(self, base: str, manifest: dict) -> None:
        self.base = base
        self.manifest = manifest
        self.proc: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.state = "stopped"          # stopped | installing | starting | running | error
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.stopped_at: Optional[float] = None
        self.stop_reason: Optional[str] = None
        self.last_activity = 0.0
        self.streams = 0                # réponses en cours de relais (flux de progression, gros téléchargement)
        self.lock = threading.RLock()

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def app_dir(self) -> str:
        return os.path.join(self.base, "app")

    @property
    def deps_dir(self) -> str:
        return os.path.join(self.base, "deps")

    @property
    def data_dir(self) -> str:
        return os.path.join(self.base, "data")

    @property
    def log_path(self) -> str:
        return os.path.join(self.base, "plugin.log")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class PluginManager:
    def __init__(self, data_dir: str, out_root: Optional[str] = None,
                 on_event: Optional[Callable[[str, str, bool], None]] = None) -> None:
        self.root = os.path.join(data_dir, "plugins")
        os.makedirs(self.root, exist_ok=True)
        self.out_root = self._pick_out_root(data_dir, out_root)
        self.plugins: dict[str, Plugin] = {}
        self.lock = threading.RLock()
        self.on_event = on_event or (lambda kind, label, ok: None)
        self._watchdog: Optional[threading.Thread] = None
        self._closing = threading.Event()
        self.load()

    @staticmethod
    def _pick_out_root(data_dir: str, wanted: Optional[str]) -> str:
        """Le dossier de sortie monté dans la stack (/plugins-out) s'il existe et qu'on peut y écrire ; sinon un dossier
        dans /data (les fichiers restent alors dans le volume de Bulle, à récupérer avec `docker cp`)."""
        for cand in ([wanted] if wanted else []) + ["/plugins-out"]:
            if cand and os.path.isdir(cand) and os.access(cand, os.W_OK):
                return os.path.abspath(cand)
        fallback = os.path.join(data_dir, "plugins-out")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    def out_dir(self, pid: str) -> str:
        return os.path.join(self.out_root, pid)

    # ---------------------------------------------------------------- inventaire
    def load(self) -> None:
        for pid in sorted(os.listdir(self.root)):
            base = os.path.join(self.root, pid)
            mpath = os.path.join(base, "app", MANIFEST)
            if not ID_RE.match(pid) or not os.path.isfile(mpath):
                continue
            try:
                with open(mpath, encoding="utf-8-sig") as f:
                    manifest = validate_manifest(json.load(f))
                if manifest["id"] != pid:
                    raise PluginError("id du manifeste différent du dossier")
            except (OSError, ValueError) as exc:
                log.warning("Plugin %s ignoré : %s", pid, exc)
                continue
            p = Plugin(base, manifest)
            if not self._deps_ok(p):
                p.state, p.error = "error", "Dépendances non installées : réinstallez le paquet"
            self.plugins[pid] = p
        if self.plugins:
            log.info("Plugins installés : %s", ", ".join(self.plugins))

    def get(self, pid: str) -> Plugin:
        p = self.plugins.get(pid)
        if p is None:
            raise KeyError(pid)
        return p

    def info(self, p: Plugin) -> dict:
        m = p.manifest
        alive = p.alive()
        if p.state == "running" and not alive:
            self._reap(p)
        return {"id": p.id, "name": m["name"], "version": m["version"], "description": m["description"],
                "state": p.state, "error": p.error, "port": p.port, "idle_minutes": m["idle_minutes"],
                "started_at": p.started_at, "stopped_at": p.stopped_at, "stop_reason": p.stop_reason,
                "last_activity": p.last_activity or None, "icon": bool(m.get("icon")),
                "output": self.out_dir(p.id), "url": f"/plugins/{p.id}/"}

    def list(self) -> list[dict]:
        with self.lock:
            return [self.info(p) for p in self.plugins.values()]

    # ---------------------------------------------------------------- installation
    def install(self, package_path: str) -> dict:
        """Installe (ou met à jour) un plugin à partir de son .zip. Les dépendances Python s'installent ensuite en
        arrière-plan (état « installing »)."""
        manifest, _prefix, _members = read_package(package_path)
        pid = manifest["id"]
        with self.lock:
            old = self.plugins.get(pid)
            if old is not None:
                self.stop(pid, reason="mise à jour")
            base = os.path.join(self.root, pid)
            os.makedirs(base, exist_ok=True)
            fresh = os.path.join(base, "app.new")
            shutil.rmtree(fresh, ignore_errors=True)
            try:
                extract_package(package_path, fresh)
            except Exception:
                shutil.rmtree(fresh, ignore_errors=True)
                raise
            current = os.path.join(base, "app")
            if os.path.isdir(current):
                # ce que le plugin écrit à côté de son code (réglages, historique…) survit à la mise à jour
                for rel in manifest["keep"]:
                    src = os.path.join(current, *rel.split("/"))
                    dst = os.path.join(fresh, *rel.split("/"))
                    if not os.path.lexists(src) or os.path.islink(src):
                        continue
                    if os.path.lexists(dst):
                        shutil.rmtree(dst) if os.path.isdir(dst) and not os.path.islink(dst) else os.remove(dst)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                shutil.rmtree(current)
            os.replace(fresh, current)
            os.makedirs(os.path.join(base, "data"), exist_ok=True)
            os.makedirs(self.out_dir(pid), exist_ok=True)
            p = Plugin(base, manifest)
            self.plugins[pid] = p
            label = f"Plugin « {manifest['name']} » {manifest['version']} " + ("mis à jour" if old else "installé")
            if self._needs_deps(p):
                p.state = "installing"
                threading.Thread(target=self._install_deps, args=(p, label), name=f"plugin-deps-{pid}", daemon=True).start()
            else:
                self.on_event("plugins", label, True)
            log.info("%s", label)
            return self.info(p)

    def _req_file(self, p: Plugin) -> Optional[str]:
        path = os.path.join(p.app_dir, p.manifest["requirements"])
        return path if os.path.isfile(path) else None

    @staticmethod
    def _hash(path: str) -> str:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _needs_deps(self, p: Plugin) -> bool:
        req = self._req_file(p)
        if not req:
            return False
        stamp = os.path.join(p.deps_dir, ".requirements.sha256")
        try:
            with open(stamp) as f:
                return f.read().strip() != self._hash(req)
        except OSError:
            return True

    def _deps_ok(self, p: Plugin) -> bool:
        return not self._needs_deps(p)

    def _install_deps(self, p: Plugin, label: str) -> None:
        req = self._req_file(p)
        assert req
        tmp = p.deps_dir + ".new"
        shutil.rmtree(tmp, ignore_errors=True)
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q",
               "--target", tmp, "-r", req]
        try:
            with open(p.log_path, "w", encoding="utf-8") as out:
                out.write("[bulle] installation des dépendances : " + " ".join(cmd) + "\n")
                out.flush()
                rc = subprocess.run(cmd, cwd=p.app_dir, stdout=out, stderr=subprocess.STDOUT, timeout=1800).returncode
            if rc != 0:
                raise PluginError(f"pip a échoué (code {rc}) : voir le journal du plugin")
            with open(os.path.join(tmp, ".requirements.sha256"), "w") as f:
                f.write(self._hash(req))
            shutil.rmtree(p.deps_dir, ignore_errors=True)
            os.replace(tmp, p.deps_dir)
            with p.lock:
                p.state, p.error = "stopped", None
            self.on_event("plugins", label + " (dépendances installées)", True)
        except (OSError, subprocess.SubprocessError, PluginError) as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            with p.lock:
                p.state, p.error = "error", f"Dépendances non installées : {exc}"
            self.on_event("plugins", f"Plugin « {p.manifest['name']} » : dépendances non installées", False)
            log.warning("Plugin %s : dépendances non installées : %s", p.id, exc)

    def remove(self, pid: str) -> None:
        """Désinstalle : le programme et son dossier data disparaissent ; le dossier de sortie est gardé (ce sont vos
        fichiers)."""
        with self.lock:
            p = self.get(pid)
            self.stop(pid, reason="désinstallation")
            shutil.rmtree(p.base, ignore_errors=True)
            del self.plugins[pid]
            self.on_event("plugins", f"Plugin « {p.manifest['name']} » désinstallé", True)

    # ---------------------------------------------------------------- démarrage / arrêt
    def start(self, pid: str) -> dict:
        p = self.get(pid)
        with p.lock:
            if p.alive() and p.state == "running":
                p.last_activity = time.time()
                return self.info(p)
            if p.state == "installing":
                raise PluginError("Installation des dépendances en cours : patientez un peu")
            if not self._deps_ok(p):
                raise PluginError("Dépendances non installées : réinstallez le paquet")
            m = p.manifest
            port = m["port"] or pick_port()
            if not port_free(port):
                raise PluginError(f"Le port {port} est déjà pris dans le conteneur (un autre plugin ?)")
            out = self.out_dir(pid)
            os.makedirs(out, exist_ok=True)
            os.makedirs(p.data_dir, exist_ok=True)
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "SSL_CERT_FILE",
                                                                  "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                                                                  "http_proxy", "https_proxy", "no_proxy")}
            env.update(m["env"])
            pypath = [p.deps_dir] if os.path.isdir(p.deps_dir) else []
            env.update({"PORT": str(port), "HOST": "127.0.0.1", "PLUGIN_ID": pid, "PLUGIN_PORT": str(port),
                        "PLUGIN_BASE": f"/plugins/{pid}/", "PLUGIN_OUTPUT": out, "PLUGIN_DATA": p.data_dir,
                        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            if pypath:
                env["PYTHONPATH"] = os.pathsep.join(pypath)
            subst = {"{python}": sys.executable, "{port}": str(port), "{output}": out, "{data}": p.data_dir}
            cmd = []
            for part in m["command"]:
                for k, v in subst.items():
                    part = part.replace(k, v)
                cmd.append(part)
            self._trim_log(p)
            logf = open(p.log_path, "a", encoding="utf-8")
            logf.write(f"\n[bulle] {time.strftime('%Y-%m-%d %H:%M:%S')} démarrage : {' '.join(cmd)} (port {port})\n")
            logf.flush()
            try:
                p.proc = subprocess.Popen(cmd, cwd=p.app_dir, env=env, stdout=logf, stderr=subprocess.STDOUT,
                                          stdin=subprocess.DEVNULL, start_new_session=True)
            except OSError as exc:
                p.proc = None
                p.state, p.error = "error", f"Impossible de lancer le programme : {exc}"
                raise PluginError(p.error) from exc
            finally:
                logf.close()   # le programme garde sa propre copie du descripteur
            p.port, p.state, p.error, p.stop_reason = port, "starting", None, None
            p.started_at, p.last_activity = time.time(), time.time()
            deadline = time.time() + m["start_timeout"]
            while time.time() < deadline:
                if p.proc.poll() is not None:
                    p.state = "error"
                    p.error = f"Le programme s'est arrêté au démarrage (code {p.proc.returncode}) : voir le journal"
                    p.proc = None
                    raise PluginError(p.error)
                if port_open(port):
                    p.state = "running"
                    self.on_event("plugins", f"Plugin « {m['name']} » démarré", True)
                    log.info("Plugin %s démarré (pid %s, port %d)", pid, p.proc.pid, port)
                    self._ensure_watchdog()
                    return self.info(p)
                time.sleep(0.2)
            self._kill(p)
            p.state = "error"
            p.error = (f"Le programme ne répond pas sur le port {port} après {m['start_timeout']:g} s : vérifiez « port » dans "
                       "plugin.json (le programme doit écouter sur 127.0.0.1, ou lire la variable PORT) et le journal")
            raise PluginError(p.error)

    def _trim_log(self, p: Plugin) -> None:
        try:
            if os.path.getsize(p.log_path) > LOG_MAX:
                with open(p.log_path, "rb") as f:
                    f.seek(-LOG_MAX // 2, os.SEEK_END)
                    tail = f.read()
                with open(p.log_path, "wb") as f:
                    f.write(b"[bulle] (journal raccourci)\n" + tail)
        except OSError:
            pass

    def _kill(self, p: Plugin) -> None:
        proc = p.proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (OSError, AttributeError):
                proc.terminate()
            try:
                proc.wait(8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, AttributeError):
                    proc.kill()
                proc.wait(5)
        p.proc = None

    def _reap(self, p: Plugin) -> None:
        """Le programme s'est arrêté tout seul (plantage, fin) : on le note."""
        with p.lock:
            if p.proc is not None and p.proc.poll() is not None:
                code = p.proc.returncode
                p.proc = None
                p.state = "error" if code else "stopped"
                p.error = f"Le programme s'est arrêté tout seul (code {code}) : voir le journal" if code else None
                p.stopped_at, p.stop_reason = time.time(), "arrêt du programme"
                self.on_event("plugins", f"Plugin « {p.manifest['name']} » arrêté tout seul (code {code})", not code)

    def stop(self, pid: str, reason: str = "à la demande") -> bool:
        p = self.get(pid)
        with p.lock:
            if not p.alive():
                if p.state in ("running", "starting"):
                    p.state = "stopped"
                p.proc = None
                return False
            self._kill(p)
            p.state, p.port = "stopped", None
            p.stopped_at, p.stop_reason = time.time(), reason
            self.on_event("plugins", f"Plugin « {p.manifest['name']} » arrêté ({reason})", True)
            log.info("Plugin %s arrêté (%s)", pid, reason)
            return True

    def stop_all(self, reason: str = "arrêt de Bulle") -> None:
        self._closing.set()
        for pid in list(self.plugins):
            try:
                self.stop(pid, reason)
            except Exception:  # noqa: BLE001
                log.exception("Arrêt du plugin %s", pid)

    # ---------------------------------------------------------------- activité, arrêt automatique
    def touch(self, p: Plugin) -> None:
        p.last_activity = time.time()

    def busy(self, p: Plugin) -> bool:
        """Le plugin dit-il qu'il travaille encore (busy_url renvoie {"busy": true}) ? Un travail de fond sans page
        ouverte (téléchargement lancé puis panneau fermé) n'est alors pas interrompu."""
        url = p.manifest.get("busy_url")
        if not url or not p.port:
            return False
        import http.client
        try:
            conn = http.client.HTTPConnection("127.0.0.1", p.port, timeout=5)
            conn.request("GET", "/" + url, headers={"Accept": "application/json", "User-Agent": "Bulle"})
            r = conn.getresponse()
            data = json.loads(r.read(1024 * 1024) or b"{}") if r.status == 200 else {}
            conn.close()
            return bool(isinstance(data, dict) and data.get("busy"))
        except (OSError, ValueError):
            return False

    def idle_check(self, now: Optional[float] = None) -> list[str]:
        """Arrête les plugins inactifs depuis plus de idle_minutes (ni requête, ni flux en cours, ni travail signalé)."""
        now = now or time.time()
        stopped = []
        for p in list(self.plugins.values()):
            if p.state == "running" and not p.alive():
                self._reap(p)
                continue
            idle = p.manifest["idle_minutes"]
            if p.state != "running" or not idle or p.streams > 0:
                continue
            if now - (p.last_activity or now) < idle * 60:
                continue
            if self.busy(p):
                p.last_activity = now
                continue
            if self.stop(p.id, reason=f"{idle:g} min sans activité"):
                stopped.append(p.id)
        return stopped

    def _ensure_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            return

        def loop() -> None:
            while not self._closing.wait(30):
                try:
                    self.idle_check()
                except Exception:  # noqa: BLE001
                    log.exception("Surveillance des plugins")
        self._watchdog = threading.Thread(target=loop, name="bulle-plugins", daemon=True)
        self._watchdog.start()

    def log_tail(self, pid: str, max_bytes: int = 64 * 1024) -> str:
        p = self.get(pid)
        try:
            with open(p.log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                return f.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def icon_path(self, pid: str) -> Optional[str]:
        p = self.get(pid)
        icon = p.manifest.get("icon")
        if not icon:
            return None
        path = os.path.join(p.app_dir, icon)
        return path if os.path.isfile(path) else None


# ------------------------------------------------------------------------------------------------ réécriture des pages
_ATTR_RE = re.compile(r"""(\s(?:href|src|action|poster|data-src|formaction)\s*=\s*)(["'])/(?![/\\])""", re.I)
_CSS_URL_RE = re.compile(r"""(url\(\s*["']?)/(?![/\\])""", re.I)
_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.I)


def shim_script(base: str) -> str:
    """Petit script ajouté en tête des pages du plugin : les adresses « /api/… » que le programme fabrique lui-même
    (fetch, EventSource, XMLHttpRequest, liens et images créés en JavaScript, innerHTML, window.open) passent par
    /plugins/<id>/."""
    b = json.dumps(base.rstrip("/"))
    return ("<script>(function(){var B=" + b + ";"
            "function fx(u){if(typeof u!=='string')return u;"
            "if(u.charAt(0)==='/'&&u.charAt(1)!=='/'&&u!==B&&u.indexOf(B+'/')!==0)return B+u;"
            "var o=location.origin;if(u.indexOf(o+'/')===0){var p=u.slice(o.length);"
            "if(p.indexOf(B+'/')!==0&&p!==B)return o+B+p}return u}"
            "var F=window.fetch;if(F)window.fetch=function(i,o){if(typeof i==='string')i=fx(i);"
            "else if(i&&i.url&&window.Request&&i instanceof Request){var n=fx(i.url);if(n!==i.url)i=new Request(n,i)}"
            "return F.call(this,i,o)};"
            "var X=window.XMLHttpRequest&&XMLHttpRequest.prototype.open;if(X)XMLHttpRequest.prototype.open=function(){"
            "arguments[1]=fx(arguments[1]);return X.apply(this,arguments)};"
            "var E=window.EventSource;if(E){var N=function(u,c){return new E(fx(u),c)};N.prototype=E.prototype;"
            "N.CONNECTING=0;N.OPEN=1;N.CLOSED=2;window.EventSource=N}"
            "var W=window.open;window.open=function(u){arguments[0]=fx(u);return W.apply(this,arguments)};"
            "function fixEl(a){if(!a||!a.getAttribute)return;var h=a.getAttribute('href');if(h&&fx(h)!==h)a.setAttribute('href',fx(h));"
            "var f=a.getAttribute('action');if(f&&fx(f)!==f)a.setAttribute('action',fx(f))}"
            "document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[href]');if(a)fixEl(a)},true);"
            "document.addEventListener('submit',function(e){fixEl(e.target)},true);"
            # images, vidéos, cadres… créés en JavaScript : propriétés (img.src = …), setAttribute, innerHTML et
            # insertAdjacentHTML ; un MutationObserver rattrape ce qui passerait autrement (ex. aperçus d'un plugin)
            "var AT=/^(?:src|href|action|poster|data-src|formaction)$/i;"
            "function fh(s){if(typeof s!=='string')return s;"
            "return s.replace(/(\\s(?:src|href|action|poster|data-src|formaction)\\s*=\\s*[\"'])\\/(?![\\/\\\\])/gi,"
            "function(m,a,i,t){return t.substr(i+a.length,B.length+1)===B+'/'?m:a+B+'/'})}"
            "function hp(C,p){var K=window[C]&&window[C].prototype;if(!K)return;var d=Object.getOwnPropertyDescriptor(K,p);"
            "if(!d||!d.set||!d.configurable)return;Object.defineProperty(K,p,{configurable:true,enumerable:d.enumerable,get:d.get,"
            "set:function(v){d.set.call(this,fx(v))}})}"
            "[['HTMLImageElement','src'],['HTMLMediaElement','src'],['HTMLSourceElement','src'],['HTMLIFrameElement','src'],"
            "['HTMLScriptElement','src'],['HTMLEmbedElement','src'],['HTMLLinkElement','href'],['HTMLVideoElement','poster'],"
            "['HTMLAnchorElement','href'],['HTMLFormElement','action']].forEach(function(x){hp(x[0],x[1])});"
            "var SA=Element.prototype.setAttribute;Element.prototype.setAttribute=function(n,v){"
            "if(typeof n==='string'&&AT.test(n))v=fx(String(v));return SA.call(this,n,v)};"
            "['innerHTML','outerHTML'].forEach(function(p){var d=Object.getOwnPropertyDescriptor(Element.prototype,p);"
            "if(d&&d.set&&d.configurable)Object.defineProperty(Element.prototype,p,{configurable:true,enumerable:d.enumerable,"
            "get:d.get,set:function(v){d.set.call(this,fh(v))}})});"
            "var IA=Element.prototype.insertAdjacentHTML;if(IA)Element.prototype.insertAdjacentHTML=function(w,h){"
            "return IA.call(this,w,fh(h))};"
            "function fixN(n){if(!n||n.nodeType!==1)return;['src','poster','data-src'].forEach(function(a){"
            "var v=n.getAttribute(a);if(v&&fx(v)!==v)SA.call(n,a,fx(v))})}"
            "if(window.MutationObserver)new MutationObserver(function(ms){ms.forEach(function(m){"
            "m.addedNodes.forEach(function(n){if(n.nodeType!==1)return;fixN(n);"
            "if(n.querySelectorAll)n.querySelectorAll('[src],[poster],[data-src]').forEach(fixN)})})})"
            ".observe(document.documentElement,{childList:true,subtree:true});"
            "})();</script>")


def _prefixer(text: str, base: str, pattern: re.Pattern, keep_groups: Callable[[re.Match], str]) -> str:
    """Ajoute `base` devant les adresses « /… » trouvées, sauf celles qui l'ont déjà."""
    def repl(m: re.Match) -> str:
        if text.startswith(base + "/", m.end() - 1) or text.startswith(base + '"', m.end() - 1) \
                or text.startswith(base + "'", m.end() - 1):
            return m.group(0)
        return keep_groups(m) + base + "/"
    return pattern.sub(repl, text)


def rewrite_html(text: str, base: str) -> str:
    base = base.rstrip("/")
    text = _prefixer(text, base, _ATTR_RE, lambda m: m.group(1) + m.group(2))
    text = _prefixer(text, base, _CSS_URL_RE, lambda m: m.group(1))
    shim = shim_script(base)
    m = _HEAD_RE.search(text)
    if m:
        return text[:m.end()] + shim + text[m.end():]
    return shim + text


def rewrite_css(text: str, base: str) -> str:
    return _prefixer(text, base.rstrip("/"), _CSS_URL_RE, lambda m: m.group(1))


# ------------------------------------------------------------------------------------------------ relais (proxy)
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
               "transfer-encoding", "upgrade", "host", "content-length"}
REWRITE_MAX = 8 * 1024 * 1024   # pages HTML / CSS réécrites en mémoire jusqu'à cette taille


def _strip_bulle_cookies(cookie_header: str) -> str:
    """Le plugin ne voit pas les cookies de session de Bulle (bulle_session, bulle_auth…), seulement les siens."""
    keep = []
    for part in cookie_header.split(";"):
        name = part.split("=", 1)[0].strip()
        if name and not name.startswith("bulle_"):
            keep.append(part.strip())
    return "; ".join(keep)


def _fix_set_cookie(value: str, base: str) -> str:
    """Un cookie posé par le plugin pour « / » ne vaut que pour /plugins/<id>/ (il ne touche pas aux pages de Bulle)."""
    parts = [x.strip() for x in value.split(";")]
    out, has_path = [parts[0]], False
    for attr in parts[1:]:
        if attr.lower().startswith("path="):
            path = attr[5:].strip() or "/"
            if not path.startswith(base):
                path = base.rstrip("/") + (path if path.startswith("/") else "/" + path)
            out.append("Path=" + path)
            has_path = True
        elif attr.lower().startswith("domain="):
            continue
        else:
            out.append(attr)
    if not has_path:
        out.append("Path=" + base)
    return "; ".join(out)


def proxy(manager: PluginManager, p: Plugin, sub: str, request: Any) -> Any:
    """Relaie la requête Flask `request` vers le programme du plugin et renvoie sa réponse (en flux pour le reste :
    progression en direct, gros fichiers)."""
    import http.client
    from flask import Response

    base = f"/plugins/{p.id}/"
    port = p.port
    if p.state != "running" or not p.alive() or not port:
        page = (f"<!doctype html><meta charset='utf-8'><title>{p.manifest['name']}</title>"
                "<body style='font:16px system-ui;padding:2em;background:#14110e;color:#f4ead7'>"
                f"<h2>{p.manifest['name']} est arrêté</h2><p>Démarrez-le depuis le laboratoire de Bulle "
                "(champignon, ou Réglages › Laboratoire).</p></body>")
        return Response(page, 503, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})
    manager.touch(p)
    path = "/" + sub
    if request.query_string:
        path += "?" + request.query_string.decode("latin-1")
    headers = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in HOP_HEADERS or lk in ("authorization", "cookie", "accept-encoding"):
            continue
        headers[k] = v
    cookies = _strip_bulle_cookies(request.headers.get("Cookie", ""))
    if cookies:
        headers["Cookie"] = cookies
    own = request.host_url.rstrip("/")
    target = f"http://127.0.0.1:{port}"
    # le programme se croit servi à la racine, sur 127.0.0.1 : Origin / Referer venant de Bulle sont traduits
    if headers.get("Origin", "").rstrip("/") == own:
        headers["Origin"] = target
    ref = headers.get("Referer", "")
    if ref.startswith(own + base):
        headers["Referer"] = target + "/" + ref[len(own + base):]
    elif ref.startswith(own):
        headers.pop("Referer", None)
    headers["Host"] = f"127.0.0.1:{port}"
    headers["X-Forwarded-For"] = request.remote_addr or ""
    headers["X-Forwarded-Proto"] = request.scheme
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Prefix"] = base.rstrip("/")
    length = request.content_length
    body: Any = None
    if request.method not in ("GET", "HEAD") and (length or request.headers.get("Transfer-Encoding")):
        body = request.get_data(cache=False) if not length or length < 16 * 1024 * 1024 else request.stream
        headers["Content-Length"] = str(length if length is not None else len(body))
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=300)
        conn.request(request.method, path, body=body, headers=headers)
        r = conn.getresponse()
    except OSError as exc:
        manager.idle_check()   # programme planté ? l'état est mis à jour
        return Response(f"{p.manifest['name']} ne répond pas : {exc}", 502, {"Content-Type": "text/plain; charset=utf-8"})

    out_headers = []
    for k, v in r.getheaders():
        lk = k.lower()
        if lk in HOP_HEADERS or lk in ("x-frame-options", "content-security-policy", "strict-transport-security"):
            continue
        if lk == "location":
            if v.startswith(target):
                v = v[len(target):] or "/"
            if v.startswith("/") and not v.startswith("//") and not v.startswith(base):
                v = base.rstrip("/") + v
        elif lk == "set-cookie":
            v = _fix_set_cookie(v, base)
        out_headers.append((k, v))
    ctype = (r.getheader("Content-Type") or "").lower()
    clen = r.getheader("Content-Length")
    rewritable = (ctype.startswith("text/html") or ctype.startswith("text/css")) and \
        not (r.getheader("Content-Encoding") or "").strip() and (clen is None or int(clen) <= REWRITE_MAX)
    if rewritable and request.method != "HEAD":
        raw = r.read(REWRITE_MAX + 1)
        conn.close()
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", ctype)
        if m:
            charset = m.group(1)
        try:
            text = raw.decode(charset, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        text = rewrite_html(text, base) if ctype.startswith("text/html") else rewrite_css(text, base)
        data = text.encode(charset if charset.lower() in ("utf-8", "utf8") else "utf-8")
        if charset.lower() not in ("utf-8", "utf8"):
            out_headers = [(k, v) for k, v in out_headers if k.lower() != "content-type"]
            out_headers.append(("Content-Type", re.sub(r"charset=[\w-]+", "charset=utf-8", r.getheader("Content-Type"))))
        resp = Response(data, r.status, out_headers)
        resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-cache")
        return resp

    if clen is not None:
        out_headers.append(("Content-Length", clen))
    streaming = ctype.startswith("text/event-stream")
    if streaming:
        out_headers.append(("X-Accel-Buffering", "no"))

    def generate():
        p.streams += 1
        try:
            while True:
                chunk = r.read1(64 * 1024) if hasattr(r, "read1") else r.read(64 * 1024)
                if not chunk:
                    break
                manager.touch(p)
                yield chunk
        except OSError:
            pass
        finally:
            p.streams -= 1
            manager.touch(p)
            conn.close()
    return Response(generate(), r.status, out_headers, direct_passthrough=True)
