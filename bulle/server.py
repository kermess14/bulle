"""Serveur web Bulle : pages statiques + API JSON."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

from .comics import COVER_WIDTH, AlbumError, Comics, pick_width
from .library import Library

VERSION = "0.1.0"
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


def create_app(library_root: Optional[str] = None, data_dir: Optional[str] = None) -> Flask:
    # chemins absolus : Flask résout les chemins relatifs par rapport au paquet, pas au dossier courant
    library_root = os.path.abspath(library_root or os.environ.get("LIBRARY_ROOT", "/library"))
    data_dir = os.path.abspath(data_dir or os.environ.get("DATA_DIR", "/data"))
    os.makedirs(data_dir, exist_ok=True)

    comics = Comics(os.path.join(data_dir, "cache"), page_cache=env_bool("PAGE_CACHE", True))
    lib = Library(library_root, os.path.join(data_dir, "bulle.sqlite"), on_invalidate=comics.invalidate)

    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions["bulle"] = {"library": lib, "comics": comics}

    scan_interval = env_int("SCAN_INTERVAL_HOURS", 12)
    preload_covers = env_bool("PRELOAD_COVERS", True)

    # ------------------------------------------------------------------ helpers
    def album_json(n: dict, with_progress: bool = True) -> dict:
        d = {
            "id": n["id"], "kind": n["kind"], "name": n["name"], "path": n["path"],
            "parent_id": n.get("parent_id"), "format": n.get("format"), "size": n.get("size", 0),
            "mtime": int(n.get("mtime") or 0), "pages": n.get("page_count"), "error": n.get("error"),
        }
        if n["kind"] == "folder":
            d["album_count"] = n.get("album_count", 0)
            d["cover_id"] = n.get("cover_id")
        if with_progress:
            if "p_page" in n:
                d["progress"] = progress_json(
                    {"page": n["p_page"], "page_count": n["p_count"], "completed": n["p_completed"],
                     "updated_at": n["p_updated"]} if n.get("p_page") is not None else None)
        return d

    def progress_json(p: Optional[dict]) -> Optional[dict]:
        if not p:
            return None
        return {"page": p["page"], "pages": p.get("page_count"), "completed": bool(p.get("completed")),
                "updated_at": p.get("updated_at")}

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

    def folder_payload(folder: dict) -> dict:
        children = lib.children(folder["id"])
        prog = lib.all_progress()
        by_id = {p["node_id"]: p for p in prog}
        out = []
        for c in children:
            j = album_json(c, with_progress=False)
            if c["kind"] == "album":
                j["progress"] = progress_json(by_id.get(c["id"]))
            else:
                prefix = c["path"] + "/"
                done = sum(1 for p in prog if p["completed"] and p["path"].startswith(prefix))
                reading = sum(1 for p in prog if not p["completed"] and p["path"].startswith(prefix))
                j["read_count"], j["reading_count"] = done, reading
            out.append(j)
        return {"folder": album_json(folder, with_progress=False), "breadcrumb": lib.breadcrumb(folder),
                "children": out}

    def cache_headers(resp: Response, immutable: bool) -> Response:
        if immutable:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "public, max-age=600"
        return resp

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

    # ------------------------------------------------------------------ API
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
        return jsonify(folder_payload(folder))

    @app.route("/api/item/<int:node_id>")
    def api_item(node_id: int):
        node = ensure_pages(get_node(node_id, "album"))
        prev_, next_ = lib.siblings(node)
        j = album_json(node, with_progress=False)
        j["progress"] = progress_json(lib.progress(node_id))
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
        if path:
            resp = send_file(path, mimetype=mime, conditional=True)
        else:
            resp = Response(data, mimetype=mime)
        return cache_headers(resp, immutable="v" in request.args)

    @app.route("/api/progress/<int:node_id>", methods=["GET"])
    def api_progress_get(node_id: int):
        get_node(node_id, "album")
        return jsonify(progress_json(lib.progress(node_id)))

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
        p = lib.set_progress(node_id, page, node.get("page_count"), completed)
        return jsonify(progress_json(p))

    @app.route("/api/progress/<int:node_id>", methods=["DELETE"])
    def api_progress_delete(node_id: int):
        get_node(node_id, "album")
        lib.clear_progress(node_id)
        return jsonify(None)

    @app.route("/api/continue")
    def api_continue():
        items = []
        for n in lib.continue_reading(limit=request.args.get("n", 20, type=int)):
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = crumbs[-2]["name"] if len(crumbs) >= 2 else ""
            items.append(j)
        return jsonify(items)

    @app.route("/api/recent")
    def api_recent():
        rows = lib.recent(limit=request.args.get("n", 24, type=int))
        items = []
        for n in rows:
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = crumbs[-2]["name"] if len(crumbs) >= 2 else ""
            items.append(j)
        return jsonify(items)

    @app.route("/api/search")
    def api_search():
        q = (request.args.get("q") or "").strip()
        if len(q) < 2:
            return jsonify([])
        items = []
        for n in lib.search(q):
            j = album_json(n)
            crumbs = lib.breadcrumb(n)
            j["folder"] = " › ".join(c["name"] for c in crumbs[1:-1])
            items.append(j)
        return jsonify(items)

    @app.route("/api/stats")
    def api_stats():
        s = lib.stats()
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
    def preload(limit_time: Optional[float] = None) -> None:
        """Génère les couvertures / compte les pages des albums pas encore ouverts."""
        todo = lib.albums_without("page_count IS NULL AND error IS NULL")
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

        workers = max(1, min(8, env_int("PRELOAD_THREADS", 3)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bulle-covers") as pool:
            futures = []
            for n in todo:
                if limit_time and time.time() - t0 > limit_time:
                    break
                futures.append(pool.submit(one, n))
            for f in futures:
                f.result()
        try:
            fixed = lib.fix_folder_covers()
            if fixed:
                log.info("Couvertures de dossiers corrigées : %d", fixed)
        except Exception:  # noqa: BLE001
            log.exception("Correction des couvertures de dossiers")
        lib.status.update(phase="idle")
        log.info("Couvertures : %d albums traités en %.0f s", lib.status["covers_done"], time.time() - t0)

    def scan_job() -> None:
        try:
            lib.scan()
        except RuntimeError as e:
            log.warning("%s", e)
            return
        except Exception:  # noqa: BLE001
            return
        if preload_covers:
            lib.status["running"] = True
            try:
                preload()
            finally:
                lib.status["running"] = False

    def start_scan_thread() -> None:
        threading.Thread(target=scan_job, name="bulle-scan", daemon=True).start()

    def scheduler() -> None:
        while True:
            time.sleep(60)
            if scan_interval <= 0 or lib.status["running"]:
                continue
            last = lib.stats().get("last_scan") or 0
            if time.time() - last >= scan_interval * 3600:
                log.info("Scan automatique (toutes les %d h)", scan_interval)
                start_scan_thread()

    app.extensions["bulle"]["start_scan"] = start_scan_thread
    if scan_interval > 0:
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
