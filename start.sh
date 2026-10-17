#!/bin/sh
# Démarrage de Bulle dans un conteneur python:3.12-slim « nu » (stack à coller, sans construction d'image) :
# installe ce qui manque la première fois, puis lance le serveur. Les dépendances Python sont gardées
# dans le volume /opt/venv pour que les redémarrages soient rapides.
set -e
cd /app
echo "[bulle] préparation…"

if ! command -v unar >/dev/null 2>&1; then
  echo "[bulle] installation de unar (lecture des CBR)…"
  if apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq --no-install-recommends unar tzdata >/dev/null 2>&1; then
    rm -rf /var/lib/apt/lists/*
    echo "[bulle] unar installé"
  else
    echo "[bulle] ATTENTION : unar n'a pas pu être installé (pas d'accès internet ?) : les CBR ne seront pas lisibles"
  fi
fi

VENV=/opt/venv
if [ ! -x "$VENV/bin/python" ]; then
  echo "[bulle] création de l'environnement Python…"
  python -m venv "$VENV"
fi
if ! cmp -s requirements.txt "$VENV/.requirements.txt"; then
  echo "[bulle] installation des dépendances Python (une seule fois, 1 à 2 minutes)…"
  if "$VENV/bin/pip" install -q --disable-pip-version-check -r requirements.txt; then
    cp requirements.txt "$VENV/.requirements.txt"
    echo "[bulle] dépendances installées"
  else
    echo "[bulle] ATTENTION : dépendances non installées (pas d'accès internet ?) — nouvel essai au prochain démarrage"
  fi
fi

# Pages HEIC/HEIF et JPEG XL : facultatif, une seule fois
if [ ! -f "$VENV/.extra-formats" ]; then
  "$VENV/bin/pip" install -q --disable-pip-version-check pillow-heif pillow-jxl-plugin >/dev/null 2>&1 \
    && echo "[bulle] formats HEIC / JPEG XL installés" || echo "[bulle] formats HEIC / JPEG XL non installés (facultatif)"
  touch "$VENV/.extra-formats"
fi

# Polices « lettrage BD » (variante autonome : elles ne sont pas dans l'archive embarquée) — facultatif, sans internet
# Bulle utilise simplement les polices du navigateur.
FONTS=bulle/static/fonts
if [ ! -f "$FONTS/Bangers.woff" ]; then
  mkdir -p "$FONTS"
  echo "[bulle] téléchargement des polices (facultatif)…"
  for f in Bangers.woff PatrickHandSC.woff ComicNeue-Regular.woff ComicNeue-Bold.woff; do
    python3 -c "import urllib.request,sys; urllib.request.urlretrieve('https://raw.githubusercontent.com/kermess14/bulle/main/bulle/static/fonts/$f', '$FONTS/$f')" 2>/dev/null || echo "[bulle] police $f non téléchargée (pas d'accès internet ?)"
  done
fi

echo "[bulle] démarrage du serveur"
exec "$VENV/bin/python" -m bulle.server
