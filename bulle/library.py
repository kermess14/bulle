"""Scanner de la bibliothèque + base SQLite (dossiers, albums, progression).

Le rangement suit vos dossiers : un dossier = un nœud, un fichier CBZ/CBR/PDF = un album.
Rien n'est deviné d'après les noms de fichiers.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Callable, Iterable, Optional

log = logging.getLogger("bulle.library")

ALBUM_EXT = {".cbz", ".zip", ".cbr", ".rar", ".pdf", ".cb7", ".7z", ".cbt", ".tar"}
SKIP_DIRS = {"@eaDir", "#recycle", ".recycle", "$RECYCLE.BIN", "System Volume Information",
             "lost+found", "_UNPACK_", "@Recycle"}

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS nodes(
  id          INTEGER PRIMARY KEY,
  parent_id   INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
  path        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  name_norm   TEXT NOT NULL,
  search_text TEXT NOT NULL,
  sort_key    TEXT NOT NULL,
  kind        TEXT NOT NULL,
  format      TEXT,
  size        INTEGER NOT NULL DEFAULT 0,
  mtime       REAL NOT NULL DEFAULT 0,
  page_count  INTEGER,
  error       TEXT,
  album_count INTEGER NOT NULL DEFAULT 0,
  cover_id    INTEGER,
  added_at    REAL NOT NULL,
  seen        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id, kind, sort_key);
CREATE INDEX IF NOT EXISTS idx_nodes_kind_mtime ON nodes(kind, mtime);
CREATE TABLE IF NOT EXISTS progress(
  node_id    INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
  page       INTEGER NOT NULL,
  page_count INTEGER,
  completed  INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


# ----------------------------------------------------------------------------
# Petits utilitaires de tri / normalisation
# ----------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces simples : pour la recherche."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


_NUM_RE = re.compile(r"(\d+)")


def natural_key(text: str) -> str:
    """Clé de tri « naturelle » stockable en texte : T2 avant T10, sans accents ni casse."""
    parts = _NUM_RE.split(normalize(text))
    out = []
    for p in parts:
        if p.isdigit():
            out.append(f"{int(p):012d}")
        else:
            out.append(p)
    return "".join(out)


def natural_sort_key(text: str):
    """Variante Python (tuple) pour trier des listes en mémoire."""
    return [int(p) if p.isdigit() else p for p in _NUM_RE.split(normalize(text))]


def display_name(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    return base if ext.lower() in ALBUM_EXT else filename


def detect_format(path: str, filename: str) -> Optional[str]:
    """Vrai format d'après les premiers octets (un .cbr qui est un zip fonctionne)."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        head = b""
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    ext = os.path.splitext(filename)[1].lower()
    return {".cbz": "zip", ".zip": "zip", ".cbr": "rar", ".rar": "rar", ".pdf": "pdf",
            ".cb7": "7z", ".7z": "7z", ".cbt": "tar", ".tar": "tar"}.get(ext)


