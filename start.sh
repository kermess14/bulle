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

echo "[bulle] démarrage du serveur"
exec "$VENV/bin/python" -m bulle.server
