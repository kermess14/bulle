"""Ouverture des albums (CBZ / CBR / PDF / 7z / tar), redimensionnement JPEG et cache disque."""
from __future__ import annotations

import glob
import io
import logging
import math
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from collections import defaultdict
from typing import Optional

from PIL import Image, ImageFile, ImageFilter, ImageOps

from .library import natural_sort_key

log = logging.getLogger("bulle.comics")

ImageFile.LOAD_TRUNCATED_IMAGES = True  # une page légèrement abîmée s'affiche quand même
Image.MAX_IMAGE_PIXELS = 400_000_000

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".gif", ".webp", ".bmp", ".avif", ".jxl", ".tif", ".tiff", ".heic"}
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jpe": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".avif": "image/avif",
        ".jxl": "image/jxl", ".tif": "image/tiff", ".tiff": "image/tiff", ".heic": "image/heic"}

# Largeurs servies : arrondies au multiple de 100 supérieur, entre MIN_WIDTH et MAX_WIDTH (cache borné).
MIN_WIDTH, MAX_WIDTH, WIDTH_STEP = 300, 3000, 100
COVER_WIDTH = 600
PDF_ORIGINAL_WIDTH = 2400
JPEG_QUALITY = 90
# Profils de qualité réglables : (qualité JPEG, sous-échantillonnage de la couleur : 0 = aucun, 2 = 4:2:0)
QUALITY_PROFILES = {"eco": (80, 2), "normal": (90, 0), "max": (95, 0)}
MAX_EXTRACTED = 8  # nombre d'archives CBR/7z gardées décompressées sur le disque

# Outils externes pour les RAR / 7z, par ordre de préférence.
EXTRACT_TOOLS = (
    ("unar", ["unar", "-q", "-f", "-D", "-o", "{dest}", "{archive}"]),
    ("unrar", ["unrar", "x", "-y", "-inul", "-o+", "{archive}", "{dest}/"]),
    ("7z", ["7z", "x", "-y", "-bd", "-bso0", "-bsp0", "-o{dest}", "{archive}"]),
    ("7za", ["7za", "x", "-y", "-bd", "-bso0", "-bsp0", "-o{dest}", "{archive}"]),
    ("7zz", ["7zz", "x", "-y", "-bd", "-bso0", "-bsp0", "-o{dest}", "{archive}"]),
    ("bsdtar", ["bsdtar", "-xf", "{archive}", "-C", "{dest}"]),
)

try:  # PDF : pypdfium2 (installé par requirements.txt) …
    import pypdfium2 as pdfium
except Exception:  # noqa: BLE001
    pdfium = None
try:  # … ou PyMuPDF si présent …
    import fitz  # type: ignore
except Exception:  # noqa: BLE001
    fitz = None
PDFTOPPM = shutil.which("pdftoppm")  # … ou poppler en dernier recours.
_pdf_lock = threading.Lock()  # pdfium n'aime pas être appelé depuis plusieurs threads à la fois


class AlbumError(Exception):
    """Erreur lisible par l'utilisateur (affichée dans la fiche de l'album)."""


def is_image_name(name: str) -> bool:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    if not base or base.startswith(".") or base.startswith("._") or base.lower() == "thumbs.db":
        return False
    if "__MACOSX/" in name.replace("\\", "/"):
        return False
    return os.path.splitext(base)[1].lower() in IMAGE_EXT


def sort_pages(names: list[str]) -> list[str]:
    return sorted(names, key=lambda n: natural_sort_key(n.replace("\\", "/")))


def pick_width(w: Optional[int]) -> int:
    """0 = original ; sinon arrondi au multiple de 100 supérieur (jamais plus petit que demandé)."""
    if not w or w <= 0:
        return 0
    w = max(MIN_WIDTH, min(MAX_WIDTH, int(w)))
    return int(math.ceil(w / WIDTH_STEP) * WIDTH_STEP)


