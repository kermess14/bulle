# Bulle — lecteur de BD maison (v0.4)

Bulle est un petit serveur web qui fait, en plus simple, ce qu'on aime dans Ubooquity
(le rangement suit vos dossiers) avec un lecteur plus moderne inspiré de Kavita.

- **Navigation par dossiers** : un dossier = une série ; les sous-dossiers sont gardés
  (ex. `Blueberry/01 - Blueberry/…`). Rien n'est deviné d'après les noms de fichiers,
  les dossiers vides sont cachés, le tri est « naturel » (T2 avant T10).
- **Formats** : CBZ, ZIP, CBR, RAR, PDF (et CB7/7z, CBT/tar). Le vrai format est détecté
  d'après le contenu : un `.cbr` qui est en fait un zip fonctionne.
- **Lecteur** : une page, **double page** (couverture et planches larges seules) ou **défilement
  continu** (touche `D`), page entière / pleine largeur / taille d'origine, clavier, tactile (balayage,
  zones de tape), sens manga, plein écran, préchargement des pages suivantes, enchaînement
  sur l'album suivant à la fin.
- **Progression** : reprise là où vous vous êtes arrêté, « Reprendre la lecture » sur l'accueil,
  badges lu / en cours (aussi sur les dossiers : « 3/16 lus »), marquer lu / non lu.
- **Profils** (« Qui lit ? ») : chacun sa progression et ses réglages d'affichage, code PIN facultatif par
  profil, et un **code d'accès** général facultatif pour toute la bibliothèque.
- **Flux OPDS** (`http://<serveur>:2205/opds`) pour lire depuis une appli mobile (Panels, Chunky, Moon+,
  Mihon…) : navigation par dossiers, reprise, récents, recherche, téléchargement et lecture page par page
  (OPDS-PSE) sans télécharger l'album.
- **Recherche** sans tenir compte des accents ni de la casse (« aigles decap » trouve
  « Aigles Décapitées (Les) »), sur les noms de dossiers et de fichiers.
- **Pages redimensionnées** par le serveur (comme Ubooquity) et mises en cache : rapide sur
  mobile, même avec des CBZ de 400 Mo.
- **Scan** automatique au démarrage puis toutes les 12 h (réglable), ou à la demande (bouton ↻).
  Les couvertures se génèrent en arrière-plan après le scan.
- **Réglages** (bouton ⚙) : taille des vignettes et zoom au survol, nombre de vignettes par page
  (la liste est alors découpée en pages, flèches ← → du clavier), accès par lettre, tri, masquer les
  albums lus, thème sombre / clair, réglages du lecteur (ajustement, sens, fond, qualité, préchargement,
  mode nuit…), qualité des images côté serveur, seuil « album lu », fréquence du scan, taille du cache.
  Les réglages d'affichage sont enregistrés sur le serveur (ils vous suivent d'un appareil à l'autre).
- **Bédéthèque** (à la demande) : dans un dossier d'albums, « Analyser » cherche la série sur
  bedetheque.com, compare les tomes officiels avec vos fichiers (présents, manquants affichés en
  cartes grisées à leur place, fichiers non reconnus, doublons), retient les titres officiels, l'année
  et, avec « Auteurs et détails », scénario / dessin / couleurs, éditeur, ISBN. La page **Collection**
  (icône livres) récapitule toutes les séries analysées (complètes, incomplètes, en cours de parution)
  et peut analyser d'un coup les dossiers restants, une requête toutes les 2,5 s, arrêtable à tout moment.
  Si la correspondance automatique hésite, Bulle propose des candidats ou accepte l'adresse de la série.
- Ne modifie **jamais** vos fichiers : le dossier des BD est monté en lecture seule ; les informations
  Bédéthèque restent dans la base de Bulle (les fichiers ne sont ni renommés ni modifiés).

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

Ces variables ne sont que des valeurs de départ : la page ⚙ Réglages de Bulle les modifie (et les
mémorise dans la base) sans redémarrer le conteneur.

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
- Dans les gros dossiers (40 entrées et plus, ou toujours selon le réglage), une barre de lettres permet de
  sauter directement à une lettre, même si la liste est découpée en pages.
