"""Lecture simple (/simple) : pages HTML rendues par le serveur, SANS JavaScript, pour de très vieux appareils (iPad 1
sous iOS 5.1 : Safari 5.1 de 2011, 256 Mo de mémoire vive).

Ce module ne fait que fabriquer du HTML à partir de données déjà préparées par le serveur (voir « /simple » dans
server.py, qui s'occupe de la session, des droits et de la progression). Règles d'écriture, pour que ça tienne sur un
vieux Safari :
  - HTML « à l'ancienne » (tableaux et blocs simples), CSS 2.1 seulement : pas de flexbox, de grid, de variables CSS, de
    calc(), de vh, de @media ; aucune balise <script>, aucun attribut on…, aucun lien javascript: ;
  - une seule page par adresse, tout le style est dans la page (aucune ressource externe : ni police, ni CDN) ;
  - tout texte qui vient de la bibliothèque (titres, noms de profil…) passe par esc().
"""
from __future__ import annotations

import unicodedata
from html import escape
from typing import Iterable, Optional

PER_PAGE = 20   # entrées par page dans les listes (gros liens faciles à toucher, listes courtes pour un vieil appareil)


def esc(s) -> str:
    """Texte → HTML sûr (aussi pour les attributs : les guillemets sont échappés)."""
    return escape("" if s is None else str(s), quote=True)


CSS = """
html,body{margin:0;padding:0}
body{background:#efeadf;color:#222;font-family:Helvetica,Arial,sans-serif;font-size:22px;line-height:1.35;-webkit-text-size-adjust:none}
#main{padding:10px 12px 26px 12px}
h1{font-size:32px;margin:6px 0 12px 0;line-height:1.15}
h2{font-size:26px;margin:20px 0 8px 0}
p{margin:8px 0}
a{color:#17508c}
form{margin:0 0 12px 0}
.muted{color:#6b665c;font-size:19px}
.err{background:#f6d6d2;border:2px solid #c0453a;color:#6d1b14;padding:12px;margin:10px 0;font-weight:bold}
.btn{display:block;width:100%;-webkit-box-sizing:border-box;box-sizing:border-box;-webkit-appearance:none;text-align:center;padding:20px 8px;margin:0;background:#2e6da4;color:#fff;border:2px solid #1d4c78;font-size:26px;font-weight:bold;text-decoration:none;font-family:Helvetica,Arial,sans-serif}
.alt{background:#e1dacb;color:#222;border-color:#b9b19e}
.off{background:#cfcabd;color:#8b8678;border-color:#bdb7a7}
.gap{margin-top:12px}
input.txt{display:block;width:100%;-webkit-box-sizing:border-box;box-sizing:border-box;font-size:26px;padding:14px 10px;margin:0 0 10px 0;border:2px solid #8f8872;background:#fff;font-family:Helvetica,Arial,sans-serif}
.lab{display:block;font-size:20px;margin:8px 0 4px 0;color:#444}
table.bar{width:100%;table-layout:fixed;border-collapse:collapse;margin:6px 0}
table.bar td{padding:0 3px;vertical-align:top}
.cnt{text-align:center;font-size:21px;padding-top:18px}
.item{border-bottom:1px solid #cdc6b6}
a.row{display:block;padding:12px 6px;color:#222;text-decoration:none;min-height:104px}
span.cvb{float:left;display:block;width:76px;height:104px;overflow:hidden;margin:0 14px 0 0;border:1px solid #888;background:#ddd}
img.cv{display:block;width:76px;height:auto}
.t{display:block;font-size:26px;font-weight:bold;line-height:1.2}
.s{display:block;font-size:20px;color:#6b665c;margin-top:4px}
.clr{display:block;clear:both;height:0;overflow:hidden}
.letters{margin:8px 0}
.letters a{display:inline-block;min-width:44px;padding:10px 6px;margin:2px;background:#e1dacb;border:1px solid #b9b19e;text-align:center;font-weight:bold;text-decoration:none;color:#222}
.letters a.cur{background:#2e6da4;color:#fff;border-color:#1d4c78}
.crumb{font-size:20px;color:#6b665c;margin:4px 0}
.pgbox{position:relative;margin:8px 0;text-align:center}
img.pg{display:block;margin:0 auto;max-width:100%;height:auto;border:1px solid #999;background:#fff}
a.zone{position:absolute;top:0;height:100%;width:50%;display:block;overflow:hidden;text-indent:-9999px}
a.zl{left:0}
a.zr{right:0}
img.pre{position:absolute;left:-9999px;top:0;width:1px;height:1px}
"""


