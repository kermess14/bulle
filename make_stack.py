"""Fabrique stack-autonome.yml : une stack Docker Compose à coller telle quelle dans Dockhand (ou Portainer),
sans rien copier sur le serveur. Le code de Bulle est embarqué dans le fichier (archive tar.gz en base64),
décompressé au démarrage dans un conteneur python:3.12-slim.

Usage : python3 make_stack.py [port]   (défaut : 2205)
"""
import base64
import io
import os
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2205
LIBRARY = os.environ.get("BULLE_LIBRARY", "/uncomp3/V3X.BD/00 - BD Français")

TEMPLATE = """\
# =====================================================================================
#  Bulle — lecteur de BD maison — stack Docker Compose à coller telle quelle
#  (Dockhand : Stacks → Create → coller ce fichier → Create). Rien d'autre à copier.
#
#  Variante AUTONOME (sans image) : le code de Bulle est embarqué ci-dessous (BULLE_SRC, archive compressée en base64) et
#  décompressé au démarrage dans un conteneur Python standard : pas d'image à construire.
#  Au premier démarrage le conteneur installe « unar » (pour les CBR) et les dépendances
#  Python : comptez 1 à 3 minutes, puis http://192.168.0.213:__PORT__
#
#  À vérifier : le chemin du dossier des BD (ligne « source »), monté en lecture seule.
# =====================================================================================
services:
  bulle:
    image: python:3.12-slim
    container_name: bulle
    restart: unless-stopped
    ports:
      - "__PORT__:__PORT__"
    volumes:
      # Le dossier des BD (le même que Kavita / Ubooquity), en lecture seule : Bulle ne modifie jamais vos fichiers.
      - "__LIBRARY__:/library:ro"
      # Progression de lecture + cache d'images (data/cache peut être vidé sans risque)
      - bulle-data:/data
      # Dépendances Python installées une fois pour toutes
      - bulle-venv:/opt/venv
    environment:
      TZ: Europe/Paris
      PORT: "__PORT__"
      LIBRARY_ROOT: /library
      DATA_DIR: /data
      SCAN_INTERVAL_HOURS: "12"   # rescan automatique ; 0 = seulement avec le bouton ↻
      SCAN_ON_START: "1"
      PRELOAD_COVERS: "1"         # couvertures générées en arrière-plan après chaque scan
      PRELOAD_THREADS: "3"        # baisser à 1 si le serveur est petit
      PAGE_CACHE: "1"
      PYTHONUNBUFFERED: "1"
      # ---- le code de Bulle (généré par make_stack.py, ne pas modifier à la main) ----
      BULLE_SRC: >-
__BLOB__
    command: ["sh", "-c", "mkdir -p /app && printenv BULLE_SRC | tr -dc 'A-Za-z0-9+/=' | base64 -d | tar xzf - -C /app && exec sh /app/start.sh"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:__PORT__/api/stats', timeout=4)"]
      interval: 60s
      timeout: 5s
      start_period: 180s
      retries: 3

volumes:
  bulle-data:
  bulle-venv:
"""


def build_blob() -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        def add(path, arcname):
            def filt(ti):
                if "__pycache__" in ti.name or ti.name.endswith(".pyc"):
                    return None
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = "root"
                ti.mtime = 0
                return ti
            tar.add(path, arcname=arcname, filter=filt)
        add(os.path.join(HERE, "bulle"), "bulle")
        add(os.path.join(HERE, "requirements.txt"), "requirements.txt")
        add(os.path.join(HERE, "start.sh"), "start.sh")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "\n".join("        " + b64[i:i + 76] for i in range(0, len(b64), 76))


def main() -> None:
    blob = build_blob()
    out = (TEMPLATE.replace("__PORT__", str(PORT)).replace("__LIBRARY__", LIBRARY).replace("__BLOB__", blob))
    if "$" in out:
        raise SystemExit("Le fichier généré contient un « $ » : Docker Compose l'interpréterait, abandon.")
    dest = os.path.join(HERE, "stack-autonome.yml")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    size = len(blob.replace("\n", "").strip())
    print(f"{dest} écrit : code embarqué {size // 1024} Ko en base64 (limite ~120 Ko), port {PORT}")
    if size > 120_000:
        raise SystemExit("Trop gros pour une variable d'environnement : passer par une image Docker.")


if __name__ == "__main__":
    main()
