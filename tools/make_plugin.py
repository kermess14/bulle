"""Fabrique le paquet (.zip) d'un plugin de Bulle à partir de son dossier.

    python tools/make_plugin.py CHEMIN/DU/DOSSIER [-o paquet.zip]

Le dossier doit contenir plugin.json (voir PLUGINS.md). Le paquet est créé à côté du dossier, nommé
<id>-<version>.zip, sans les fichiers jetables ou personnels : __pycache__, .git, .venv, .env… et tout ce que liste
« exclude » dans plugin.json (ex. vos réglages, votre historique, vos téléchargements).
Il ne reste plus qu'à l'envoyer dans Bulle : Réglages › Laboratoire › « Installer un plugin ».
"""
import argparse
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bulle.plugins import PluginError, build_package  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Fabrique le paquet .zip d'un plugin de Bulle")
    ap.add_argument("dossier", help="dossier du plugin (celui qui contient plugin.json)")
    ap.add_argument("-o", "--out", help="fichier .zip à créer (par défaut : <id>-<version>.zip à côté du dossier)")
    ap.add_argument("-l", "--list", action="store_true", help="afficher la liste des fichiers mis dans le paquet")
    args = ap.parse_args()
    try:
        path, manifest, count = build_package(args.dossier, args.out)
    except PluginError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    size = os.path.getsize(path)
    print(f"Paquet prêt : {path}")
    print(f"  {manifest['name']} {manifest['version']} (id « {manifest['id']} ») — {count} fichiers, {size / 1024:.0f} Ko")
    if args.list:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                print("   ", name)
    print("À envoyer dans Bulle : Réglages › Laboratoire › Installer un plugin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
