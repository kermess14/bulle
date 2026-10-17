# Bulle — lecteur de BD maison (prototype v0.1)

Bulle est un petit serveur web qui fait, en plus simple, ce qu'on aime dans Ubooquity
(le rangement suit vos dossiers) avec un lecteur plus moderne inspiré de Kavita.

- **Navigation par dossiers** : un dossier = une série ; les sous-dossiers sont gardés
  (ex. `Blueberry/01 - Blueberry/…`). Rien n'est deviné d'après les noms de fichiers,
  les dossiers vides sont cachés, le tri est « naturel » (T2 avant T10).
- **Formats** : CBZ, ZIP, CBR, RAR, PDF (et CB7/7z, CBT/tar). Le vrai format est détecté
  d'après le contenu : un `.cbr` qui est en fait un zip fonctionne.
- **Lecteur** : page entière / pleine largeur / taille d'origine, clavier, tactile (balayage,
  zones de tape), sens manga, plein écran, préchargement des pages suivantes, enchaînement
  sur l'album suivant à la fin.
- **Progression** : reprise là où vous vous êtes arrêté, « Reprendre la lecture » sur l'accueil,
  badges lu / en cours (aussi sur les dossiers : « 3/16 lus »), marquer lu / non lu.
- **Recherche** sans tenir compte des accents ni de la casse (« aigles decap » trouve
  « Aigles Décapitées (Les) »), sur les noms de dossiers et de fichiers.
- **Pages redimensionnées** par le serveur (comme Ubooquity) et mises en cache : rapide sur
  mobile, même avec des CBZ de 400 Mo.
- **Scan** automatique au démarrage puis toutes les 12 h (réglable), ou à la demande (bouton ↻).
  Les couvertures se génèrent en arrière-plan après le scan.
- Ne modifie **jamais** vos fichiers : le dossier des BD est monté en lecture seule.

Dépôt : https://github.com/kermess14/bulle

## Installation sur le serveur OMV (Dockhand) : la stack à coller

L'image Docker est construite automatiquement par GitHub à chaque modification du dépôt
(`.github/workflows/docker.yml`) et publiée sur **`ghcr.io/kermess14/bulle:latest`**.
Le fichier **`stack.yml`** est la stack à coller :

1. Dans Dockhand : **Stacks → Create**, nom `bulle`, coller le contenu de `stack.yml`.
2. Vérifier la ligne du dossier des BD (`"/uncomp3/V3X.BD/00 - BD Français:/library:ro"`,
   le dossier que Kavita et Ubooquity utilisent) et le port (`2205`), puis **Create**.
