"""Bédéthèque (bedetheque.com) : recherche d'une série, lecture de sa fiche, comparaison avec un dossier.

Règles de politesse : uniquement à la demande de l'utilisateur, une requête à la fois, un délai entre
deux requêtes, pages gardées en cache (base SQLite) pendant plusieurs semaines, User-Agent qui dit qui
nous sommes. Les chemins interdits par le robots.txt du site (/ajax/, /api/, images de couvertures…)
ne sont jamais appelés : on lit seulement les pages de recherche et de séries, comme un visiteur.
Rien n'est jamais écrit dans les fichiers de l'utilisateur.
"""
from __future__ import annotations

import difflib
import gzip
import logging
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Callable, Optional

from bs4 import BeautifulSoup

log = logging.getLogger("bulle.bedetheque")

BASE = "https://www.bedetheque.com"
USER_AGENT = "Bulle/0.2 (+https://github.com/kermess14/bulle ; lecteur de BD personnel, requetes a la demande)"
PAGE_TTL = 30 * 24 * 3600          # fiches de séries : 30 jours
SEARCH_TTL = 7 * 24 * 3600         # résultats de recherche : 7 jours
INDEX_TTL = 30 * 24 * 3600         # index alphabétique des séries (une page par lettre) : 30 jours
DETAIL_PER_PAGE = 10               # albums détaillés par page de série
INDEX_LETTERS = "0ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class BdtError(Exception):
    """Erreur lisible : site injoignable, refus, page inattendue…"""


# ----------------------------------------------------------------------------
# Normalisation des noms
# ----------------------------------------------------------------------------
ARTICLES = ("le", "la", "les", "l", "the", "un", "une")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_title(s: str) -> str:
    """Minuscules, sans accents ni ponctuation, articles retirés (« Aigles Décapitées (Les) » = « les aigles decapitees »)."""
    s = strip_accents(s).lower().replace("’", "'").replace("œ", "oe")
    s = re.sub(r"\(\s*(l'|les|le|la|the|un|une|des|a|an)\s*\)", " ", s)      # article entre parenthèses à la fin
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    words = s.split()
    while words and words[0] in ARTICLES:
        words.pop(0)
    return " ".join(words)


def similarity(a: str, b: str) -> float:
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def query_from_folder(name: str) -> str:
    """Nettoie un nom de dossier pour en faire une recherche : « Légendaires (Les) - Patrick Sobral (2004-2025) » → « Légendaires (Les) »."""
    q = name
    q = re.sub(r"\((?:19|20)\d\d(?:\s*[-–]\s*(?:(?:19|20)\d\d)?)?\)", " ", q)  # (2004-2025), (1999)
    q = re.sub(r"\b(?:T|Tomes?)\s*\d+\s*(?:à|a|-|–)\s*\d+\b", " ", q, flags=re.I)   # T 1 à 4
    q = re.sub(r"\b\d+\s*T\b", " ", q)                                             # 4T
    q = re.sub(r"\b(int[ée]grales?|one[- ]?shots?|hors[- ]s[ée]rie|cycles?\s*\d*|complet(?:e)?)\b", " ", q, flags=re.I)
    segments = [seg.strip(" -–,;") for seg in re.split(r"\s+-\s+", q)]
    segments = [seg for seg in segments if seg and not re.fullmatch(r"[\d\s.]+|T\s*\d+", seg, re.I)]
    first = segments[0] if segments else q
    first = re.sub(r"\s+", " ", first).strip(" -–,;")
    return first or name