# ----------------------------------------------------------------------------
# Les différents formats
# ----------------------------------------------------------------------------
class Album:
    fmt = "?"

    def __init__(self, path: str):
        self.path = path
        self.pages: list[str] = []

    def read(self, index: int) -> tuple[bytes, str]:
        """Octets d'origine de la page + extension (ex. '.jpg')."""
        raise NotImplementedError

    def render(self, index: int, width: int) -> Image.Image:
        """Image PIL de la page (utilisé pour les PDF, qui n'ont pas de « fichier » par page)."""
        data, _ = self.read(index)
        return Image.open(io.BytesIO(data))

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _check(self, index: int) -> None:
        if not self.pages:
            raise AlbumError("Aucune image trouvée dans ce fichier")
        if index < 0 or index >= len(self.pages):
            raise AlbumError(f"Page {index + 1} inexistante (l'album en compte {len(self.pages)})")


class ZipAlbum(Album):
    fmt = "zip"

    def __init__(self, path: str):
        super().__init__(path)
        try:
            self.zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as e:
            raise AlbumError(f"Archive ZIP illisible : {e}") from e
        except OSError as e:
            raise AlbumError(f"Fichier inaccessible : {e}") from e
        self.pages = sort_pages([i.filename for i in self.zf.infolist()
                                 if not i.is_dir() and is_image_name(i.filename)])

    def read(self, index: int) -> tuple[bytes, str]:
        self._check(index)
        name = self.pages[index]
        try:
            return self.zf.read(name), os.path.splitext(name)[1].lower()
        except (zipfile.BadZipFile, RuntimeError, OSError) as e:
            raise AlbumError(f"Page {index + 1} illisible : {e}") from e

    def close(self) -> None:
        self.zf.close()


class TarAlbum(Album):
    fmt = "tar"

    def __init__(self, path: str):
        super().__init__(path)
        try:
            self.tf = tarfile.open(path)
        except (tarfile.TarError, OSError) as e:
            raise AlbumError(f"Archive TAR illisible : {e}") from e
        self.pages = sort_pages([m.name for m in self.tf.getmembers() if m.isfile() and is_image_name(m.name)])

    def read(self, index: int) -> tuple[bytes, str]:
        self._check(index)
        name = self.pages[index]
        f = self.tf.extractfile(name)
        if f is None:
            raise AlbumError(f"Page {index + 1} illisible")
        return f.read(), os.path.splitext(name)[1].lower()

    def close(self) -> None:
        self.tf.close()


class ExtractedAlbum(Album):
    """RAR / 7z : l'archive est décompressée une fois (outil externe) dans le cache, puis lue sur disque."""
    fmt = "rar"

    def __init__(self, path: str, dest: str):
        super().__init__(path)
        self.dest = dest
        marker = os.path.join(dest, ".bulle-ok")
        if not os.path.exists(marker):
            self._extract(dest)
            with open(marker, "w") as f:
                f.write(str(time.time()))
        else:
            try:
                os.utime(marker, None)  # LRU : on note l'accès
            except OSError:
                pass
        names = []
        for dirpath, dirnames, filenames in os.walk(dest):
            dirnames[:] = [d for d in dirnames if d != "__MACOSX"]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), dest)
                if is_image_name(rel):
                    names.append(rel)
        self.pages = sort_pages(names)

    @staticmethod
    def available_tool() -> Optional[tuple[str, list[str]]]:
        for name, cmd in EXTRACT_TOOLS:
            if shutil.which(name):
                return name, cmd
        return None

    def _extract(self, dest: str) -> None:
        tool = self.available_tool()
        if not tool:
            raise AlbumError("Aucun outil pour ouvrir les CBR/RAR (installez « unar », présent dans l'image Docker)")
        name, cmd = tool
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
        argv = [a.format(dest=dest, archive=self.path) for a in cmd]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired as e:
            shutil.rmtree(dest, ignore_errors=True)
            raise AlbumError(f"Décompression trop longue avec {name}") from e
        except OSError as e:
            shutil.rmtree(dest, ignore_errors=True)
            raise AlbumError(f"Impossible de lancer {name} : {e}") from e
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            shutil.rmtree(dest, ignore_errors=True)
            raise AlbumError(f"Archive illisible ({name}, code {proc.returncode}) : {' / '.join(tail)}")

    def read(self, index: int) -> tuple[bytes, str]:
        self._check(index)
        name = self.pages[index]
        try:
            with open(os.path.join(self.dest, name), "rb") as f:
                return f.read(), os.path.splitext(name)[1].lower()
        except OSError as e:
            raise AlbumError(f"Page {index + 1} illisible : {e}") from e


