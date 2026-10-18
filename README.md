# Bulle — lecteur de BD maison (v0.19.1)

Bulle est un petit serveur web qui fait, en plus simple, ce qu'on aime dans Ubooquity
(le rangement suit vos dossiers) avec un lecteur plus moderne inspiré de Kavita.

- **Navigation par dossiers** : un dossier = une série ; les sous-dossiers sont gardés
  (ex. `Blueberry/01 - Blueberry/…`). Rien n'est deviné d'après les noms de fichiers,
  les dossiers vides sont cachés, le tri est « naturel » (T2 avant T10).
- **Formats** : CBZ / ZIP, CBR / RAR (RAR 4 et RAR 5, via `unar`), CB7 / 7z, CBT / tar (y compris
  tar.gz), PDF (pypdfium2). Le vrai format est détecté d'après le contenu : un `.cbr` qui est en fait un
  zip fonctionne, et un `.cbr` qui est en réalité une archive ACE (vieux format propriétaire) est signalé
  comme tel, avec le conseil de le reconvertir en CBZ. Les CBZ dont les noms internes sont mal encodés
  (refusés par Python par prudence) sont lus quand même.
- **Lecteur** : une page, **double page** (couverture et planches larges seules), **défilement
  continu** ou **case par case** (touche `C` : les cases sont repérées automatiquement, par leurs
  gouttières *et* par leurs cadres — y compris les cases incrustées sur une grande image — et le lecteur
  glisse et zoome de l'une à l'autre, puis enchaîne sur la première case de la planche suivante ; une
  planche sans cases reconnues reste entière), page entière / pleine largeur / taille d'origine, clavier, tactile (balayage, zones de tape),
  sens manga (l'ordre des cases suit), plein écran, préchargement, enchaînement sur l'album suivant.
  **Zoom libre** : Ctrl + molette (centré sur la souris), pincement, `+` / `-` / `0`, double-clic ;
  une fois zoomé, la souris ou le doigt déplacent la page et Bulle va chercher une version plus nette.
  **Clic droit** (ou `T`) : bande des miniatures de toutes les pages, molette pour la faire défiler,
  clic pour y aller, clic droit ou Échap pour revenir. Pas de barre de défilement visible.
- **Progression** : reprise là où vous vous êtes arrêté, « Reprendre la lecture » sur l'accueil,
  badges lu / en cours (aussi sur les dossiers : « 3/16 lus »), marquer lu / non lu.
- **Colonne de gauche** : Bibliothèque, À lire, ★ Favoris, Listes (personnalisées, chacune affichée
  dans la colonne avec son nombre d'éléments), Historique (albums terminés), Collection, « Au hasard »
  (ouvre un album pas encore lu) et Réglages. Un album ou une série se met en favori ou dans une liste
  en la **glissant-déposant** sur la colonne (sur « Listes » : crée une nouvelle liste), depuis sa fiche
  (« i ») ou le haut de la page de la série. Les favoris portent un coin plié ★ sur la couverture.
- **Pochettes** : style « livre » (dos, tranche, fine bordure et ombre de la couleur dominante de la
  couverture, inclinaison 3D au survol, pile d'albums derrière les séries), « halo coloré » ou « simple ».
  La couleur est calculée une fois par couverture, côté serveur.
- **Habillage bande dessinée** (ligne claire) : contours noirs et ombres dures, lettrage BD (polices
  libres Bangers, Patrick Hand SC, Comic Neue embarquées), titres en cartouches jaunes, boutons et
  messages en bulles, petites onomatopées (« HOP ! ») quand on ajoute un favori. Un habillage « sobre »
  reste disponible. Le lecteur, lui, reste noir et sans fioritures.
- **Mosaïque de couvertures** en fond de toutes les pages (pas dans le lecteur) : vos propres albums,
  qui dérivent lentement et se remplacent en fondu (ou fixe, ou désactivée) ; opacité et luminosité
  réglables, et un effet « verre dépoli » qui rend la colonne, les panneaux et les fiches translucides.
- **Le laboratoire** : un petit champignon discret à côté du logo ouvre **BDConverter** (votre
  convertisseur PDF → CBZ) dans un panneau, sans quitter Bulle. Adresse réglable (« auto » = même
  machine que Bulle, port 3111 ; vide = champignon masqué).
- `Échap` ferme ce qui est ouvert, sinon revient en arrière (réglages, listes, recherche → page
  précédente ; dossier → dossier parent).
- Sur chaque vignette reconnue par Bédéthèque, un bouton « … » à côté du « i » ouvre le résumé dans
  une bulle.
- **Profils** (« Qui lit ? ») : chacun sa progression et ses réglages d'affichage, code PIN facultatif par
  profil, et un **code d'accès** général facultatif pour toute la bibliothèque.
- **Flux OPDS** (`http://<serveur>:2205/opds`) pour lire depuis une appli mobile (Panels, Chunky, Moon+,
  Mihon…) : navigation par dossiers, reprise, récents, recherche, téléchargement et lecture page par page
  (OPDS-PSE) sans télécharger l'album.
- **Recherche** sans tenir compte des accents ni de la casse (« aigles decap » trouve
  « Aigles Décapitées (Les) »), sur les noms de dossiers et de fichiers.
- **Pages et couvertures redimensionnées** par le serveur (comme Ubooquity) à la taille réellement
  affichée sur votre écran, puis mises en cache : net et rapide, même avec des CBZ de 400 Mo.
- **Scan** automatique au démarrage puis toutes les 12 h (réglable), ou à la demande (bouton ↻).
  Les couvertures se génèrent en arrière-plan après le scan.
- **Réglages** (bouton ⚙) : taille des vignettes et zoom au survol, nombre de vignettes par page
  (la liste est alors découpée en pages, flèches ← → du clavier), accès par lettre, tri, masquer les
  albums lus, thème sombre / clair, réglages du lecteur (ajustement, sens, fond, qualité, préchargement,
  mode nuit…), qualité des images côté serveur, seuil « album lu », fréquence du scan, taille du cache.
  Les réglages d'affichage sont enregistrés sur le serveur (ils vous suivent d'un appareil à l'autre).
- **Bédéthèque** (à la demande) : dans un dossier d'albums, « Analyser » cherche la série dans l'index
  alphabétique de bedetheque.com (une page par lettre, gardée un mois), compare les tomes officiels avec vos fichiers (présents, manquants affichés en
  cartes grisées à leur place, fichiers non reconnus, doublons), retient les titres officiels, l'année
  et, avec « Auteurs et détails », scénario / dessin / couleurs, éditeur, ISBN. Le **résumé** de chaque
  album (le début, tel que le site le montre, avec un lien « lire la suite ») est lu à l'ouverture de sa
  fiche — une fois pour toutes — ou pour toute la série avec le bouton « Résumés ». La page **Collection**
  (icône livres) récapitule toutes les séries analysées (complètes, incomplètes, en cours de parution)
  et peut analyser d'un coup les dossiers restants, arrêtable à tout moment. Rythme poli et réglable :
  au plus 10 requêtes par minute, espacées irrégulièrement, et une pause de 2 à 3 minutes toutes les 50
  requêtes pour les tâches de fond ; Bulle s'identifie honnêtement (`User-Agent: Bulle/<version> (+dépôt)`).
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
| `PORT` | `2205` | port d'écoute dans le conteneur (le `ports:` de la stack doit pointer dessus : `"2205:2205"`, ou `"2025:2205"` pour un autre port côté machine) |
| `SCAN_INTERVAL_HOURS` | `12` | rescan automatique (0 = désactivé) |
| `SCAN_ON_START` | `1` | scan au démarrage (aussi réglable dans Réglages › Images et cache, qui l'emporte) |
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
puis ouvrir `http://localhost:2205` (ou le port donné par `PORT`). Pour les CBR il faut l'outil `unar` (ou `unrar`, `7z`,
`bsdtar`) installé sur la machine ; les PDF utilisent `pypdfium2` (installé par `requirements.txt`).

## Utilisation

- Cliquer sur une couverture : ouvre le dossier, ou lance la lecture de l'album (reprise automatique).
- Le petit « i » sur un album : fiche (taille, pages, progression, marquer lu / non lu,
  recommencer, télécharger, ouvrir le dossier). Un album illisible y explique pourquoi.
- Dans les gros dossiers (40 entrées et plus, ou toujours selon le réglage), une barre de lettres (grandes,
  à droite ; taille et côté réglables) permet de sauter directement à une lettre, même si la liste est
  découpée en pages.
- Qualité HD / SD : Bulle mesure la vraie taille des pages (deux pages par album, vers le tiers et les deux tiers ;
  le fichier n'est jamais modifié). Grand côté de 2400 px et plus = HD, en dessous = SD. Une pastille « HD » se pose
  sur la couverture (« HD 4/6 » sur une série mélangée ; en mode SD, la pastille compte les SD : « SD 2/6 »), la fiche « i » donne la résolution, et le sélecteur
  « Qualité : Tout / HD / SD » sous « Bibliothèque » filtre les vignettes (mémorisé par profil). La mesure se fait
  toute seule en arrière-plan après chaque scan (albums nouveaux ou modifiés, et tout le stock la première fois) ;
  Réglages › Bibliothèque › Qualité HD / SD : compteurs, « Mesurer maintenant », « Tout remesurer », arrêt, mesure
  automatique (variable QUALITY_AUTO) et seuil HD réglable (changer le seuil reclasse sans remesurer).
  API : `POST /api/quality/measure` (`{"limit": n}`, `{"ids": [...]}`, `{"remeasure": true}`), `POST /api/quality/stop`,
  `GET /api/quality`.
- Comptes : chaque profil a un rôle, administrateur (réglages, scans, comptes, rubrique Adulte) ou lecteur (lecture,
  progression, listes, réglages d'affichage) ; le premier profil est administrateur, il en faut toujours un. Mot de
  passe facultatif par compte (4 caractères au moins, gardé chiffré) ; sans profil choisi, les droits d'administrateur
  ne valent que si rien ne protège Bulle. Réglages › Mon compte : vignette (photo réduite à 96 px, ou emoji / initiales),
  nom, mot de passe, déconnexion ; Réglages › Comptes et accès (administrateur) : rôles, ajout, suppression.
- Journal de lecture : Bulle note les pages tournées dans son lecteur (par profil, album et jour : pages, temps —
  écarts entre deux pages plafonnés à 5 min —, albums terminés ; un saut par la barre de progression ne compte pas).
  « Historique » montre les albums en cours (page atteinte, date) et les terminés ; « Activité » : 30 derniers jours,
  pages par jour (14 j) et par mois, séries en cours, albums les plus lus, totaux, et pour l'administrateur le résumé
  de tous les comptes. API : `GET /api/history`, `/api/history/reading`, `/api/activity`.
- Glissez une vignette (album ou série) sur « À lire », « Favoris » ou une liste de la colonne de gauche
  pour l'y ajouter ; sur « Listes » pour créer une liste. Au survol d'un album dont le résumé est connu,
  une info-bulle le montre.
- Dans le lecteur : `←` `→` ou `Espace` pour tourner les pages (en mode largeur, `Espace` fait d'abord
  défiler la page), clic sur les bords de l'image, balayage ou tape sur les bords sur mobile ;
  tape / clic au centre pour afficher ou cacher les barres. Molette = page suivante / précédente
  en mode page entière.
  En case par case, glissez (doigt ou souris) pour recadrer une case mal détectée ou qui déborde : on ne sort pas de
  la planche, et la case suivante repart d'un cadrage propre ; un balayage vif tourne toujours la page.
  `D` change l'affichage (1 page, 2 pages, défilement), `F` l'ajustement, `M` le sens manga, `P` le plein
  écran, `Début` / `Fin` première / dernière page, `Échap` revient au dossier.
- Le lecteur retient l'ajustement choisi et le sens de lecture par album (dans le navigateur),
  et le dernier ajustement choisi devient celui par défaut.
- À la dernière page, une flèche de plus propose l'album suivant du dossier (`Entrée` pour enchaîner).
- En bas de la colonne de gauche, jusqu'à deux couvertures posées au hasard dans l'espace libre ; une nouvelle arrive toutes les 6 à 8 secondes avec une transition
  différente à chaque fois (fondu, glissé, bascule, zoom, chute, flou, toupie) ; un clic ouvre sa fiche. Désactivable
  dans Réglages › Affichage.
- Sur iPad / iPhone : dans Safari, bouton Partager → « Sur l'écran d'accueil ». Bulle s'ouvre alors comme une appli,
  vraiment plein écran, sans barre d'adresse ni la croix de fermeture que Safari ajoute en mode plein écran.
- Rubrique Adulte : en haut d'une série, le bouton « 18+ » la range dans la rubrique ; avec un code défini
  (Réglages › Adulte), ces séries disparaissent de partout — accueil, recherche, hasard, mosaïque, OPDS —
  tant que le code n'est pas entré (entrée « Adulte » de la colonne de gauche, ou invite automatique en
  ouvrant une série 18+ par un lien). Une fois entré, le code vaut 12 heures sur l'appareil. Rien n'est
  déplacé ni modifié dans les fichiers.
  Option « Cacher l'entrée Adulte du menu » (Réglages › Adulte) : plus aucune trace dans la colonne ni sur les séries
  tant que la rubrique est verrouillée ; on y accède par Réglages › Adulte ou l'adresse `#/adult`.
- Habillages (Réglages › Affichage) : Bande dessinée, Bling-bling, Girly, Néon arcade, Aquarium (bancs de
  poissons, bulles qui remontent), Nuit étoilée (étoiles qui scintillent, étoile filante), Fanzine risographie
  (papier, encres fluo mal calées, scotch, tampons) ou Sobre, pour tout le site ; le lecteur reste sobre.
  Les réglages s'affichent en « signets » (une rubrique à la fois) ou en « briques » (tout sur une page).
  Échap (ou « Fermer ») quitte les réglages d'un coup et ramène là où on était.
- « ↻ Rescanner » sur une série relit ce dossier sur le disque : les fichiers ajoutés apparaissent, ceux jetés
  disparaissent, puis les couvertures sont refaites (le scan complet fait de même pour toute la bibliothèque).
  Les albums « retirés » de Bulle restent ignorés même s'ils sont sur le disque : la page de la série les liste
  avec un bouton « Remettre ».
- Fichier renommé ou déplacé sur le disque : au scan (ou dès qu'on l'ouvre), Bulle le retrouve (même taille, même
  date) et garde sa fiche : lecture en cours, favoris, listes, couverture choisie. Un fichier jeté disparaît.
- Page illisible dans un album (image abîmée, format inconnu, HEIC/JPEG XL sans module) : le reste de l'album
  s'ouvre, la couverture est prise sur la page lisible suivante, et la miniature du lecteur affiche quel fichier de
  l'archive pose problème et son vrai format (une extension .jpg ne garantit rien). Les pages HEIC/HEIF et JPEG XL
  sont lues avec l'image Docker. Une couverture « de secours » est refaite toute seule (à l'ouverture de l'album
  ou au scan) dès que la vraie page redevient lisible.
- Pages JPEG portant des métadonnées géantes (commentaire, XMP…) : ces métadonnées sont ignorées à la
  conversion, la page s'affiche (« broken data stream when writing image file »).
- Couverture choisie à la main : dans le lecteur, clic droit (ou T) ouvre les miniatures ; au survol d'une page,
  « ★ Couverture » en fait la couverture de l'album (gardé dans la base de Bulle, le fichier n'est pas touché ;
  re-choisir la page 1 revient au comportement normal).
- Rescanner un fichier : le ↻ d'une pochette, ou « Rescanner ce fichier » dans sa fiche, relit le fichier sur le disque
  (format, taille, pages, couverture) — pour rattraper un raté du scan sur un disque réseau lent. « ↻ Rescanner » en
  haut d'une série fait de même pour tous ses albums ; un scan normal redonne aussi leur chance aux albums en échec.
- Versions : chaque version a son tag sur GitHub (`v0.11.0`…) et, depuis la 0.11, son image Docker
  `ghcr.io/kermess14/bulle:0.11.0` en plus de `latest` (pour revenir à une version précise).
- Couvertures : la première page de l'album dans l'ordre naturel des noms de fichiers — et un fichier nommé comme une
  couverture (« cover », « couv », « front »…) passe en tête même s'il se trie après les pages numérotées. « ↻ Couvertures »
  en haut d'une série refait celles de tous ses albums ; sur n'importe quelle pochette, un petit ↻ (au survol, en bas
  à droite) ou « Refaire la couverture » dans la fiche relit le fichier et refait la couverture, même si elle existe.
  Les couvertures et pages en cache sont liées à la date du fichier : un fichier remplacé ou un numéro d'album
  réattribué ne peut plus afficher une ancienne image.
- CBR / RAR / 7z : l'archive est décompressée une fois dans le cache (les 20 dernières lues restent décompressées,
  variable `EXTRACT_KEEP`), avec unar, puis 7z et bsdtar en secours ; une archive dont une entrée est abîmée reste
  lisible (les autres pages). Réglages › Images et cache propose « Réessayer les albums en échec ».
- Retirer de Bulle : « ✕ Retirer de Bulle » dans la fiche d'un album, ou « ✕ Retirer » en haut d'un dossier, l'enlève de
  la base (progression et listes comprises) et les scans l'ignorent ensuite. Rien n'est supprimé ni modifié sur le
  disque. Réglages › Bibliothèque › « Retirés de Bulle » permet de le remettre. (Un fichier supprimé du disque, lui,
  disparaît tout seul au scan suivant.)
- Arrêter un scan : bouton « ■ Arrêter » dans la notification du scan (ou clic sur ↻ pendant un scan). Arrêté pendant
  le parcours des dossiers, la bibliothèque reste exactement comme avant ; pendant les couvertures, celles déjà faites
  restent et les autres se font à l'ouverture des albums.
- Scan au démarrage : désactivable dans Réglages › Images et cache (plus de scan après chaque mise à jour) ; les
  nouvelles BD arrivent alors avec ↻ ou le rescan automatique. Les guillemets dans la stack (`SCAN_ON_START="0"`) sont
  acceptés.
- Scan (Réglages › Images et cache) : rapide (liste seulement, couvertures faites à l'affichage), normal (couvertures
  manquantes en tâche de fond) ou minutieux (chaque album rouvert, pages recomptées, couverture refaite — long sur un
  NAS, mais rien ne reste faux).

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
| `GET /api/cover/<id>?w=300` | couverture (album, ou premier album d'un dossier) ; `w` = largeur voulue (sinon 600 px) |
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
| `GET` `POST /api/lists` · `GET` `PUT` `DELETE /api/lists/<id>` · `POST /api/lists/<id>/items` · `DELETE /api/lists/<id>/items/<album>` | listes du profil (Favoris et À lire créées d'office) |
| `GET /api/panels/<id>/<page>` | cases de la planche (fractions de la page, ordre occidental + ordre manga), détectées une fois puis gardées |
| `GET /api/covers/sample?n=` | couvertures au hasard (mosaïque de fond) |
| `GET` `POST /api/bdt/album/<id>/summary` · `POST /api/bdt/summaries/<dossier>` · `GET` `DELETE /api/bdt/summaries` | résumé d'un album lié à Bédéthèque (lu une fois, puis gardé) ; résumés de tout un dossier en tâche de fond |
| `POST /api/favorites/toggle` · `GET /api/history` · `GET /api/random` | favori on/off · albums terminés · un album au hasard |
| `GET /api/bdt/debug?q=` | diagnostic : ce que Bédéthèque renvoie au serveur |
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
  Les résumés sont ceux affichés à un visiteur sans JavaScript : le début du texte seulement, d'où le lien
  « lire la suite sur Bédéthèque ».
- Le glisser-déposer des vignettes fonctionne à la souris (et sur iPad) ; sur un téléphone, passez par la
  fiche de l'album.
- La détection des cases combine les gouttières (bandes de fond uni qui traversent la planche) et les
  cadres (traits d'encre rectilignes fermant un rectangle). Les cases sans cadre ni gouttière (bords
  déchirés, cases en biais, dessins qui se chevauchent) ne sont pas découpées, ou pas toujours comme un
  œil humain le ferait. Dans ce cas, la planche entière s'affiche et la touche `C` repasse en mode page.
- Les CBR dépendent de l'outil `unar` installé dans l'image Docker ; ce chemin n'a pas pu être
  testé hors Docker (les CBZ, les PDF et les `.cbr` qui sont en réalité des zip l'ont été).
  Si un album s'affiche « illisible », la fiche (bouton « i ») donne la raison.
- Si un fichier est renommé ou déplacé, sa progression de lecture est perdue (elle suit le chemin du fichier).