def layout(title: str, body: str) -> str:
    """Page complète : doctype simple, jeu de caractères, style intégré. Largeur « de l'appareil » : 768 px en portrait et
    1024 px en paysage sur un iPad 1 ; le pincement pour zoomer reste possible."""
    return ("<!DOCTYPE html>\n"
            '<html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title>"
            f'<style type="text/css">{CSS}</style></head>'
            f'<body><div id="main">{body}</div></body></html>\n')


def link_button(href: Optional[str], label: str, cls: str = "") -> str:
    """Gros bouton-lien ; sans adresse : bouton grisé, non cliquable."""
    if href is None:
        return f'<span class="btn off">{esc(label)}</span>'
    return f'<a class="btn {cls}" href="{esc(href)}">{esc(label)}</a>'


def bar(left: str, middle: str, right: str) -> str:
    """Trois cases de même largeur (tableau, comme en 2005) : précédent / au milieu / suivant."""
    return f'<table class="bar"><tr><td>{left}</td><td>{middle}</td><td>{right}</td></tr></table>'


def progress_label(p: Optional[dict], count: Optional[int] = None) -> str:
    """« Lu », « page 12 / 48 » ou rien, d'après la progression enregistrée."""
    if not p:
        return ""
    if p.get("completed"):
        return "Lu"
    n = count or p.get("page_count")
    page = int(p.get("page") or 0) + 1
    return f"page {page} / {n}" if n else f"page {page}"


def letter_of(name: str) -> str:
    """Lettre de l'index alphabétique : A à Z sans accent, « # » pour le reste (chiffres, signes)."""
    for ch in unicodedata.normalize("NFKD", name or ""):
        if unicodedata.combining(ch):
            continue
        if ch.isalpha():
            up = ch.upper()
            return up if "A" <= up <= "Z" else "#"
        if ch.isalnum():
            return "#"
    return "#"


# ---------------------------------------------------------------- connexion et profils
def message_page(title: str, text: str, links: Iterable[tuple[str, str]] = ()) -> str:
    """Page de message (erreur, album illisible…) avec des gros boutons pour s'en sortir."""
    btns = "".join(f'<div class="gap">{link_button(h, l)}</div>' for h, l in links)
    return layout(title + " — Bulle", f"<h1>{esc(title)}</h1><p>{esc(text)}</p>{btns}")


def login_page(accounts: bool, error: Optional[str] = None) -> str:
    """Connexion : nom + mot de passe (mode « comptes »), ou le code d'accès de la bibliothèque."""
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    if accounts:
        form = ('<form method="post" action="/simple/connexion">'
                '<label class="lab" for="n">Nom du compte</label>'
                '<input class="txt" id="n" type="text" name="name" autocomplete="off" autocapitalize="off" autocorrect="off">'
                '<label class="lab" for="m">Mot de passe</label>'
                '<input class="txt" id="m" type="password" name="password" autocomplete="off">'
                '<button class="btn" type="submit">Se connecter</button></form>')
    else:
        form = ('<form method="post" action="/simple/connexion">'
                '<label class="lab" for="c">Code d\'accès</label>'
                '<input class="txt" id="c" type="password" name="pin" autocomplete="off">'
                '<button class="btn" type="submit">Entrer</button></form>')
    return layout("Connexion — Bulle", f"<h1>Bulle</h1>{err}{form}")


def profiles_page(profiles: list[dict], error: Optional[str] = None, only: Optional[int] = None) -> str:
    """« Qui lit ? » : un gros bouton par profil ; un profil protégé demande son mot de passe dans la même case."""
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    rows = []
    for p in profiles:
        pin = ""
        if p.get("has_pin"):
            pin = (f'<label class="lab" for="p{int(p["id"])}">Mot de passe de {esc(p["name"])}</label>'
                   f'<input class="txt" id="p{int(p["id"])}" type="password" name="pin" autocomplete="off">')
        av = str(p.get("avatar") or "")
        mark = f"{esc(av)} " if av and not av.startswith("data:") and len(av) <= 4 else ""
        rows.append(f'<form method="post" action="/simple/profil"><input type="hidden" name="id" value="{int(p["id"])}">'
                    f'{pin}<button class="btn" type="submit">{mark}{esc(p["name"])}</button></form>')
    return layout("Qui lit ? — Bulle", f"<h1>Qui lit ?</h1>{err}{''.join(rows)}")