# ----------------------------------------------------------------------------
# La bibliothèque
# ----------------------------------------------------------------------------
class Library:
    def __init__(self, root: str, db_path: str,
                 on_invalidate: Optional[Callable[[Iterable[int]], None]] = None):
        self.root = os.path.abspath(root)
        self.db_path = db_path
        self.on_invalidate = on_invalidate or (lambda ids: None)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.scan_lock = threading.Lock()
        self.status = {
            "running": False, "phase": "idle", "started_at": None, "finished_at": None,
            "duration": None, "albums": 0, "folders": 0, "added": 0, "removed": 0,
            "changed": 0, "error": None, "covers_done": 0, "covers_total": 0,
        }
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._write_lock:
            self.conn.executescript(SCHEMA)

    # -- connexion par thread --------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def abs_path(self, rel: str) -> str:
        return os.path.join(self.root, rel) if rel else self.root

    # -- scan ------------------------------------------------------------------
    def scan(self) -> dict:
        """Parcourt le dossier des BD et met la base à jour. Thread-safe (un scan à la fois)."""
        if not self.scan_lock.acquire(blocking=False):
            raise RuntimeError("Un scan est déjà en cours")
        t0 = time.time()
        self.status.update(running=True, phase="scan", started_at=t0, finished_at=None,
                           error=None, added=0, removed=0, changed=0)
        try:
            result = self._scan()
            self.status.update(**result)
            return result
        except Exception as e:  # noqa: BLE001
            log.exception("Scan failed")
            self.status["error"] = str(e)
            raise
        finally:
            self.status.update(running=False, phase="idle", finished_at=time.time(),
                               duration=round(time.time() - t0, 1))
            self.scan_lock.release()

    def _walk(self):
        """Parcours itératif ; renvoie (chemin relatif, sous-dossiers, fichiers albums)."""
        stack = [""]
        while stack:
            rel = stack.pop()
            try:
                with os.scandir(self.abs_path(rel)) as it:
                    entries = list(it)
            except OSError as e:
                log.warning("Dossier illisible %s : %s", rel or "/", e)
                continue
            dirs, files = [], []
            for e in entries:
                name = e.name
                if name.startswith(".") or name in SKIP_DIRS:
                    continue
                try:
                    if e.is_dir(follow_symlinks=True):
                        dirs.append(name)
                    elif e.is_file(follow_symlinks=True):
                        if os.path.splitext(name)[1].lower() in ALBUM_EXT:
                            st = e.stat(follow_symlinks=True)
                            files.append((name, st.st_size, st.st_mtime))
                except OSError:
                    continue
            yield rel, dirs, files
            for d in dirs:
                stack.append(f"{rel}/{d}" if rel else d)

    def _scan(self) -> dict:
        if not os.path.isdir(self.root):
            raise RuntimeError(f"Dossier des BD introuvable : {self.root}")
        gen = int(time.time())
        now = time.time()

        # 1) Tout lire en mémoire
        folders: dict[str, dict] = {}
        albums: list[dict] = []
        for rel, dirs, files in self._walk():
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ("" if rel else None)
            folders[rel] = {"path": rel, "parent": parent, "name": rel.rsplit("/", 1)[-1] if rel else "",
                            "direct": len(files), "count": 0}
            for name, size, mtime in files:
                albums.append({"path": f"{rel}/{name}" if rel else name, "parent": rel,
                               "name": display_name(name), "file": name, "size": size, "mtime": mtime})
            self.status["albums"] = len(albums)

        # 2) Nombre d'albums par dossier (y compris sous-dossiers)
        for rel in sorted(folders, key=lambda p: p.count("/"), reverse=True):
            f = folders[rel]
            f["count"] += f["direct"]
            if f["parent"] is not None and f["parent"] in folders:
                folders[f["parent"]]["count"] += f["count"]
        # On ignore les dossiers vides (sauf la racine)
        folders = {p: f for p, f in folders.items() if f["count"] > 0 or p == ""}

        conn = self.conn
        with self._write_lock:
            existing = {r["path"]: dict(r) for r in conn.execute(
                "SELECT id, path, kind, size, mtime FROM nodes")}
            ids: dict[str, int] = {}
            added = changed = 0
            invalidate: list[int] = []
            cur = conn.cursor()
            cur.execute("BEGIN")
            try:
                # Dossiers, du haut vers le bas
                for rel in sorted(folders, key=lambda p: (p.count("/"), p)):
                    f = folders[rel]
                    parent_id = ids.get(f["parent"]) if f["parent"] is not None else None
                    name = f["name"] or "Accueil"
                    row = existing.get(rel)
                    if row:
                        cur.execute(
                            "UPDATE nodes SET parent_id=?, name=?, name_norm=?, search_text=?, sort_key=?, "
                            "kind='folder', album_count=?, seen=? WHERE id=?",
                            (parent_id, name, normalize(name), normalize(rel), natural_key(name),
                             f["count"], gen, row["id"]))
                        ids[rel] = row["id"]
                    else:
                        cur.execute(
                            "INSERT INTO nodes(parent_id, path, name, name_norm, search_text, sort_key, kind, "
                            "album_count, added_at, seen) VALUES(?,?,?,?,?,?, 'folder', ?,?,?)",
                            (parent_id, rel, name, normalize(name), normalize(rel), natural_key(name),
                             f["count"], now, gen))
                        ids[rel] = cur.lastrowid
                        if rel:
                            added += 1
                # Albums
                for a in albums:
                    parent_id = ids[a["parent"]]
                    row = existing.get(a["path"])
                    if row:
                        if abs(row["mtime"] - a["mtime"]) > 1 or row["size"] != a["size"]:
                            fmt = detect_format(self.abs_path(a["path"]), a["file"])
                            cur.execute(
                                "UPDATE nodes SET parent_id=?, name=?, name_norm=?, search_text=?, sort_key=?, "
                                "kind='album', format=?, size=?, mtime=?, page_count=NULL, error=NULL, seen=? "
                                "WHERE id=?",
                                (parent_id, a["name"], normalize(a["name"]), normalize(a["path"]),
                                 natural_key(a["name"]), fmt, a["size"], a["mtime"], gen, row["id"]))
                            invalidate.append(row["id"])
                            changed += 1
                        else:
                            cur.execute("UPDATE nodes SET parent_id=?, seen=? WHERE id=?",
                                        (parent_id, gen, row["id"]))
                        ids[a["path"]] = row["id"]
                    else:
                        fmt = detect_format(self.abs_path(a["path"]), a["file"])
                        cur.execute(
                            "INSERT INTO nodes(parent_id, path, name, name_norm, search_text, sort_key, kind, "
                            "format, size, mtime, added_at, seen) VALUES(?,?,?,?,?,?,'album',?,?,?,?,?)",
                            (parent_id, a["path"], a["name"], normalize(a["name"]), normalize(a["path"]),
                             natural_key(a["name"]), fmt, a["size"], a["mtime"], now, gen))
                        ids[a["path"]] = cur.lastrowid
                        added += 1
                # Disparus
                gone = [r["id"] for r in cur.execute("SELECT id FROM nodes WHERE seen<>?", (gen,))]
                removed = len(gone)
                if gone:
                    cur.execute("DELETE FROM nodes WHERE seen<>?", (gen,))
                    invalidate.extend(gone)
                # Couverture des dossiers = premier album (récursif)
                by_parent_albums: dict[str, list[dict]] = {}
                for a in albums:
                    by_parent_albums.setdefault(a["parent"], []).append(a)
                by_parent_folders: dict[str, list[str]] = {}
                for rel, f in folders.items():
                    if f["parent"] is not None and f["parent"] in folders:
                        by_parent_folders.setdefault(f["parent"], []).append(rel)
                cover_cache: dict[str, Optional[int]] = {}

                def first_album(rel: str) -> Optional[int]:
                    if rel in cover_cache:
                        return cover_cache[rel]
                    res = None
                    direct = by_parent_albums.get(rel)
                    if direct:
                        best = min(direct, key=lambda a: natural_sort_key(a["name"]))
                        res = ids.get(best["path"])
                    else:
                        for sub in sorted(by_parent_folders.get(rel, []),
                                          key=lambda p: natural_sort_key(folders[p]["name"])):
                            res = first_album(sub)
                            if res:
                                break
                    cover_cache[rel] = res
                    return res

                for rel in folders:
                    cur.execute("UPDATE nodes SET cover_id=? WHERE id=?", (first_album(rel), ids[rel]))
                cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_scan', ?)", (str(now),))
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
        if invalidate:
            try:
                self.on_invalidate(invalidate)
            except Exception:  # noqa: BLE001
                log.exception("Invalidation du cache")
        result = {"albums": len(albums), "folders": max(0, len(folders) - 1), "added": added,
                  "removed": removed, "changed": changed}
        log.info("Scan terminé : %(albums)d albums, %(folders)d dossiers, +%(added)d, -%(removed)d, "
                 "~%(changed)d modifiés", result)
        return result

    # -- lecture ---------------------------------------------------------------
    def node(self, node_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return dict(r) if r else None

    def root_node(self) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM nodes WHERE path=''").fetchone()
        return dict(r) if r else None

    def breadcrumb(self, node: dict) -> list[dict]:
        crumbs = []
        cur = node
        guard = 0
        while cur and guard < 64:
            crumbs.append({"id": cur["id"], "name": cur["name"], "kind": cur["kind"]})
            cur = self.node(cur["parent_id"]) if cur["parent_id"] is not None else None
            guard += 1
        crumbs.reverse()
        return crumbs

    def children(self, node_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE parent_id=? ORDER BY CASE kind WHEN 'folder' THEN 0 ELSE 1 END, sort_key",
            (node_id,)).fetchall()
        return [dict(r) for r in rows]

    def siblings(self, node: dict) -> tuple[Optional[dict], Optional[dict]]:
        """Album précédent / suivant dans le même dossier."""
        rows = self.conn.execute(
            "SELECT id, name, sort_key FROM nodes WHERE parent_id=? AND kind='album' ORDER BY sort_key, id",
            (node["parent_id"],)).fetchall()
        prev = nxt = None
        for i, r in enumerate(rows):
            if r["id"] == node["id"]:
                if i > 0:
                    prev = {"id": rows[i - 1]["id"], "name": rows[i - 1]["name"]}
                if i + 1 < len(rows):
                    nxt = {"id": rows[i + 1]["id"], "name": rows[i + 1]["name"]}
                break
        return prev, nxt

    def all_progress(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.node_id, p.page, p.page_count, p.completed, p.updated_at, n.path "
            "FROM progress p JOIN nodes n ON n.id=p.node_id").fetchall()
        return [dict(r) for r in rows]

    def progress(self, node_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM progress WHERE node_id=?", (node_id,)).fetchone()
        return dict(r) if r else None

    def set_progress(self, node_id: int, page: int, page_count: Optional[int],
                     completed: Optional[bool] = None) -> dict:
        if page_count is None:
            page_count = (self.node(node_id) or {}).get("page_count")
        page = max(0, int(page))
        if page_count:
            page = min(page, page_count - 1)
        if completed is None:
            completed = bool(page_count) and page >= page_count - 1
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO progress(node_id, page, page_count, completed, updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET page=excluded.page, page_count=excluded.page_count, "
                "completed=excluded.completed, updated_at=excluded.updated_at",
                (node_id, page, page_count, 1 if completed else 0, time.time()))
            self.conn.commit()
        return self.progress(node_id)

    def clear_progress(self, node_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM progress WHERE node_id=?", (node_id,))
            self.conn.commit()

    def set_pages(self, node_id: int, page_count: Optional[int], error: Optional[str]) -> None:
        with self._write_lock:
            self.conn.execute("UPDATE nodes SET page_count=?, error=? WHERE id=?",
                              (page_count, (error or None), node_id))
            if page_count:
                # garde la progression cohérente si le nombre de pages vient d'être découvert
                self.conn.execute(
                    "UPDATE progress SET page_count=?, completed=CASE WHEN page>=?-1 THEN 1 ELSE completed END "
                    "WHERE node_id=?", (page_count, page_count, node_id))
            self.conn.commit()

    def continue_reading(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT n.*, p.page AS p_page, p.page_count AS p_count, p.completed AS p_completed, "
            "p.updated_at AS p_updated FROM progress p JOIN nodes n ON n.id=p.node_id "
            "WHERE p.completed=0 ORDER BY p.updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 24) -> list[dict]:
        rows = self.conn.execute(
            "SELECT n.*, p.page AS p_page, p.page_count AS p_count, p.completed AS p_completed, "
            "p.updated_at AS p_updated FROM nodes n LEFT JOIN progress p ON p.node_id=n.id "
            "WHERE n.kind='album' ORDER BY n.added_at DESC, n.mtime DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 120) -> list[dict]:
        words = [w for w in normalize(query).split(" ") if w]
        if not words:
            return []
        where = " AND ".join("search_text LIKE ? ESCAPE '\\'" for _ in words)
        params = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
        rows = self.conn.execute(
            f"SELECT n.*, p.page AS p_page, p.page_count AS p_count, p.completed AS p_completed, "
            f"p.updated_at AS p_updated FROM nodes n LEFT JOIN progress p ON p.node_id=n.id "
            f"WHERE n.path<>'' AND {where} "
            f"ORDER BY CASE n.kind WHEN 'folder' THEN 0 ELSE 1 END, n.sort_key LIMIT ?",
            (*params, limit * 4)).fetchall()
        q = " ".join(words)

        def rank(r):
            name = r["name_norm"]
            if name.startswith(q):
                score = 0
            elif all(re.search(r"(^|\W)" + re.escape(w) + r"(\W|$)", name) for w in words):
                score = 1  # mots entiers dans le nom
            elif all(w in name for w in words):
                score = 2
            else:
                score = 3  # trouvé seulement via les dossiers parents
            return (score, 0 if r["kind"] == "folder" else 1, r["sort_key"])

        return [dict(r) for r in sorted(rows, key=rank)[:limit]]

    def albums_without(self, predicate_sql: str = "1=1") -> list[dict]:
        rows = self.conn.execute(
            f"SELECT id, path, format, mtime, page_count, error FROM nodes WHERE kind='album' AND {predicate_sql} "
            "ORDER BY sort_key").fetchall()
        return [dict(r) for r in rows]

    def fix_folder_covers(self) -> int:
        """Si la couverture d'un dossier pointe sur un album illisible, prend le premier album lisible."""
        with self._write_lock:
            cur = self.conn.execute(
                "UPDATE nodes SET cover_id = ("
                "  SELECT a.id FROM nodes a WHERE a.kind='album' AND a.error IS NULL AND a.page_count IS NOT NULL"
                "   AND (nodes.path='' OR a.path LIKE nodes.path || '/%' ESCAPE '\\') ORDER BY a.path LIMIT 1)"
                " WHERE kind='folder' AND cover_id IN (SELECT id FROM nodes WHERE error IS NOT NULL)")
            self.conn.commit()
            return cur.rowcount

    def stats(self) -> dict:
        r = self.conn.execute(
            "SELECT SUM(CASE WHEN kind='album' THEN 1 ELSE 0 END) AS albums, "
            "SUM(CASE WHEN kind='folder' AND path<>'' THEN 1 ELSE 0 END) AS folders, "
            "SUM(CASE WHEN kind='album' THEN size ELSE 0 END) AS size FROM nodes").fetchone()
        p = self.conn.execute(
            "SELECT SUM(completed) AS done, SUM(CASE WHEN completed=0 THEN 1 ELSE 0 END) AS reading "
            "FROM progress").fetchone()
        last = self.conn.execute("SELECT value FROM meta WHERE key='last_scan'").fetchone()
        return {"albums": r["albums"] or 0, "folders": r["folders"] or 0, "size": r["size"] or 0,
                "read": p["done"] or 0, "reading": p["reading"] or 0,
                "last_scan": float(last["value"]) if last else None}
