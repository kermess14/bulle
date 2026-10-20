"""BDfugue (librairie BD en ligne, www.bdfugue.com) : source de secours quand un album ou une série n'est pas sur
Bédéthèque. Mêmes règles de politesse que pour Bédéthèque (même client : délais, plafond par minute, cache) ; seules
des pages publiques autorisées par le robots.txt du site sont lues : la recherche (/catalogsearch/result/), les fiches
produit (/<nom-de-l-album>) et les pages de série (/serie/<nom>).

Les données sont remises dans le même format que celles de Bédéthèque (série : {url, title, genre, albums: [...]},
album : {number, kind, title, year, url, writers, pencillers, publisher, isbn, pages, ...}) : le reste de Bulle les
utilise sans savoir d'où elles viennent.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup

from .bedetheque import norm_title, similarity

BASE = "https://www.bdfugue.com"
NAME = "BDfugue"

_MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
           "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
# pages qui ne sont pas des fiches produit (menus, rubriques, compte…)
_NOT_PRODUCT = re.compile(r"^/(?:serie|bd|manga|comics|catalogsearch|customer|checkout|wishlist|sales|aide|vendre|"
                          r"librairies|media|static|auteur|editeur|collection|promos?|nouveautes|jeunesse|"
                          r"contactez-nous|frais-port|offrir-bd)(?:/|$)", re.I)


def is_url(s: str) -> bool:
    return bool(re.match(r"https?://(?:www\.)?bdfugue\.com/", (s or "").strip()))


def canonical(s: str) -> Optional[str]:
    """Adresse BDfugue remise sous forme canonique (sans paramètres), sinon None."""
    m = re.match(r"https?://(?:www\.)?bdfugue\.com(/[^?#\s]*)", (s or "").strip())
    if not m:
        return None
    path = m.group(1).rstrip("/") or "/"
    return BASE + path


def product_url(s: str) -> Optional[str]:
    """Adresse d'une fiche album BDfugue, sinon None (page de série, rubrique…)."""
    u = canonical(s)
    if not u:
        return None
    path = u[len(BASE):]
    if path == "/" or path.count("/") != 1 or _NOT_PRODUCT.match(path) or "." in path.rsplit("/", 1)[-1]:
        return None
    return u


def series_url(s: str) -> Optional[str]:
    u = canonical(s)
    return u if u and re.match(r"^/serie/[^/]+$", u[len(BASE):]) else None


def search_url(query: str) -> str:
    return f"{BASE}/catalogsearch/result/?q={urllib.parse.quote_plus(query.strip())}"


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_title(raw: str) -> dict:
    """« les feux d'askell tome 3 - corail sanglant » → série « les feux d'askell », tome 3, titre « corail sanglant ».
    Aussi : « Marie-Lune T.3 - … », « Zombies tome 1 », « Blake & Mortimer - hors-série tome 15 - Affaires classées »,
    « Les feux d'askell - intégrale », et les mentions commerciales (« + ex-libris offert », « (éd. 2013) »)."""
    t = re.sub(r"\s+", " ", raw or "").strip()
    t = re.sub(r"\s*\+\s*(?:ex-?libris|cadeau|tirage|offert|marque-?page)[^()]*$", "", t, flags=re.I).strip()
    edition = None
    m = re.search(r"\s*\((?:[ée]d\.?|[ée]dition)\s*((?:19|20)\d\d)\)\s*$", t, re.I)
    if m:
        edition = int(m.group(1))
        t = t[:m.start()].strip()
    kind = "tome"
    if re.search(r"int[ée]grale|tomes?\s*\d+\s*(?:à|a|-)\s*(?:tome\s*)?\d+|t\.?\s*\d+\s*à\s*t", t, re.I):
        kind = "int"
    elif re.search(r"hors[- ]s[ée]rie|\bHS\b", t, re.I):
        kind = "hs"
    elif re.search(r"coffret|pack|\bpp\d", t, re.I):
        kind = "other"
    m = re.match(r"^(?P<series>.+?)\s*(?:-\s*)?(?:hors[- ]s[ée]rie\s*)?(?:tome|t\.)\s*(?P<num>\d{1,3})(?!\d)(?!\s*à)\s*(?:-\s*(?P<title>.+))?$",
                 t, re.I)
    if m and kind != "int":
        series = m.group("series").strip(" -")
        series = re.sub(r"\s*-\s*hors[- ]s[ée]rie$", "", series, flags=re.I)
        title = (m.group("title") or "").strip() or None
        return {"series": series, "number": int(m.group("num")), "title": title, "kind": kind, "edition": edition,
                "full": t}
    parts = [p.strip() for p in re.split(r"\s+-\s+", t) if p.strip()]
    series = parts[0] if parts else t
    title = " - ".join(parts[1:]) or None
    return {"series": series, "number": None, "title": title if kind != "tome" else (title or None), "kind": kind,
            "edition": edition, "full": t}


