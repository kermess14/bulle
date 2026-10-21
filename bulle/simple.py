"""Lecture simple (/simple) : pages HTML rendues par le serveur, SANS JavaScript, pour de très vieux appareils (iPad 1
sous iOS 5.1 : Safari 5.1 de 2011, 256 Mo de mémoire vive).

Ce module ne fait que fabriquer du HTML à partir de données déjà préparées par le serveur (voir « /simple » dans
server.py, qui s'occupe de la session, des droits et de la progression). Règles d'écriture, pour que ça tienne sur un
vieux Safari :
  - HTML « à l'ancienne » (tableaux et blocs simples), CSS 2.1 seulement : pas de flexbox, de grid, de variables CSS, de
    calc(), de vh, de @media ; aucune balise <script>, aucun attribut on…, aucun lien javascript: ;
  - une seule page par adresse, tout le style est dans la page (aucune ressource externe : ni police, ni CDN) ;
  - tout texte qui vient de la bibliothèque (titres, noms de profil…) passe par esc() ;
  - AUCUN lien <a href> : toute la navigation passe par nav_form() (voir plus bas).
"""
from __future__ import annotations

import unicodedata
from html import escape
from typing import Iterable, Optional
from urllib.parse import parse_qsl

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
form{margin:0 0 12px 0}
form.nav{margin:0}
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
table.rowtab{width:100%;border-collapse:collapse}
table.rowtab td{padding:0;vertical-align:top}
table.rowtab td.cvc{width:78px;padding:12px 14px 12px 6px}
button.cvbtn{display:block;width:78px;height:106px;padding:0;margin:0;overflow:hidden;line-height:0;border:1px solid #888;background:#ddd;-webkit-appearance:none;-webkit-box-sizing:border-box;box-sizing:border-box}
button.cvbtn img.cv{display:block;width:76px;height:auto}
button.rowbtn{display:block;width:100%;min-height:130px;padding:12px 6px;margin:0;border:0;background:transparent;-webkit-appearance:none;-webkit-box-sizing:border-box;box-sizing:border-box;text-align:left;color:#222;font-family:Helvetica,Arial,sans-serif;font-size:22px;line-height:1.35}
.t{display:block;font-size:26px;font-weight:bold;line-height:1.2}
.s{display:block;font-size:20px;color:#6b665c;margin-top:4px}
.letters{margin:8px 0}
.letters form{display:inline;margin:0}
.letters button{display:inline-block;min-width:44px;padding:10px 6px;margin:2px;background:#e1dacb;border:1px solid #b9b19e;font-weight:bold;color:#222;font-size:22px;font-family:Helvetica,Arial,sans-serif;-webkit-appearance:none}
.letters button.cur{background:#2e6da4;color:#fff;border-color:#1d4c78}
.crumb{font-size:20px;color:#6b665c;margin:4px 0}
"""


# Écran d'accueil de l'iPad : iOS 5 ne connaît pas le manifest web (iOS 11.3), il lit ces balises propres à Apple. Elles sont dans
# le <head> de TOUTES les pages /simple (on peut ajouter l'icône depuis n'importe laquelle ; la page de départ de l'icône
# est celle où l'on se trouvait : /simple pour avoir l'accueil). Les icônes sont servies sans authentification (l'iPad les
# demande avant la connexion).
# LIENS : dans une application de l'écran d'accueil, iOS (avant 11.3) rouvre Safari, avec sa barre d'adresse, pour tout
# <a href> touché (l'application s'ouvre en plein écran sur /simple, puis le premier lien en sort). Ce qui reste dans
# l'application : la soumission d'un formulaire (ce n'est pas un « lien touché »). Toute la navigation de /simple passe
# donc par nav_form() : un petit formulaire GET dont le bouton est l'élément touchable. Pas de <a href>, pas de
# target="_blank", pas de redirection JavaScript.
APPLE_HEAD = ('<meta name="apple-mobile-web-app-capable" content="yes">'
              '<meta name="apple-mobile-web-app-status-bar-style" content="black">'
              '<meta name="apple-mobile-web-app-title" content="Bulle">'
              '<link rel="apple-touch-icon" href="/simple/icone-72.png">'
              '<link rel="apple-touch-icon" sizes="72x72" href="/simple/icone-72.png">'
              '<link rel="apple-touch-icon" sizes="144x144" href="/simple/icone-144.png">')

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'
# Lecture : ni zoom ni défilement. « maximum-scale=1 » évite aussi le bogue d'iOS qui agrandit la page quand on tourne
# l'iPad de portrait en paysage (la planche ne tiendrait plus dans l'écran) ; sans zoom, pas de délai au toucher non plus.
VIEWPORT_READER = ('<meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1, '
                   'maximum-scale=1, user-scalable=no">')


def layout(title: str, body: str) -> str:
    """Page complète : doctype simple, jeu de caractères, balises Apple, style intégré. Largeur « de l'appareil » : 768 px
    en portrait et 1024 px en paysage sur un iPad 1 ; le pincement pour zoomer reste possible."""
    return ("<!DOCTYPE html>\n"
            f'<html lang="fr"><head><meta charset="utf-8">{VIEWPORT}{APPLE_HEAD}'
            f"<title>{esc(title)}</title>"
            f'<style>{CSS}</style></head>'
            f'<body><div id="main">{body}</div></body></html>\n')


def nav_form(href: str, inner: str, cls: str = "", form_cls: str = "", aria: str = "") -> str:
    """Un « lien » qui reste dans l'application iOS : un petit formulaire GET dont le bouton est ce que l'on touche.
    Les paramètres de l'adresse (?p=3, ?l=S…) deviennent des champs cachés (un formulaire GET remplace la partie « ? » de
    son action) ; l'adresse visitée est donc la même qu'avec un lien. `inner` : contenu du bouton (déjà échappé) ;
    `aria` : libellé pour les lecteurs d'écran d'un bouton sans texte."""
    path, _, query = href.partition("?")
    hidden = "".join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">' for k, v in parse_qsl(query, keep_blank_values=True))
    label = f' aria-label="{esc(aria)}" title="{esc(aria)}"' if aria else ""
    klass = f' class="{esc(cls)}"' if cls else ""
    return (f'<form method="get" action="{esc(path)}" class="nav {esc(form_cls)}">{hidden}'
            f'<button type="submit"{klass}{label}>{inner}</button></form>')


def link_button(href: Optional[str], label: str, cls: str = "") -> str:
    """Gros bouton de navigation ; sans adresse : bouton grisé, non touchable."""
    if href is None:
        return f'<span class="btn off">{esc(label)}</span>'
    return nav_form(href, esc(label), cls=f"btn {cls}".strip())


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
    """Une ligne : la couverture et le titre sont chacun un bouton qui mène au même endroit (tableau : rien de fragile
    dans un bouton). La couverture a sa case de taille fixe : la liste ne « saute » pas quand les images arrivent."""
    sub = f'<span class="s">{esc(it["sub"])}</span>' if it.get("sub") else ""
    title = nav_form(it["href"], f'<span class="t">{esc(it["name"])}</span>{sub}', cls="rowbtn")
    if it.get("cover"):
        cover = nav_form(it["href"], f'<img class="cv" src="{esc(it["cover"])}" alt="">', cls="cvbtn",
                         aria=it["name"])
        cells = f'<td class="cvc">{cover}</td><td>{title}</td>'
    else:
        cells = f'<td colspan="2">{title}</td>'
    return f'<div class="item"><table class="rowtab"><tr>{cells}</tr></table></div>'


def home_page(name: str, continuing: list[dict], change_profile: bool, logout: bool) -> str:
    parts = [f"<h1>Bulle</h1><p>Bonjour <b>{esc(name)}</b></p>",
             link_button("/simple/series", "Toutes les séries")]
    if continuing:
        parts.append("<h2>Reprendre la lecture</h2>")
        parts.extend(_row(it) for it in continuing)
    if change_profile:
        parts.append(f'<div class="gap">{link_button("/simple?choix=1", "Changer de profil", "alt")}</div>')
    if logout:
        parts.append('<form method="post" action="/simple/deconnexion" class="gap">'
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
            links.append(nav_form(f"{base}?l={'0' if L == '#' else L}", esc(L), cls="cur" if L == cur else ""))
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
# Lecture : QUE la planche, plein écran, fond noir. Rien d'autre que deux grandes zones tactiles (moitié gauche de l'écran :
# page précédente, moitié droite : page suivante) et un petit bouton discret en haut à gauche (44 px) qui ramène à l'album.
# La planche est l'image de fond d'une zone qui remplit l'écran, avec « background-size: contain » : le navigateur la fait
# tenir entièrement dans l'écran (paysage comme portrait, avec ou sans barre d'outils de Safari), centrée, sans déformation
# et sans défilement, quelle que soit la taille de l'écran ; une petite planche est agrandie. Cela ne dépend d'aucune
# hauteur en pourcentage (peu fiables sur un vieux Safari) ni de JavaScript.
READER_CSS = """
html,body{margin:0;padding:0;height:100%;background:#000;overflow:hidden}
div.screen{position:fixed;left:0;top:0;right:0;bottom:0;background-color:#000;background-repeat:no-repeat;background-position:center center;-webkit-background-size:contain;background-size:contain}
form.nav{margin:0}
button.zone{position:fixed;top:0;height:100%;width:50%;margin:0;padding:0;border:0;background:transparent;-webkit-appearance:none;-webkit-box-sizing:border-box;box-sizing:border-box;z-index:1;outline:none;-webkit-tap-highlight-color:rgba(0,0,0,0)}
button.zl{left:0}
button.zr{right:0}
button.back{position:fixed;left:6px;top:6px;width:44px;height:44px;margin:0;padding:0;z-index:2;overflow:hidden;text-align:center;font:bold 34px/40px Helvetica,Arial,sans-serif;color:#fff;background:#333;background:rgba(0,0,0,.45);border:1px solid #777;border:1px solid rgba(255,255,255,.35);border-radius:8px;opacity:.6;-webkit-appearance:none;-webkit-box-sizing:border-box;box-sizing:border-box;outline:none;-webkit-tap-highlight-color:rgba(0,0,0,0)}
img.pre{position:absolute;left:-9999px;top:0;width:1px;height:1px}
"""


BACK_LABEL = "Retour à l'album"   # libellé (lecteurs d'écran) du petit bouton


def reader_page(title: str, page: int, pages: int, img: str, preload: Optional[str], prev_url: Optional[str],
                next_url: Optional[str], back_url: str) -> str:
    """Une planche, plein écran (voir plus haut). Les zones gauche / droite et le petit bouton sont des boutons de
    formulaires GET (sans JavaScript, et qui ne font pas sortir de l'application iOS) ; sans texte, avec un libellé pour
    les lecteurs d'écran. `preload` : la planche suivante, demandée par une image invisible pour qu'elle soit déjà là
    quand on tourne la page."""
    zl = nav_form(prev_url, "", cls="zone zl", aria="Page précédente") if prev_url else ""
    zr = nav_form(next_url, "", cls="zone zr", aria="Page suivante") if next_url else ""
    pre = f'<img class="pre" src="{esc(preload)}" alt="">' if preload else ""
    label = f"{title} — page {page} / {pages}"
    return ("<!DOCTYPE html>\n"
            f'<html lang="fr"><head><meta charset="utf-8">{VIEWPORT_READER}{APPLE_HEAD}'
            f"<title>{esc(label)}</title>"
            f'<style>{READER_CSS}</style></head>'
            f'<body><div class="screen" role="img" aria-label="{esc(label)}" '
            f'style="background-image:url(&#39;{esc(img)}&#39;)"></div>'
            f'{zl}{zr}'
            f'{nav_form(back_url, "‹", cls="back", aria=BACK_LABEL)}'
            f'{pre}</body></html>\n')