class PdfAlbum(Album):
    fmt = "pdf"

    def __init__(self, path: str):
        super().__init__(path)
        self.doc = None
        self.backend = None
        if pdfium is not None:
            try:
                with _pdf_lock:
                    self.doc = pdfium.PdfDocument(path)
                    n = len(self.doc)
                self.backend = "pdfium"
            except Exception as e:  # noqa: BLE001
                raise AlbumError(f"PDF illisible : {e}") from e
        elif fitz is not None:
            try:
                self.doc = fitz.open(path)
                n = self.doc.page_count
                self.backend = "fitz"
            except Exception as e:  # noqa: BLE001
                raise AlbumError(f"PDF illisible : {e}") from e
        elif PDFTOPPM:
            n = self._poppler_count()
            self.backend = "poppler"
        else:
            raise AlbumError("Aucun moteur PDF (installez pypdfium2)")
        if n <= 0:
            raise AlbumError("PDF sans page")
        self.pages = [f"page-{i + 1:04d}.pdf" for i in range(n)]

    def _poppler_count(self) -> int:
        pdfinfo = shutil.which("pdfinfo")
        if not pdfinfo:
            raise AlbumError("pdfinfo introuvable")
        out = subprocess.run([pdfinfo, self.path], capture_output=True, text=True, timeout=120).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
        raise AlbumError("PDF illisible (pdfinfo)")

    def render(self, index: int, width: int) -> Image.Image:
        self._check(index)
        target = width or PDF_ORIGINAL_WIDTH
        try:
            if self.backend == "pdfium":
                with _pdf_lock:
                    page = self.doc[index]
                    w_pt, _ = page.get_size()
                    scale = max(0.1, target / max(1.0, w_pt))
                    bitmap = page.render(scale=scale, may_draw_forms=False)
                    img = bitmap.to_pil()
                    page.close()
                return img
            if self.backend == "fitz":
                page = self.doc[index]
                scale = max(0.1, target / max(1.0, page.rect.width))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            proc = subprocess.run(
                [PDFTOPPM, "-f", str(index + 1), "-l", str(index + 1), "-jpeg", "-r", "300",
                 "-scale-to-x", str(target), "-scale-to-y", "-1", self.path],
                capture_output=True, timeout=300)
            if proc.returncode != 0 or not proc.stdout:
                raise AlbumError("Rendu PDF impossible (pdftoppm)")
            return Image.open(io.BytesIO(proc.stdout))
        except AlbumError:
            raise
        except Exception as e:  # noqa: BLE001
            raise AlbumError(f"Page {index + 1} illisible : {e}") from e

    def read(self, index: int) -> tuple[bytes, str]:
        img = self.render(index, 0)
        return encode_jpeg(img), ".jpg"

    def close(self) -> None:
        if self.doc is not None:
            try:
                with _pdf_lock:
                    self.doc.close()
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------------------
# Images
# ----------------------------------------------------------------------------
def flatten(img: Image.Image) -> Image.Image:
    """Convertit en RGB, transparence sur fond blanc, orientation EXIF respectée."""
    try:
        img = ImageOps.exif_transpose(img) or img
    except Exception:  # noqa: BLE001
        pass
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def encode_jpeg(img: Image.Image, quality: int = JPEG_QUALITY, subsampling: int = 0) -> bytes:
    out = io.BytesIO()
    flatten(img).save(out, "JPEG", quality=quality, subsampling=subsampling, progressive=True, optimize=False)
    return out.getvalue()


