"""Scanner de la bibliothèque + base SQLite (dossiers, albums, progression).

Le rangement suit vos dossiers : un dossier = un nœud, un fichier CBZ/CBR/PDF = un album.
Rien n'est deviné d'après les noms de fichiers.
"""
from __future__ import annotations

import json
import logging
import math
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
  color       TEXT,
  cover_page  INTEGER,
  res_w       INTEGER,
  res_h       INTEGER,
  added_at    REAL NOT NULL,
  seen        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id, kind, sort_key);
CREATE INDEX IF NOT EXISTS idx_nodes_kind_mtime ON nodes(kind, mtime);
CREATE TABLE IF NOT EXISTS profiles(
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  pin_hash   TEXT,
  avatar     TEXT,
  role       TEXT NOT NULL DEFAULT 'reader',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS progress(
  profile_id INTEGER NOT NULL DEFAULT 1 REFERENCES profiles(id) ON DELETE CASCADE,
  node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  page       INTEGER NOT NULL,
  page_count INTEGER,
  completed  INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  PRIMARY KEY(profile_id, node_id)
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profile_settings(
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  key        TEXT NOT NULL,
  value      TEXT NOT NULL,
  PRIMARY KEY(profile_id, key)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
-- Bédéthèque : lien dossier ↔ série, métadonnées d'albums (jamais écrites dans les fichiers), cache des pages
CREATE TABLE IF NOT EXISTS bdt_series(
  folder_id   INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
  bdt_id      INTEGER,
  url         TEXT NOT NULL,
  title       TEXT,
  genre       TEXT,
  status      TEXT,
  years       TEXT,
  tomes_count INTEGER,
  data        TEXT NOT NULL,
  score       REAL,
  manual      INTEGER NOT NULL DEFAULT 0,
  detailed    INTEGER NOT NULL DEFAULT 0,
  present     INTEGER,
  total       INTEGER,
  fetched_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS bdt_albums(
  node_id    INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
  folder_id  INTEGER,
  url        TEXT,
  number     INTEGER,
  kind       TEXT,
  title      TEXT,
  year       INTEGER,
  data       TEXT NOT NULL,
  how        TEXT,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bdt_albums_folder ON bdt_albums(folder_id);
CREATE TABLE IF NOT EXISTS bdt_cache(
  url        TEXT PRIMARY KEY,
  fetched_at REAL NOT NULL,
  body       BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS bdt_index(
  id        INTEGER PRIMARY KEY,
  letter    TEXT NOT NULL,
  name      TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  url       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bdt_index_letter ON bdt_index(letter);
CREATE TABLE IF NOT EXISTS bdt_index_letters(letter TEXT PRIMARY KEY, fetched_at REAL NOT NULL, count INTEGER NOT NULL);
-- Bédéthèque, dossiers de one shots : chaque album est cherché comme sa propre série
CREATE TABLE IF NOT EXISTS bdt_folder_mode(folder_id INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE, mode TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bdt_oneshots(
  node_id      INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
  folder_id    INTEGER NOT NULL,
  status       TEXT NOT NULL,
  query        TEXT,
  score        REAL,
  manual       INTEGER NOT NULL DEFAULT 0,
  series_url   TEXT,
  series_title TEXT,
  candidates   TEXT,
  updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bdt_oneshots_folder ON bdt_oneshots(folder_id);
-- Listes par profil : favoris, à lire, listes personnalisées
CREATE TABLE IF NOT EXISTS lists(
  id         INTEGER PRIMARY KEY,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'custom',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS list_items(
  list_id  INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  node_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  added_at REAL NOT NULL,
  PRIMARY KEY(list_id, node_id)
);
CREATE TABLE IF NOT EXISTS panels(
  node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  page    INTEGER NOT NULL,
  data    TEXT NOT NULL,
  PRIMARY KEY(node_id, page)
);
CREATE TABLE IF NOT EXISTS reading_log(
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  node_id    INTEGER NOT NULL,
  day        TEXT NOT NULL,
  pages      INTEGER NOT NULL DEFAULT 0,
  seconds    INTEGER NOT NULL DEFAULT 0,
  finished   INTEGER NOT NULL DEFAULT 0,
  first_at   REAL NOT NULL,
  last_at    REAL NOT NULL,
  PRIMARY KEY(profile_id, node_id, day)
);
CREATE INDEX IF NOT EXISTS idx_rlog_profile_day ON reading_log(profile_id, day);
"""
SCHEMA_VERSION = 10
DEFAULT_PROFILE = 1


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
    head = b""
    for attempt in range(3):   # disque réseau lent ou en veille : on réessaie avant de se rabattre sur l'extension
        try:
            with open(path, "rb") as f:
                head = f.read(512)
            break
        except OSError:
            time.sleep(0.4 * (attempt + 1))
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"          # RAR 4 (Rar!\x1a\x07\x00) et RAR 5 (Rar!\x1a\x07\x01\x00)
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head[7:14] == b"**ACE**":
        return "ace"          # archive ACE (vieux format propriétaire), parfois déguisée en .cbr
    if head[257:262] == b"ustar" or head.startswith((b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00")):
        return "tar"          # tar brut, ou compressé gzip / bzip2 / xz (tarfile reconnaît tout seul)
    ext = os.path.splitext(filename)[1].lower()
    return {".cbz": "zip", ".zip": "zip", ".cbr": "rar", ".rar": "rar", ".pdf": "pdf",
            ".cb7": "7z", ".7z": "7z", ".cbt": "tar", ".tar": "tar"}.get(ext)


# ----------------------------------------------------------------------------
# La bibliothèque
# ----------------------------------------------------------------------------
class ScanStopped(RuntimeError):
    """Scan arrêté à la demande : rien n'a été écrit dans la base."""


class ScanAborted(RuntimeError):
    """Scan annulé par sécurité (dossier des BD vide ou injoignable, ou la moitié des albums disparus d'un coup) :
    rien n'a été écrit dans la base, pour ne pas tout effacer à cause d'un partage réseau pas encore monté."""


class Library:
    def __init__(self, root: str, db_path: str,
                 on_invalidate: Optional[Callable[[Iterable[int]], None]] = None):
        self.root = os.path.abspath(root)
        self.db_path = db_path
        self.on_invalidate = on_invalidate or (lambda ids: None)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.scan_lock = threading.Lock()
        self.stop_requested = threading.Event()   # « Arrêter » : le scan ou la génération des couvertures s'interrompt
        self.status = {
            "running": False, "phase": "idle", "started_at": None, "finished_at": None,
            "duration": None, "albums": 0, "folders": 0, "added": 0, "new_folders": 0, "removed": 0,
            "changed": 0, "error": None, "covers_done": 0, "covers_total": 0,
        }
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._write_lock:
            self._migrate()
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO profiles(id, name, role, created_at) VALUES(?, 'Moi', 'admin', ?)",
                              (DEFAULT_PROFILE, time.time()))
            if not self.conn.execute("SELECT 1 FROM profiles WHERE role='admin'").fetchone():
                self.conn.execute("UPDATE profiles SET role='admin' WHERE id=?", (DEFAULT_PROFILE,))   # jamais sans administrateur
            self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                              (str(SCHEMA_VERSION),))
            self.conn.commit()

    def _migrate(self) -> None:
        """Base v1 (progression sans profil) → v2 : on recrée la table progress avec le profil 1 ; colonnes ajoutées ensuite."""
        conn = self.conn
        node_cols = [r["name"] for r in conn.execute("PRAGMA table_info(nodes)")]
        if node_cols and "color" not in node_cols:
            conn.execute("ALTER TABLE nodes ADD COLUMN color TEXT")
            conn.commit()
        if node_cols and "cover_page" not in node_cols:
            conn.execute("ALTER TABLE nodes ADD COLUMN cover_page INTEGER")   # page choisie comme couverture (sinon la 1re)
            conn.commit()
        if node_cols and "res_w" not in node_cols:
            # taille réelle des pages (mesurée sur deux pages de l'album) : sert à classer HD / SD ; 0 = pas mesurable
            conn.execute("ALTER TABLE nodes ADD COLUMN res_w INTEGER")
            conn.execute("ALTER TABLE nodes ADD COLUMN res_h INTEGER")
            conn.commit()
        prof_cols = [r["name"] for r in conn.execute("PRAGMA table_info(profiles)")]
        if prof_cols and "role" not in prof_cols:
            # comptes : le premier profil devient administrateur, les autres lecteurs
            conn.execute("ALTER TABLE profiles ADD COLUMN role TEXT NOT NULL DEFAULT 'reader'")
            conn.execute("UPDATE profiles SET role='admin' WHERE id=?", (DEFAULT_PROFILE,))
            conn.commit()
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(progress)")]
        if cols and "profile_id" not in cols:
            log.info("Migration de la base : progression rattachée au profil par défaut")
            conn.executescript(f"""
                BEGIN;
                CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL, pin_hash TEXT,
                                                    avatar TEXT, created_at REAL NOT NULL);
                INSERT OR IGNORE INTO profiles(id, name, created_at) VALUES({DEFAULT_PROFILE}, 'Moi', {time.time()});
                ALTER TABLE progress RENAME TO progress_v1;
                CREATE TABLE progress(
                  profile_id INTEGER NOT NULL DEFAULT 1 REFERENCES profiles(id) ON DELETE CASCADE,
                  node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                  page       INTEGER NOT NULL,
                  page_count INTEGER,
                  completed  INTEGER NOT NULL DEFAULT 0,
                  updated_at REAL NOT NULL,
                  PRIMARY KEY(profile_id, node_id)
                );
                INSERT INTO progress(profile_id, node_id, page, page_count, completed, updated_at)
                  SELECT {DEFAULT_PROFILE}, node_id, page, page_count, completed, updated_at FROM progress_v1;
                DROP TABLE progress_v1;
                COMMIT;
            """)

    # -- réglages --------------------------------------------------------------
    def get_settings(self, profile_id: Optional[int] = None) -> dict:
        """Réglages globaux (profile_id=None) ou d'un profil, sous forme de dict (valeurs JSON)."""
        if profile_id is None:
            rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        else:
            rows = self.conn.execute("SELECT key, value FROM profile_settings WHERE profile_id=?",
                                     (profile_id,)).fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except ValueError:
                out[r["key"]] = r["value"]
        return out

    def set_settings(self, values: dict, profile_id: Optional[int] = None) -> None:
        """Enregistre (fusionne) des réglages ; une valeur None efface la clé (retour au défaut)."""
        with self._write_lock:
            for key, val in values.items():
                if profile_id is None:
                    if val is None:
                        self.conn.execute("DELETE FROM settings WHERE key=?", (key,))
                    else:
                        self.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                                          (key, json.dumps(val, ensure_ascii=False)))
                else:
                    if val is None:
                        self.conn.execute("DELETE FROM profile_settings WHERE profile_id=? AND key=?",
                                          (profile_id, key))
                    else:
                        self.conn.execute(
                            "INSERT OR REPLACE INTO profile_settings(profile_id, key, value) VALUES(?,?,?)",
                            (profile_id, key, json.dumps(val, ensure_ascii=False)))
            self.conn.commit()

    # -- profils ---------------------------------------------------------------
    def profiles(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, name, avatar, role, pin_hash IS NOT NULL AS has_pin FROM profiles "
                                 "ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def profiles_full(self) -> list[dict]:
        """Avec les empreintes des mots de passe : pour la connexion seulement, jamais renvoyé au navigateur."""
        return [dict(r) for r in self.conn.execute("SELECT * FROM profiles ORDER BY id").fetchall()]

    def profile(self, profile_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return dict(r) if r else None

    def add_profile(self, name: str, pin_hash: Optional[str] = None, avatar: Optional[str] = None,
                    role: str = "reader") -> dict:
        with self._write_lock:
            cur = self.conn.execute("INSERT INTO profiles(name, pin_hash, avatar, role, created_at) VALUES(?,?,?,?,?)",
                                    (name.strip() or "Lecteur", pin_hash, avatar, role, time.time()))
            self.conn.commit()
            return self.profile(cur.lastrowid)

    def update_profile(self, profile_id: int, **fields) -> Optional[dict]:
        allowed = {k: v for k, v in fields.items() if k in ("name", "pin_hash", "avatar", "role")}
        if allowed:
            with self._write_lock:
                sets = ", ".join(f"{k}=?" for k in allowed)
                self.conn.execute(f"UPDATE profiles SET {sets} WHERE id=?", (*allowed.values(), profile_id))
                self.conn.commit()
        return self.profile(profile_id)

    def delete_profile(self, profile_id: int) -> bool:
        if profile_id == DEFAULT_PROFILE:
            return False
        with self._write_lock:
            cur = self.conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
            self.conn.commit()
            return cur.rowcount > 0

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
    SAFETY_MIN_ALBUMS = 10      # en dessous, la bibliothèque est trop petite pour juger
    SAFETY_MAX_GONE = 0.5       # plus de la moitié des albums disparus d'un coup : on n'y croit pas

    def scan(self, under: Optional[str] = None, force: bool = False) -> dict:
        """Parcourt le dossier des BD et met la base à jour. Thread-safe (un scan à la fois).
        `under` : ne relit sur le disque que ce dossier (et ses sous-dossiers) ; le reste de la base est gardé tel
        quel. Les fichiers ajoutés y apparaissent, ceux jetés disparaissent."""
        if not self.scan_lock.acquire(blocking=False):
            raise RuntimeError("Un scan est déjà en cours")
        t0 = time.time()
        self.stop_requested.clear()
        self.status.update(running=True, phase="scan", started_at=t0, finished_at=None,
                           error=None, added=0, new_folders=0, removed=0, changed=0, renamed=0, stopped=False, aborted=False)
        try:
            result = self._scan(under, force=force)
            self.status.update(**result)
            return result
        except ScanAborted as e:
            log.warning("Scan annulé par sécurité, base inchangée : %s", e)
            self.status["error"] = str(e)
            self.status["aborted"] = True
            raise
        except ScanStopped:
            log.info("Scan arrêté à la demande : base inchangée")
            self.status["stopped"] = "scan"
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("Scan failed")
            self.status["error"] = str(e)
            raise
        finally:
            self.status.update(running=False, phase="idle", finished_at=time.time(),
                               duration=round(time.time() - t0, 1))
            self.scan_lock.release()

    def _walk(self, ignored: Optional[set] = None, start: str = ""):
        """Parcours itératif ; renvoie (chemin relatif, sous-dossiers, fichiers albums). Les chemins de `ignored`
        (dossiers ou fichiers retirés de Bulle) sont sautés. `start` : dossier de départ (relatif)."""
        ignored = ignored or set()
        if start and not os.path.isdir(self.abs_path(start)):
            return
        stack = [start]
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
                if ignored and (f"{rel}/{name}" if rel else name) in ignored:
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

    def _scan(self, under: Optional[str] = None, force: bool = False) -> dict:
        if not os.path.isdir(self.root):
            raise RuntimeError(f"Dossier des BD introuvable : {self.root}")
        # numéro de passage toujours croissant (deux scans dans la même seconde ne doivent pas se confondre)
        gen = max(int(time.time()), (self.conn.execute("SELECT MAX(seen) FROM nodes").fetchone()[0] or 0) + 1)
        now = time.time()
        under = (under or "").strip("/")
        # dossier lui-même renommé ou déplacé : on relit son parent (le plus proche qui existe encore), pour que ses
        # albums soient retrouvés sous leur nouveau nom au lieu d'être effacés
        while under and not os.path.isdir(self.abs_path(under)):
            under = under.rsplit("/", 1)[0] if "/" in under else ""

        # 1) Tout lire en mémoire (sans les fichiers et dossiers retirés de Bulle : ils restent sur le disque)
        ignored = self.ignored_paths()
        folders: dict[str, dict] = {}
        albums: list[dict] = []
        if under:
            # scan d'un seul dossier : le reste de la bibliothèque est repris tel quel depuis la base
            inside = lambda p: p == under or p.startswith(under + "/")  # noqa: E731
            rows = [dict(r) for r in self.conn.execute("SELECT path, kind, size, mtime FROM nodes")]
            for r in rows:
                if r["kind"] == "folder" and not inside(r["path"]):
                    p = r["path"]
                    folders[p] = {"path": p, "parent": (p.rsplit("/", 1)[0] if "/" in p else "") if p else None,
                                  "name": p.rsplit("/", 1)[-1] if p else "", "direct": 0, "count": 0}
            for r in rows:
                if r["kind"] == "album" and not inside(r["path"]):
                    p = r["path"]
                    parent = p.rsplit("/", 1)[0] if "/" in p else ""
                    if parent not in folders:
                        continue
                    folders[parent]["direct"] += 1
                    file = p.rsplit("/", 1)[-1]
                    albums.append({"path": p, "parent": parent, "name": display_name(file), "file": file,
                                   "size": r["size"], "mtime": r["mtime"], "keep": True})
            # dossiers parents du dossier relu (au cas où ils manqueraient dans la base)
            anc = under
            while "/" in anc:
                anc = anc.rsplit("/", 1)[0]
                folders.setdefault(anc, {"path": anc, "parent": anc.rsplit("/", 1)[0] if "/" in anc else "",
                                         "name": anc.rsplit("/", 1)[-1], "direct": 0, "count": 0})
            folders.setdefault("", {"path": "", "parent": None, "name": "", "direct": 0, "count": 0})
        for rel, dirs, files in self._walk(ignored, under):
            if self.stop_requested.is_set():
                raise ScanStopped("Scan arrêté")   # avant toute écriture : la base reste comme avant le scan
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ("" if rel else None)
            folders[rel] = {"path": rel, "parent": parent, "name": rel.rsplit("/", 1)[-1] if rel else "",
                            "direct": len(files), "count": 0}
            for name, size, mtime in files:
                albums.append({"path": f"{rel}/{name}" if rel else name, "parent": rel,
                               "name": display_name(name), "file": name, "size": size, "mtime": mtime})
        # Garde-fou, avant toute écriture : un dossier des BD vide ou injoignable (partage réseau pas encore monté,
        # disque en veille, NAS éteint) ressemble à « tout a été supprimé ». Sans ce contrôle, Bulle effacerait
        # toute sa base (couvertures, mesures, progression) puis referait tout au scan suivant.
        if not under and not force:
            known = [r["path"] for r in self.conn.execute(
                "SELECT path FROM nodes WHERE kind='album'")]
            if len(known) >= self.SAFETY_MIN_ALBUMS:
                seen_paths = {a["path"] for a in albums}
                gone = sum(1 for p in known if p not in seen_paths)
                if not albums:
                    raise ScanAborted(f"le dossier des BD paraît vide ou injoignable ({self.root}) alors que Bulle "
                                      f"connaît {len(known)} albums : le partage n'est peut-être pas monté")
                if gone > len(known) * self.SAFETY_MAX_GONE:
                    raise ScanAborted(f"{gone} albums sur {len(known)} auraient disparu d'un coup (seulement "
                                      f"{len(albums)} trouvés) : disque ou partage réseau injoignable ?")
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
                "SELECT id, path, kind, size, mtime, format, error FROM nodes")}
            ids: dict[str, int] = {}
            added = changed = renamed = 0
            new_folders = 0   # comptés à part : « 3 nouveaux albums » ne doit pas devenir 4 parce que leur série est nouvelle
            # albums disparus de leur place : si un fichier « nouveau » a la même taille et la même date, c'est le même
            # album renommé ou déplacé ; on garde sa fiche (lecture en cours, favoris, listes, couverture choisie…)
            present = {a["path"] for a in albums}
            orphans: dict[tuple, list[dict]] = {}
            for r in existing.values():
                if r["kind"] == "album" and r["path"] not in present and r["size"] is not None:
                    orphans.setdefault((r["size"], int(round(r["mtime"] or 0))), []).append(r)
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
                            new_folders += 1
                # Albums
                for a in albums:
                    if self.stop_requested.is_set():
                        raise ScanStopped("Scan arrêté")   # ROLLBACK plus bas : rien n'est gardé de ce scan
                    parent_id = ids[a["parent"]]
                    row = existing.get(a["path"])
                    if row:
                        if abs(row["mtime"] - a["mtime"]) > 1 or row["size"] != a["size"]:
                            fmt = detect_format(self.abs_path(a["path"]), a["file"])
                            cur.execute(
                                "UPDATE nodes SET parent_id=?, name=?, name_norm=?, search_text=?, sort_key=?, "
                                "kind='album', format=?, size=?, mtime=?, page_count=NULL, error=NULL, res_w=NULL, res_h=NULL, seen=? "
                                "WHERE id=?",
                                (parent_id, a["name"], normalize(a["name"]), normalize(a["path"]),
                                 natural_key(a["name"]), fmt, a["size"], a["mtime"], gen, row["id"]))
                            invalidate.append(row["id"])
                            changed += 1
                        elif row.get("error") and not a.get("keep"):
                            # album en échec : son format a peut-être été mal lu la dernière fois (disque qui n'a pas
                            # répondu) ; on relit les premiers octets et on lui redonne sa chance s'il a changé
                            fmt = detect_format(self.abs_path(a["path"]), a["file"])
                            if fmt != row.get("format"):
                                cur.execute("UPDATE nodes SET parent_id=?, format=?, page_count=NULL, error=NULL, res_w=NULL, res_h=NULL, seen=? "
                                            "WHERE id=?", (parent_id, fmt, gen, row["id"]))
                                invalidate.append(row["id"])
                                changed += 1
                            else:
                                cur.execute("UPDATE nodes SET parent_id=?, seen=? WHERE id=?", (parent_id, gen, row["id"]))
                        else:
                            cur.execute("UPDATE nodes SET parent_id=?, seen=? WHERE id=?",
                                        (parent_id, gen, row["id"]))
                        ids[a["path"]] = row["id"]
                    elif orphans.get((a["size"], int(round(a["mtime"])))):
                        cands = orphans[(a["size"], int(round(a["mtime"])))]
                        # plusieurs candidats : même nom de fichier d'abord (dossier renommé), puis même dossier
                        best = next((c for c in cands if c["path"].rsplit("/", 1)[-1] == a["file"]), None) or \
                            next((c for c in cands if (c["path"].rsplit("/", 1)[0] if "/" in c["path"] else "") == a["parent"]), None) or \
                            cands[0]
                        cands.remove(best)
                        row = best
                        cur.execute(
                            "UPDATE nodes SET parent_id=?, path=?, name=?, name_norm=?, search_text=?, sort_key=?, "
                            "error=NULL, seen=? WHERE id=?",
                            (parent_id, a["path"], a["name"], normalize(a["name"]), normalize(a["path"]),
                             natural_key(a["name"]), gen, row["id"]))
                        ids[a["path"]] = row["id"]
                        renamed += 1
                        log.info("Renommé ou déplacé : %s → %s", row["path"], a["path"])
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
                gone_rows = cur.execute("SELECT id, kind FROM nodes WHERE seen<>?", (gen,)).fetchall()
                gone = [r["id"] for r in gone_rows]
                removed = sum(1 for r in gone_rows if r["kind"] == "album")   # albums seulement, comme « nouveaux »
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
                self.panels_clear(invalidate)
                self.on_invalidate(invalidate)
            except Exception:  # noqa: BLE001
                log.exception("Invalidation du cache")
        result = {"albums": len(albums), "folders": max(0, len(folders) - 1), "added": added,
                  "new_folders": new_folders, "removed": removed, "changed": changed, "renamed": renamed}
        log.info("Scan terminé%s : %%(albums)d albums, %%(folders)d dossiers, +%%(added)d, -%%(removed)d, "
                 "~%%(changed)d modifiés" % (f" ({under})" if under else ""), result)

        return result

    # -- lecture ---------------------------------------------------------------
    def refresh_file(self, node_id: int) -> Optional[dict]:
        """Relit un album sur le disque : taille, date, vrai format (d'après ses premiers octets), erreur effacée.
        Pour rattraper un raté du scan (disque réseau lent qui n'a pas répondu, fichier remplacé depuis…).
        Renvoie le nœud à jour, ou None si le fichier n'existe plus."""
        n = self.node(node_id)
        if not n or n["kind"] != "album":
            return n
        path = self.abs_path(n["path"])
        try:
            st = os.stat(path)
        except OSError:
            return None
        fmt = detect_format(path, os.path.basename(path))
        with self._write_lock:
            self.conn.execute("UPDATE nodes SET format=?, size=?, mtime=?, page_count=NULL, error=NULL, res_w=NULL, res_h=NULL WHERE id=?",
                              (fmt, st.st_size, st.st_mtime, node_id))
            self.conn.commit()
        self.panels_clear([node_id])
        return self.node(node_id)

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

    # -- progression (par profil) -----------------------------------------------
    @staticmethod
    def is_complete(page: int, page_count: Optional[int], threshold: float = 1.0) -> bool:
        """Lu si on a atteint la dernière page, ou la part `threshold` de l'album (ex. 0.9 = 90 %)."""
        if not page_count:
            return False
        needed = min(page_count - 1, max(0, int(math.ceil(page_count * threshold)) - 1))
        return page >= needed

    def all_progress(self, profile_id: int = DEFAULT_PROFILE) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.node_id, p.page, p.page_count, p.completed, p.updated_at, n.path "
            "FROM progress p JOIN nodes n ON n.id=p.node_id WHERE p.profile_id=?", (profile_id,)).fetchall()
        return [dict(r) for r in rows]

    def progress(self, node_id: int, profile_id: int = DEFAULT_PROFILE) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM progress WHERE profile_id=? AND node_id=?",
                              (profile_id, node_id)).fetchone()
        return dict(r) if r else None

    def set_progress(self, node_id: int, page: int, page_count: Optional[int],
                     completed: Optional[bool] = None, profile_id: int = DEFAULT_PROFILE,
                     threshold: float = 1.0) -> dict:
        if page_count is None:
            page_count = (self.node(node_id) or {}).get("page_count")
        page = max(0, int(page))
        if page_count:
            page = min(page, page_count - 1)
        if completed is None:
            completed = self.is_complete(page, page_count, threshold)
        before = self.progress(node_id, profile_id)
        now = time.time()
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO progress(profile_id, node_id, page, page_count, completed, updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(profile_id, node_id) DO UPDATE SET page=excluded.page, "
                "page_count=excluded.page_count, completed=excluded.completed, updated_at=excluded.updated_at",
                (profile_id, node_id, page, page_count, 1 if completed else 0, now))
            self._log_reading(profile_id, node_id, before, page, completed, now)
            self.conn.commit()
        return self.progress(node_id, profile_id)

    # -- journal de lecture (pour l'historique et la page Activité) -----------------
    LOG_GAP = 300   # au-delà de 5 minutes sans tourner de page, on considère que la lecture s'était arrêtée

    def _log_reading(self, profile_id: int, node_id: int, before: Optional[dict], page: int, completed: bool,
                     now: float) -> None:
        """Une ligne par profil, album et jour : pages tournées, temps passé (somme des écarts entre deux pages, chacun
        plafonné à 5 min), et si l'album a été terminé ce jour-là. Un saut (barre de progression, reprise) ne compte pas
        comme des pages lues."""
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        delta = 0 if before is None else abs(page - int(before["page"]))
        pages = delta if 0 < delta <= 5 else 0
        last = float(before["updated_at"]) if before else 0
        seconds = int(min(self.LOG_GAP, now - last)) if last and pages else 0
        finished = 1 if completed and not (before and before["completed"]) else 0
        self.conn.execute(
            "INSERT INTO reading_log(profile_id, node_id, day, pages, seconds, finished, first_at, last_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(profile_id, node_id, day) DO UPDATE SET pages=pages+excluded.pages, "
            "seconds=seconds+excluded.seconds, finished=MAX(finished, excluded.finished), last_at=excluded.last_at",
            (profile_id, node_id, day, pages, seconds, finished, now, now))

    def reading_now(self, profile_id: int, limit: int = 60) -> list[dict]:
        """Albums en cours (progression sans être terminés), les plus récents d'abord."""
        rows = self.conn.execute(
            self._ALBUM_WITH_PROGRESS + "WHERE p.completed=0 ORDER BY p.updated_at DESC LIMIT ?",
            (profile_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def activity(self, profile_id: int, months: int = 12) -> dict:
        """Chiffres de la page Activité pour un profil : totaux, par mois, 14 derniers jours, séries en cours."""
        c = self.conn
        tot = c.execute("SELECT COALESCE(SUM(pages),0) AS pages, COALESCE(SUM(seconds),0) AS seconds, "
                        "COALESCE(SUM(finished),0) AS finished, COUNT(DISTINCT day) AS days FROM reading_log WHERE profile_id=?",
                        (profile_id,)).fetchone()
        since30 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
        last30 = c.execute("SELECT COALESCE(SUM(pages),0) AS pages, COALESCE(SUM(seconds),0) AS seconds, "
                           "COALESCE(SUM(finished),0) AS finished, COUNT(DISTINCT day) AS days FROM reading_log "
                           "WHERE profile_id=? AND day>=?", (profile_id, since30)).fetchone()
        by_month = [dict(r) for r in c.execute(
            "SELECT substr(day,1,7) AS month, SUM(pages) AS pages, SUM(seconds) AS seconds, SUM(finished) AS finished, "
            "COUNT(DISTINCT day) AS days FROM reading_log WHERE profile_id=? GROUP BY month ORDER BY month DESC LIMIT ?",
            (profile_id, months))][::-1]
        since14 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 13 * 86400))
        by_day = {r["day"]: dict(r) for r in c.execute(
            "SELECT day, SUM(pages) AS pages, SUM(seconds) AS seconds, SUM(finished) AS finished FROM reading_log "
            "WHERE profile_id=? AND day>=? GROUP BY day", (profile_id, since14))}
        days = []
        for i in range(13, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            days.append(dict(by_day.get(d) or {"day": d, "pages": 0, "seconds": 0, "finished": 0}))
        # séries en cours : dossier parent des albums commencés mais pas terminés
        series = [dict(r) for r in c.execute(
            "SELECT f.id, f.name, f.album_count, COUNT(*) AS reading, MAX(p.updated_at) AS last_at, "
            "SUM(CASE WHEN q.completed=1 THEN 1 ELSE 0 END) AS done "
            "FROM progress p JOIN nodes n ON n.id=p.node_id JOIN nodes f ON f.id=n.parent_id "
            "LEFT JOIN progress q ON q.profile_id=p.profile_id AND q.node_id IN (SELECT id FROM nodes WHERE parent_id=f.id) "
            "WHERE p.profile_id=? AND p.completed=0 AND f.path<>'' GROUP BY f.id ORDER BY last_at DESC LIMIT 12",
            (profile_id,))]
        # albums les plus lus (temps) sur 30 jours
        top = [dict(r) for r in c.execute(
            "SELECT n.id, n.name, SUM(l.seconds) AS seconds, SUM(l.pages) AS pages FROM reading_log l JOIN nodes n ON n.id=l.node_id "
            "WHERE l.profile_id=? AND l.day>=? GROUP BY n.id ORDER BY seconds DESC LIMIT 5", (profile_id, since30))]
        return {"total": dict(tot), "last30": dict(last30), "months": by_month, "days": days, "series": series, "top": top}

    def activity_by_profile(self, days: int = 30) -> list[dict]:
        since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
        return [dict(r) for r in self.conn.execute(
            "SELECT pr.id, pr.name, pr.avatar, COALESCE(SUM(l.pages),0) AS pages, COALESCE(SUM(l.seconds),0) AS seconds, "
            "COALESCE(SUM(l.finished),0) AS finished, MAX(l.last_at) AS last_at FROM profiles pr "
            "LEFT JOIN reading_log l ON l.profile_id=pr.id AND l.day>=? GROUP BY pr.id ORDER BY pr.id", (since,))]

    def clear_progress(self, node_id: int, profile_id: int = DEFAULT_PROFILE) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM progress WHERE profile_id=? AND node_id=?", (profile_id, node_id))
            self.conn.commit()

    def set_cover_page(self, node_id: int, page: Optional[int]) -> None:
        """Page choisie comme couverture (None = la première). Seulement dans la base : le fichier n'est pas touché."""
        with self._write_lock:
            self.conn.execute("UPDATE nodes SET cover_page=? WHERE id=?", (page, node_id))
            self.conn.commit()

    def set_color(self, node_id: int, color: Optional[str]) -> None:
        with self._write_lock:
            self.conn.execute("UPDATE nodes SET color=? WHERE id=?", (color, node_id))
            self.conn.commit()

    def colors_for(self, node_ids: list[int]) -> dict[int, Optional[str]]:
        return {k: v["color"] for k, v in self.cover_meta_for(node_ids).items()}

    def cover_meta_for(self, node_ids: list[int]) -> dict[int, dict]:
        """Pour des albums (couvertures de dossiers) : id → {color, mtime}."""
        out: dict[int, dict] = {}
        for i in range(0, len(node_ids), 500):
            chunk = node_ids[i:i + 500]
            for r in self.conn.execute(f"SELECT id, color, mtime FROM nodes WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                out[r["id"]] = {"id": r["id"], "color": r["color"], "mtime": r["mtime"]}
        return out

    # -- qualité (HD / SD) ------------------------------------------------------
    def set_resolution(self, node_id: int, width: int, height: int) -> None:
        """Taille des pages d'un album (0×0 = pas mesurable, ex. PDF) ; remise à zéro quand le fichier change."""
        with self._write_lock:
            self.conn.execute("UPDATE nodes SET res_w=?, res_h=? WHERE id=?", (int(width), int(height), node_id))
            self.conn.commit()

    def albums_for_measure(self, ids: Optional[list[int]] = None, limit: Optional[int] = None,
                           remeasure: bool = False) -> list[dict]:
        """Albums à mesurer : ceux demandés (ids), sinon les premiers de la bibliothèque dans l'ordre des dossiers."""
        cols = "id, path, name, format, mtime, size, page_count, error, cover_page, res_w"
        if ids:
            out = []
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                out += [dict(r) for r in self.conn.execute(
                    f"SELECT {cols} FROM nodes WHERE kind='album' AND id IN ({','.join('?' * len(chunk))})", chunk)]
            order = {v: k for k, v in enumerate(ids)}
            out.sort(key=lambda r: order.get(r["id"], 0))
        else:
            out = [dict(r) for r in self.conn.execute(
                f"SELECT {cols} FROM nodes WHERE kind='album' ORDER BY path COLLATE NOCASE")]
        if not remeasure:
            out = [r for r in out if r["res_w"] is None]
        return out[:limit] if limit else out

    def quality_by_dir(self, hd_min: int) -> dict[str, list[int]]:
        """Dossier (chemin) → [albums HD, albums SD] directement dedans, pour les albums déjà mesurés."""
        out: dict[str, list[int]] = {}
        for r in self.conn.execute("SELECT path, res_w, res_h FROM nodes WHERE kind='album' AND res_w > 0"):
            d = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
            c = out.setdefault(d, [0, 0])
            c[0 if max(r["res_w"], r["res_h"]) >= hd_min else 1] += 1
        return out

    def quality_stats(self, hd_min: int) -> dict:
        r = self.conn.execute(
            "SELECT SUM(CASE WHEN res_w > 0 AND MAX(res_w, res_h) >= ? THEN 1 ELSE 0 END) AS hd, "
            "SUM(CASE WHEN res_w > 0 AND MAX(res_w, res_h) < ? THEN 1 ELSE 0 END) AS sd, "
            "SUM(CASE WHEN res_w IS NULL THEN 1 ELSE 0 END) AS todo, "
            "SUM(CASE WHEN res_w = 0 THEN 1 ELSE 0 END) AS na FROM nodes WHERE kind='album'", (hd_min, hd_min)).fetchone()
        return {k: r[k] or 0 for k in ("hd", "sd", "todo", "na")}

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

    _ALBUM_WITH_PROGRESS = ("SELECT n.*, p.page AS p_page, p.page_count AS p_count, p.completed AS p_completed, "
                            "p.updated_at AS p_updated FROM nodes n "
                            "LEFT JOIN progress p ON p.node_id=n.id AND p.profile_id=? ")

    def continue_reading(self, limit: int = 20, profile_id: int = DEFAULT_PROFILE) -> list[dict]:
        rows = self.conn.execute(
            self._ALBUM_WITH_PROGRESS + "WHERE p.completed=0 ORDER BY p.updated_at DESC LIMIT ?",
            (profile_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 24, profile_id: int = DEFAULT_PROFILE) -> list[dict]:
        rows = self.conn.execute(
            self._ALBUM_WITH_PROGRESS + "WHERE n.kind='album' ORDER BY n.added_at DESC, n.mtime DESC LIMIT ?",
            (profile_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 120, profile_id: int = DEFAULT_PROFILE) -> list[dict]:
        words = [w for w in normalize(query).split(" ") if w]
        if not words:
            return []
        where = " AND ".join("search_text LIKE ? ESCAPE '\\'" for _ in words)
        params = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
        rows = self.conn.execute(
            self._ALBUM_WITH_PROGRESS + f"WHERE n.path<>'' AND {where} "
            f"ORDER BY CASE n.kind WHEN 'folder' THEN 0 ELSE 1 END, n.sort_key LIMIT ?",
            (profile_id, *params, limit * 4)).fetchall()
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

    def node_by_path(self, path: str) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM nodes WHERE path=?", (path.strip("/"),)).fetchone()
        return dict(r) if r else None

    def albums_under(self, folder_path: str) -> list[dict]:
        """Albums d'un dossier et de ses sous-dossiers."""
        prefix = folder_path.strip("/")
        rows = self.conn.execute(
            "SELECT id, path, format, mtime, page_count, error, cover_page FROM nodes WHERE kind='album' AND (path LIKE ? OR ?='') "
            "ORDER BY sort_key", (prefix + "/%", prefix)).fetchall()
        return [dict(r) for r in rows]

    def albums_without(self, predicate_sql: str = "1=1") -> list[dict]:
        rows = self.conn.execute(
            f"SELECT id, path, format, mtime, page_count, error, cover_page FROM nodes WHERE kind='album' AND {predicate_sql} "
            "ORDER BY sort_key").fetchall()
        return [dict(r) for r in rows]

    # -- fichiers et dossiers retirés de Bulle (restent sur le disque) -----------------
    def ignored_paths(self) -> set:
        return {str(p).strip("/") for p in (self.get_settings(None).get("ignored_paths") or []) if str(p).strip("/")}

    def ignore_node(self, node_id: int) -> dict:
        """Retire un album ou un dossier de Bulle : enlevé de la base (progression, listes… comprises) et ignoré par les
        scans suivants. Le fichier n'est ni supprimé ni modifié sur le disque. Annulable avec unignore_path()."""
        n = self.node(node_id)
        if not n or not n["path"]:
            raise ValueError("Rien à retirer")
        path = n["path"].strip("/")
        rows = self.conn.execute("SELECT id, path, kind FROM nodes").fetchall()
        gone = [r for r in rows if r["path"] == path or r["path"].startswith(path + "/")]
        ids = [r["id"] for r in gone]
        n_albums = sum(1 for r in gone if r["kind"] == "album")
        with self._write_lock:
            paths = sorted(self.ignored_paths() | {path})
            self.set_settings({"ignored_paths": paths}, None)
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                self.conn.execute(f"DELETE FROM nodes WHERE id IN ({','.join('?' * len(chunk))})", chunk)
            # dossiers parents : un album de moins ; un dossier devenu vide disparaît aussi (comme au scan)
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            while True:
                self.conn.execute("UPDATE nodes SET album_count = MAX(0, album_count - ?) WHERE path=? AND kind='folder'",
                                  (n_albums, parent))
                r = self.conn.execute("SELECT id, album_count FROM nodes WHERE path=?", (parent,)).fetchone()
                if parent and r and r["album_count"] <= 0:
                    self.conn.execute("DELETE FROM nodes WHERE id=?", (r["id"],))
                    ids.append(r["id"])
                if not parent:
                    break
                parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
            # couvertures de dossiers qui pointaient sur un album retiré : premier album restant du dossier
            for f in self.conn.execute("SELECT id, path FROM nodes WHERE kind='folder' AND cover_id IS NOT NULL "
                                       "AND cover_id NOT IN (SELECT id FROM nodes)").fetchall():
                first = None
                for a in self.conn.execute("SELECT id, path FROM nodes WHERE kind='album' ORDER BY sort_key").fetchall():
                    if f["path"] == "" or a["path"].startswith(f["path"] + "/"):
                        first = a["id"]
                        break
                self.conn.execute("UPDATE nodes SET cover_id=? WHERE id=?", (first, f["id"]))
            self.conn.commit()
        try:
            self.panels_clear(ids)
            self.on_invalidate(ids)
        except Exception:  # noqa: BLE001
            log.exception("Invalidation du cache")
        return {"path": path, "albums": n_albums, "ids": ids}

    def unignore_path(self, path: str) -> list:
        """Remet un chemin retiré : il réapparaîtra au prochain scan."""
        path = str(path).strip("/")
        with self._write_lock:
            paths = sorted(p for p in self.ignored_paths() if p != path)
            self.set_settings({"ignored_paths": paths}, None)
        return paths

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

    # -- Bédéthèque ----------------------------------------------------------------
    def bdt_cache_get(self, url: str) -> Optional[tuple[float, bytes]]:
        r = self.conn.execute("SELECT fetched_at, body FROM bdt_cache WHERE url=?", (url,)).fetchone()
        return (r["fetched_at"], r["body"]) if r else None

    def bdt_cache_put(self, url: str, body: bytes) -> None:
        with self._write_lock:
            self.conn.execute("INSERT OR REPLACE INTO bdt_cache(url, fetched_at, body) VALUES(?,?,?)",
                              (url, time.time(), body))
            self.conn.commit()

    def bdt_series_get(self, folder_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM bdt_series WHERE folder_id=?", (folder_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["data"] = json.loads(d["data"])
        return d

    def bdt_series_set(self, folder_id: int, series: dict, score: Optional[float], manual: bool,
                       present: Optional[int] = None, total: Optional[int] = None) -> None:
        with self._write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO bdt_series(folder_id, bdt_id, url, title, genre, status, years, tomes_count, "
                "data, score, manual, detailed, present, total, fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (folder_id, series.get("id"), series["url"], series.get("title"), series.get("genre"),
                 series.get("status"), series.get("years"), series.get("tomes_count"),
                 json.dumps(series, ensure_ascii=False), score, 1 if manual else 0,
                 1 if series.get("detailed") else 0, present, total, time.time()))
            self.conn.commit()

    def bdt_series_for(self, folder_ids: list[int]) -> dict[int, dict]:
        """Résumé des liens Bédéthèque pour plusieurs dossiers (cartes des dossiers)."""
        if not folder_ids:
            return {}
        out = {}
        for i in range(0, len(folder_ids), 500):
            chunk = folder_ids[i:i + 500]
            rows = self.conn.execute(
                f"SELECT folder_id, title, url, status, present, total, score, manual FROM bdt_series "
                f"WHERE folder_id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
            for r in rows:
                out[r["folder_id"]] = dict(r)
        return out

    def bdt_series_delete(self, folder_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM bdt_series WHERE folder_id=?", (folder_id,))
            self.conn.execute("DELETE FROM bdt_albums WHERE folder_id=?", (folder_id,))
            self.conn.commit()

    def bdt_series_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.folder_id, s.bdt_id, s.url, s.title, s.genre, s.status, s.years, s.tomes_count, s.score, "
            "s.manual, s.detailed, s.present, s.total, s.fetched_at, n.name AS folder_name, n.path AS folder_path, "
            "n.album_count "
            "FROM bdt_series s JOIN nodes n ON n.id=s.folder_id ORDER BY n.sort_key").fetchall()
        return [dict(r) for r in rows]

    def bdt_albums_set(self, folder_id: int, matches: list[dict]) -> None:
        """matches : [{id, how, album}] ; remplace les métadonnées des albums du dossier."""
        with self._write_lock:
            self.conn.execute("DELETE FROM bdt_albums WHERE folder_id=?", (folder_id,))
            now = time.time()
            for m in matches:
                a = m["album"]
                self.conn.execute(
                    "INSERT OR REPLACE INTO bdt_albums(node_id, folder_id, url, number, kind, title, year, data, how, "
                    "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (m["id"], folder_id, a.get("url"), a.get("number"), a.get("kind"), a.get("title"), a.get("year"),
                     json.dumps(a, ensure_ascii=False), m.get("how"), now))
            self.conn.commit()

    def bdt_albums_for_folder(self, folder_id: int) -> dict[int, dict]:
        rows = self.conn.execute("SELECT * FROM bdt_albums WHERE folder_id=?", (folder_id,)).fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data"])
            out[d["node_id"]] = d
        return out

    # -- cases détectées (lecture case par case) -------------------------------
    def panels_get(self, node_id: int, page: int) -> Optional[dict]:
        r = self.conn.execute("SELECT data FROM panels WHERE node_id=? AND page=?", (node_id, page)).fetchone()
        return json.loads(r["data"]) if r else None

    def panels_set(self, node_id: int, page: int, data: dict) -> None:
        with self._write_lock:
            self.conn.execute("INSERT OR REPLACE INTO panels(node_id, page, data) VALUES(?,?,?)",
                              (node_id, page, json.dumps(data)))
            self.conn.commit()

    def panels_clear(self, node_ids) -> None:
        ids = list(node_ids)
        if not ids:
            return
        with self._write_lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                self.conn.execute(f"DELETE FROM panels WHERE node_id IN ({','.join('?' * len(chunk))})", chunk)
            self.conn.commit()

    def bdt_album_update(self, node_id: int, **fields) -> None:
        """Complète les données Bédéthèque d'un album (ex. résumé)."""
        row = self.bdt_album(node_id)
        if not row:
            return
        data = row["data"]
        data.update(fields)
        with self._write_lock:
            self.conn.execute("UPDATE bdt_albums SET data=?, updated_at=? WHERE node_id=?",
                              (json.dumps(data, ensure_ascii=False), time.time(), node_id))
            self.conn.commit()

    def bdt_album(self, node_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM bdt_albums WHERE node_id=?", (node_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["data"] = json.loads(d["data"])
        return d

    # -- Bédéthèque : dossiers de one shots ------------------------------------------
    def bdt_folder_mode(self, folder_id: int) -> Optional[str]:
        r = self.conn.execute("SELECT mode FROM bdt_folder_mode WHERE folder_id=?", (folder_id,)).fetchone()
        return r["mode"] if r else None

    def bdt_folder_mode_set(self, folder_id: int, mode: Optional[str]) -> None:
        with self._write_lock:
            if mode:
                self.conn.execute("INSERT OR REPLACE INTO bdt_folder_mode(folder_id, mode) VALUES(?,?)", (folder_id, mode))
            else:
                self.conn.execute("DELETE FROM bdt_folder_mode WHERE folder_id=?", (folder_id,))
            self.conn.commit()

    def bdt_folder_modes(self) -> dict[int, str]:
        return {r["folder_id"]: r["mode"] for r in self.conn.execute("SELECT folder_id, mode FROM bdt_folder_mode")}

    def bdt_oneshot_set(self, node_id: int, folder_id: int, status: str, query: Optional[str] = None,
                        score: Optional[float] = None, manual: bool = False, series: Optional[dict] = None,
                        candidates: Optional[list] = None, album: Optional[dict] = None) -> None:
        """Résultat de la recherche d'un one shot ; `album` (données Bédéthèque de l'album) va dans bdt_albums."""
        now = time.time()
        with self._write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO bdt_oneshots(node_id, folder_id, status, query, score, manual, series_url, "
                "series_title, candidates, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (node_id, folder_id, status, query, score, 1 if manual else 0, (series or {}).get("url"),
                 (series or {}).get("title"), json.dumps(candidates or [], ensure_ascii=False), now))
            self.conn.execute("DELETE FROM bdt_albums WHERE node_id=?", (node_id,))
            if album is not None:
                self.conn.execute(
                    "INSERT INTO bdt_albums(node_id, folder_id, url, number, kind, title, year, data, how, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (node_id, folder_id, album.get("url"), album.get("number"), album.get("kind"), album.get("title"),
                     album.get("year"), json.dumps(album, ensure_ascii=False), "oneshot", now))
            self.conn.commit()

    def bdt_oneshot_delete(self, node_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM bdt_oneshots WHERE node_id=?", (node_id,))
            self.conn.execute("DELETE FROM bdt_albums WHERE node_id=?", (node_id,))
            self.conn.commit()

    def bdt_oneshots_clear(self, folder_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM bdt_oneshots WHERE folder_id=?", (folder_id,))
            self.conn.execute("DELETE FROM bdt_albums WHERE folder_id=?", (folder_id,))
            self.conn.commit()

    def bdt_oneshots_for(self, folder_id: int) -> dict[int, dict]:
        out = {}
        for r in self.conn.execute("SELECT * FROM bdt_oneshots WHERE folder_id=?", (folder_id,)):
            d = dict(r)
            d["candidates"] = json.loads(d["candidates"] or "[]")
            out[d["node_id"]] = d
        return out

    def bdt_oneshot_counts(self) -> dict[int, dict]:
        """Par dossier de one shots : nombre d'albums trouvés / à choisir / introuvables."""
        out: dict[int, dict] = {}
        for r in self.conn.execute("SELECT o.folder_id, o.status, COUNT(*) AS n FROM bdt_oneshots o "
                                   "JOIN nodes a ON a.id=o.node_id AND a.parent_id=o.folder_id GROUP BY o.folder_id, o.status"):
            out.setdefault(r["folder_id"], {"ok": 0, "ambiguous": 0, "not_found": 0})[r["status"]] = r["n"]
        return out

    def bdt_index_age(self, letter: str) -> Optional[float]:
        r = self.conn.execute("SELECT fetched_at FROM bdt_index_letters WHERE letter=?", (letter,)).fetchone()
        return (time.time() - r["fetched_at"]) if r else None

    def bdt_index_rows(self, letter: str) -> list[dict]:
        rows = self.conn.execute("SELECT id, name, name_norm, url FROM bdt_index WHERE letter=?", (letter,)).fetchall()
        return [dict(r) for r in rows]

    def bdt_index_store(self, letter: str, rows: list[dict], norm) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM bdt_index WHERE letter=?", (letter,))
            self.conn.executemany("INSERT OR REPLACE INTO bdt_index(id, letter, name, name_norm, url) VALUES(?,?,?,?,?)",
                                  [(r["id"], letter, r["name"], norm(r["name"]), r["url"]) for r in rows])
            self.conn.execute("INSERT OR REPLACE INTO bdt_index_letters(letter, fetched_at, count) VALUES(?,?,?)",
                              (letter, time.time(), len(rows)))
            self.conn.commit()

    def bdt_index_stats(self) -> dict:
        rows = self.conn.execute("SELECT letter, fetched_at, count FROM bdt_index_letters ORDER BY letter").fetchall()
        return {r["letter"]: {"fetched_at": r["fetched_at"], "count": r["count"]} for r in rows}

    # -- listes (favoris, à lire, personnalisées) ------------------------------------
    def lists(self, profile_id: int) -> list[dict]:
        """Listes du profil, en créant « Favoris » et « À lire » si besoin."""
        rows = self.conn.execute("SELECT kind FROM lists WHERE profile_id=?", (profile_id,)).fetchall()
        kinds = {r["kind"] for r in rows}
        with self._write_lock:
            for kind, name in (("favorites", "Favoris"), ("readlater", "À lire")):
                if kind not in kinds:
                    self.conn.execute("INSERT INTO lists(profile_id, name, kind, created_at) VALUES(?,?,?,?)",
                                      (profile_id, name, kind, time.time()))
            self.conn.commit()
        rows = self.conn.execute(
            "SELECT l.id, l.name, l.kind, l.created_at, (SELECT COUNT(*) FROM list_items i WHERE i.list_id=l.id) AS count "
            "FROM lists l WHERE l.profile_id=? ORDER BY CASE l.kind WHEN 'favorites' THEN 0 WHEN 'readlater' THEN 1 ELSE 2 END, "
            "l.created_at", (profile_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_get(self, list_id: int, profile_id: int) -> Optional[dict]:
        r = self.conn.execute("SELECT * FROM lists WHERE id=? AND profile_id=?", (list_id, profile_id)).fetchone()
        return dict(r) if r else None

    def list_create(self, profile_id: int, name: str) -> dict:
        with self._write_lock:
            cur = self.conn.execute("INSERT INTO lists(profile_id, name, kind, created_at) VALUES(?,?,'custom',?)",
                                    (profile_id, name, time.time()))
            self.conn.commit()
            return self.list_get(cur.lastrowid, profile_id)

    def list_rename(self, list_id: int, profile_id: int, name: str) -> None:
        with self._write_lock:
            self.conn.execute("UPDATE lists SET name=? WHERE id=? AND profile_id=?", (name, list_id, profile_id))
            self.conn.commit()

    def list_delete(self, list_id: int, profile_id: int) -> bool:
        with self._write_lock:
            cur = self.conn.execute("DELETE FROM lists WHERE id=? AND profile_id=? AND kind='custom'", (list_id, profile_id))
            self.conn.commit()
            return cur.rowcount > 0

    def list_items(self, list_id: int, profile_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT n.*, i.added_at AS list_added, p.page AS p_page, p.page_count AS p_count, p.completed AS p_completed, "
            "p.updated_at AS p_updated FROM list_items i JOIN nodes n ON n.id=i.node_id "
            "LEFT JOIN progress p ON p.node_id=n.id AND p.profile_id=? WHERE i.list_id=? ORDER BY i.added_at DESC",
            (profile_id, list_id)).fetchall()
        return [dict(r) for r in rows]

    def list_add(self, list_id: int, node_id: int) -> None:
        with self._write_lock:
            self.conn.execute("INSERT OR IGNORE INTO list_items(list_id, node_id, added_at) VALUES(?,?,?)",
                              (list_id, node_id, time.time()))
            self.conn.commit()

    def list_remove(self, list_id: int, node_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM list_items WHERE list_id=? AND node_id=?", (list_id, node_id))
            self.conn.commit()

    def list_membership(self, node_id: int, profile_id: int) -> list[int]:
        rows = self.conn.execute("SELECT i.list_id FROM list_items i JOIN lists l ON l.id=i.list_id "
                                 "WHERE i.node_id=? AND l.profile_id=?", (node_id, profile_id)).fetchall()
        return [r["list_id"] for r in rows]

    def favorites_ids(self, profile_id: int) -> set[int]:
        rows = self.conn.execute("SELECT i.node_id FROM list_items i JOIN lists l ON l.id=i.list_id "
                                 "WHERE l.profile_id=? AND l.kind='favorites'", (profile_id,)).fetchall()
        return {r["node_id"] for r in rows}

    def history(self, profile_id: int, limit: int = 60) -> list[dict]:
        rows = self.conn.execute(
            self._ALBUM_WITH_PROGRESS + "WHERE p.completed=1 ORDER BY p.updated_at DESC LIMIT ?",
            (profile_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def random_album(self, unread_only: bool = True, profile_id: int = DEFAULT_PROFILE) -> Optional[dict]:
        if unread_only:
            r = self.conn.execute(
                "SELECT n.* FROM nodes n LEFT JOIN progress p ON p.node_id=n.id AND p.profile_id=? "
                "WHERE n.kind='album' AND n.error IS NULL AND p.node_id IS NULL ORDER BY RANDOM() LIMIT 1",
                (profile_id,)).fetchone()
            if r:
                return dict(r)
        r = self.conn.execute("SELECT * FROM nodes WHERE kind='album' AND error IS NULL ORDER BY RANDOM() LIMIT 1").fetchone()
        return dict(r) if r else None

    def random_covers(self, n: int = 60) -> list[dict]:
        """Albums au hasard ayant une couverture (pour la mosaïque de fond)."""
        rows = self.conn.execute(
            "SELECT id, path, mtime, color FROM nodes WHERE kind='album' AND error IS NULL AND page_count IS NOT NULL "
            "ORDER BY RANDOM() LIMIT ?", (max(1, min(400, n)),)).fetchall()
        return [dict(r) for r in rows]

    def folders_with_albums(self) -> list[dict]:
        """Dossiers contenant directement des albums (candidats à l'analyse Bédéthèque)."""
        rows = self.conn.execute(
            "SELECT f.id, f.name, f.path, f.album_count, (SELECT COUNT(*) FROM nodes a WHERE a.parent_id=f.id AND "
            "a.kind='album') AS direct FROM nodes f WHERE f.kind='folder' AND f.path<>'' ORDER BY f.sort_key").fetchall()
        return [dict(r) for r in rows if r["direct"] > 0]

    def stats(self, profile_id: int = DEFAULT_PROFILE) -> dict:
        r = self.conn.execute(
            "SELECT SUM(CASE WHEN kind='album' THEN 1 ELSE 0 END) AS albums, "
            "SUM(CASE WHEN kind='folder' AND path<>'' THEN 1 ELSE 0 END) AS folders, "
            "SUM(CASE WHEN kind='album' THEN size ELSE 0 END) AS size, "
            "SUM(CASE WHEN kind='album' AND error IS NOT NULL THEN 1 ELSE 0 END) AS errors FROM nodes").fetchone()
        p = self.conn.execute(
            "SELECT SUM(completed) AS done, SUM(CASE WHEN completed=0 THEN 1 ELSE 0 END) AS reading "
            "FROM progress WHERE profile_id=?", (profile_id,)).fetchone()
        last = self.conn.execute("SELECT value FROM meta WHERE key='last_scan'").fetchone()
        return {"albums": r["albums"] or 0, "folders": r["folders"] or 0, "size": r["size"] or 0, "errors": r["errors"] or 0,
                "read": p["done"] or 0, "reading": p["reading"] or 0,
                "last_scan": float(last["value"]) if last else None}