NUM_PATTERNS = [
    re.compile(r"(?<![a-z0-9])(?:HS|INT|int[ée]grale|hors[- ]s[ée]rie)\s*0*(\d{1,3})(?![0-9])", re.I),  # HS2, Intégrale 3
    re.compile(r"(?<![a-z0-9])T(?:ome)?\s*0*(\d{1,3})(?![0-9])", re.I),          # T01, Tome 3
    re.compile(r"(?<![a-z0-9])(?:n°|#|no\.?)\s*0*(\d{1,3})(?![0-9])", re.I),      # n°3, #3
    re.compile(r"(?:^|\s-\s)0*(\d{1,3})(?:\s-\s|\s*[.)]\s|$)"),                  # « 03 - Titre », « 03. Titre »
    re.compile(r"(?<![a-z0-9])vol(?:ume)?\.?\s*0*(\d{1,3})(?![0-9])", re.I),      # Vol. 2
]
SPECIAL_RE = re.compile(r"(?<![a-z])(HS|hors[- ]s[ée]rie|INT|int[ée]grale|HC|SP)(?![a-z])", re.I)


def parse_album_name(name: str) -> dict:
    """Extrait un numéro de tome et un titre probable d'un nom de fichier (sans extension)."""
    special = SPECIAL_RE.search(name)
    kind = "tome"
    if special:
        tag = special.group(1).lower()
        kind = "int" if tag.startswith("int") else "hs" if tag.startswith("h") and tag != "hc" else "other"
    number = None
    for pat in NUM_PATTERNS:
        m = pat.search(name)
        if m:
            number = int(m.group(1))
            break
    title = None
    parts = [p.strip() for p in re.split(r"\s+-\s+", name) if p.strip()]
    if len(parts) >= 2:
        last = parts[-1]
        if not re.fullmatch(r"(?i)T(?:ome)?\s*\d+|\d+", last):
            title = re.sub(r"^\s*(?:T(?:ome)?\s*\d+\s*[-:.]?\s*)", "", last).strip() or None
    return {"number": number, "kind": kind, "title": title}