def _shrink(img: Image.Image, width: int, sharpen: bool) -> Image.Image:
    """Réduit à `width` px de large (jamais agrandi) avec un léger renforcement de netteté."""
    if width and img.width > width:
        scale = width / img.width
        target = (width, max(1, round(img.height * scale)))
        if getattr(img, "format", None) == "JPEG" and scale <= 0.5:
            img.draft("RGB", (target[0] * 2, target[1] * 2))  # décodage réduit, mais gardé 2x plus grand que la cible
        img = flatten(img).resize(target, Image.Resampling.LANCZOS, reducing_gap=3.0)
        if sharpen and scale < 0.9:
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=3))
    else:
        img.load()
    return img


def resize_to_jpeg(data: bytes, width: int, quality: int = JPEG_QUALITY, subsampling: int = 0,
                   sharpen: bool = True) -> bytes:
    """Décode, réduit à `width` pixels de large (jamais agrandi) et encode en JPEG."""
    try:
        img = Image.open(io.BytesIO(data))
        return encode_jpeg(_shrink(img, width, sharpen), quality, subsampling)
    except AlbumError:
        raise
    except Exception as e:  # noqa: BLE001
        raise AlbumError(f"Image illisible : {e}") from e


def image_to_jpeg(img: Image.Image, width: int, quality: int = JPEG_QUALITY, subsampling: int = 0,
                  sharpen: bool = True) -> bytes:
    return encode_jpeg(_shrink(img, width, sharpen), quality, subsampling)


def dominant_color(img: Image.Image) -> Optional[str]:
    """Couleur « signature » d'une couverture : la teinte la plus présente, ni trop sombre ni trop claire."""
    try:
        import colorsys
        small = flatten(img).resize((40, 60), Image.Resampling.BOX)
        q = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        palette = q.getpalette()
        counts = q.getcolors() or []
        best, best_score = None, -1.0
        for count, idx in counts:
            r, g, b = palette[idx * 3: idx * 3 + 3]
            h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            score = count * (0.15 + sat) * (1.0 - abs(l - 0.45) * 1.4)
            if score > best_score:
                best, best_score = (r, g, b), score
        if best is None:
            return None
        r, g, b = best
        h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        l = min(0.62, max(0.32, l))           # ni noir ni blanc : lisible en bordure et en ombre
        sat = 0.0 if sat < 0.12 else min(0.9, max(0.35, sat))   # une couverture grise reste grise
        r, g, b = colorsys.hls_to_rgb(h, l, sat)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------
