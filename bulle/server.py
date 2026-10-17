"""Serveur web Bulle : pages statiques + API JSON."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from flask import Flask, Response, abort, jsonify, make_response, request, send_file, send_from_directory

from .comics import COVER_WIDTH, QUALITY_PROFILES, AlbumError, Comics, pick_width
from .library import DEFAULT_PROFILE, Library

VERSION = "0.2.0"
log = logging.getLogger("bulle")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


# Réglages globaux (serveur) : défauts tirés des variables d'environnement, modifiables dans la page Réglages.
def global_defaults() -> dict:
    return {
        "scan_interval_hours": env_int("SCAN_INTERVAL_HOURS", 12),
        "preload_covers": env_bool("PRELOAD_COVERS", True),
        "preload_threads": max(1, min(8, env_int("PRELOAD_THREADS", 3))),
        "page_cache": env_bool("PAGE_CACHE", True),
        "cache_max_gb": 5,
        "quality": "normal",          # eco / normal / max
        "sharpen": True,
        "cover_width": COVER_WIDTH,
        "read_threshold": 1.0,        # 1.0 = lu à la dernière page ; 0.9 = lu à partir de 90 %
    }


GLOBAL_TYPES = {
    "scan_interval_hours": (int, 0, 720), "preload_covers": (bool,), "preload_threads": (int, 1, 8),
    "page_cache": (bool,), "cache_max_gb": (float, 0, 1000), "quality": (str, tuple(QUALITY_PROFILES)),
    "sharpen": (bool,), "cover_width": (int, 200, 1200), "read_threshold": (float, 0.5, 1.0),
}


def create_app(library_root: Optional[str] = None, data_dir: Optional[str] = None) -> Flask:
    # chemins absolus : Flask résout les chemins relatifs par rapport au paquet, pas au dossier courant
    library_root = os.path.abspath(library_root or os.environ.get("LIBRARY_ROOT", "/library"))
    data_dir = os.path.abspath(data_dir or os.environ.get("DATA_DIR", "/data"))
    os.makedirs(data_dir, exist_ok=True)

    comics = Comics(os.path.join(data_dir, "cache"), page_cache=env_bool("PAGE_CACHE", True))
    lib = Library(library_root, os.path.join(data_dir, "bulle.sqlite"), on_invalidate=comics.invalidate)

    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions["bulle"] = {"library": lib, "comics": comics}

    # ------------------------------------------------------------------ réglages
    def settings() -> dict:
        s = global_defaults()
        s.update(lib.get_settings(None))
        return s

    def apply_settings(s: dict) -> None:
        comics.configure(quality=s["quality"], sharpen=s["sharpen"], cover_width=s["cover_width"],
                         page_cache=s["page_cache"])

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
                    val = str(val)
                    if val not in spec[1]:
                        abort(400, description=f"Valeur invalide pour {key}")
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

    # ------------------------------------------------------------------ profils
    def current_profile() -> int:
        raw = request.cookies.get("bulle_profile")
        if raw and raw.isdigit() and lib.profile(int(raw)):
            return int(raw)
        return DEFAULT_PROFILE

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
            "pages": n.get("page_count"), "error": n.get("error"),
        }
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
            node["page_count"], node["error"] = n, None
        except AlbumError as e:
            lib.set_pages(node["id"], None, str(e))
            node["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("Ouverture de %s", node["path"])
            lib.set_pages(node["id"], None, f"Erreur inattendue : {e}")
            node["error"] = f"Erreur inattendue : {e}"
        return node

    def get_node(node_id: int, kind: Optional[str] = None) -> dict:
        node = lib.node(node_id)
        if not node or (kind and node["kind"] != kind):
            abort(404, description="Introuvable (relancez un scan ?)")
        return node

    def folder_payload(folder: dict, profile_id: int) -> dict:
        children = lib.children(folder["id"])
        prog = lib.all_progress(profile_id)
        by_id = {p["node_id"]: p for p in prog}
        out = []
        for c in children:
            j = album_json(c, with_progress=False)
            if c["kind"] == "album":
                j["progress"] = progress_json(by_id.get(c["id"]))
            else:
                prefix = c["path"] + "/"
                j["read_count"] = sum(1 for p in prog if p["completed"] and p["path"].startswith(prefix))
                j["reading_count"] = sum(1 for p in prog if not p["completed"] and p["path"].startswith(prefix))
            out.append(j)
        return {"folder": album_json(folder, with_progress=False), "breadcrumb": lib.breadcrumb(folder),
                "children": out}

    def cache_headers(resp: Response, immutable: bool) -> Response:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if immutable else "public, max-age=600"
        return resp

    def with_folder(items: list[dict]) -> list[dict]:
        out = []
        for n in items:
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
            out.append(j)
        return out

    # ------------------------------------------------------------------ pages
    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html", max_age=0)

    @app.route("/read/<int:node_id>")
    def read_page(node_id: int):
        return send_from_directory(STATIC_DIR, "reader.html", max_age=0)

    @app.route("/static/<path:filename>")
    def static_files(filename: str):
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
        node = ensure_pages(get_node(node_id, "album"))
        prev_, next_ = lib.siblings(node)
        j = album_json(node, with_progress=False)
        j["progress"] = progress_json(lib.progress(node_id, current_profile()))
        j["breadcrumb"] = lib.breadcrumb(node)[:-1]
        j["prev"], j["next"] = prev_, next_
        return jsonify(j)

    @app.route("/api/cover/<int:node_id>")
    def api_cover(node_id: int):
        node = get_node(node_id)
        if node["kind"] == "folder":
            if not node.get("cover_id"):
                abort(404, description="Dossier sans album")
            node = get_node(node["cover_id"], "album")
        try:
            path = comics.cover(node, lib.abs_path(node["path"]))
        except AlbumError as e:
            if not node.get("page_count") and not node.get("error"):
                lib.set_pages(node["id"], None, str(e))
            abort(415, description=str(e))
        resp = send_file(path, mimetype="image/jpeg", conditional=True)
        return cache_headers(resp, immutable="v" in request.args)

    @app.route("/api/page/<int:node_id>/<int:index>")
    def api_page(node_id: int, index: int):
        node = get_node(node_id, "album")
        width = pick_width(request.args.get("w", 1200, type=int))
        try:
            path, data, mime = comics.page(node, lib.abs_path(node["path"]), index, width)
        except AlbumError as e:
            abort(415, description=str(e))
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
        return jsonify({"global": settings(), "profile": lib.get_settings(pid), "profile_id": pid,
                        "profiles": lib.profiles(), "version": VERSION, "library_root": library_root,
                        "quality_profiles": {k: {"quality": v[0], "chroma": v[1]} for k, v in QUALITY_PROFILES.items()}})

    @app.route("/api/settings", methods=["PUT", "POST"])
    def api_settings_set():
        body = request.get_json(force=True, silent=True) or {}
        pid = current_profile()
        if isinstance(body.get("global"), dict):
            lib.set_settings(validate_global(body["global"]), None)
            apply_settings(settings())
        if isinstance(body.get("profile"), dict):
            lib.set_settings(validate_profile_settings(body["profile"]), pid)
        return api_settings_get()

    @app.route("/api/profiles", methods=["GET"])
    def api_profiles():
        return jsonify({"profiles": lib.profiles(), "current": current_profile()})

    @app.route("/api/profiles/select", methods=["POST"])
    def api_profile_select():
        body = request.get_json(force=True, silent=True) or {}
        pid = int(body.get("id", DEFAULT_PROFILE))
        if not lib.profile(pid):
            abort(404, description="Profil inconnu")
        resp = make_response(jsonify({"current": pid}))
        resp.set_cookie("bulle_profile", str(pid), max_age=10 * 365 * 24 * 3600, samesite="Lax")
        return resp

    @app.route("/api/cache", methods=["GET"])
    def api_cache():
        return jsonify(comics.cache_size())

    @app.route("/api/cache/clear", methods=["POST"])
    def api_cache_clear():
        n = comics.clear_pages()
        return jsonify({"cleared": n, "cache": comics.cache_size()})

    @app.route("/api/covers/rebuild", methods=["POST"])
    def api_covers_rebuild():
        if lib.status["running"]:
            return jsonify(lib.status), 409
        comics.clear_covers()
        threading.Thread(target=lambda: run_background(preload_missing_covers), name="bulle-covers",
                         daemon=True).start()
        time.sleep(0.2)
        return jsonify(lib.status), 202

    @app.route("/api/stats")
    def api_stats():
        s = lib.stats(current_profile())
        s["scan"] = lib.status
        s["version"] = VERSION
        s["library_root"] = library_root
        return jsonify(s)

    @app.route("/api/scan", methods=["GET"])
    def api_scan_status():
        return jsonify(lib.status)

    @app.route("/api/scan", methods=["POST"])
    def api_scan_start():
        if lib.status["running"]:
            return jsonify(lib.status), 409
        start_scan_thread()
        time.sleep(0.2)
        return jsonify(lib.status), 202

    @app.route("/api/download/<int:node_id>")
    def api_download(node_id: int):
        node = get_node(node_id, "album")
        path = lib.abs_path(node["path"])
        if not os.path.isfile(path):
            abort(404, description="Fichier introuvable")
        return send_file(path, as_attachment=True, download_name=os.path.basename(path), conditional=True)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(415)
    def api_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": getattr(e, "description", str(e))}), e.code
        return e

    # ------------------------------------------------------------------ tâches de fond
    def preload_albums(todo: list[dict], label: str) -> None:
        """Ouvre chaque album une fois : nombre de pages + couverture, en parallèle."""
        lib.status.update(phase="covers", covers_total=len(todo), covers_done=0)
        t0 = time.time()
        counter_lock = threading.Lock()

        def one(n: dict) -> None:
            try:
                count = comics.inspect(n, lib.abs_path(n["path"]), make_cover=True)
                lib.set_pages(n["id"], count, None)
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
        lib.status.update(phase="idle")
        log.info("%s : %d albums traités en %.0f s", label, lib.status["covers_done"], time.time() - t0)

    def preload() -> None:
        preload_albums(lib.albums_without("page_count IS NULL AND error IS NULL"), "Couvertures")

    def preload_missing_covers() -> None:
        todo = [n for n in lib.albums_without("error IS NULL") if not os.path.exists(comics.cover_path(n["id"]))]
        preload_albums(todo, "Couvertures régénérées")

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

    def scan_job() -> None:
        try:
            lib.scan()
        except RuntimeError as e:
            log.warning("%s", e)
            return
        except Exception:  # noqa: BLE001
            return
        if settings()["preload_covers"]:
            run_background(preload)
        trim_cache()

    def start_scan_thread() -> None:
        threading.Thread(target=scan_job, name="bulle-scan", daemon=True).start()

    def scheduler() -> None:
        last_trim = time.time()
        while True:
            time.sleep(60)
            if lib.status["running"]:
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
    if env_bool("SCAN_ON_START", True):
        start_scan_thread()
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = env_int("PORT", 2203)
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
