"""Fabrique les icônes « application » de la lecture simple (/simple) à partir du logo de Bulle (static/icon-512.png).

  python tools/make_icons.py

Écrit bulle/static/simple-icone-72.png (iPad 1) et simple-icone-144.png (iPad Retina) : carrées, SANS transparence (RVB,
sans canal alpha) et sans coins arrondis : iOS ajoute lui-même les coins arrondis (et le reflet) à l'icône de l'écran
d'accueil. Servies par le serveur sous /simple/icone-72.png et /simple/icone-144.png.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(os.path.dirname(HERE), "bulle", "static")
BACKGROUND = (15, 17, 21)   # le fond du logo (#0f1115)


def main() -> None:
    src = Image.open(os.path.join(STATIC, "icon-512.png")).convert("RGBA")
    flat = Image.new("RGB", src.size, BACKGROUND)
    flat.paste(src, mask=src.getchannel("A"))   # tout ce qui était transparent devient le fond du logo
    for size in (72, 144):
        out = flat.resize((size, size), Image.Resampling.LANCZOS)
        path = os.path.join(STATIC, f"simple-icone-{size}.png")
        out.save(path, "PNG", optimize=True)
        print(f"{path} : {size}x{size}, {os.path.getsize(path)} octets")


if __name__ == "__main__":
    main()