def _date(s: str) -> tuple[Optional[str], Optional[int]]:
    s = (s or "").strip()
    m = re.search(r"((?:19|20)\d\d)", s)
    return (s or None), (int(m.group(1)) if m else None)


def parse_search(html: str, query: str, year: Optional[int] = None) -> list[dict]:
    """Albums de la page de résultats : [{url, name, series, number, title, kind, authors, cover, score}]."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select("h3 a[href]"):
        url = product_url(a["href"])
        if not url or url in seen:
            continue
        seen.add(url)
        name = _text(a)
        if not name:
            continue
        card = a
        for _ in range(4):   # la carte du produit : le premier parent qui contient l'image
            card = card.parent
            if card is None or card.find("img"):
                break
        img = card.find("img") if card is not None else None
        cover = None
        if img is not None:
            src = img.get("src") or img.get("data-src") or ""
            if "/media/catalog/product/" in src:
                cover = src.split("?")[0]
        who = card.select_one(".text-gray-400") if card is not None else None
        p = parse_title(name)
        score = max(similarity(query, p["full"]), similarity(query, p["series"]),
                    similarity(query, p["title"] or "") if p["title"] else 0.0,
                    similarity(query, f"{p['series']} {p['title'] or ''}"))
        out.append({"url": url, "name": p["full"], "series": p["series"], "number": p["number"], "title": p["title"],
                    "kind": p["kind"], "authors": _text(who) or None, "cover": cover, "score": round(score, 3),
                    "edition": p["edition"]})
    out.sort(key=lambda r: -r["score"])
    return out


def _attributes(soup) -> dict:
    """Tableau « Détails » de la fiche : {libellé en minuscules sans « : » : valeur}."""
    out = {}
    for lab in soup.select(".product-attribute-label"):
        val = lab.find_next_sibling(class_="product-attribute-value") or lab.find_next_sibling()
        key = _text(lab).rstrip(" :").strip().lower()
        if key and val is not None and key not in out:
            out[key] = val
    return out


def _people(text: str) -> dict:
    """« Scotch Arleston (Scénario) / Jean-Louis Mourier (Dessin, Couleurs) » → rôles."""
    roles = {"writers": [], "pencillers": [], "colorists": []}
    for part in re.split(r"\s*/\s*", text or ""):
        m = re.match(r"(.+?)\s*\(([^()]*)\)\s*$", part.strip())
        name, what = (m.group(1).strip(), m.group(2).lower()) if m else (part.strip(), "")
        if not name or name.lower() in ("unknown", "..."):
            continue
        if not what or "sc" in what:
            roles["writers"].append(name)
        if not what or "dessin" in what:
            roles["pencillers"].append(name)
        if "couleur" in what:
            roles["colorists"].append(name)
    return roles


def parse_product(html: str, url: str) -> dict:
    """Fiche d'un album : {url, title, series, number, kind, year, date, summary, cover, publisher, writers, …,
    series_url}."""
    soup = BeautifulSoup(html, "html.parser")
    ld = {}
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            j = json.loads(s.string or s.get_text() or "")
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product":
            ld = j
            break
    h1 = _text(soup.find("h1"))
    name = h1 or ld.get("name") or ""
    p = parse_title(name)
    attrs = _attributes(soup)
    get = lambda *keys: next((_text(attrs[k]) for k in keys if k in attrs and _text(attrs[k])), None)  # noqa: E731
    series = get("série", "serie") or p["series"]
    number = p["number"]
    tome = get("tome")
    if tome and re.fullmatch(r"\d{1,3}", tome):
        number = int(tome)
    title = get("titre album") or p["title"]
    date, year = _date(get("date de parution", "parution") or "")
    if not date:
        m = re.search(r"Parution\s+(\d{1,2}(?:er)?\s+\w+\s+(?:19|20)\d\d)", soup.get_text(" "))
        if m:
            date, year = _date(m.group(1))
    summary_el = soup.select_one("[itemprop=description]")
    summary = _text(summary_el) or None
    image = ld.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if not image:
        og = soup.find("meta", attrs={"property": "og:image"})
        image = og.get("content") if og else None
    cover = image.split("?")[0] if isinstance(image, str) and image else None
    pages = get("nombre de pages", "pages")
    m = re.search(r"\d+", pages or "")
    roles = _people(get("auteur(s)", "auteurs") or "")
    s_link = None
    for a in soup.find_all("a", href=True):
        su = series_url(a["href"])
        if su:
            s_link = su
            break
    isbn = re.sub(r"[^0-9Xx]", "", get("référence", "reference", "ean", "isbn") or str(ld.get("gtin13") or "")) or None
    genre = get("genres", "genre(s)", "genre")
    return {"url": canonical(url), "name": p["full"], "series": series, "number": number, "kind": p["kind"],
            "title": title or (series if number is None else None), "date": date, "year": year, "summary": summary,
            "cover": cover, "publisher": get("éditeur", "editeur"), "collection": get("collection"),
            "isbn": isbn, "pages": int(m.group()) if m else None, "genre": genre, "series_url": s_link, **roles}


def album_from_product(prod: dict) -> dict:
    """Un album au format des séries de Bédéthèque."""
    num = prod.get("number")
    return {"num_raw": str(num) if num is not None else "", "number": num, "suffix": None,
            "kind": prod.get("kind") or "tome", "title": prod.get("title") or prod.get("series") or prod.get("name"),
            "date": prod.get("date"), "year": prod.get("year"), "url": prod["url"],
            "writers": prod.get("writers") or [], "pencillers": prod.get("pencillers") or [],
            "colorists": prod.get("colorists") or [], "publisher": prod.get("publisher"),
            "collection": prod.get("collection"), "isbn": prod.get("isbn"), "pages": prod.get("pages"),
            "legal": prod.get("date"), "cover": prod.get("cover"), "summary": prod.get("summary"), "source": "bdfugue"}


def series_from_product(prod: dict) -> dict:
    """Une « série » d'un seul album (one shot, ou série sans page sur BDfugue)."""
    alb = album_from_product(prod)
    return {"id": None, "url": prod["url"], "title": prod.get("series") or prod.get("name"), "genre": prod.get("genre"),
            "status": None, "years": str(prod["year"]) if prod.get("year") else None, "tomes_count": None,
            "albums": [alb], "details": {}, "detailed": 1 if (alb["publisher"] or alb["writers"]) else 0,
            "source": "bdfugue"}


