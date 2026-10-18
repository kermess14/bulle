"""Serveur web Bulle : pages statiques + API JSON."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import logging
import glob
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from flask import Flask, Response, abort, g as flask_g, jsonify, make_response, request, send_file, send_from_directory
from itsdangerous import BadSignature, URLSafeSerializer
from PIL import Image

from . import opds

from .bedetheque import (INDEX_TTL, USER_AGENT, BdtError, BedethequeClient, compare, index_letter_for, norm_title,
                         parse_album_name, query_from_folder)
from .comics import COVER_WIDTH, QUALITY_PROFILES, AlbumError, Comics, pick_width
from .library import DEFAULT_PROFILE, Library
from .panels import PANELS_VERSION, detect_panels

VERSION = "0.21.1"
HD_MIN_PX = 2400   # seuil HD par défaut : grand côté des pages (réglable dans Réglages › Bibliothèque)
PANELS_WIDTH = 600   # largeur de l'image analysée pour trouver les cases
log = logging.getLogger("bulle")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def env_str(name: str, default: str = "") -> str:
    """Variable d'environnement sans espaces ni guillemets autour : dans une stack écrite « - SCAN_ON_START="0" »,
    Docker garde les guillemets dans la valeur ; on les enlève pour que « "0" » vaille bien 0."""
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


def env_int(name: str, default: int) -> int:
    try:
        return int(float(env_str(name, str(default))))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    if os.environ.get(name) is None:
        return default
    return env_str(name).lower() not in ("0", "false", "no", "non", "off", "")


# Réglages globaux (serveur) : défauts tirés des variables d'environnement, modifiables dans la page Réglages.
def global_defaults() -> dict:
    return {
        "scan_interval_hours": env_int("SCAN_INTERVAL_HOURS", 12),
        "scan_on_start": env_bool("SCAN_ON_START", True),   # scan au démarrage du conteneur (après une mise à jour)
        "preload_covers": env_bool("PRELOAD_COVERS", True),
        "scan_mode": "normal",        # rapide : liste seulement ; normal : + couvertures manquantes ; minutieux : + chaque album rouvert, couverture refaite
        "preload_threads": max(1, min(8, env_int("PRELOAD_THREADS", 3))),
        "page_cache": env_bool("PAGE_CACHE", True),
        "cache_max_gb": 5,
        "quality": "normal",          # eco / normal / max
        "sharpen": True,
        "cover_width": COVER_WIDTH,
        "read_threshold": 1.0,        # 1.0 = lu à la dernière page ; 0.9 = lu à partir de 90 %
        "bdt_enabled": True,          # analyse Bédéthèque à la demande
        "bdt_interval": 2.5,          # secondes minimum entre deux requêtes vers bedetheque.com
        "bdt_per_minute": 10,         # plafond par minute glissante (intervalle moyen 60/n, irrégulier)
        "bdt_pause_every": 50,        # tâches de fond : pause après n requêtes…
        "bdt_pause_minutes": 2.5,     # … de cette durée (± 20 %)
        "bdt_auto_summary": True,     # résumé lu sur la fiche Bédéthèque quand on ouvre la fiche d'un album
        "require_profile": False,     # demander « qui lit ? » à l'ouverture
        "opds_enabled": True,         # flux OPDS pour les applis mobiles
        "tools_url": "auto",          # BDConverter dans le menu caché (champignon) : adresse, "auto" = même machine, port 3111, "" = masqué
        "adult_paths": [],            # dossiers de la rubrique Adulte (chemins relatifs), cachés tant que le code n'est pas entré
        "adult_hide_tab": False,      # l'entrée « Adulte » n'apparaît pas dans le menu (accès par Réglages › Adulte)
        "quality_auto": env_bool("QUALITY_AUTO", True),   # mesure HD / SD des albums nouveaux ou modifiés après chaque scan
        "hd_min_px": HD_MIN_PX,       # grand côté des pages à partir duquel un album est HD
    }


GLOBAL_TYPES = {
    "scan_interval_hours": (int, 0, 720), "scan_on_start": (bool,), "preload_covers": (bool,), "scan_mode": (str,), "preload_threads": (int, 1, 8),
    "page_cache": (bool,), "cache_max_gb": (float, 0, 1000), "quality": (str, tuple(QUALITY_PROFILES)),
    "sharpen": (bool,), "cover_width": (int, 200, 1200), "read_threshold": (float, 0.5, 1.0),
    "bdt_enabled": (bool,), "bdt_interval": (float, 1.0, 30.0), "bdt_auto_summary": (bool,),
    "bdt_per_minute": (float, 1.0, 60.0), "bdt_pause_every": (int, 0, 1000), "bdt_pause_minutes": (float, 0.5, 30.0),
    "require_profile": (bool,), "opds_enabled": (bool,), "tools_url": (str,), "adult_paths": (list,), "ignored_paths": (list,), "adult_hide_tab": (bool,),
    "quality_auto": (bool,), "hd_min_px": (int, 800, 8000),
}


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"pbkdf2${salt}${digest}"


def check_pin(stored: Optional[str], pin: str) -> bool:
    if not stored:
        return True
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return hmac.compare_digest(candidate, digest)


def create_app(library_root: Optional[str] = None, data_dir: Optional[str] = None) -> Flask:
    # chemins absolus : Flask résout les chemins relatifs par rapport au paquet, pas au dossier courant
    library_root = os.path.abspath(library_root or os.environ.get("LIBRARY_ROOT", "/library"))
    data_dir = os.path.abspath(data_dir or os.environ.get("DATA_DIR", "/data"))
    os.makedirs(data_dir, exist_ok=True)

    comics = Comics(os.path.join(data_dir, "cache"), page_cache=env_bool("PAGE_CACHE", True))
    lib = Library(library_root, os.path.join(data_dir, "bulle.sqlite"), on_invalidate=comics.invalidate)
    try:
        migrated = comics.migrate_cover_names(lib.albums_without("1=1"))
        if migrated:
            log.info("Couvertures renommées avec la date de leur fichier : %d", migrated)
    except Exception:  # noqa: BLE001
        log.exception("Renommage des couvertures")

    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions["bulle"] = {"library": lib, "comics": comics}

    # ------------------------------------------------------------------ réglages
    def settings() -> dict:
        s = global_defaults()
        s.update(lib.get_settings(None))
        return s

    bdt = BedethequeClient(lib.bdt_cache_get, lib.bdt_cache_put)
    import bulle.bedetheque as _bdt_mod
    _bdt_mod.USER_AGENT = f"Bulle/{VERSION} (+https://github.com/kermess14/bulle ; lecteur de BD personnel, requetes a la demande)"
    bdt_job = {"running": False, "done": 0, "total": 0, "current": None, "errors": [], "stop": False, "linked": 0,
               "ambiguous": 0, "not_found": 0}

    hdcfg = {"min": HD_MIN_PX}   # seuil HD en cours (relu à chaque changement de réglage)

    def apply_settings(s: dict) -> None:
        hdcfg["min"] = int(s.get("hd_min_px") or HD_MIN_PX)
        comics.configure(quality=s["quality"], sharpen=s["sharpen"], cover_width=s["cover_width"],
                         page_cache=s["page_cache"])
        bdt.min_interval = float(s["bdt_interval"])
        bdt.per_minute = float(s["bdt_per_minute"])
        bdt.pause_every = int(s["bdt_pause_every"])
        bdt.pause_minutes = float(s["bdt_pause_minutes"])

    def validate_global(values: dict) -> dict:
        out = {}
        for key, val in values.items():
            if key not in GLOBAL_TYPES:
                abort(400, description=f"Réglage inconnu : {key}")
            if val is None:
                out[key] = None
                continue
            spec = GLOBAL_TYPES[key]
            typ = spec[0]
            try:
                if typ is bool:
                    val = bool(val) if not isinstance(val, str) else val.lower() in ("1", "true", "on", "oui")
                elif typ is int:
                    val = max(spec[1], min(spec[2], int(val)))
                elif typ is float:
                    val = max(spec[1], min(spec[2], float(val)))
                elif typ is str:
                    val = str(val).strip()[:500]
                    if len(spec) > 1 and val not in spec[1]:
                        abort(400, description=f"Valeur invalide pour {key}")
                elif typ is list:
                    val = [str(v).strip("/") for v in (val or []) if str(v).strip("/")][:2000]
            except (TypeError, ValueError):
                abort(400, description=f"Valeur invalide pour {key}")
            out[key] = val
        return out

    def validate_profile_settings(values: dict) -> dict:
        if len(values) > 80:
            abort(400, description="Trop de réglages")
        out = {}
        for key, val in values.items():
            if not isinstance(key, str) or len(key) > 48:
                abort(400, description="Clé de réglage invalide")
            if val is not None and not isinstance(val, (str, int, float, bool)):
                abort(400, description=f"Valeur invalide pour {key}")
            if isinstance(val, str) and len(val) > 300:
                abort(400, description=f"Valeur trop longue pour {key}")
            out[key] = val
        return out

    apply_settings(settings())

    # ------------------------------------------------------------------ profils, cookies signés, code d'accès
    secret_row = lib.conn.execute("SELECT value FROM meta WHERE key='secret'").fetchone()
    if secret_row:
        secret = secret_row["value"]
    else:
        secret = secrets.token_hex(32)
        with lib._write_lock:
            lib.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('secret', ?)", (secret,))
            lib.conn.commit()
    signer = URLSafeSerializer(secret, salt="bulle")

    def access_pin_hash() -> Optional[str]:
        return lib.get_settings(None).get("access_pin_hash") or None

    # ---- rubrique Adulte : dossiers cachés tant que le code n'est pas entré (cookie signé, valable 12 h)
    ADULT_TTL = 12 * 3600

    def adult_pin_hash() -> Optional[str]:
        return lib.get_settings(None).get("adult_pin_hash") or None

    def adult_paths() -> list[str]:
        cached = getattr(flask_g, "_adult_paths", None)
        if cached is None:
            cached = [p.strip("/") for p in (settings().get("adult_paths") or []) if p.strip("/")]
            flask_g._adult_paths = cached
        return cached

    def is_adult_path(path: str) -> bool:
        path = (path or "").strip("/")
        return any(path == p or path.startswith(p + "/") for p in adult_paths())

    def adult_unlocked() -> bool:
        stored = adult_pin_hash()
        if not stored:
            return True
        tok = request.cookies.get("bulle_adult")
        if not tok:
            return False
        try:
            data = signer.loads(tok)
            return data.get("adult") == stored[-16:] and time.time() - float(data.get("t", 0)) < ADULT_TTL
        except (BadSignature, AttributeError, ValueError, TypeError):
            return False

    def hidden(node: dict) -> bool:
        return bool(adult_paths()) and is_adult_path(node.get("path", "")) and not adult_unlocked()

    def visible(nodes: list[dict]) -> list[dict]:
        if not adult_paths() or adult_unlocked():
            return nodes
        return [n for n in nodes if not is_adult_path(n.get("path", ""))]

    def auth_ok() -> bool:
        stored = access_pin_hash()
        if not stored:
            return True
        tok = request.cookies.get("bulle_auth")
        if tok:
            try:
                return signer.loads(tok) == {"auth": stored[-16:]}
            except BadSignature:
                return False
        auth = request.authorization  # OPDS : Basic, mot de passe = code d'accès
        if auth and auth.password is not None and check_pin(stored, auth.password):
            return True
        return False

    @app.before_request
    def gate():
        path = request.path
        if path.startswith("/static/") or path in ("/api/auth/login", "/api/auth/status") or path == "/favicon.ico":
            return None
        if auth_ok():
            return None
        if path.startswith("/opds"):
            return Response("Code d'accès requis", 401, {"WWW-Authenticate": 'Basic realm="Bulle"'})
        if path.startswith("/api/"):
            return jsonify({"error": "Code d'accès requis", "auth_required": True}), 401
        return None  # pages HTML : l'interface affichera l'écran du code

    def current_profile() -> int:
        tok = request.cookies.get("bulle_profile")
        if tok:
            try:
                pid = int(signer.loads(tok).get("p", DEFAULT_PROFILE))
                if lib.profile(pid):
                    return pid
            except (BadSignature, AttributeError, ValueError, TypeError):
                pass
        return DEFAULT_PROFILE

    def current_role() -> str:
        """Rôle de la session. Sans profil choisi (pas de cookie), on retombe sur le premier profil, mais ses droits
        d'administrateur ne valent que si rien ne protège Bulle : ni « qui lit ? » à l'ouverture, ni mot de passe sur
        ce profil. Sinon il faut s'identifier pour administrer."""
        p = lib.profile(current_profile())
        role = (p or {}).get("role") or "reader"
        if role == "admin" and not profile_selected() and (settings()["require_profile"] or (p or {}).get("pin_hash")):
            return "reader"
        return role

    def is_admin() -> bool:
        return current_role() == "admin"

    def require_admin() -> None:
        """Actions réservées à l'administrateur : réglages du serveur, scans, profils des autres, rubrique Adulte…
        Un lecteur peut lire, noter sa progression, gérer ses listes et son propre compte."""
        if not is_admin():
            abort(403, description="admin_required")

    def profile_selected() -> bool:
        tok = request.cookies.get("bulle_profile")
        if not tok:
            return False
        try:
            return bool(lib.profile(int(signer.loads(tok).get("p", 0))))
        except (BadSignature, AttributeError, ValueError, TypeError):
            return False

    # ------------------------------------------------------------------ helpers
    def progress_json(p: Optional[dict]) -> Optional[dict]:
        if not p:
            return None
        return {"page": p["page"], "pages": p.get("page_count"), "completed": bool(p.get("completed")),
                "updated_at": p.get("updated_at")}

    def album_json(n: dict, with_progress: bool = True) -> dict:
        d = {
            "id": n["id"], "kind": n["kind"], "name": n["name"], "path": n["path"],
            "parent_id": n.get("parent_id"), "format": n.get("format"), "size": n.get("size", 0),
            "mtime": int(n.get("mtime") or 0), "added": int(n.get("added_at") or 0),
            "pages": n.get("page_count"), "error": n.get("error"), "color": n.get("color"),
        }
        if n["kind"] == "album" and n.get("cover_page") is not None:
            d["cover_page"] = n.get("cover_page")
        if n["kind"] == "album" and n.get("res_w"):
            # qualité mesurée sur les pages elles-mêmes (pas sur le nom ni la fiche)
            d["res"] = [n["res_w"], n["res_h"]]
            d["q"] = "hd" if max(n["res_w"], n["res_h"]) >= hdcfg["min"] else "sd"
        if n["kind"] == "album" and n.get("page_count"):
            # version de la couverture (date du fichier de cache) : refaite = nouvelle adresse, le navigateur ne peut pas
            # ressortir l'ancienne image de son cache
            try:
                d["cover_ver"] = int(os.path.getmtime(comics.cover_path(n)))
            except OSError:
                pass
        if n["kind"] == "folder":
            d["album_count"] = n.get("album_count", 0)
            d["cover_id"] = n.get("cover_id")
        if with_progress and "p_page" in n:
            d["progress"] = progress_json(
                {"page": n["p_page"], "page_count": n["p_count"], "completed": n["p_completed"],
                 "updated_at": n["p_updated"]} if n.get("p_page") is not None else None)
        return d

    def ensure_pages(node: dict) -> dict:
        """Compte les pages (et génère la couverture) la première fois qu'on ouvre un album."""
        if node["kind"] != "album" or node.get("page_count") or node.get("error"):
            return node
        try:
            n = comics.inspect(node, lib.abs_path(node["path"]), make_cover=True)
            lib.set_pages(node["id"], n, None)
            lib.set_color(node["id"], comics.cover_color(node, lib.abs_path(node["path"])))
            node["page_count"], node["error"] = n, None
        except AlbumError as e:
            lib.set_pages(node["id"], None, str(e))
            node["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("Ouverture de %s", node["path"])
            lib.set_pages(node["id"], None, f"Erreur inattendue : {e}")
            node["error"] = f"Erreur inattendue : {e}"
        return node

    heal_lock = threading.Lock()

    def heal(node: dict) -> dict:
        """Album dont le fichier n'est plus à sa place (renommé, déplacé, jeté) : relit tout de suite son dossier sur le
        disque. Renommé ou déplacé, il est retrouvé (même taille, même date) et garde sa fiche ; jeté, il disparaît."""
        if node.get("kind") != "album" or os.path.isfile(lib.abs_path(node["path"])):
            return node
        if lib.status["running"] or not heal_lock.acquire(blocking=False):
            return node
        try:
            parent = node["path"].rsplit("/", 1)[0] if "/" in node["path"] else ""
            log.info("Fichier introuvable %s : relecture du dossier « %s »", node["path"], parent or "/")
            lib.scan(under=parent or None)
        except RuntimeError as e:
            log.warning("%s", e)
        finally:
            heal_lock.release()
        fresh = lib.node(node["id"])
        if not fresh:
            abort(404, description="Ce fichier n'est plus sur le disque : il a été retiré de Bulle")
        return fresh   # même contenu sous un autre nom : couverture et pages en cache restent bonnes

    def get_node(node_id: int, kind: Optional[str] = None, allow_hidden: bool = False) -> dict:
        node = lib.node(node_id)
        if not node or (kind and node["kind"] != kind):
            abort(404, description="Introuvable (relancez un scan ?)")
        if not allow_hidden and hidden(node):
            abort(403, description="adult_locked")
        return node

    def meta_json(m: Optional[dict]) -> Optional[dict]:
        if not m:
            return None
        a = m["data"]
        return {"number": m.get("number"), "kind": m.get("kind"), "title": m.get("title"), "year": m.get("year"),
                "url": m.get("url"), "how": m.get("how"), "writers": a.get("writers") or [],
                "pencillers": a.get("pencillers") or [], "colorists": a.get("colorists") or [],
                "publisher": a.get("publisher"), "collection": a.get("collection"), "isbn": a.get("isbn"),
                "pages": a.get("pages"), "date": a.get("date"), "summary": a.get("summary"),
                "summary_at": a.get("summary_at")}

    def folder_payload(folder: dict, profile_id: int) -> dict:
        children = visible(lib.children(folder["id"]))
        adult_set = set(adult_paths())
        prog = lib.all_progress(profile_id)
        by_id = {p["node_id"]: p for p in prog}
        metas = lib.bdt_albums_for_folder(folder["id"])
        links = lib.bdt_series_for([c["id"] for c in children if c["kind"] == "folder"])
        favs = lib.favorites_ids(profile_id)
        cover_meta = lib.cover_meta_for([c["cover_id"] for c in children if c["kind"] == "folder" and c.get("cover_id")])
        qdirs = lib.quality_by_dir(hdcfg["min"])
        out = []
        for c in children:
            j = album_json(c, with_progress=False)
            if c["kind"] == "folder" and c.get("cover_id"):
                meta = cover_meta.get(c["cover_id"])
                if meta:
                    j["color"] = meta["color"]
                    try:
                        j["cover_ver"] = int(os.path.getmtime(comics.cover_path(meta)))
                    except OSError:
                        pass
            if c["kind"] == "folder" and c["path"].strip("/") in adult_set:
                j["adult"] = True
            if c["id"] in favs:
                j["fav"] = True
            if c["kind"] == "album":
                j["progress"] = progress_json(by_id.get(c["id"]))
                if c["id"] in metas:
                    j["meta"] = meta_json(metas[c["id"]])
            else:
                prefix = c["path"] + "/"
                j["read_count"] = sum(1 for p in prog if p["completed"] and p["path"].startswith(prefix))
                j["reading_count"] = sum(1 for p in prog if not p["completed"] and p["path"].startswith(prefix))
                hd = sd = 0
                for d, (h, sd_) in qdirs.items():
                    if d == c["path"] or d.startswith(prefix):
                        hd += h
                        sd += sd_
                if hd or sd:
                    j["hd_count"], j["sd_count"] = hd, sd
                if c["id"] in links:
                    lk = links[c["id"]]
                    j["bdt"] = {"title": lk["title"], "present": lk["present"], "total": lk["total"],
                                "status": lk["status"]}
            out.append(j)
        payload = {"folder": album_json(folder, with_progress=False), "breadcrumb": lib.breadcrumb(folder),
                   "children": out}
        payload["folder"]["fav"] = folder["id"] in favs
        payload["folder"]["adult"] = folder["path"].strip("/") in adult_set
        payload["adult_unlocked"] = adult_unlocked()
        link = lib.bdt_series_get(folder["id"])
        if link:
            payload["bdt"] = bdt_report(folder, link, children)
        payload["bdt_enabled"] = bool(settings()["bdt_enabled"])
        if folder["path"]:
            pre = folder["path"].strip("/") + "/"
            payload["ignored_here"] = sorted(p for p in lib.ignored_paths() if p.startswith(pre))
        return payload

    def bdt_report(folder: dict, link: dict, children: Optional[list[dict]] = None) -> dict:
        """Lien + comparaison dossier ↔ série (sans requête réseau)."""
        children = children if children is not None else lib.children(folder["id"])
        files = [{"id": c["id"], "name": c["name"]} for c in children if c["kind"] == "album"]
        series = link["data"]
        cmp_ = compare(series, files)
        return {
            "series": {"id": series.get("id"), "url": series["url"], "title": series.get("title"),
                       "genre": series.get("genre"), "status": series.get("status"), "years": series.get("years"),
                       "tomes_count": series.get("tomes_count"), "detailed": bool(link.get("detailed")),
                       "score": link.get("score"), "manual": bool(link.get("manual")),
                       "fetched_at": link.get("fetched_at")},
            "present": cmp_["present"], "total": cmp_["total"],
            "missing": [{"number": a["number"], "title": a["title"], "year": a["year"], "url": a["url"]}
                        for a in cmp_["missing"]],
            "unmatched": [{"id": u["id"], "name": u["name"]} for u in cmp_["unmatched"]],
            "duplicates": [{"ids": d["ids"]} for d in cmp_["duplicates"]],
            "specials": [{"num_raw": a["num_raw"], "title": a["title"], "year": a["year"]} for a in cmp_["specials"]][:30],
            "matches": {m["id"]: {"number": m["album"]["number"], "title": m["album"]["title"], "how": m["how"]}
                        for m in cmp_["matches"]},
        }

    def cache_headers(resp: Response, immutable: bool) -> Response:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if immutable else "public, max-age=600"
        return resp

    def with_folder(items: list[dict]) -> list[dict]:
        out = []
        for n in visible(items):
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
            out.append(j)
        return out

    # ------------------------------------------------------------------ pages
    def html_page(name: str) -> Response:
        """Page HTML avec le numéro de version collé aux adresses des fichiers (style.css?v=…) : après une mise à jour,
        le navigateur ne peut plus garder l'ancienne feuille de style ou l'ancien script en mémoire."""
        with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
            html = f.read()
        for asset in ("style.css", "app.js", "reader.js"):
            html = html.replace(f'"/static/{asset}"', f'"/static/{asset}?v={VERSION}"')
        html = html.replace("<head>", f'<head>\n<meta name="bulle-version" content="{VERSION}">', 1)
        resp = make_response(html)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/")
    def index():
        return html_page("index.html")

    @app.route("/read/<int:node_id>")
    def read_page(node_id: int):
        return html_page("reader.html")

    @app.route("/static/<path:filename>")
    def static_files(filename: str):
        if filename.endswith(".webmanifest"):
            resp = send_from_directory(STATIC_DIR, filename, max_age=0, conditional=True)
            resp.mimetype = "application/manifest+json"
            return resp
        return send_from_directory(STATIC_DIR, filename, max_age=0, conditional=True)

    # ------------------------------------------------------------------ API : navigation
    @app.route("/api/browse")
    @app.route("/api/browse/<int:node_id>")
    def api_browse(node_id: Optional[int] = None):
        if node_id is None:
            folder = lib.root_node()
            if not folder:
                return jsonify({"folder": None, "breadcrumb": [], "children": [], "empty": True,
                                "scan": lib.status})
        else:
            folder = get_node(node_id, "folder")
        return jsonify(folder_payload(folder, current_profile()))

    @app.route("/api/item/<int:node_id>")
    def api_item(node_id: int):
        node = ensure_pages(heal(get_node(node_id, "album")))
        if node.get("page_count") and comics.has_fallback_cover(node["id"]):
            # couverture de secours (la vraie page était illisible) : on retente, elle l'est peut-être devenue
            try:
                comics.inspect(node, lib.abs_path(node["path"]), make_cover=True, force=True)
                if not comics.has_fallback_cover(node["id"]):
                    lib.set_color(node["id"], comics.cover_color(node, lib.abs_path(node["path"])))
                    log.info("Vraie couverture retrouvée pour %s", node["path"])
            except AlbumError:
                pass
        prev_, next_ = lib.siblings(node)
        j = album_json(node, with_progress=False)
        j["progress"] = progress_json(lib.progress(node_id, current_profile()))
        j["breadcrumb"] = lib.breadcrumb(node)[:-1]
        j["prev"], j["next"] = prev_, next_
        j["meta"] = meta_json(lib.bdt_album(node_id))
        j["lists"] = lib.list_membership(node_id, current_profile())
        if node.get("parent_id"):
            link = lib.bdt_series_get(node["parent_id"])
            if link:
                j["series"] = {"title": link["title"], "url": link["url"], "status": link["status"]}
        return jsonify(j)

    @app.route("/api/cover/<int:node_id>")
    def api_cover(node_id: int):
        node = get_node(node_id)
        if node["kind"] == "folder":
            if not node.get("cover_id"):
                abort(404, description="Dossier sans album")
            node = get_node(node["cover_id"], "album")
        try:
            width = request.args.get("w", 0, type=int)
            path = comics.cover_sized(node, lib.abs_path(node["path"]), width) if width else \
                comics.cover(node, lib.abs_path(node["path"]))
        except AlbumError as e:
            if not node.get("page_count") and not node.get("error"):
                lib.set_pages(node["id"], None, str(e))
            abort(415, description=str(e))
        resp = send_file(path, mimetype="image/jpeg", conditional=True)
        return cache_headers(resp, immutable="v" in request.args)

    panels_sem = threading.BoundedSemaphore(2)

    @app.route("/api/panels/<int:node_id>/<int:index>")
    def api_panels(node_id: int, index: int):
        """Cases de la planche (détectées une fois, puis gardées en base) pour la lecture case par case."""
        node = get_node(node_id, "album")
        cached = lib.panels_get(node_id, index)
        if cached is not None and cached.get("v") == PANELS_VERSION:
            return jsonify(cached)
        try:
            # une version de la page déjà en cache (celle que le lecteur vient d'afficher) évite une conversion de plus
            path, data = comics.cached_page_at_least(node, index, PANELS_WIDTH), None
            if path is None:
                path, data, _ = comics.page(node, lib.abs_path(node["path"]), index, PANELS_WIDTH)
            with Image.open(path or io.BytesIO(data)) as im:
                im.load()
                with panels_sem:   # deux détections à la fois au plus : les autres requêtes (pages, interface) gardent des fils
                    result = detect_panels(im)
        except AlbumError as e:
            abort(415, description=str(e))
        except Exception as e:  # noqa: BLE001
            log.warning("Détection des cases %s p.%d : %s", node["path"], index, e)
            result = {"panels": [], "rtl": [], "v": PANELS_VERSION}
        lib.panels_set(node_id, index, result)
        return jsonify(result)

    @app.route("/api/page/<int:node_id>/<int:index>")
    def api_page(node_id: int, index: int):
        node = get_node(node_id, "album")
        width = pick_width(request.args.get("w", 1200, type=int))
        try:
            path, data, mime = comics.page(node, lib.abs_path(node["path"]), index, width)
        except AlbumError as e:
            fresh = heal(node)   # fichier renommé ou déplacé pendant la lecture : on le retrouve et on réessaie
            if fresh["path"] == node["path"]:
                abort(415, description=str(e))
            try:
                path, data, mime = comics.page(fresh, lib.abs_path(fresh["path"]), index, width)
            except AlbumError as e2:
                abort(415, description=str(e2))
        resp = send_file(path, mimetype=mime, conditional=True) if path else Response(data, mimetype=mime)
        return cache_headers(resp, immutable="v" in request.args)

    # ------------------------------------------------------------------ API : progression
    @app.route("/api/progress/<int:node_id>", methods=["GET"])
    def api_progress_get(node_id: int):
        get_node(node_id, "album")
        return jsonify(progress_json(lib.progress(node_id, current_profile())))

    @app.route("/api/progress/<int:node_id>", methods=["PUT", "POST"])
    def api_progress_set(node_id: int):
        node = get_node(node_id, "album")
        body = request.get_json(force=True, silent=True) or {}
        completed = body.get("completed")
        if completed is not None:
            completed = bool(completed)
        if completed and not node.get("page_count"):
            node = ensure_pages(node)
        if "page" in body:
            page = body["page"]
        elif completed:
            page = (node.get("page_count") or 1) - 1
        else:
            abort(400, description="Il manque « page »")
        try:
            page = int(page)
        except (TypeError, ValueError):
            abort(400, description="« page » doit être un nombre")
        p = lib.set_progress(node_id, page, node.get("page_count"), completed, profile_id=current_profile(),
                             threshold=float(settings()["read_threshold"]))
        return jsonify(progress_json(p))

    @app.route("/api/progress/<int:node_id>", methods=["DELETE"])
    def api_progress_delete(node_id: int):
        get_node(node_id, "album")
        lib.clear_progress(node_id, current_profile())
        return jsonify(None)

    @app.route("/api/continue")
    def api_continue():
        return jsonify(with_folder(lib.continue_reading(limit=request.args.get("n", 20, type=int),
                                                        profile_id=current_profile())))

    @app.route("/api/recent")
    def api_recent():
        return jsonify(with_folder(lib.recent(limit=request.args.get("n", 24, type=int),
                                              profile_id=current_profile())))

    @app.route("/api/search")
    def api_search():
        q = (request.args.get("q") or "").strip()
        if len(q) < 2:
            return jsonify([])
        return jsonify(with_folder(lib.search(q, profile_id=current_profile())))

    # ------------------------------------------------------------------ API : réglages, profils, cache
    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        pid = current_profile()
        g = settings()
        g.pop("access_pin_hash", None)
        g["access_pin_set"] = bool(access_pin_hash())
        g.pop("adult_pin_hash", None)
        g["adult_pin_set"] = bool(adult_pin_hash())
        g["adult_unlocked"] = adult_unlocked()
        g["adult_count"] = len(adult_paths())
        if not adult_unlocked():
            g.pop("adult_paths", None)
        g["img_tag"] = f"{comics.cover_width}{comics.profile_tag}"
        return jsonify({"global": g, "profile": lib.get_settings(pid), "profile_id": pid, "role": current_role(),
                        "profile_selected": profile_selected(), "profiles": lib.profiles(), "version": VERSION,
                        "library_root": library_root,
                        "quality_profiles": {k: {"quality": v[0], "chroma": v[1]} for k, v in QUALITY_PROFILES.items()}})

    @app.route("/api/settings", methods=["PUT", "POST"])
    def api_settings_set():
        body = request.get_json(force=True, silent=True) or {}
        pid = current_profile()
        if isinstance(body.get("global"), dict):
            require_admin()
            g = dict(body["global"])
            if "access_pin" in g:
                pin = str(g.pop("access_pin") or "").strip()
                lib.set_settings({"access_pin_hash": hash_pin(pin) if pin else None}, None)
            if "adult_pin" in g:
                if adult_pin_hash() and not adult_unlocked():
                    abort(403, description="adult_locked")
                pin = str(g.pop("adult_pin") or "").strip()
                lib.set_settings({"adult_pin_hash": hash_pin(pin) if pin else None}, None)
            if ("adult_paths" in g or "adult_hide_tab" in g) and adult_pin_hash() and not adult_unlocked():
                abort(403, description="adult_locked")
            lib.set_settings(validate_global(g), None)
            apply_settings(settings())
            if "hd_min_px" in g:
                log.info("Seuil HD changé : %d px (albums reclassés sans remesurer)", hdcfg["min"])
            if g.get("quality_auto") is True:
                auto_measure()   # mesure automatique rallumée : on rattrape tout de suite les albums pas mesurés
        if isinstance(body.get("profile"), dict):
            lib.set_settings(validate_profile_settings(body["profile"]), pid)
        resp = make_response(api_settings_get())
        if isinstance(body.get("global"), dict) and "adult_pin" in body["global"]:
            stored = adult_pin_hash()
            if stored:
                resp.set_cookie("bulle_adult", signer.dumps({"adult": stored[-16:], "t": time.time()}), max_age=ADULT_TTL, samesite="Lax")
            else:
                resp.delete_cookie("bulle_adult")
        if isinstance(body.get("global"), dict) and "access_pin" in body["global"]:
            stored = access_pin_hash()
            if stored:
                resp.set_cookie("bulle_auth", signer.dumps({"auth": stored[-16:]}), max_age=10 * 365 * 24 * 3600,
                                samesite="Lax")
            else:
                resp.delete_cookie("bulle_auth")
        return resp

    # ------------------------------------------------------------------ API : rubrique Adulte
    @app.route("/api/adult")
    def api_adult():
        unlocked = adult_unlocked()
        out = {"pin_set": bool(adult_pin_hash()), "unlocked": unlocked, "count": len(adult_paths())}
        if unlocked:
            folders = []
            for p in adult_paths():
                node = lib.node_by_path(p)
                if node:
                    folders.append(album_json(node, with_progress=False))
            out["folders"] = folders
        return jsonify(out)

    @app.route("/api/adult/unlock", methods=["POST"])
    def api_adult_unlock():
        body = request.get_json(force=True, silent=True) or {}
        stored = adult_pin_hash()
        if stored and not check_pin(stored, str(body.get("pin") or "")):
            time.sleep(0.8)
            abort(403, description="Code incorrect")
        resp = make_response(jsonify({"unlocked": True}))
        if stored:
            resp.set_cookie("bulle_adult", signer.dumps({"adult": stored[-16:], "t": time.time()}), max_age=ADULT_TTL, samesite="Lax")
        return resp

    @app.route("/api/adult/lock", methods=["POST"])
    def api_adult_lock():
        resp = make_response(jsonify({"unlocked": False}))
        resp.delete_cookie("bulle_adult")
        return resp

    @app.route("/api/adult/folder", methods=["PUT"])
    def api_adult_folder():
        """Marque (ou démarque) un dossier comme faisant partie de la rubrique Adulte."""
        require_admin()
        if adult_pin_hash() and not adult_unlocked():
            abort(403, description="adult_locked")
        body = request.get_json(force=True, silent=True) or {}
        folder = get_node(int(body.get("folder_id", 0)), "folder", allow_hidden=True)
        paths = [p for p in adult_paths() if p != folder["path"].strip("/")]
        if body.get("adult"):
            paths.append(folder["path"].strip("/"))
        lib.set_settings({"adult_paths": paths}, None)
        flask_g._adult_paths = None
        return jsonify({"adult": bool(body.get("adult")), "count": len(paths)})

    # ------------------------------------------------------------------ API : couvertures, par série ou par album
    @app.route("/api/covers/rebuild/folder/<int:folder_id>", methods=["POST"])
    def api_covers_rebuild_folder(folder_id: int):
        """Rescanne une série sur le disque, en tâche de fond : les fichiers ajoutés (ou remis) apparaissent, ceux
        jetés disparaissent, puis les couvertures (et la couleur) de tous ses albums sont refaites."""
        require_admin()
        folder = get_node(folder_id, "folder")
        if lib.status["running"]:
            return jsonify(lib.status), 409
        path, name = folder["path"], folder["name"] or "la bibliothèque"
        before = len(lib.albums_under(path))

        def job() -> None:
            try:
                lib.scan(under=path)
            except RuntimeError as e:   # scan déjà en cours, ou arrêté avec « Arrêter »
                log.warning("%s", e)
                return
            except Exception:  # noqa: BLE001
                return
            todo = []
            for n in lib.albums_under(path):
                fresh = lib.refresh_file(n["id"])   # relit taille, date et format sur le disque (rattrape les ratés)
                if fresh:
                    comics.invalidate([n["id"]])
                    todo.append(fresh)
            run_background(lambda: preload_albums(todo, f"Rescan de {name}", force=True))

        threading.Thread(target=job, name="bulle-rescan", daemon=True).start()
        time.sleep(0.2)
        return jsonify({"count": before, "scan": lib.status}), 202

    @app.route("/api/covers/page/<int:node_id>", methods=["POST"])
    def api_covers_page(node_id: int):
        """Choisit la page qui sert de couverture (depuis le lecteur) ; {"page": null} revient à la première page.
        Rien n'est écrit dans le fichier : le choix est gardé dans la base de Bulle."""
        require_admin()
        node = get_node(node_id, "album")
        body = request.get_json(force=True, silent=True) or {}
        page = body.get("page")
        if page is not None:
            try:
                page = int(page)
            except (TypeError, ValueError):
                abort(400, description="Numéro de page invalide")
            if page < 0 or (node.get("page_count") and page >= node["page_count"]):
                abort(400, description="Cette page n'existe pas dans l'album")
            if page == 0:
                page = None
        lib.set_cover_page(node["id"], page)
        node = lib.node(node["id"])
        try:
            comics.inspect(node, lib.abs_path(node["path"]), make_cover=True, force=True)
            lib.set_color(node["id"], comics.cover_color(node, lib.abs_path(node["path"])))
        except AlbumError as e:
            abort(415, description=str(e))
        return jsonify(album_json(lib.node(node["id"]), with_progress=False))

    @app.route("/api/covers/retry-errors", methods=["POST"])
    def api_covers_retry_errors():
        """Réessaie tous les albums en échec, en tâche de fond (après une correction, ou un disque réseau revenu)."""
        require_admin()
        if lib.status["running"]:
            return jsonify(lib.status), 409
        todo = [f for f in (lib.refresh_file(n["id"]) for n in lib.albums_without("error IS NOT NULL")) if f]
        threading.Thread(target=lambda: run_background(lambda: preload_albums(todo, "Albums en échec réessayés", force=True)),
                         name="bulle-covers", daemon=True).start()
        time.sleep(0.2)
        return jsonify({"count": len(todo), "scan": lib.status}), 202

    @app.route("/api/covers/retry/<int:node_id>", methods=["POST"])
    def api_covers_retry(node_id: int):
        """Réessaie un album en échec (ou refait sa couverture) tout de suite."""
        node = get_node(node_id, "album")
        comics.invalidate([node["id"]])
        fresh = lib.refresh_file(node["id"])   # taille, date et vrai format relus sur le disque
        if fresh is None:
            abort(404, description="Fichier introuvable sur le disque (déplacé ou supprimé) : lancez un scan")
        node = ensure_pages(fresh)
        return jsonify(album_json(node, with_progress=False))

    @app.route("/api/auth/status")
    def api_auth_status():
        return jsonify({"required": bool(access_pin_hash()), "ok": auth_ok()})

    @app.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        body = request.get_json(force=True, silent=True) or {}
        stored = access_pin_hash()
        if stored and not check_pin(stored, str(body.get("pin") or "")):
            time.sleep(0.8)  # freine les essais en rafale
            abort(403, description="Code d'accès incorrect")
        resp = make_response(jsonify({"ok": True}))
        if stored:
            resp.set_cookie("bulle_auth", signer.dumps({"auth": stored[-16:]}), max_age=10 * 365 * 24 * 3600,
                            samesite="Lax")
        return resp

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        resp = make_response(jsonify({"ok": True}))
        resp.delete_cookie("bulle_auth")
        resp.delete_cookie("bulle_profile")
        return resp

    @app.route("/api/profiles", methods=["GET"])
    def api_profiles():
        return jsonify({"profiles": lib.profiles(), "current": current_profile(), "selected": profile_selected(),
                        "require_profile": bool(settings()["require_profile"])})

    def profile_json(p: dict) -> dict:
        return {"id": p["id"], "name": p["name"], "avatar": p.get("avatar"), "role": p.get("role") or "reader",
                "has_pin": bool(p.get("pin_hash"))}

    def clean_avatar(val) -> Optional[str]:
        """Vignette : quelques caractères (emoji, initiales) ou une petite image (data:image/…, ≤ 60 Ko, réduite côté
        navigateur)."""
        v = str(val or "").strip()
        if not v:
            return None
        if v.startswith("data:image/"):
            if len(v) > 60_000 or ";base64," not in v[:40]:
                abort(400, description="Image de profil trop lourde")
            return v
        return v[:8]

    @app.route("/api/profiles", methods=["POST"])
    def api_profile_create():
        body = request.get_json(force=True, silent=True) or {}
        if len(lib.profiles()) > 1 or settings()["require_profile"]:
            require_admin()   # la toute première création (profil « Moi » seul, sans mire) reste libre
        name = str(body.get("name") or "").strip()[:40]
        if not name:
            abort(400, description="Il faut un nom")
        if len(lib.profiles()) >= 20:
            abort(400, description="Trop de profils")
        pin = str(body.get("pin") or "").strip()
        role = "admin" if body.get("role") == "admin" and is_admin() else "reader"
        p = lib.add_profile(name, hash_pin(pin) if pin else None, clean_avatar(body.get("avatar")), role)
        return jsonify(profile_json(p))

    @app.route("/api/profiles/<int:pid>", methods=["PUT"])
    def api_profile_update(pid: int):
        p = lib.profile(pid)
        if not p:
            abort(404, description="Profil inconnu")
        body = request.get_json(force=True, silent=True) or {}
        if pid != current_profile():
            require_admin()   # son propre compte : libre ; celui des autres : administrateur
        fields = {}
        if "name" in body:
            fields["name"] = str(body["name"] or "").strip()[:40] or p["name"]
        if "avatar" in body:
            fields["avatar"] = clean_avatar(body["avatar"])
        if "pin" in body:
            pin = str(body["pin"] or "").strip()
            if pin and len(pin) < 4:
                abort(400, description="Mot de passe trop court (4 caractères au moins)")
            fields["pin_hash"] = hash_pin(pin) if pin else None
        if "role" in body:
            require_admin()
            role = "admin" if body["role"] == "admin" else "reader"
            if role != "admin" and p.get("role") == "admin" and \
                    not lib.conn.execute("SELECT 1 FROM profiles WHERE role='admin' AND id<>?", (pid,)).fetchone():
                abort(400, description="Il faut garder au moins un administrateur")
            fields["role"] = role
        p = lib.update_profile(pid, **fields)
        return jsonify(profile_json(p))

    @app.route("/api/profiles/<int:pid>", methods=["DELETE"])
    def api_profile_delete(pid: int):
        require_admin()
        if pid == DEFAULT_PROFILE:
            abort(400, description="Le premier profil ne peut pas être supprimé")
        if not lib.delete_profile(pid):
            abort(404, description="Profil inconnu")
        resp = make_response(jsonify(None))
        if current_profile() == pid:
            resp.delete_cookie("bulle_profile")
        return resp

    @app.route("/api/profiles/select", methods=["POST"])
    def api_profile_select():
        body = request.get_json(force=True, silent=True) or {}
        try:
            pid = int(body.get("id", DEFAULT_PROFILE))
        except (TypeError, ValueError):
            abort(400, description="Profil invalide")
        p = lib.profile(pid)
        if not p:
            abort(404, description="Profil inconnu")
        if p.get("pin_hash") and not check_pin(p["pin_hash"], str(body.get("pin") or "")):
            time.sleep(0.8)
            abort(403, description="Code PIN incorrect")
        resp = make_response(jsonify({"current": pid, "name": p["name"], "role": p.get("role") or "reader"}))
        resp.set_cookie("bulle_profile", signer.dumps({"p": pid}), max_age=10 * 365 * 24 * 3600, samesite="Lax")
        return resp

    @app.route("/api/profiles/logout", methods=["POST"])
    def api_profile_logout():
        """Se déconnecter : on revient à l'écran « qui lit ? » (la rubrique Adulte est reverrouillée aussi)."""
        resp = make_response(jsonify({"ok": True}))
        resp.delete_cookie("bulle_profile")
        resp.delete_cookie("bulle_adult")
        return resp

    @app.route("/api/cache", methods=["GET"])
    def api_cache():
        return jsonify(comics.cache_size())

    @app.route("/api/cache/clear", methods=["POST"])
    def api_cache_clear():
        require_admin()
        n = comics.clear_pages()
        return jsonify({"cleared": n, "cache": comics.cache_size()})

    @app.route("/api/covers/rebuild", methods=["POST"])
    def api_covers_rebuild():
        require_admin()
        if lib.status["running"]:
            return jsonify(lib.status), 409
        comics.clear_covers()
        threading.Thread(target=lambda: run_background(preload_missing_covers), name="bulle-covers",
                         daemon=True).start()
        time.sleep(0.2)
        return jsonify(lib.status), 202

    # ------------------------------------------------------------------ API : qualité (HD / SD)
    quality_job = {"running": False, "done": 0, "total": 0, "hd": 0, "sd": 0, "na": 0, "errors": 0,
                   "started_at": None, "finished_at": None, "stop": False, "reason": None}
    quality_lock = threading.Lock()

    REASONS = {"auto": "automatique, après le scan", "manual": "à la demande", "remeasure": "tout remesurer"}

    def fmt_eta(sec: float) -> str:
        sec = int(max(0, sec))
        return f"{sec // 3600} h {sec % 3600 // 60:02d}" if sec >= 3600 else f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"

    def measure_job(todo: list[dict], reason: str = "manual") -> None:
        if not quality_lock.acquire(blocking=False):
            return
        quality_job.update(running=True, done=0, total=len(todo), hd=0, sd=0, na=0, errors=0,
                           started_at=time.time(), finished_at=None, stop=False, reason=reason, current=None)
        total, t0 = len(todo), time.time()
        log.info("Mesure HD/SD : début (%s) — %d albums à mesurer, seuil HD %d px, lecture seule",
                 REASONS.get(reason, reason), total, hdcfg["min"])
        last_report, failures = t0, []
        try:
            for n in todo:
                if quality_job["stop"]:
                    log.info("Mesure HD/SD : arrêtée à la demande après %d albums sur %d", quality_job["done"], total)
                    break
                quality_job["current"] = n.get("name") or n["path"]
                t1 = time.time()
                try:
                    w, h = comics.measure(n, lib.abs_path(n["path"]))
                    lib.set_resolution(n["id"], w, h)
                    key = "na" if not w else "hd" if max(w, h) >= hdcfg["min"] else "sd"
                    quality_job[key] += 1
                    log.debug("Mesure HD/SD : %s → %s (%d × %d) en %.2f s", n["path"], key.upper(), w, h, time.time() - t1)
                except AlbumError as e:
                    # illisible : noté « pas mesurable » (0 × 0) pour ne pas le retenter à chaque scan ; remis à zéro
                    # si le fichier change, et « Tout remesurer » le retente
                    lib.set_resolution(n["id"], 0, 0)
                    quality_job["errors"] += 1
                    failures.append(n["path"])
                    log.warning("Mesure HD/SD : %s illisible, noté « pas mesurable » : %s", n["path"], e)
                except Exception:  # noqa: BLE001
                    quality_job["errors"] += 1
                    failures.append(n["path"])
                    log.exception("Mesure HD/SD : erreur inattendue sur %s", n["path"])
                quality_job["done"] += 1
                done = quality_job["done"]
                if time.time() - last_report >= 20 or done % 250 == 0:
                    last_report = time.time()
                    el = time.time() - t0
                    rate = done / el if el > 0 else 0
                    log.info("Mesure HD/SD : %d / %d (%d %%) — %d HD, %d SD, %d illisibles — %.1f albums/s, reste ≈ %s",
                             done, total, done * 100 // max(1, total), quality_job["hd"], quality_job["sd"],
                             quality_job["errors"], rate, fmt_eta((total - done) / rate) if rate else "?")
            el = time.time() - t0
            log.info("Mesure HD/SD : terminée — %d albums en %s (%.1f/s) : %d HD, %d SD, %d PDF ou non mesurables, %d illisibles",
                     quality_job["done"], fmt_eta(el), quality_job["done"] / el if el > 0 else 0, quality_job["hd"],
                     quality_job["sd"], quality_job["na"], quality_job["errors"])
            if failures:
                log.info("Mesure HD/SD : albums illisibles (%d) : %s%s", len(failures), " | ".join(failures[:10]),
                         f" … et {len(failures) - 10} autres" if len(failures) > 10 else "")
            st = lib.quality_stats(hdcfg["min"])
            log.info("Mesure HD/SD : bibliothèque — %d HD, %d SD, %d à mesurer, %d non mesurables", st["hd"], st["sd"], st["todo"], st["na"])
        finally:
            quality_job.update(running=False, finished_at=time.time(), stop=False, current=None)
            quality_lock.release()

    def start_measure(todo: list[dict], reason: str) -> bool:
        if quality_job["running"] or not todo:
            return False
        threading.Thread(target=measure_job, args=(todo, reason), name="bulle-quality", daemon=True).start()
        return True

    def auto_measure() -> None:
        """Après un scan : albums lisibles pas encore mesurés (nouveaux, modifiés, ou tout le stock la première fois)."""
        if not settings().get("quality_auto", True):
            return
        todo = [n for n in lib.albums_for_measure() if not n.get("error")]
        if not todo:
            log.debug("Mesure HD/SD : rien de nouveau à mesurer")
        elif not start_measure(todo, "auto"):
            log.info("Mesure HD/SD : déjà en cours, les %d nouveaux albums attendront la prochaine fois", len(todo))

    @app.route("/api/quality", methods=["GET"])
    def api_quality_status():
        return jsonify({"job": quality_job, "stats": lib.quality_stats(hdcfg["min"]), "hd_min": hdcfg["min"],
                        "auto": bool(settings().get("quality_auto", True))})

    @app.route("/api/quality/measure", methods=["POST"])
    def api_quality_measure():
        """Mesure la taille des pages : {"ids": [...]} ou {"limit": 500} (premiers albums de la bibliothèque) ;
        "remeasure": true pour refaire ceux déjà mesurés. Lecture seule : les fichiers ne sont jamais modifiés."""
        require_admin()
        if quality_job["running"]:
            return jsonify({"job": quality_job}), 409
        body = request.get_json(silent=True) or {}
        ids = [int(i) for i in body.get("ids") or [] if str(i).isdigit()]
        limit = body.get("limit")
        limit = int(limit) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else None
        todo = lib.albums_for_measure(ids or None, limit, bool(body.get("remeasure")))
        start_measure(todo, "remeasure" if body.get("remeasure") else "manual")
        time.sleep(0.1)
        return jsonify({"job": quality_job, "stats": lib.quality_stats(hdcfg["min"])}), 202

    @app.route("/api/quality/stop", methods=["POST"])
    def api_quality_stop():
        require_admin()
        if quality_job["running"]:
            quality_job["stop"] = True
        return jsonify({"job": quality_job})

    @app.route("/api/stats")
    def api_stats():
        s = lib.stats(current_profile())
        s["scan"] = lib.status
        s["version"] = VERSION
        s["library_root"] = library_root
        s["img_tag"] = f"{comics.cover_width}{comics.profile_tag}"
        return jsonify(s)

    @app.route("/api/scan", methods=["GET"])
    def api_scan_status():
        return jsonify(lib.status)

    @app.route("/api/scan", methods=["POST"])
    def api_scan_start():
        require_admin()
        if lib.status["running"]:
            return jsonify(lib.status), 409
        start_scan_thread()
        time.sleep(0.2)
        return jsonify(lib.status), 202

    @app.route("/api/ignore/<int:node_id>", methods=["POST"])
    def api_ignore(node_id: int):
        """Retire un album ou un dossier de Bulle (le fichier reste sur le disque, les scans l'ignorent)."""
        require_admin()
        node = get_node(node_id)
        if not node.get("path"):
            abort(400, description="La bibliothèque entière ne peut pas être retirée")
        if lib.status["running"]:
            abort(409, description="Un scan est en cours : réessayez quand il est fini")
        res = lib.ignore_node(node_id)
        res.pop("ids", None)
        res["parent_id"] = node.get("parent_id")
        return jsonify(res)

    @app.route("/api/ignored", methods=["GET"])
    def api_ignored():
        return jsonify(sorted(lib.ignored_paths()))

    @app.route("/api/ignored", methods=["DELETE"])
    def api_unignore():
        """Remet un chemin retiré ; un scan est lancé pour le faire réapparaître."""
        require_admin()
        body = request.get_json(force=True, silent=True) or {}
        path = str(body.get("path") or "").strip("/")
        paths = lib.unignore_path(path)
        if lib.status["running"]:
            pending_scan.set()   # un scan tourne déjà : on en relance un dès qu'il est fini
        else:
            start_scan_thread(path.rsplit("/", 1)[0] if "/" in path else None)
        return jsonify(paths)

    @app.route("/api/scan/stop", methods=["POST"])
    def api_scan_stop():
        """Arrête le scan (la base reste comme avant) ou la génération des couvertures en cours (celles déjà faites
        restent, les autres seront faites à l'ouverture des albums ou au prochain scan)."""
        require_admin()
        if lib.status["running"]:
            lib.stop_requested.set()
        return jsonify(lib.status)

    @app.route("/api/download/<int:node_id>")
    def api_download(node_id: int):
        node = get_node(node_id, "album")
        path = lib.abs_path(node["path"])
        if not os.path.isfile(path):
            abort(404, description="Fichier introuvable")
        return send_file(path, as_attachment=True, download_name=os.path.basename(path), conditional=True)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(415)
    @app.errorhandler(502)
    def api_error(e):
        if request.path.startswith("/api/"):
            desc = getattr(e, "description", str(e))
            if desc == "adult_locked":
                return jsonify({"error": "Rubrique Adulte verrouillée : entrez le code", "adult_locked": True}), 403
            if desc == "admin_required":
                return jsonify({"error": "Réservé à l'administrateur de Bulle", "admin_required": True}), 403
            return jsonify({"error": desc}), e.code
        if request.path.startswith("/static/") or request.path.startswith("/opds"):
            return e
        return error_page(e), e.code

    def error_page(e) -> str:
        """Page d'erreur aux couleurs de Bulle (au lieu de la page nue de Flask) : l'adresse demandée est affichée pour
        comprendre d'où vient le lien cassé, avec un bouton vers l'accueil."""
        from markupsafe import escape
        titles = {404: "Page introuvable", 403: "Accès refusé", 400: "Demande incorrecte", 409: "Déjà en cours"}
        title = titles.get(e.code, f"Erreur {e.code}")
        desc = getattr(e, "description", "") or ""
        if e.code == 404:
            desc = "Cette adresse ne correspond à rien dans Bulle. Si vous arrivez d'un lien ou d'une icône, il pointe peut-être vers une adresse d'une ancienne version."
        return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Bulle</title><link rel="stylesheet" href="/static/style.css?v={VERSION}">
<style>.errpage{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
.errbox{{max-width:560px;width:100%;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px 26px}}
.errbox h1{{margin:0 0 8px;font-size:26px}}.errbox code{{display:block;word-break:break-all;background:var(--bg-2);padding:8px 10px;border-radius:8px;margin:12px 0}}
.errbox .btn{{display:inline-block;margin-top:10px}}</style></head>
<body><div class="errpage"><div class="errbox"><h1>{title}</h1><p class="muted">{escape(desc)}</p>
<small class="muted">Adresse demandée</small><code>{escape(request.url)}</code>
<a class="btn" href="/">← Retour à l'accueil</a> <small class="muted" style="margin-left:10px">Bulle v{VERSION}</small></div></div></body></html>"""

    # ------------------------------------------------------------------ API : listes, favoris, historique, hasard
    def list_json(l: dict) -> dict:
        return {"id": l["id"], "name": l["name"], "kind": l["kind"], "count": l.get("count", 0)}

    @app.route("/api/lists", methods=["GET"])
    def api_lists():
        return jsonify([list_json(l) for l in lib.lists(current_profile())])

    @app.route("/api/lists", methods=["POST"])
    def api_list_create():
        body = request.get_json(force=True, silent=True) or {}
        name = str(body.get("name") or "").strip()[:60]
        if not name:
            abort(400, description="Il faut un nom de liste")
        l = lib.list_create(current_profile(), name)
        return jsonify(list_json(l))

    @app.route("/api/lists/<int:list_id>", methods=["GET"])
    def api_list_get(list_id: int):
        pid = current_profile()
        l = lib.list_get(list_id, pid)
        if not l:
            abort(404, description="Liste inconnue")
        items = []
        for n in visible(lib.list_items(list_id, pid)):
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
            j["list_added"] = n.get("list_added")
            if n["kind"] == "folder":
                j["album_count"] = n.get("album_count", 0)
            items.append(j)
        return jsonify({"list": list_json(l), "items": items})

    @app.route("/api/lists/<int:list_id>", methods=["PUT"])
    def api_list_rename(list_id: int):
        pid = current_profile()
        if not lib.list_get(list_id, pid):
            abort(404, description="Liste inconnue")
        body = request.get_json(force=True, silent=True) or {}
        name = str(body.get("name") or "").strip()[:60]
        if not name:
            abort(400, description="Il faut un nom de liste")
        lib.list_rename(list_id, pid, name)
        return jsonify(list_json(lib.list_get(list_id, pid)))

    @app.route("/api/lists/<int:list_id>", methods=["DELETE"])
    def api_list_delete(list_id: int):
        if not lib.list_delete(list_id, current_profile()):
            abort(400, description="Cette liste ne peut pas être supprimée")
        return jsonify(None)

    @app.route("/api/lists/<int:list_id>/items", methods=["POST"])
    def api_list_add(list_id: int):
        pid = current_profile()
        if not lib.list_get(list_id, pid):
            abort(404, description="Liste inconnue")
        body = request.get_json(force=True, silent=True) or {}
        node = get_node(int(body.get("node_id", 0)))
        lib.list_add(list_id, node["id"])
        return jsonify({"lists": lib.list_membership(node["id"], pid)})

    @app.route("/api/lists/<int:list_id>/items/<int:node_id>", methods=["DELETE"])
    def api_list_remove(list_id: int, node_id: int):
        pid = current_profile()
        if not lib.list_get(list_id, pid):
            abort(404, description="Liste inconnue")
        lib.list_remove(list_id, node_id)
        return jsonify({"lists": lib.list_membership(node_id, pid)})

    @app.route("/api/favorites/toggle", methods=["POST"])
    def api_fav_toggle():
        pid = current_profile()
        body = request.get_json(force=True, silent=True) or {}
        node = get_node(int(body.get("node_id", 0)))
        fav = next(l for l in lib.lists(pid) if l["kind"] == "favorites")
        if node["id"] in lib.favorites_ids(pid):
            lib.list_remove(fav["id"], node["id"])
            return jsonify({"fav": False})
        lib.list_add(fav["id"], node["id"])
        return jsonify({"fav": True})

    @app.route("/api/history")
    def api_history():
        return jsonify(with_folder(lib.history(current_profile(), limit=request.args.get("n", 60, type=int))))

    @app.route("/api/history/reading")
    def api_history_reading():
        return jsonify(with_folder(lib.reading_now(current_profile(), limit=request.args.get("n", 60, type=int))))

    @app.route("/api/activity")
    def api_activity():
        """Chiffres de lecture du profil courant ; l'administrateur voit aussi le résumé de tous les comptes."""
        out = lib.activity(current_profile())
        if is_admin():
            out["profiles"] = lib.activity_by_profile(30)
        return jsonify(out)

    @app.route("/api/covers/sample")
    def api_covers_sample():
        """Couvertures au hasard pour la mosaïque de fond (seulement celles déjà générées : pas de travail serveur)."""
        n = request.args.get("n", 60, type=int)
        rows = lib.random_covers(n * 2)
        if adult_paths() and not adult_unlocked():
            rows = [r for r in rows if not is_adult_path(r["path"])]
        out = [{"id": r["id"], "mtime": int(r["mtime"] or 0)} for r in rows if os.path.exists(comics.cover_path(r))][:n]
        return jsonify(out)

    @app.route("/api/random")
    def api_random():
        n = None
        for _ in range(12):   # au hasard, mais jamais un album de la rubrique Adulte verrouillée
            n = lib.random_album(unread_only=request.args.get("unread", "1") != "0", profile_id=current_profile())
            if not n or not hidden(n):
                break
            n = None
        if not n:
            abort(404, description="Aucun album")
        j = album_json(n)
        crumbs = lib.breadcrumb(n)
        j["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
        return jsonify(j)

    # ------------------------------------------------------------------ OPDS
    def opds_base() -> str:
        return request.host_url.rstrip("/")

    def opds_response(xml: bytes, kind: str = opds.ACQ) -> Response:
        resp = Response(xml)
        resp.headers["Content-Type"] = kind + "; charset=utf-8"
        return resp

    def opds_check() -> None:
        if not settings()["opds_enabled"]:
            abort(404, description="Flux OPDS désactivé dans les réglages")

    def opds_enrich(albums: list[dict]) -> list[dict]:
        pid = current_profile()
        out = []
        for n in albums:
            d = dict(n)
            crumbs = lib.breadcrumb(n)
            d["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
            if "p_page" in n and n.get("p_page") is not None:
                d["progress"] = {"page": n["p_page"], "completed": bool(n.get("p_completed"))}
            m = lib.bdt_album(n["id"])
            d["meta"] = meta_json(m) if m else None
            out.append(d)
        return out

    @app.route("/opds")
    @app.route("/opds/")
    def opds_root():
        opds_check()
        root = lib.root_node()
        return opds_response(opds.root_feed(opds_base(), root["id"] if root else None, lib.stats()), opds.NAV)

    @app.route("/opds/opensearch.xml")
    def opds_opensearch():
        opds_check()
        return Response(opds.opensearch(opds_base()), mimetype="application/opensearchdescription+xml")

    @app.route("/opds/folder/<int:node_id>")
    def opds_folder(node_id: int):
        opds_check()
        folder = get_node(node_id, "folder")
        children = visible(lib.children(node_id))
        pid = current_profile()
        prog = {p["node_id"]: {"page": p["page"], "completed": bool(p["completed"])} for p in lib.all_progress(pid)}
        metas = {k: meta_json(v) for k, v in lib.bdt_albums_for_folder(node_id).items()}
        page = max(1, request.args.get("page", 1, type=int))
        return opds_response(opds.folder_feed(opds_base(), folder, children, metas, prog, page))

    @app.route("/opds/continue")
    def opds_continue():
        opds_check()
        albums = opds_enrich(visible(lib.continue_reading(limit=100, profile_id=current_profile())))
        return opds_response(opds.list_feed(opds_base(), "Reprendre la lecture", "/opds/continue", albums))

    @app.route("/opds/recent")
    def opds_recent():
        opds_check()
        albums = opds_enrich(visible(lib.recent(limit=100, profile_id=current_profile())))
        return opds_response(opds.list_feed(opds_base(), "Ajouts récents", "/opds/recent", albums))

    @app.route("/opds/search")
    def opds_search():
        opds_check()
        q = (request.args.get("q") or "").strip()
        albums = opds_enrich([n for n in visible(lib.search(q, limit=200, profile_id=current_profile())) if n["kind"] == "album"]) if len(q) >= 2 else []
        page = max(1, request.args.get("page", 1, type=int))
        return opds_response(opds.list_feed(opds_base(), f"Recherche : {q}", opds.search_href(q), albums, page))

    # ------------------------------------------------------------------ API : Bédéthèque
    def bdt_check_enabled() -> None:
        if not settings()["bdt_enabled"]:
            abort(409, description="Les requêtes vers Bédéthèque sont désactivées dans les réglages")

    def bdt_index_for(query: str, force: bool = False) -> Optional[list[dict]]:
        """Lignes de l'index alphabétique pour la lettre de la requête (téléchargé une fois par mois)."""
        letter = index_letter_for(query)
        age = lib.bdt_index_age(letter)
        if force or age is None or age > INDEX_TTL:
            rows = bdt.index_letter(letter, force=force)
            if not rows:
                raise BdtError(f"La page de l'index Bédéthèque pour la lettre {letter} est vide ou illisible")
            lib.bdt_index_store(letter, rows, norm_title)
        return lib.bdt_index_rows(letter)

    def bdt_search(query: str, hint_int: bool = False) -> list[dict]:
        """Recherche d'une série : index alphabétique d'abord, recherche du site en secours."""
        try:
            rows = bdt_index_for(query)
        except BdtError as e:
            log.warning("Index Bédéthèque indisponible (%s), recherche du site", e)
            rows = None
        if rows:
            res = bdt.search_index(query, rows, hint_int=hint_int)
            if res:
                return res
        return bdt.search_site(query)

    def analyze_folder(folder: dict, url: Optional[str] = None, details: bool = False, force: bool = False) -> dict:
        """Analyse d'un dossier : recherche (ou lien existant / adresse donnée), lecture de la série, comparaison."""
        children = lib.children(folder["id"])
        files = [{"id": c["id"], "name": c["name"]} for c in children if c["kind"] == "album"]
        kinds = [parse_album_name(f["name"])["kind"] for f in files]
        hint_int = bool(files) and sum(1 for k in kinds if k == "int") * 2 >= len(files)
        if not files:
            return {"status": "no_albums", "message": "Ce dossier ne contient pas d'albums directement "
                                                      "(analysez ses sous-dossiers)."}
        existing = lib.bdt_series_get(folder["id"])
        candidates: list[dict] = []
        score: Optional[float] = None
        manual = False
        if url:
            series = bdt.series(url, details=details, force=force)
            manual = True
        elif existing and not force:
            series = existing["data"]
            score, manual = existing.get("score"), bool(existing.get("manual"))
            if details and not existing.get("detailed"):
                series = bdt.series(series["url"], details=True)
        else:
            query = query_from_folder(folder["name"])
            if existing and existing.get("manual"):
                series = bdt.series(existing["url"], details=details or bool(existing.get("detailed")), force=True)
                manual = True
            else:
                candidates = bdt_search(query, hint_int)
                if not candidates and len(query.split()) > 2:
                    candidates = bdt_search(" ".join(query.split()[:2]), hint_int)
                if not candidates:
                    return {"status": "not_found", "query": query,
                            "message": f"Aucune série trouvée sur Bédéthèque pour « {query} »."}
                best = candidates[0]
                if best["score"] < 0.75:
                    return {"status": "ambiguous", "query": query, "candidates": candidates[:8],
                            "message": "Plusieurs séries possibles : choisissez la bonne."}
                score = best["score"]
                series = bdt.series(best["url"], details=details)
        cmp_ = compare(series, files)
        lib.bdt_series_set(folder["id"], series, score, manual, present=cmp_["present"], total=cmp_["total"])
        lib.bdt_albums_set(folder["id"], cmp_["matches"])
        link = lib.bdt_series_get(folder["id"])
        report = bdt_report(folder, link, children)
        report["status"] = "ok"
        report["candidates"] = [c for c in candidates[:6] if c["url"] != series["url"]]
        report["query"] = query_from_folder(folder["name"])
        return report

    @app.route("/api/bdt/status")
    def api_bdt_status():
        s = settings()
        return jsonify({"enabled": bool(s["bdt_enabled"]), "interval": max(float(s["bdt_interval"]), 60.0 / float(s["bdt_per_minute"])),
                        "pausing_until": bdt.pausing_until,
                        "requests_made": bdt.requests_made, "last_error": bdt.last_error, "job": bdt_job,
                        "linked": len(lib.bdt_series_all()), "candidates": len(lib.folders_with_albums()),
                        "index": lib.bdt_index_stats()})

    @app.route("/api/bdt/search")
    def api_bdt_search():
        bdt_check_enabled()
        q = (request.args.get("q") or "").strip()
        if len(q) < 2:
            return jsonify([])
        try:
            return jsonify(bdt_search(q)[:12])
        except BdtError as e:
            abort(502, description=str(e))

    @app.route("/api/bdt/debug")
    def api_bdt_debug():
        """Diagnostic : ce que Bédéthèque renvoie au serveur (index et recherche du site)."""
        bdt_check_enabled()
        q = (request.args.get("q") or "Blueberry").strip()
        out = {"query": q, "letter": index_letter_for(q), "index": lib.bdt_index_stats(), "user_agent": _bdt_mod.USER_AGENT}
        try:
            rows = bdt_index_for(q)
            out["index_rows"] = len(rows)
            out["index_hits"] = bdt.search_index(q, rows)[:5]
        except BdtError as e:
            out["index_error"] = str(e)
        try:
            out["site_hits"] = bdt.search_site(q)[:5]
        except BdtError as e:
            out["site_error"] = str(e)
        out["requests_made"], out["last_error"] = bdt.requests_made, bdt.last_error
        return jsonify(out)

    @app.route("/api/bdt/analyze/<int:folder_id>", methods=["POST"])
    def api_bdt_analyze(folder_id: int):
        require_admin()
        bdt_check_enabled()
        folder = get_node(folder_id, "folder")
        body = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify(analyze_folder(folder, url=(body.get("url") or "").strip() or None,
                                          details=bool(body.get("details")), force=bool(body.get("force"))))
        except BdtError as e:
            abort(502, description=str(e))

    @app.route("/api/bdt/series/<int:folder_id>", methods=["GET"])
    def api_bdt_series(folder_id: int):
        folder = get_node(folder_id, "folder")
        link = lib.bdt_series_get(folder_id)
        if not link:
            return jsonify(None)
        r = bdt_report(folder, link)
        r["status"] = "ok"
        return jsonify(r)

    @app.route("/api/bdt/series/<int:folder_id>", methods=["DELETE"])
    def api_bdt_series_delete(folder_id: int):
        require_admin()
        get_node(folder_id, "folder")
        lib.bdt_series_delete(folder_id)
        return jsonify(None)

    def fetch_summary(node_id: int, force: bool = False) -> Optional[dict]:
        """Résumé d'un album lié à Bédéthèque : lu sur la fiche de l'album, puis conservé dans la base."""
        m = lib.bdt_album(node_id)
        if not m or not m.get("url"):
            return None
        if not force and m["data"].get("summary_at"):
            return m
        text = bdt.album_summary(m["url"], force=force)
        lib.bdt_album_update(node_id, summary=text or "", summary_at=time.time())
        return lib.bdt_album(node_id)

    @app.route("/api/bdt/album/<int:node_id>/summary", methods=["GET"])
    def api_bdt_summary_get(node_id: int):
        get_node(node_id, "album")
        m = lib.bdt_album(node_id)
        return jsonify({"linked": bool(m and m.get("url")), "summary": (m or {}).get("data", {}).get("summary"),
                        "summary_at": (m or {}).get("data", {}).get("summary_at")})

    @app.route("/api/bdt/album/<int:node_id>/summary", methods=["POST"])
    def api_bdt_summary(node_id: int):
        """Va chercher le résumé (une requête vers la fiche de l'album, puis mise en cache)."""
        bdt_check_enabled()
        get_node(node_id, "album")
        body = request.get_json(force=True, silent=True) or {}
        try:
            m = fetch_summary(node_id, force=bool(body.get("force")))
        except BdtError as e:
            abort(502, description=str(e))
        if not m:
            abort(409, description="Cet album n'est pas encore lié à Bédéthèque : analysez d'abord sa série.")
        return jsonify({"linked": True, "summary": m["data"].get("summary"), "summary_at": m["data"].get("summary_at")})

    summary_job: dict = {"running": False, "done": 0, "total": 0, "folder": None, "folder_id": None,
                         "errors": [], "stop": False}

    @app.route("/api/bdt/summaries/<int:folder_id>", methods=["POST"])
    def api_bdt_summaries(folder_id: int):
        """Résumés de tous les albums liés d'un dossier, en tâche de fond (une requête par album)."""
        bdt_check_enabled()
        folder = get_node(folder_id, "folder")
        if summary_job["running"]:
            return jsonify(summary_job), 409
        metas = lib.bdt_albums_for_folder(folder_id)
        ids = [nid for nid, m in metas.items() if m.get("url") and not m["data"].get("summary_at")]
        summary_job.update(running=True, done=0, total=len(ids), folder=folder["name"], folder_id=folder_id,
                           errors=[], stop=False)

        def job():
            bdt.mark_background(True)
            try:
                for nid in ids:
                    if summary_job["stop"]:
                        break
                    try:
                        fetch_summary(nid)
                    except BdtError as e:
                        summary_job["errors"].append(str(e))
                        if "refuse" in str(e) or "vérification" in str(e):
                            break
                    except Exception as e:  # noqa: BLE001
                        log.exception("Résumé de l'album %s", nid)
                        summary_job["errors"].append(f"Erreur inattendue : {e}")
                    summary_job["done"] += 1
            finally:
                summary_job["running"] = False

        threading.Thread(target=job, name="bulle-summaries", daemon=True).start()
        time.sleep(0.2)
        return jsonify(summary_job), 202

    @app.route("/api/bdt/summaries", methods=["GET"])
    def api_bdt_summaries_status():
        return jsonify(summary_job)

    @app.route("/api/bdt/summaries", methods=["DELETE"])
    def api_bdt_summaries_stop():
        summary_job["stop"] = True
        return jsonify(summary_job)

    @app.route("/api/bdt/collection")
    def api_bdt_collection():
        rows = lib.bdt_series_all()
        linked_ids = {r["folder_id"] for r in rows}
        unlinked = [f for f in lib.folders_with_albums() if f["id"] not in linked_ids]
        return jsonify({"series": rows, "unlinked": [{"id": f["id"], "name": f["name"], "albums": f["direct"]}
                                                     for f in unlinked]})

    @app.route("/api/bdt/batch", methods=["GET"])
    def api_bdt_batch_status():
        return jsonify(bdt_job)

    @app.route("/api/bdt/batch", methods=["DELETE"])
    def api_bdt_batch_stop():
        require_admin()
        bdt_job["stop"] = True
        return jsonify(bdt_job)

    @app.route("/api/bdt/batch", methods=["POST"])
    def api_bdt_batch_start():
        require_admin()
        bdt_check_enabled()
        if bdt_job["running"]:
            return jsonify(bdt_job), 409
        body = request.get_json(force=True, silent=True) or {}
        ids = body.get("folder_ids")
        if not ids:
            linked = {r["folder_id"] for r in lib.bdt_series_all()}
            ids = [f["id"] for f in lib.folders_with_albums() if f["id"] not in linked]
        ids = [int(i) for i in ids][:2000]
        bdt_job.update(running=True, done=0, total=len(ids), current=None, errors=[], stop=False, linked=0,
                       ambiguous=0, not_found=0)

        def job():
            bdt.mark_background(True)
            try:
                for fid in ids:
                    if bdt_job["stop"]:
                        break
                    folder = lib.node(fid)
                    if not folder or folder["kind"] != "folder":
                        bdt_job["done"] += 1
                        continue
                    bdt_job["current"] = folder["name"]
                    try:
                        r = analyze_folder(folder, details=bool(body.get("details")))
                        if r.get("status") == "ok":
                            bdt_job["linked"] += 1
                        elif r.get("status") == "ambiguous":
                            bdt_job["ambiguous"] += 1
                        elif r.get("status") == "not_found":
                            bdt_job["not_found"] += 1
                    except BdtError as e:
                        bdt_job["errors"].append({"folder": folder["name"], "error": str(e)})
                        if "refuse" in str(e) or "vérification" in str(e):
                            break  # inutile d'insister si le site bloque
                    except Exception as e:  # noqa: BLE001
                        log.exception("Analyse Bédéthèque de %s", folder["name"])
                        bdt_job["errors"].append({"folder": folder["name"], "error": f"Erreur inattendue : {e}"})
                    bdt_job["done"] += 1
            finally:
                bdt_job["running"] = False
                bdt_job["current"] = None

        threading.Thread(target=job, name="bulle-bdt", daemon=True).start()
        time.sleep(0.2)
        return jsonify(bdt_job), 202

    # ------------------------------------------------------------------ tâches de fond
    def preload_albums(todo: list[dict], label: str, force: bool = False) -> None:
        """Ouvre chaque album une fois : nombre de pages + couverture, en parallèle (`force` : couverture refaite
        même si elle existe, à partir de la première page)."""
        lib.stop_requested.clear()
        lib.status.update(phase="covers", covers_total=len(todo), covers_done=0, stopped=False)
        t0 = time.time()
        counter_lock = threading.Lock()

        def one(n: dict) -> None:
            if lib.stop_requested.is_set():   # « Arrêter » : les albums pas encore commencés sont laissés pour plus tard
                return
            try:
                count = comics.inspect(n, lib.abs_path(n["path"]), make_cover=True, force=force)
                lib.set_pages(n["id"], count, None)
                lib.set_color(n["id"], comics.cover_color(n, lib.abs_path(n["path"])))
            except AlbumError as e:
                lib.set_pages(n["id"], None, str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("Couverture de %s", n["path"])
                lib.set_pages(n["id"], None, f"Erreur inattendue : {e}")
            with counter_lock:
                lib.status["covers_done"] += 1

        workers = int(settings()["preload_threads"])
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bulle-covers") as pool:
            for f in [pool.submit(one, n) for n in todo]:
                f.result()
        try:
            fixed = lib.fix_folder_covers()
            if fixed:
                log.info("Couvertures de dossiers corrigées : %d", fixed)
        except Exception:  # noqa: BLE001
            log.exception("Correction des couvertures de dossiers")
        if lib.stop_requested.is_set():
            lib.status["stopped"] = "covers"
            log.info("%s arrêté à la demande après %d albums", label, lib.status["covers_done"])
        lib.status.update(phase="idle")
        log.info("%s : %d albums traités en %.0f s", label, lib.status["covers_done"], time.time() - t0)

    def preload() -> None:
        preload_albums(lib.albums_without("page_count IS NULL AND error IS NULL"), "Couvertures")
        # couvertures de secours (vraie page illisible la dernière fois) : on retente à chaque scan
        ids = set()
        for f in glob.glob(os.path.join(comics.covers_dir, "*.fallback")):
            try:
                ids.add(int(os.path.basename(f).split(".")[0]))
            except ValueError:
                pass
        todo = [n for n in (lib.node(i) for i in ids) if n and n["kind"] == "album"]
        if todo and not lib.stop_requested.is_set():
            preload_albums(todo, "Couvertures de secours", force=True)

    def preload_thorough() -> None:
        """Scan minutieux : chaque album est rouvert (pages recomptées, erreurs réessayées) et sa couverture refaite."""
        preload_albums(lib.albums_without("1=1"), "Vérification minutieuse", force=True)

    def preload_missing_covers() -> None:
        todo = [n for n in lib.albums_without("error IS NULL") if not os.path.exists(comics.cover_path(n))]
        preload_albums(todo, "Couvertures régénérées")

    def preload_colors() -> None:
        """Bibliothèques créées avant la v0.6 : calcule la couleur des couvertures existantes."""
        todo = [n for n in lib.albums_without("color IS NULL AND error IS NULL AND page_count IS NOT NULL")
                if os.path.exists(comics.cover_path(n))]
        if not todo:
            return
        t0 = time.time()
        for n in todo:
            lib.set_color(n["id"], comics.cover_color(n, lib.abs_path(n["path"])) or "")
        log.info("Couleurs de %d couvertures calculées en %.0f s", len(todo), time.time() - t0)

    def trim_cache() -> None:
        gb = float(settings()["cache_max_gb"])
        if gb > 0:
            removed = comics.trim_pages(int(gb * 1e9))
            if removed:
                log.info("Cache des pages réduit : %d fichiers supprimés", removed)

    def run_background(fn) -> None:
        lib.status["running"] = True
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("Tâche de fond")
        finally:
            lib.status["running"] = False

    pending_scan = threading.Event()   # scan demandé pendant qu'un autre tournait

    def scan_job(under: Optional[str] = None) -> None:
        try:
            lib.scan(under=under)
        except RuntimeError as e:
            log.warning("%s", e)
            return
        except Exception:  # noqa: BLE001
            return
        mode = settings().get("scan_mode") or "normal"
        if mode == "thorough":
            run_background(preload_thorough)
        elif mode != "fast" and settings()["preload_covers"]:
            run_background(preload)
        try:
            preload_colors()
        except Exception:  # noqa: BLE001
            log.exception("Couleurs des couvertures")
        try:
            auto_measure()
        except Exception:  # noqa: BLE001
            log.exception("Mesure de la qualité")
        trim_cache()
        if pending_scan.is_set() and not lib.status["running"]:
            pending_scan.clear()
            start_scan_thread()

    def start_scan_thread(under: Optional[str] = None) -> None:
        threading.Thread(target=scan_job, args=(under,), name="bulle-scan", daemon=True).start()

    def scheduler() -> None:
        last_trim = time.time()
        while True:
            time.sleep(60)
            if lib.status["running"]:
                continue
            if pending_scan.is_set():
                pending_scan.clear()
                start_scan_thread()
                continue
            interval = int(settings()["scan_interval_hours"])
            last = lib.stats().get("last_scan") or 0
            if interval > 0 and time.time() - last >= interval * 3600:
                log.info("Scan automatique (toutes les %d h)", interval)
                start_scan_thread()
            if time.time() - last_trim > 3600:
                last_trim = time.time()
                trim_cache()

    app.extensions["bulle"]["start_scan"] = start_scan_thread
    threading.Thread(target=scheduler, name="bulle-scheduler", daemon=True).start()
    # Scan au démarrage (après une mise à jour, un redémarrage) : réglable dans la page Réglages, prioritaire sur la
    # variable SCAN_ON_START. Désactivé sur une bibliothèque vide : la page d'accueil propose alors le bouton ↻.
    if settings().get("scan_on_start", True):
        start_scan_thread()
    else:
        log.info("Scan au démarrage désactivé (Réglages › Images et cache) : bouton ↻ ou rescan automatique")
    return app


def main() -> None:
    # LOG_LEVEL=DEBUG dans la stack pour voir le détail (ex. chaque album mesuré) ; INFO par défaut
    level = getattr(logging, env_str("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = env_int("PORT", 2205)
    host = os.environ.get("HOST", "0.0.0.0")
    app = create_app()
    log.info("Bulle %s — bibliothèque : %s — http://%s:%d", VERSION, os.environ.get("LIBRARY_ROOT", "/library"),
             host, port)
    try:
        from waitress import serve  # type: ignore
        serve(app, host=host, port=port, threads=env_int("THREADS", 8), ident="bulle")
    except ImportError:
        log.info("waitress absent : serveur Flask de secours")
        app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