# ---------------------------------------------------------------- accueil, listes
def _row(it: dict) -> str:
    # la couverture a sa case de taille fixe : la liste ne « saute » pas quand les images arrivent (lentement, sur un NAS)
    cover = f'<span class="cvb"><img class="cv" src="{esc(it["cover"])}" alt=""></span>' if it.get("cover") else ""
    sub = f'<span class="s">{esc(it["sub"])}</span>' if it.get("sub") else ""
    return (f'<div class="item"><a class="row" href="{esc(it["href"])}">{cover}'
            f'<span class="t">{esc(it["name"])}</span>{sub}<span class="clr"></span></a></div>')


def home_page(name: str, continuing: list[dict], change_profile: bool, logout: bool) -> str:
    parts = [f"<h1>Bulle</h1><p>Bonjour <b>{esc(name)}</b></p>",
             link_button("/simple/series", "Toutes les séries")]
    if continuing:
        parts.append("<h2>Reprendre la lecture</h2>")
        parts.extend(_row(it) for it in continuing)
    if change_profile:
        parts.append(f'<div class="gap">{link_button("/simple?choix=1", "Changer de profil", "alt")}</div>')
    if logout:
        parts.append('<form class="gap" method="post" action="/simple/deconnexion">'
                     '<button class="btn alt" type="submit">Se déconnecter</button></form>')
    return layout("Bulle — lecture simple", "".join(parts))


def list_page(title: str, items: list[dict], page: int, base: str, up: Optional[tuple[str, str]],
              crumb: str = "", letter: str = "") -> str:
    """Liste de gros liens (dossiers, albums), PER_PAGE par page, avec en tête un index alphabétique quand elle est longue.
    `items` : {"href", "name", "cover" (adresse ou vide), "sub", "letter"} ; `base` : adresse de la liste (sans ?)."""
    total = len(items)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, pages))
    chunk = items[(page - 1) * PER_PAGE: page * PER_PAGE]
    head = [f"<h1>{esc(title)}</h1>"]
    if crumb:
        head.append(f'<div class="crumb">{esc(crumb)}</div>')
    head.append(link_button(*up, cls="alt") if up else "")
    if total > 2 * PER_PAGE:
        seen: list[str] = []
        for it in items:
            if it["letter"] not in seen:
                seen.append(it["letter"])
        cur = chunk[0]["letter"] if chunk else ""
        links = []
        for L in seen:
            attr = ' class="cur"' if L == cur else ""
            links.append(f'<a{attr} href="{esc(base)}?l={esc(L if L != "#" else "0")}">{esc(L)}</a>')
        head.append('<div class="letters">' + "".join(links) + "</div>")

    def nav() -> str:
        if pages <= 1:
            return ""
        prev = link_button(f"{base}?p={page - 1}", "« Précédente") if page > 1 else link_button(None, "« Précédente")
        nxt = link_button(f"{base}?p={page + 1}", "Suivante »") if page < pages else link_button(None, "Suivante »")
        return bar(prev, f'<div class="cnt">Page {page} / {pages}</div>', nxt)

    body = "".join(head) + nav()
    body += "".join(_row(it) for it in chunk) if chunk else '<p class="muted">Rien ici pour le moment.</p>'
    body += nav()
    body += f'<div class="gap">{link_button("/simple", "Accueil", "alt")}</div>'
    return layout(f"{title} — Bulle", body)


# ---------------------------------------------------------------- lecture
def reader_page(title: str, page: int, pages: int, img: str, preload: Optional[str], prev_url: Optional[str],
                next_url: Optional[str], next_label: str, back_url: str) -> str:
    """Une planche entière : en haut et en bas, précédent / retour à l'album / suivant ; deux grandes zones sur l'image
    (moitié gauche : précédente, moitié droite : suivante), de simples liens. `preload` : la planche suivante, demandée
    par une image invisible pour qu'elle soit déjà là quand on tourne la page."""
    def buttons() -> str:
        return bar(link_button(prev_url, "« Précédente"), link_button(back_url, "Album", "alt"),
                   link_button(next_url, next_label))
    zl = f'<a class="zone zl" href="{esc(prev_url)}">Page précédente</a>' if prev_url else ""
    zr = f'<a class="zone zr" href="{esc(next_url)}">Page suivante</a>' if next_url else ""
    pre = f'<img class="pre" src="{esc(preload)}" alt="">' if preload else ""
    body = (buttons() + f'<div class="crumb">{esc(title)} — page {page} / {pages}</div>'
            f'<div class="pgbox"><img class="pg" src="{esc(img)}" alt="Page {page}">{zl}{zr}</div>{pre}' + buttons())
    return layout(f"{title} — page {page}", body)