# Le gestionnaire : ouverture + cache
# ----------------------------------------------------------------------------
class Comics:
    def __init__(self, cache_dir: str, page_cache: bool = True, quality: str = "normal", sharpen: bool = True,
                 cover_width: int = COVER_WIDTH):
        self.cache_dir = cache_dir
        self.page_cache = page_cache
        self.quality_name = quality if quality in QUALITY_PROFILES else "normal"
        self.sharpen = sharpen
        self.cover_width = int(cover_width) if cover_width else COVER_WIDTH
        self.pages_dir = os.path.join(cache_dir, "pages")
        self.covers_dir = os.path.join(cache_dir, "covers")
        self.extract_dir = os.path.join(cache_dir, "extract")
        for d in (self.pages_dir, self.covers_dir, self.extract_dir):
            os.makedirs(d, exist_ok=True)
        self._locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def lock(self, node_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks[node_id]

    # -- réglages de qualité -----------------------------------------------------
    def configure(self, quality: Optional[str] = None, sharpen: Optional[bool] = None,
                  cover_width: Optional[int] = None, page_cache: Optional[bool] = None) -> None:
        if quality in QUALITY_PROFILES:
            self.quality_name = quality
        if sharpen is not None:
            self.sharpen = bool(sharpen)
        if cover_width:
            self.cover_width = max(200, min(1200, int(cover_width)))
        if page_cache is not None:
            self.page_cache = bool(page_cache)

    @property
    def jpeg(self) -> tuple[int, int]:
        return QUALITY_PROFILES[self.quality_name]

    @property
    def profile_tag(self) -> str:
        q, sub = self.jpeg
        return f"q{q}{'s' if self.sharpen else ''}{'c' if sub == 0 else ''}"

    # -- ouverture --------------------------------------------------------------
    def open(self, node: dict, abs_path: str) -> Album:
        fmt = node.get("format")
        if not os.path.isfile(abs_path):
            raise AlbumError("Fichier introuvable (déplacé ou supprimé ? relancez un scan)")
        if fmt == "zip":
            return ZipAlbum(abs_path)
        if fmt == "pdf":
            return PdfAlbum(abs_path)
        if fmt == "tar":
            return TarAlbum(abs_path)
        if fmt in ("rar", "7z"):
            dest = os.path.join(self.extract_dir, str(node["id"]))
            album = ExtractedAlbum(abs_path, dest)
            self._evict_extracted(keep=str(node["id"]))
            return album
        raise AlbumError(f"Format non géré : {fmt or 'inconnu'}")

    def _evict_extracted(self, keep: str) -> None:
        try:
            entries = []
            for name in os.listdir(self.extract_dir):
                if name == keep:
                    continue
                marker = os.path.join(self.extract_dir, name, ".bulle-ok")
                try:
                    entries.append((os.path.getmtime(marker), name))
                except OSError:
                    entries.append((0, name))
            entries.sort()
            while len(entries) >= MAX_EXTRACTED:
                _, name = entries.pop(0)
                shutil.rmtree(os.path.join(self.extract_dir, name), ignore_errors=True)
        except OSError:
            pass

    # -- cache ------------------------------------------------------------------
    def cover_path(self, node_id: int) -> str:
        return os.path.join(self.covers_dir, f"{node_id}-{self.cover_width}-{self.profile_tag}.jpg")

    def page_path(self, node_id: int, index: int, width: int) -> str:
        return os.path.join(self.pages_dir, str(node_id), f"{index}-{width}-{self.profile_tag}.jpg")

    def cache_size(self) -> dict:
        """Taille du cache (octets) par partie."""
        out = {}
        for name, d in (("pages", self.pages_dir), ("covers", self.covers_dir), ("extract", self.extract_dir)):
            total = 0
            for dirpath, _, files in os.walk(d):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
            out[name] = total
        out["total"] = sum(out.values())
        return out

    def trim_pages(self, max_bytes: int) -> int:
        """Supprime les pages en cache les moins récemment utilisées jusqu'à repasser sous max_bytes."""
        if max_bytes <= 0:
            return 0
        entries = []
        total = 0
        for dirpath, _, files in os.walk(self.pages_dir):
            for f in files:
                p = os.path.join(dirpath, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                entries.append((max(st.st_atime, st.st_mtime), st.st_size, p))
                total += st.st_size
        removed = 0
        if total <= max_bytes:
            return 0
        for _, size, p in sorted(entries):
            try:
                os.unlink(p)
                total -= size
                removed += 1
            except OSError:
                pass
            if total <= max_bytes:
                break
        return removed

    @staticmethod
    def _write_atomic(path: str, data: bytes) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def invalidate(self, node_ids) -> None:
        for nid in node_ids:
            for p in glob.glob(os.path.join(self.covers_dir, f"{nid}-*.jpg")) + \
                    [os.path.join(self.covers_dir, f"{nid}.jpg")]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            for d in (os.path.join(self.pages_dir, str(nid)), os.path.join(self.extract_dir, str(nid))):
                shutil.rmtree(d, ignore_errors=True)

    def clear_pages(self) -> int:
        n = 0
        for name in os.listdir(self.pages_dir):
            shutil.rmtree(os.path.join(self.pages_dir, name), ignore_errors=True)
            n += 1
        for name in os.listdir(self.extract_dir):
            shutil.rmtree(os.path.join(self.extract_dir, name), ignore_errors=True)
        return n

    def clear_covers(self) -> int:
        n = 0
        for name in os.listdir(self.covers_dir):
            try:
                os.unlink(os.path.join(self.covers_dir, name))
                n += 1
            except OSError:
                pass
        return n

    # -- opérations de haut niveau ------------------------------------------------
    def inspect(self, node: dict, abs_path: str, make_cover: bool = True) -> int:
        """Ouvre l'album : renvoie le nombre de pages et génère la couverture si demandée."""
        with self.lock(node["id"]):
            with self.open(node, abs_path) as album:
                n = len(album.pages)
                if n == 0:
                    raise AlbumError("Aucune image trouvée dans ce fichier")
                if make_cover and not os.path.exists(self.cover_path(node["id"])):
                    self._write_atomic(self.cover_path(node["id"]), self._render(album, 0, self.cover_width))
                return n

    def cover_color(self, node: dict, abs_path: str) -> Optional[str]:
        """Couleur dominante de la couverture (génère la couverture si besoin)."""
        try:
            path = self.cover(node, abs_path)
            with Image.open(path) as img:
                return dominant_color(img)
        except (AlbumError, OSError):
            return None

    def cover(self, node: dict, abs_path: str) -> str:
        """Chemin du fichier de couverture (généré au besoin)."""
        p = self.cover_path(node["id"])
        if os.path.exists(p):
            return p
        self.inspect(node, abs_path, make_cover=True)
        return p

    def cover_sized(self, node: dict, abs_path: str, width: int) -> str:
        """Couverture réduite à la largeur demandée (multiple de 50 px), dérivée de la couverture standard."""
        width = max(100, min(self.cover_width, int(math.ceil(width / 50.0) * 50)))
        if width >= self.cover_width:
            return self.cover(node, abs_path)
        p = os.path.join(self.covers_dir, f"{node['id']}-{width}-{self.profile_tag}.jpg")
        if os.path.exists(p):
            return p
        base = self.cover(node, abs_path)
        with self.lock(node["id"]):
            if os.path.exists(p):
                return p
            quality, subsampling = self.jpeg
            try:
                with open(base, "rb") as f:
                    data = f.read()
                self._write_atomic(p, resize_to_jpeg(data, width, quality, subsampling, self.sharpen))
            except OSError as e:
                raise AlbumError(f"Couverture illisible : {e}") from e
        return p

    def page(self, node: dict, abs_path: str, index: int, width: int) -> tuple[Optional[str], Optional[bytes], str]:
        """Page `index` à la largeur `width` (0 = originale).

        Renvoie (chemin_fichier_cache, octets, mimetype) : l'un des deux premiers est rempli.
        """
        width = pick_width(width)
        if width and self.page_cache:
            cached = self.page_path(node["id"], index, width)
            if os.path.exists(cached):
                return cached, None, "image/jpeg"
        with self.lock(node["id"]):
            with self.open(node, abs_path) as album:
                if width == 0:
                    data, ext = album.read(index)
                    return None, data, MIME.get(ext, "application/octet-stream")
                data = self._render(album, index, width)
                if self.page_cache:
                    cached = self.page_path(node["id"], index, width)
                    try:
                        self._write_atomic(cached, data)
                        return cached, None, "image/jpeg"
                    except OSError as e:
                        log.warning("Cache pages indisponible : %s", e)
                return None, data, "image/jpeg"

    def _render(self, album: Album, index: int, width: int) -> bytes:
        quality, subsampling = self.jpeg
        if isinstance(album, PdfAlbum):
            return image_to_jpeg(album.render(index, width), width, quality, subsampling, self.sharpen)
        data, _ = album.read(index)
        return resize_to_jpeg(data, width, quality, subsampling, self.sharpen)