def parse_series_page(html: str, url: str) -> tuple[dict, Optional[str]]:
    """Page « /serie/… » : (série au format Bédéthèque, adresse de la page suivante ou None)."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    for sel in ("h1", "h2"):
        el = soup.find(sel)
        if el and _text(el):
            title = _text(el)
            break
    title = re.sub(r",?\s*la s[ée]rie.*$", "", title or "", flags=re.I).strip() or None
    t = soup.find("title")
    if t:
        tt = re.sub(r",\s*la s[ée]rie.*$", "", _text(t), flags=re.I).strip()
        if tt and (not title or title.isupper()):
            title = tt
    albums = []
    for r in parse_search(html, title or ""):
        if title and r["kind"] != "int" and similarity(title, r["series"]) < 0.6:
            continue   # (suggestions d'une autre série sur la page)
        num = r["number"] if r["kind"] in ("tome", "hs") else None
        albums.append({"num_raw": str(num) if num is not None else "", "number": num, "suffix": None,
                       "kind": r["kind"], "title": r["title"] or r["name"], "date": None, "year": r.get("edition"),
                       "url": r["url"], "cover": r["cover"], "source": "bdfugue"})
    albums.sort(key=lambda a: (a["kind"] != "tome", a["number"] if a["number"] is not None else 999))
    nxt = None
    for a in soup.find_all("a", href=True):
        if re.search(r"suivant", _text(a), re.I) and re.search(r"[?&]p=\d+", a["href"]):
            nxt = a["href"] if a["href"].startswith("http") else BASE + a["href"]
            break
    data = {"id": None, "url": canonical(url), "title": title, "genre": None, "status": None, "years": None,
            "tomes_count": len({a["number"] for a in albums if a["kind"] == "tome" and a["number"] is not None}) or None,
            "albums": albums, "details": {}, "detailed": 0, "source": "bdfugue"}
    return data, nxt


def series_candidates(hits: list[dict], query: str) -> list[dict]:
    """Résultats de recherche regroupés par série, présentés comme les propositions de Bédéthèque. L'adresse est celle
    d'un album de la série : la choisir mène à la page de la série."""
    groups: dict[str, dict] = {}
    for h in hits:
        key = norm_title(h["series"])
        g = groups.get(key)
        if g is None:
            groups[key] = {"url": h["url"], "name": h["series"], "score": round(similarity(query, h["series"]), 3),
                           "genre": NAME, "tomes": None, "exact": norm_title(query) == key, "source": "bdfugue",
                           "cover": h.get("cover")}
    return sorted(groups.values(), key=lambda c: -c["score"])