# ----------------------------------------------------------------------------
# Client HTTP poli + cache
# ----------------------------------------------------------------------------
class BedethequeClient:
    def __init__(self, cache_get: Callable[[str], Optional[tuple[float, bytes]]],
                 cache_put: Callable[[str, bytes], None], min_interval: float = 2.5):
        self._cache_get = cache_get
        self._cache_put = cache_put
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self.last_error: Optional[str] = None
        self.requests_made = 0

    def fetch(self, url: str, ttl: float = PAGE_TTL, force: bool = False) -> str:
        if not url.startswith(BASE + "/"):
            raise BdtError("Adresse hors de bedetheque.com")
        path = url[len(BASE):]
        if re.match(r"^/(ajax|api|images|Couvertures|thb_couv|Planches|Versos|fiche|admin)", path, re.I):
            raise BdtError("Cette page de Bédéthèque est réservée (robots.txt) : non consultée")
        if not force:
            cached = self._cache_get(url)
            if cached and time.time() - cached[0] < ttl:
                return zlib.decompress(cached[1]).decode("utf-8", "replace")
        mock = _mock_page(url)  # tests hors ligne uniquement (variable BULLE_BDT_MOCK)
        if mock is not None:
            self.requests_made += 1
            self._cache_put(url, zlib.compress(mock.encode("utf-8"), 6))
            return mock
        with self._lock:
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "fr-FR,fr;q=0.9", "Accept-Encoding": "gzip",
            })
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                        raw = gzip.decompress(raw)
                    charset = resp.headers.get_content_charset() or "utf-8"
                    html = raw.decode(charset, "replace")
            except urllib.error.HTTPError as e:
                self.last_error = f"Bédéthèque a répondu {e.code} pour {path}"
                if e.code in (403, 429, 503):
                    raise BdtError(f"Bédéthèque refuse pour l'instant les requêtes de Bulle (code {e.code}). "
                                   "Réessayez plus tard ; si cela persiste, le site bloque les lecteurs automatiques.") from e
                if e.code == 404:
                    raise BdtError("Page Bédéthèque introuvable (adresse changée ?)") from e
                raise BdtError(f"Erreur Bédéthèque (code {e.code})") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                self.last_error = f"Bédéthèque injoignable : {e}"
                raise BdtError(f"Bédéthèque injoignable : {getattr(e, 'reason', e)}") from e
            finally:
                self._last = time.time()
                self.requests_made += 1
        if re.search(r"<title>\s*Just a moment|cf-browser-verification|Attention Required", html, re.I):
            self.last_error = "Page de vérification (anti-robot) renvoyée"
            raise BdtError("Bédéthèque a renvoyé une page de vérification au lieu du contenu : "
                           "le site n'accepte pas les lecteurs automatiques en ce moment.")
        self.last_error = None
        self._cache_put(url, zlib.compress(html.encode("utf-8"), 6))
        return html

    # -- recherche ----------------------------------------------------------
    def search_site(self, query: str) -> list[dict]:
        """La recherche du site lui-même (peut renvoyer une page sans résultats aux lecteurs automatiques)."""
        q = query.strip()
        if len(q) < 2:
            return []
        url = f"{BASE}/search/tout?qs=1&RechWhere=7&RechTexte={urllib.parse.quote(q)}"
        html = self.fetch(url, ttl=SEARCH_TTL)
        return parse_search(html, q)

    def index_letter(self, letter: str, force: bool = False) -> list[dict]:
        """Toutes les séries d'une lettre (page « Séries BD - A » du site) : [{id, name, url}]."""
        letter = letter.upper() if letter.upper() in INDEX_LETTERS else "0"
        html = self.fetch(f"{BASE}/bandes_dessinees_{letter}.html", ttl=INDEX_TTL, force=force)
        return parse_index(html)

    def search_index(self, query: str, index_rows: list[dict], hint_int: bool = False, limit: int = 12) -> list[dict]:
        """Recherche locale dans l'index d'une lettre : exact, préfixe, puis ressemblance."""
        q = norm_title(query)
        if not q:
            return []
        out = []
        for row in index_rows:
            name_n = row.get("name_norm") or norm_title(row["name"])
            if name_n == q:
                score = 1.0
            elif name_n.startswith(q + " ") or q.startswith(name_n + " "):
                score = 0.9 - min(0.2, abs(len(name_n) - len(q)) / 100)
            else:
                score = difflib.SequenceMatcher(None, q, name_n).ratio()
                if score < 0.55:
                    continue
            if hint_int:
                score += 0.25 if "integrale" in name_n else -0.08
            elif "integrale" in name_n and "integrale" not in q:
                score -= 0.08
            out.append({"id": row["id"], "url": row["url"], "name": row["name"], "genre": None, "tomes": None,
                        "exact": name_n == q, "score": round(min(1.0, score), 3)})
        out.sort(key=lambda c: -c["score"])
        return out[:limit]

    def search_series(self, query: str, index_rows: Optional[list[dict]] = None, hint_int: bool = False) -> list[dict]:
        """Recherche d'une série : par l'index alphabétique si on nous le donne, sinon par la recherche du site."""
        if index_rows is not None:
            return self.search_index(query, index_rows, hint_int=hint_int)
        return self.search_site(query)

    def series(self, url_or_id, details: bool = False, force: bool = False) -> dict:
        url = series_url(url_or_id)
        html = self.fetch(url, force=force)
        data = parse_series(html, url)
        if details and data["albums"]:
            n_pages = max(1, -(-len(data["albums"]) // DETAIL_PER_PAGE))
            for i in range(1, n_pages):
                page_url = re.sub(r"\.html$", f"__{i}.html", url)
                try:
                    data["details"].update(parse_details(self.fetch(page_url, force=force)))
                except BdtError as e:
                    log.warning("Page de détails %s : %s", page_url, e)
                    break
            merge_details(data)
        else:
            merge_details(data)
        return data


def _mock_page(url: str) -> Optional[str]:
    """Pour les tests sans réseau : BULLE_BDT_MOCK=<dossier> contenant map.json {"morceau d'adresse": "fichier.html"}."""
    import json
    import os
    d = os.environ.get("BULLE_BDT_MOCK")
    if not d:
        return None
    try:
        mapping = json.load(open(os.path.join(d, "map.json"), encoding="utf-8"))
    except OSError:
        return None
    for key, fname in mapping.items():
        if key in urllib.parse.unquote(url):
            with open(os.path.join(d, fname), encoding="utf-8") as f:
                return f.read()
    raise BdtError(f"(test) page simulée absente pour {url}")


def series_url(url_or_id) -> str:
    """Accepte un identifiant (« 5323 ») ou une adresse de série, renvoie l'adresse canonique."""
    s = str(url_or_id).strip()
    if s.isdigit():
        return f"{BASE}/serie-{s}-BD.html"
    m = re.search(r"serie-(\d+)-BD([-\w]*?)(?:__\d+)?\.html", s)
    if m:
        return f"{BASE}/serie-{m.group(1)}-BD{m.group(2)}.html"
    raise BdtError("Adresse de série Bédéthèque non reconnue (attendu : …/serie-1234-BD-Nom.html)")


# ----------------------------------------------------------------------------
# Analyse des pages
# ----------------------------------------------------------------------------
def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_search(html: str, query: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    head = None
    for h in soup.find_all("h2"):
        if re.search(r"s[ée]ries?\s+trouv", h.get_text(), re.I):
            head = h
            break
    lists = []
    if head is not None:
        container = head.parent
        sib = container.find_next_sibling()
        while sib is not None and not (getattr(sib, "name", None) == "ul" and "bdt-liste" in (sib.get("class") or [])):
            if getattr(sib, "name", None) == "div" and "bdt-section-head" in (sib.get("class") or []):
                break
            sib = sib.find_next_sibling()
        if sib is not None and getattr(sib, "name", None) == "ul":
            lists.append(sib)
    if not lists:  # repli : toutes les listes contenant des liens de séries
        lists = [ul for ul in soup.find_all("ul") if ul.find("a", href=re.compile(r"/serie-\d+-BD"))]
    seen = set()
    for ul in lists:
        for a in ul.find_all("a", href=re.compile(r"/serie-\d+-BD")):
            href = a["href"]
            m = re.search(r"serie-(\d+)-BD", href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            name_el = a.select_one(".bdt-liste-l1") or a
            name = _text(name_el).replace("Correspondance exacte", "").strip()
            metas = [_text(x) for x in a.select(".bdt-liste-meta")]
            tomes = None
            genre = None
            for mt in metas:
                mm = re.search(r"(\d+)\s*tomes?", mt)
                if mm:
                    tomes = int(mm.group(1))
                elif mt:
                    genre = mt
            exact = a.select_one(".bdt-liste-exact") is not None
            score = similarity(query, name)
            if exact:
                score = max(score, 0.95)
            out.append({"id": int(m.group(1)), "url": href if href.startswith("http") else BASE + href,
                        "name": name, "genre": genre, "tomes": tomes, "exact": exact, "score": round(score, 3)})
    out.sort(key=lambda c: (-c["score"], -(c["tomes"] or 0)))
    return out


_INDEX_RE = re.compile(r'href="(?:https?://www\.bedetheque\.com)?(/serie-(\d+)-BD[^"]*?\.html)"[^>]*>(.*?)</a>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_index(html: str) -> list[dict]:
    """Page « Séries BD - A » : liens de séries (nom + adresse), sans passer par BeautifulSoup (page de 3 Mo)."""
    import html as html_mod
    out = []
    seen = set()
    for m in _INDEX_RE.finditer(html):
        sid = int(m.group(2))
        if sid in seen:
            continue
        inner = m.group(3)
        b = re.search(r"<b>(.*?)</b>", inner, re.S)
        name = html_mod.unescape(_TAG_RE.sub(" ", b.group(1) if b else inner))
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            continue
        seen.add(sid)
        out.append({"id": sid, "name": name, "url": BASE + m.group(1)})
    return out


def index_letter_for(query: str) -> str:
    """Lettre de l'index où Bédéthèque range une série (articles rejetés à la fin : « Aigles (Les) » → A, chiffres → 0)."""
    q = norm_title(query)
    if not q:
        return "0"
    c = q[0].upper()
    return c if c in INDEX_LETTERS and c != "0" else "0"


def parse_series(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = ""
    if h1:
        a = h1.find("a")
        title = _text(a) if a else re.sub(r"^\s*S[ée]rie\s*:\s*", "", _text(h1))
    genre = _text(soup.select_one(".bdt-sh-genre")) or None
    status = _text(soup.select_one(".bdt-sh-parution")) or None
    years = None
    by = soup.select_one(".bdt-ah-by")
    if by:
        m = re.search(r"((?:19|20)\d\d)\s*(?:[-–]\s*((?:19|20)\d\d)?)?", _text(by))
        if m:
            years = m.group(1) + ("-" + m.group(2) if m.group(2) else ("-" if "-" in _text(by) or "–" in _text(by) else ""))
    tomes_count = None
    for li in soup.select(".bdt-ah-pastilles li"):
        m = re.search(r"(\d+)\s*tomes?", _text(li))
        if m:
            tomes_count = int(m.group(1))
    sid = None
    m = re.search(r"serie-(\d+)-BD", url)
    if m:
        sid = int(m.group(1))
    albums = []
    for li in soup.select(".bdt-box-albums-liste li"):
        a = li.find("a", href=True)
        if not a:
            continue
        num_el = li.select_one(".bdt-box-albums-num")
        raw = (num_el.get("title") if num_el and num_el.get("title") else _text(num_el)).strip()
        kind, number, suffix = classify_number(raw)
        t = _text(li.select_one(".bdt-box-albums-titre")) or a.get("title") or ""
        date = _text(li.select_one(".bdt-box-albums-dl")) or None
        year = None
        if date:
            my = re.search(r"((?:19|20)\d\d)", date)
            year = int(my.group(1)) if my else None
        href = a["href"]
        albums.append({"num_raw": raw, "number": number, "suffix": suffix, "kind": kind, "title": t,
                       "date": date, "year": year, "url": href if href.startswith("http") else BASE + href})
    data = {"id": sid, "url": url, "title": title, "genre": genre, "status": status, "years": years,
            "tomes_count": tomes_count, "albums": albums, "details": parse_details(html)}
    return data


def classify_number(raw: str) -> tuple[str, Optional[int], Optional[str]]:
    """« 12 » → tome 12 ; « 12a » → tome 12 (variante a) ; « HS1 » → hors-série 1 ; « INT 3 » → intégrale 3."""
    s = raw.strip()
    m = re.fullmatch(r"(\d+)\s*([a-z]?)", s, re.I)
    if m:
        return "tome", int(m.group(1)), (m.group(2).lower() or None)
    m = re.fullmatch(r"(HS|INT|HC|SP|Pir|BOBD|TL|TT|Pub|Cof|COF)\.?\s*(\d*)\s*([a-z]?)", s, re.I)
    if m:
        tag = m.group(1).upper()
        kind = {"HS": "hs", "INT": "int"}.get(tag, "other")
        return kind, (int(m.group(2)) if m.group(2) else None), (m.group(3).lower() or None)
    return "other", None, None


def parse_details(html: str) -> dict:
    """Blocs « Détail des albums » : { url_album: {writers, pencillers, colorists, publisher, collection, isbn, pages, legal} }."""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for ed in soup.select(".bdt-edition"):
        head = ed.select_one(".bdt-edition-head h3 a[href]") or ed.select_one(".bdt-edition-head a[href]")
        if not head:
            continue
        href = head["href"]
        url = href if href.startswith("http") else BASE + href
        info = {"writers": [], "pencillers": [], "colorists": [], "publisher": None, "collection": None,
                "isbn": None, "pages": None, "legal": None}
        for dl in ed.select("dl"):
            for dt in dl.find_all("dt"):
                label = _text(dt).lower()
                dd = dt.find_next_sibling("dd")
                if dd is None:
                    continue
                if label.startswith("sc"):
                    info["writers"] += people(dd)
                elif label.startswith("dessin"):
                    info["pencillers"] += people(dd)
                elif label.startswith("couleur"):
                    info["colorists"] += people(dd)
                elif label.startswith("éditeur") or label.startswith("editeur"):
                    info["publisher"] = _text(dd) or None
                elif label.startswith("collection"):
                    info["collection"] = _text(dd) or None
                elif "isbn" in label or "ean" in label:
                    info["isbn"] = re.sub(r"[^0-9Xx]", "", _text(dd)) or None
                elif label.startswith("planches"):
                    m = re.search(r"\d+", _text(dd))
                    info["pages"] = int(m.group()) if m else None
                elif label.startswith("dépôt") or label.startswith("depot"):
                    info["legal"] = _text(dd) or None
        out[url] = info
    return out


def people(dd) -> list[str]:
    els = dd.select("[itemprop]") or dd.select("a") or [dd]
    out = []
    for el in els:
        n = _text(el).strip(" ,")
        if not n:
            continue
        if "," in n:  # « Nom, Prénom » → « Prénom Nom »
            last, first = [p.strip() for p in n.split(",", 1)]
            n = f"{first} {last}".strip()
        if n not in out:
            out.append(n)
    return out


def merge_details(data: dict) -> None:
    for alb in data["albums"]:
        det = data["details"].get(alb["url"])
        if det:
            alb.update({k: v for k, v in det.items()})
    data["detailed"] = sum(1 for a in data["albums"] if a.get("publisher") or a.get("writers"))


# ----------------------------------------------------------------------------
# Comparaison avec un dossier
# ----------------------------------------------------------------------------
def compare(series: dict, files: list[dict]) -> dict:
    """files : [{id, name}] (albums du dossier). Renvoie correspondances, tomes manquants, fichiers non reconnus, doublons."""
    tomes = [a for a in series["albums"] if a["kind"] == "tome" and a["number"] is not None]
    by_num: dict[int, list[dict]] = {}
    for a in tomes:
        by_num.setdefault(a["number"], []).append(a)
    matches, unmatched, used = [], [], {}
    for f in files:
        parsed = parse_album_name(f["name"])
        cand = None
        how = None
        if parsed["kind"] == "tome" and parsed["number"] is not None and parsed["number"] in by_num:
            cand, how = by_num[parsed["number"]][0], "num"
        elif parsed["title"]:
            best = max(((similarity(parsed["title"], a["title"]), a) for a in series["albums"] if a["title"]),
                       key=lambda x: x[0], default=(0, None))
            if best[0] >= 0.86:
                cand, how = best[1], "title"
        if cand is None and parsed["kind"] in ("hs", "int") and parsed["number"] is not None:
            specials = [a for a in series["albums"] if a["kind"] == parsed["kind"] and a["number"] == parsed["number"]]
            if specials:
                cand, how = specials[0], "num"
            elif parsed["number"] in by_num:
                cand, how = by_num[parsed["number"]][0], "num"   # ex. série « L'Intégrale » numérotée normalement
        if cand is None:
            unmatched.append({"id": f["id"], "name": f["name"], "parsed": parsed})
            continue
        key = cand["url"]
        used.setdefault(key, []).append(f["id"])
        matches.append({"id": f["id"], "name": f["name"], "how": how, "album": cand})
    present_nums = {m["album"]["number"] for m in matches if m["album"]["kind"] == "tome" and m["album"]["number"] is not None}
    missing = [a for a in tomes if a["number"] not in present_nums]
    # un seul tome par numéro dans « manquants » (éditions a/b)
    seen = set()
    missing_unique = []
    for a in missing:
        if a["number"] in seen:
            continue
        seen.add(a["number"])
        missing_unique.append(a)
    duplicates = [{"url": k, "ids": v} for k, v in used.items() if len(v) > 1]
    total = len({a["number"] for a in tomes})
    return {"matches": matches, "missing": missing_unique, "unmatched": unmatched, "duplicates": duplicates,
            "present": len(present_nums), "total": total,
            "specials": [a for a in series["albums"] if a["kind"] != "tome"]}