3. Ouvrir `http://192.168.0.213:2205`. Le premier scan démarre tout seul ; les couvertures
   se génèrent ensuite en arrière-plan (comptez de quelques minutes à une demi-heure pour quelques
   milliers d'albums ; on peut déjà naviguer et lire pendant ce temps, les couvertures des dossiers
   ouverts sont générées en priorité et un bandeau en bas indique l'avancement).

Autre possibilité dans Dockhand : **Stacks → From Git**, dépôt `https://github.com/kermess14/bulle`,
branche `main`, fichier `stack.yml` — avec l'auto-update, le serveur suit le dépôt tout seul.

La progression de lecture et le cache d'images sont dans le volume Docker `bulle-data`
(remplacer `bulle-data:/data` par un chemin du serveur, ex. `/srv/.../bulle/data:/data`, pour les
avoir sous la main). Mise à jour : redéployer la stack (« pull » de l'image) ; la progression est conservée.

### Variante autonome, sans image : `stack-autonome.yml`

Même chose mais sans dépendre de GitHub : le code de Bulle est embarqué dans le fichier (archive
compressée en base64 dans la variable `BULLE_SRC`) et décompressé au démarrage dans un conteneur
`python:3.12-slim` standard, qui installe `unar` et les dépendances Python la première fois
(1 à 3 minutes, lignes `[bulle] …` dans les logs ; ensuite elles restent dans le volume `bulle-venv`).
Après une modification du code, `python3 make_stack.py` régénère ce fichier.

### Variante « construite » (SSH)

`docker-compose.yml` + `Dockerfile` : copier le dossier `bulle` sur le serveur puis
`cd bulle && docker compose up -d --build`. Les données sont alors dans `./data`.

### Réglages (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `LIBRARY_ROOT` | `/library` | dossier des BD dans le conteneur |
| `DATA_DIR` | `/data` | base de données et cache |
| `PORT` | `2203` | port d'écoute (`2205` dans la stack et le docker-compose fournis) |
| `SCAN_INTERVAL_HOURS` | `12` | rescan automatique (0 = désactivé) |
| `SCAN_ON_START` | `1` | scan au démarrage |
| `PRELOAD_COVERS` | `1` | générer les couvertures après un scan |
| `PAGE_CACHE` | `1` | garder les pages redimensionnées sur disque |
| `THREADS` | `8` | nombre de requêtes servies en parallèle |
| `PRELOAD_THREADS` | `3` | couvertures générées en parallèle après un scan (baisser à 1 sur un petit serveur) |

### Sans Docker (pour essayer sur un PC)

```
pip install -r requirements.txt
LIBRARY_ROOT="/chemin/vers/mes/BD" DATA_DIR=./data python -m bulle.server
```
puis ouvrir `http://localhost:2203` (ou le port donné par `PORT`). Pour les CBR il faut l'outil `unar` (ou `unrar`, `7z`,
`bsdtar`) installé sur la machine ; les PDF utilisent `pypdfium2` (installé par `requirements.txt`).

## Utilisation

- Cliquer sur une couverture : ouvre le dossier, ou lance la lecture de l'album (reprise automatique).
- Le petit « i » sur un album : fiche (taille, pages, progression, marquer lu / non lu,
  recommencer, télécharger, ouvrir le dossier). Un album illisible y explique pourquoi.
- Dans les gros dossiers (40 entrées et plus), une barre de lettres permet de sauter directement à une lettre.
- Dans le lecteur : `←` `→` ou `Espace` pour tourner les pages (en mode largeur, `Espace` fait d'abord
  défiler la page), clic sur les bords de l'image, balayage ou tape sur les bords sur mobile ;
  tape / clic au centre pour afficher ou cacher les barres. Molette = page suivante / précédente
  en mode page entière.
  `F` change l'ajustement, `M` le sens manga, `P` le plein écran, `Début` / `Fin` première / dernière
  page, `Échap` revient au dossier.
- Le lecteur retient l'ajustement choisi et le sens de lecture par album (dans le navigateur),
  et le dernier ajustement choisi devient celui par défaut.
- À la dernière page, une flèche de plus propose l'album suivant du dossier (`Entrée` pour enchaîner).

## Comment c'est fait

```
bulle/
  bulle/library.py   scanner des dossiers + base SQLite (albums, dossiers, progression, recherche)
  bulle/comics.py    ouverture CBZ/CBR/PDF, redimensionnement JPEG, cache disque
  bulle/server.py    serveur web Flask (servi par waitress) + API JSON + scan périodique
  bulle/static/      interface : index.html + app.js (navigation), reader.html + reader.js (lecteur), style.css
  stack.yml          la stack à coller dans Dockhand (image ghcr.io/kermess14/bulle)
  stack-autonome.yml la même stack sans image (code embarqué), générée par make_stack.py
  start.sh           ce que fait le conteneur de la stack autonome au démarrage
  Dockerfile, docker-compose.yml, requirements.txt   l'image (construite par GitHub Actions, ou en SSH)
  .github/workflows/docker.yml   construction et publication automatiques de l'image
```

L'API (toutes les réponses en JSON, sauf les images) :

| Route | Rôle |
|---|---|
| `GET /api/browse` · `/api/browse/<id>` | contenu d'un dossier (fil d'Ariane, enfants, progression) |
| `GET /api/item/<id>` | fiche d'un album (pages, précédent / suivant, progression) |
| `GET /api/cover/<id>` | couverture (album, ou premier album d'un dossier), 400 px de large |
| `GET /api/page/<id>/<n>?w=1200` | page `n` (0 = première) redimensionnée en JPEG ; `w=0` = fichier d'origine |
| `GET` `PUT` `DELETE /api/progress/<id>` | progression (`{"page": 12}` ou `{"completed": true}`) ; `DELETE` = non lu |
| `GET /api/continue` · `/api/recent` | reprendre la lecture · ajouts récents |
| `GET /api/search?q=` | recherche dans les noms (sans accents ni casse) |
| `POST /api/scan` · `GET /api/scan` | lancer un scan · état du scan et des couvertures |
| `GET /api/stats` | nombre d'albums, de dossiers, taille, dernier scan |
| `GET /api/download/<id>` | télécharger le fichier d'origine |
| `GET /read/<id>` | la page du lecteur (`?page=0` pour recommencer au début) |

Les largeurs de pages servies sont arrondies à 400, 600, 800, 1000, 1200, 1600, 2000 ou 2400 px
pour que le cache reste raisonnable (~300 Ko par page lue en 1200 px). Les CBR sont décompressés
une fois dans `data/cache/extract` (les 8 derniers albums ouverts sont gardés).

## Limites du prototype et suite possible

- Pas de comptes utilisateurs ni de mot de passe : à réserver au réseau local (ou derrière
  un reverse proxy avec authentification).
- Pas encore de double page ni de lecture en « défilement continu ».
- Pas de flux OPDS (pour les applis de lecture mobiles) : simple à ajouter ensuite.
- Les métadonnées `ComicInfo.xml` (celles que BDConverter ajoutera) ne sont pas encore lues ;
  ce sera la base pour les collections automatiques et les fiches plus riches.
- Les CBR dépendent de l'outil `unar` installé dans l'image Docker ; ce chemin n'a pas pu être
  testé hors Docker (les CBZ, les PDF et les `.cbr` qui sont en réalité des zip l'ont été).
  Si un album s'affiche « illisible », la fiche (bouton « i ») donne la raison.
- Si un fichier est renommé ou déplacé, sa progression de lecture est perdue (elle suit le chemin du fichier).