def album_candidates(hits: list[dict], limit: int = 8) -> list[dict]:
    out = []
    for h in hits[:limit]:
        out.append({"url": h["url"], "name": h["name"] + (f" — {h['authors']}" if h.get("authors") else ""),
                    "score": h["score"], "album": True, "genre": f"album {NAME}", "tomes": None, "exact": False,
                    "source": "bdfugue", "cover": h.get("cover")})
    return out


def product_from_url(url: str, fallback_title: Optional[str] = None) -> dict:
    """Fiche « devinée » d'après l'adresse seule, quand la page ne peut pas être lue (site qui refuse les lecteurs
    automatiques) : « /les-feux-d-askell-t-3-corail-sanglant » → les feux d'askell, tome 3, corail sanglant."""
    u = canonical(url) or url
    slug = u.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-?97[89]\d{10}$", "", slug)                 # EAN en fin d'adresse
    words = re.sub(r"-+", " ", slug).strip()
    words = re.sub(r"\b([dlj]) (?=[aeiouyh])", r"\1'", words)     # « d askell » → « d'askell »
    words = re.sub(r"\bt ?(\d{1,3}) a t ?(\d{1,3})\b", r"- tomes \1 à \2", words)   # intégrale « t 1 a t 3 »
    words = re.sub(r"\bt ?(\d{1,3})\b(?! à)", r"tome \1 -", words, count=1)
    words = words.strip(" -")
    p = parse_title(words)
    title = p["title"] or (fallback_title if p["number"] is None and fallback_title else None)
    series = p["series"].strip(" -") or fallback_title or words
    if fallback_title and p["number"] is None and not p["title"]:
        series = fallback_title          # one shot : le nom du fichier est plus juste que l'adresse
    return {"url": u, "name": words, "series": series[:1].upper() + series[1:], "number": p["number"],
            "kind": p["kind"], "title": title, "date": None, "year": None, "summary": None, "cover": None,
            "publisher": None, "collection": None, "isbn": None, "pages": None, "genre": None, "series_url": None,
            "writers": [], "pencillers": [], "colorists": [], "guessed": True}

