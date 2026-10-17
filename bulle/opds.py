"""Flux OPDS 1.2 (+ OPDS-PSE pour lire page par page) : pour les applis de lecture mobiles
(Panels, Chunky, Moon+ Reader, Mihon/Tachiyomi, KOReader, Librera…).

Adresse à donner à l'appli : http://<serveur>:<port>/opds
"""
from __future__ import annotations

import datetime as dt
import math
import urllib.parse
from xml.etree import ElementTree as ET

ATOM = "http://www.w3.org/2005/Atom"
OPDS = "http://opds-spec.org/2010/catalog"
PSE = "http://vaemendis.net/opds-pse/ns"
OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"
NAV = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ = "application/atom+xml;profile=opds-catalog;kind=acquisition"
PER_PAGE = 100

ET.register_namespace("", ATOM)
ET.register_namespace("opds", OPDS)
ET.register_namespace("pse", PSE)

MIME = {"zip": "application/vnd.comicbook+zip", "rar": "application/vnd.comicbook-rar", "pdf": "application/pdf",
        "7z": "application/x-7z-compressed", "tar": "application/x-tar"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _feed(title: str, self_href: str, kind: str, base: str) -> ET.Element:
    feed = ET.Element(f"{{{ATOM}}}feed")
    ET.SubElement(feed, f"{{{ATOM}}}id").text = "urn:bulle:" + self_href
    ET.SubElement(feed, f"{{{ATOM}}}title").text = title
    ET.SubElement(feed, f"{{{ATOM}}}updated").text = _now()
    author = ET.SubElement(feed, f"{{{ATOM}}}author")
    ET.SubElement(author, f"{{{ATOM}}}name").text = "Bulle"
    ET.SubElement(feed, f"{{{ATOM}}}link", rel="self", href=base + self_href, type=kind)
    ET.SubElement(feed, f"{{{ATOM}}}link", rel="start", href=base + "/opds", type=NAV)
    ET.SubElement(feed, f"{{{ATOM}}}link", rel="search", href=base + "/opds/opensearch.xml",
                  type="application/opensearchdescription+xml")
    return feed


def _nav_entry(feed: ET.Element, title: str, href: str, base: str, content: str = "", cover: str = "") -> None:
    e = ET.SubElement(feed, f"{{{ATOM}}}entry")
    ET.SubElement(e, f"{{{ATOM}}}title").text = title
    ET.SubElement(e, f"{{{ATOM}}}id").text = "urn:bulle:" + href
    ET.SubElement(e, f"{{{ATOM}}}updated").text = _now()
    if content:
        ET.SubElement(e, f"{{{ATOM}}}content", type="text").text = content
    ET.SubElement(e, f"{{{ATOM}}}link", rel="subsection", href=base + href, type=NAV)
    if cover:
        ET.SubElement(e, f"{{{ATOM}}}link", rel="http://opds-spec.org/image", href=base + cover, type="image/jpeg")
        ET.SubElement(e, f"{{{ATOM}}}link", rel="http://opds-spec.org/image/thumbnail", href=base + cover, type="image/jpeg")


def _album_entry(feed: ET.Element, a: dict, base: str, folder: str = "", meta: dict | None = None,
                 progress: dict | None = None) -> None:
    e = ET.SubElement(feed, f"{{{ATOM}}}entry")
    title = a["name"]
    if meta and meta.get("title"):
        title = (f"T{meta['number']} · " if meta.get("number") is not None else "") + meta["title"]
    ET.SubElement(e, f"{{{ATOM}}}title").text = title
    ET.SubElement(e, f"{{{ATOM}}}id").text = f"urn:bulle:album:{a['id']}"
    ET.SubElement(e, f"{{{ATOM}}}updated").text = dt.datetime.fromtimestamp(
        a.get("mtime") or 0, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bits = []
    if folder:
        bits.append(folder)
    if a.get("page_count"):
        bits.append(f"{a['page_count']} pages")
    if a.get("size"):
        bits.append(f"{a['size'] / 1e6:.0f} Mo")
    if meta:
        if meta.get("writers"):
            bits.append("Scénario : " + ", ".join(meta["writers"]))
        if meta.get("pencillers"):
            bits.append("Dessin : " + ", ".join(meta["pencillers"]))
        if meta.get("publisher"):
            bits.append(meta["publisher"] + (f" ({meta['year']})" if meta.get("year") else ""))
    if progress and progress.get("page") is not None:
        bits.append("lu ✓" if progress.get("completed") else f"en cours, page {progress['page'] + 1}")
    text = " · ".join(bits)
    if meta and meta.get("summary"):
        text = (text + "\n\n" if text else "") + meta["summary"]
    ET.SubElement(e, f"{{{ATOM}}}content", type="text").text = text
    if meta:
        for w in (meta.get("writers") or []) + (meta.get("pencillers") or []):
            au = ET.SubElement(e, f"{{{ATOM}}}author")
            ET.SubElement(au, f"{{{ATOM}}}name").text = w
    ext = a["path"].rsplit(".", 1)[-1].lower()
    mime = MIME.get(a.get("format") or "", "application/octet-stream")
    cover = f"/api/cover/{a['id']}?v={int(a.get('mtime') or 0)}"
    ET.SubElement(e, f"{{{ATOM}}}link", rel="http://opds-spec.org/image", href=base + cover, type="image/jpeg")
    ET.SubElement(e, f"{{{ATOM}}}link", rel="http://opds-spec.org/image/thumbnail", href=base + cover, type="image/jpeg")
    ET.SubElement(e, f"{{{ATOM}}}link", rel="http://opds-spec.org/acquisition",
                  href=base + f"/api/download/{a['id']}", type=mime, title=f"Télécharger ({ext.upper()})")
    if a.get("page_count"):
        link = ET.SubElement(e, f"{{{ATOM}}}link", rel=f"{PSE}#stream", type="image/jpeg",
                             href=base + f"/api/page/{a['id']}/{{pageNumber}}?w=1600&v={int(a.get('mtime') or 0)}")
        link.set(f"{{{PSE}}}count", str(a["page_count"]))
        if progress and progress.get("page") is not None:
            link.set(f"{{{PSE}}}lastRead", str(progress["page"]))


def _paginate(feed: ET.Element, href: str, page: int, total: int, base: str) -> None:
    pages = max(1, math.ceil(total / PER_PAGE))
    sep = "&" if "?" in href else "?"
    if page < pages:
        ET.SubElement(feed, f"{{{ATOM}}}link", rel="next", href=f"{base}{href}{sep}page={page + 1}", type=ACQ)
    if page > 1:
        ET.SubElement(feed, f"{{{ATOM}}}link", rel="previous", href=f"{base}{href}{sep}page={page - 1}", type=ACQ)


def to_xml(feed: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(feed, encoding="unicode").encode("utf-8")


def root_feed(base: str, root_id: int | None, stats: dict) -> bytes:
    feed = _feed("Bulle", "/opds", NAV, base)
    _nav_entry(feed, "Reprendre la lecture", "/opds/continue", base, "Les albums commencés")
    _nav_entry(feed, "Ajouts récents", "/opds/recent", base, "Les derniers albums ajoutés")
    if root_id is not None:
        _nav_entry(feed, "Bibliothèque", f"/opds/folder/{root_id}", base,
                   f"{stats.get('albums', 0)} albums, rangés par dossiers")
    return to_xml(feed)


def opensearch(base: str) -> bytes:
    root = ET.Element(f"{{{OPENSEARCH}}}OpenSearchDescription")
    ET.SubElement(root, f"{{{OPENSEARCH}}}ShortName").text = "Bulle"
    ET.SubElement(root, f"{{{OPENSEARCH}}}Description").text = "Rechercher une série ou un album"
    ET.SubElement(root, f"{{{OPENSEARCH}}}Url", type=ACQ, template=base + "/opds/search?q={searchTerms}")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode").encode("utf-8")


def folder_feed(base: str, folder: dict, children: list[dict], metas: dict, progress: dict, page: int) -> bytes:
    href = f"/opds/folder/{folder['id']}"
    feed = _feed(folder["name"] or "Bibliothèque", href, ACQ, base)
    if folder.get("parent_id"):
        ET.SubElement(feed, f"{{{ATOM}}}link", rel="up", href=base + f"/opds/folder/{folder['parent_id']}", type=ACQ)
    start, end = (page - 1) * PER_PAGE, page * PER_PAGE
    for c in children[start:end]:
        if c["kind"] == "folder":
            cover = f"/api/cover/{c['cover_id']}?v=f{c['cover_id']}" if c.get("cover_id") else ""
            _nav_entry(feed, c["name"], f"/opds/folder/{c['id']}", base, f"{c.get('album_count', 0)} albums", cover)
        else:
            _album_entry(feed, c, base, meta=metas.get(c["id"]), progress=progress.get(c["id"]))
    _paginate(feed, href, page, len(children), base)
    return to_xml(feed)


def list_feed(base: str, title: str, href: str, albums: list[dict], page: int = 1) -> bytes:
    feed = _feed(title, href, ACQ, base)
    start, end = (page - 1) * PER_PAGE, page * PER_PAGE
    for a in albums[start:end]:
        _album_entry(feed, a, base, folder=a.get("folder", ""), meta=a.get("meta"), progress=a.get("progress"))
    _paginate(feed, href, page, len(albums), base)
    return to_xml(feed)


def search_href(q: str) -> str:
    return "/opds/search?q=" + urllib.parse.quote(q)