- Dans le lecteur : `←` `→` ou `Espace` pour tourner les pages (en mode largeur, `Espace` fait d'abord
  défiler la page), clic sur les bords de l'image, balayage ou tape sur les bords sur mobile ;
  tape / clic au centre pour afficher ou cacher les barres. Molette = page suivante / précédente
  en mode page entière.
  `D` change l'affichage (1 page, 2 pages, défilement), `F` l'ajustement, `M` le sens manga, `P` le plein
  écran, `Début` / `Fin` première / dernière page, `Échap` revient au dossier.
- Le lecteur retient l'ajustement choisi et le sens de lecture par album (dans le navigateur),
  et le dernier ajustement choisi devient celui par défaut.
- À la dernière page, une flèche de plus propose l'album suivant du dossier (`Entrée` pour enchaîner).

## Comment c'est fait

```
bulle/
  bulle/library.py   scanner des dossiers + base SQLite (albums, dossiers, progression, recherche)
  bulle/comics.py    ouverture CBZ/CBR/PDF, redimensionnement JPEG, cache disque
  bulle/bedetheque.py recherche et lecture des fiches Bédéthèque (poliment, avec cache), comparaison avec un dossier
  bulle/opds.py      flux OPDS / OPDS-PSE pour les applis de lecture
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
| `GET` `PUT /api/settings` | réglages globaux (serveur) et du profil courant ; `PUT {"global": {...}, "profile": {...}}` |
| `GET /api/cache` · `POST /api/cache/clear` · `POST /api/covers/rebuild` | taille du cache, vider les pages, régénérer les couvertures |
| `GET` `POST /api/profiles` · `PUT` `DELETE /api/profiles/<id>` · `POST /api/profiles/select` | profils (`{"id", "pin"}` pour choisir) |
| `GET /api/auth/status` · `POST /api/auth/login` · `POST /api/auth/logout` | code d'accès général (`PUT /api/settings {"global": {"access_pin": "…"}}` pour le définir, `""` pour l'enlever) |
| `GET /opds` · `/opds/folder/<id>` · `/opds/continue` · `/opds/recent` · `/opds/search?q=` | flux OPDS (authentification Basic avec le code d'accès s'il y en a un) |
| `POST /api/bdt/analyze/<dossier>` | analyse Bédéthèque d'un dossier (`{"url": …}` pour imposer la série, `{"details": true}` pour les auteurs, `{"force": true}` pour relire) |
| `GET` `DELETE /api/bdt/series/<dossier>` · `GET /api/bdt/search?q=` | lien existant / oublier · chercher une série |
| `GET /api/bdt/collection` · `POST` `GET` `DELETE /api/bdt/batch` · `GET /api/bdt/status` | collection · analyse groupée (lancer, suivre, arrêter) · état |
| `GET /api/download/<id>` | télécharger le fichier d'origine |
| `GET /read/<id>` | la page du lecteur (`?page=0` pour recommencer au début) |

Les largeurs de pages servies sont arrondies à la centaine supérieure (300 à 3000 px) : le navigateur
reçoit une image au moins aussi grande que ce qu'il affiche, jamais agrandie. Les JPEG sont encodés en
qualité 90 sans sous-échantillonnage de la couleur (réglable), avec un léger renforcement de netteté
après réduction (~400 Ko par page lue en 1200 px). Les CBR sont décompressés
une fois dans `data/cache/extract` (les 8 derniers albums ouverts sont gardés).

## Limites du prototype et suite possible

- Le code d'accès et les PIN protègent des curieux du réseau local, pas d'Internet : pour exposer Bulle
  dehors, passez par un reverse proxy avec authentification et HTTPS.
- Les métadonnées `ComicInfo.xml` (celles que BDConverter ajoutera) ne sont pas encore lues.
- Bédéthèque n'a pas d'API : Bulle lit les pages de recherche et de série comme un visiteur, lentement,
  en respectant le robots.txt du site (pas de couvertures ni de pages « ajax »). Si le site refuse les
  requêtes, Bulle le dit clairement et le lien peut toujours être donné à la main (adresse de la série).
- Les CBR dépendent de l'outil `unar` installé dans l'image Docker ; ce chemin n'a pas pu être
  testé hors Docker (les CBZ, les PDF et les `.cbr` qui sont en réalité des zip l'ont été).
  Si un album s'affiche « illisible », la fiche (bouton « i ») donne la raison.
- Si un fichier est renommé ou déplacé, sa progression de lecture est perdue (elle suit le chemin du fichier).
