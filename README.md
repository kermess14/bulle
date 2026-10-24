# Bulle — lecteur de BD maison (v0.45.0)

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
- **Plugins** (administrateur) : de petits programmes empaquetés en `.zip`, installés depuis Réglages › Laboratoire,
  lancés à la demande dans le conteneur de Bulle, affichés dans le panneau du champignon (un onglet par outil) et
  arrêtés tout seuls après un moment sans activité. Ils écrivent dans un dossier de sortie à part
  (`/plugins-out`) : la bibliothèque reste en lecture seule. Mode d'emploi et format : [PLUGINS.md](PLUGINS.md).
- `Échap` ferme ce qui est ouvert, sinon revient en arrière (réglages, listes, recherche → page
  précédente ; dossier → dossier parent).
- Sur chaque vignette reconnue par Bédéthèque, un bouton « … » à côté du « i » ouvre le résumé dans
  une bulle.
- **Profils** (« Qui lit ? ») : chacun sa progression et ses réglages d'affichage, code PIN facultatif par
  profil, et un **code d'accès** général facultatif pour toute la bibliothèque.
- **Flux OPDS** (`http://<serveur>:2205/opds`) pour lire depuis une appli mobile (Panels, Chunky, Moon+,
  Mihon…) : navigation par dossiers, reprise, récents, recherche, téléchargement et lecture page par page
  (OPDS-PSE) sans télécharger l'album.
- **Lecture simple** (`http://<serveur>:2205/simple`) pour un très vieil appareil (iPad 1, iOS 5.1) : pages HTML sans
  aucun JavaScript, la planche seule en plein écran sur fond noir (deux grandes zones tactiles pour tourner les
  pages), progression enregistrée, installable comme une application sur l'écran d'accueil de l'iPad.
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
| `PANELS_ENGINE` | `auto` | moteur de détection des cases : `auto` = le modèle appris s'il peut tourner (image Docker), sinon les règles ; `classic` = les règles seules ; `model` = le modèle (les règles en secours) |
| `PANELS_MODEL_THREADS` | `2` | cœurs de processeur utilisés par le modèle de cases pour une planche |
| `SCAN_ON_START` | `1` | scan au démarrage (aussi réglable dans Réglages › Images et cache, qui l'emporte) |
| `PRELOAD_COVERS` | `1` | générer les couvertures après un scan |
| `PAGE_CACHE` | `1` | garder les pages redimensionnées sur disque |
| `THREADS` | `8` | nombre de requêtes servies en parallèle |
| `PRELOAD_THREADS` | `3` | couvertures générées en parallèle après un scan (baisser à 1 sur un petit serveur) |
| `PLUGINS` | `1` | plugins du laboratoire (0 = désactivés) |
| `PLUGINS_OUT` | `/plugins-out` | dossier de sortie des plugins (s'il n'est pas monté : `/data/plugins-out`) |

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

- **Zoom par pincement au pavé tactile du Mac (v0.45.0)**. En page entière, pincer le pavé tactile ne zoomait qu'après un premier clic sur la loupe + : Chrome, Firefox et Edge envoient ce geste comme une molette avec Ctrl, en tout petits pas, et chaque pas, appliqué seul depuis 100 %, retombait sous le seuil « presque 100 % ». Les pas d'un même geste sont maintenant cumulés depuis le zoom de départ (comme le pincement sur écran tactile) ; Safari, qui envoie des événements « gesture », est traité de la même façon (seulement sans écran tactile : l'iPad garde son pincement). Le glissement à deux doigts déplace ensuite la page zoomée, comme avant. Test navigateur ajouté (`test_trackpad_pinch_zooms_from_100`, qui échoue sur l'ancien code). Essayé dans Chromium avec des événements simulés ; pas encore sur un vrai Mac (Safari surtout).
- **Cases détectées par un modèle appris, hors ligne (v0.45.0)**. Nouveau moteur de cases « model » (`bulle/panels_model.py`) : un petit réseau de détection (YOLO11n, `bulle/models/cases-yolo11n.onnx`, 10 Mo), appris sur 380 planches corrigées à la main (bancs privés, jamais dans le dépôt), tourne dans le conteneur avec onnxruntime, sur le processeur du serveur : pas de réseau, pas d'API, rien n'est envoyé, et il ne réapprend pas (même planche, même résultat). Il devient le moteur par défaut (`PANELS_ENGINE=auto`) quand il peut tourner ; sinon (onnxruntime absent, fichier manquant, architecture sans module) Bulle garde le détecteur à règles, qui reste aussi le secours page par page si le modèle échoue. Ses cases ont leur propre version (1001 ; les règles restent en `PANELS_VERSION` 20) : changer de moteur fait recalculer les cases gardées, au fil de la lecture, sans scan de la bibliothèque ; les corrections faites à la main restent prioritaires. Moins de deux cases trouvées : page entière, comme avant. Mesures (IoU 0,5, sur des planches que le modèle n'avait pas apprises : apprentissage sur une partie des bancs, mesure sur l'autre) : validation 100 planches F1 94,9 → 96,9 %, planches parfaites 75 → 79 ; banc difficile 240 planches F1 89,1 → 93,7 %, parfaites 141 → 149 (avec des contours exigés plus précis, IoU 0,75 : 76,8 → 88,5 %). Le modèle final, appris sur les 380 planches, n'a donc pas de mesure indépendante : ces chiffres en sont une borne basse. Un modèle plus gros (YOLOv12x, 119 Mo) fait un peu mieux (97,6 % et 94,9 %) mais demanderait plusieurs secondes par planche sans carte graphique. Temps mesuré : 60 à 100 ms par planche sur deux cœurs d'un Xeon récent (pas encore mesuré sur le serveur OMV, Xeon E5-1607 de 2012 : 0,2 à 0,4 s attendues). Image Docker : `onnxruntime` et `numpy` en plus (facultatifs : si l'installation échoue sur une architecture, les règles). La stack autonome n'embarque pas le modèle (trop gros pour ses variables) : elle garde les règles. `/api/stats` donne `panels_engine` ; le diagnostic des cases donne `engine`. Apprentissage refait sur un PC à carte graphique avec `tools/entrainer_cases.py` (torch et ultralytics, seulement sur ce PC) ; mesure avec `tools/banc_cases.py score <banc> --engine model`. Tests : `ModelEngine` dans `tools/test_panels_contracts.py` (contrat, ordre manga, résultat stable, page blanche, secours sans modèle), exécutés dans GitHub Actions. Licence : le modèle de départ (Ultralytics YOLO11n) est sous AGPL-3.0, et le modèle appris en dérive ; seul le fichier `.onnx` est utilisé (pas la bibliothèque Ultralytics) ; à revoir avant toute distribution commerciale. Ce lot reprend aussi la 0.43.1 (export des corrections, outils du banc), jamais fusionnée. Non testé sur le serveur réel ni sur appareil (iPad, tactile) : planches du banc, Chromium de bureau et serveur de test seulement ; pages de couverture et pages de texte peu représentées dans les mesures.
- **Plugins réservés au réseau local (v0.44.2)**. Les plugins du laboratoire (Data Reaper…) ne sont plus accessibles depuis Internet : il faut ouvrir Bulle par son adresse de la maison (`http://192.168…:2205`, nom court, `.local`) et venir d’une adresse privée (adresse réelle transmise par le proxy comprise). Ouvert par le nom de domaine public, Bulle fait comme s’il n’y avait pas de plugins : rien dans le laboratoire ni dans Réglages, 404 sur `/plugins/` et `/api/plugins`. BDConverter n’est pas concerné. Variable `PLUGINS_INTERNET: "1"` pour revenir à l’ancien comportement.
- **Images des plugins créées en JavaScript (v0.44.1)**. Le script d’adaptation ajouté aux pages d’un plugin relaie désormais aussi les adresses « /… » des images, vidéos et cadres fabriqués en JavaScript (`img.src = …`, `setAttribute`, `innerHTML`, `insertAdjacentHTML`, et un `MutationObserver` pour le reste). Avant, un aperçu comme `/api/cover?url=…` partait à la racine de Bulle au lieu de `/plugins/<id>/api/cover?url=…` et restait « Aperçu indisponible » (cas de Data Reaper).
- **Plugins du laboratoire (v0.44.0)**. Un plugin est un programme web empaqueté dans un `.zip` avec une fiche
  `plugin.json` (id, nom, version, commande, port…) ; `tools/make_plugin.py` fabrique le paquet en laissant de côté les
  fichiers jetables ou personnels (liste `exclude`). Réglages › Laboratoire : installer / mettre à jour (même id),
  ouvrir, arrêter, journal, désinstaller (le dossier de sortie est gardé). Le paquet est vérifié avant d'être décompressé
  (pas de `../`, de lien symbolique, de taille démesurée) ; ses dépendances (`requirements.txt`) s'installent en
  arrière-plan dans `/data/plugins/<id>/deps`. Bulle lance le programme à la demande (sur 127.0.0.1 dans le conteneur),
  le relaie sous `/plugins/<id>/` — réservé à l'administrateur, les cookies de Bulle ne lui sont pas transmis — et
  réécrit les adresses « /… » des pages (HTML, CSS, `fetch`, `EventSource`…) pour qu'une appli écrite pour la racine
  marche sans modification. Arrêt automatique après `idle_minutes` sans activité, sauf pendant un flux en direct ou si
  le plugin répond `{"busy": true}` à son `busy_url` ; un plugin lancé apparaît dans Réglages › Tâches. Le panneau du
  champignon a un onglet par outil (BDConverter et les plugins). Nouveau volume facultatif dans la stack :
  `/plugins-out`. Plugin d'exemple : `examples/plugins/bonjour`. Tests : `tools/test_plugins.py`. Essayé dans un Chromium
  de bureau avec le serveur de secours de Flask ; pas encore derrière waitress sur le serveur OMV.
- **Export des corrections lisible par le banc, essai d'un modèle de vision (v0.43.1)**. L'export de la 0.43.0 écrivait `"set": "export"` dans `gt.json`, que `banc_cases.py` refuse (seuls `dev` et `val` existent) : le champ est retiré, le banc répartit alors les planches par album. Nouvel outil d'essai `tools/banc_vision.py` : envoie les planches du banc à l'API Claude (seulement avec `--oui`, clé dans la variable `ANTHROPIC_API_KEY`, plafond de dépense, réponses gardées pour ne pas repayer) et compare ses cases à celles du détecteur actuel avec les mesures de `banc_cases.py score`. Mesuré sur 140 planches (validation et développement) : utilisée seulement quand elle trouve au moins 2 cases de plus que le détecteur, la vision donne F1 94,9 → 97,4 % (validation) et 90,6 → 97,3 % (développement). Deux outils pour agrandir le banc sans développeur : `tools/banc_echantillon.py` tire des planches au hasard dans la bibliothèque (rien n'est envoyé) et `tools/banc_vision.py --annoter` fait proposer des cases par le modèle, puis ne garde à vérifier que les planches où il n'est pas d'accord avec le détecteur (images dans `a-verifier/`). Avec ces outils, 250 planches de 250 séries différentes ont été annotées (1,51 $) : 105 en accord, 145 relues une à une (vision juste 97 fois, détecteur juste 6 fois, les deux 32, 10 écartées) ; elles forment un jeu de développement de 240 planches (`gt.json`, jamais dans le dépôt), où le détecteur actuel donne F1 89,1 % (IoU 0,5). Cause dominante des erreurs, sur ce jeu et sur la validation : des cases fusionnées (201 cases attendues sont englobées dans une détection plus grande), surtout sur des planches sans gouttière blanche continue (traits tracés à la main, gouttières sombres, décor qui déborde). Neuf variantes de seuils (couverture et encre des traits, bords, gouttière, tolérance) sur 380 planches ne bougent presque rien (±3 cases sur 1 490 sur le nouveau jeu) : le réglage des seuils est épuisé, la suite demande une logique nouvelle. Bulle n'utilise pas et n'appelle jamais l'API ; aucun changement de la détection (`PANELS_VERSION` reste 20).
- **Reprise à la case près, corrections manuelles complètes, interface de détecteur (v0.43.0)**. (1) La progression garde désormais la case en cours (`panel`, `panel_count` dans la table `progress`, colonnes ajoutées sans toucher aux anciennes lignes) : en rouvrant l'album, le lecteur revient à cette case, mais seulement si la page est la même et si le nombre de cases est le même qu'à l'enregistrement (écran différent, correction ou nouvelle détection : début de la page, comme avant). Hors case par case, la case est effacée. (2) Éditeur de cases (administrateur) : ordre de lecture réglable (`[` et `]` déplacent la case choisie ; « Ordre : fixé » vaut dans les deux sens de lecture, « auto » recalcule à l'enregistrement), bouton « Page entière » (correction sans case, gardée), et correction signalée « peut-être périmée » quand le fichier de l'album a changé (elle est gardée au lieu d'être effacée ; « Enregistrer » la valide, « Rétablir l'automatique » l'abandonne). « Exporter les corrections » (`GET /api/panels/export`, admin, 200 planches au plus) donne un zip : planches à la largeur d'analyse, `gt.json` au format de `tools/banc_cases.py score`, `auto.json` (ce que la détection trouve aujourd'hui) et `corrections.json` ; le fichier reste chez l'administrateur, rien n'est envoyé nulle part. (3) Interface de détecteur stable (`panels.run_detector`, `register_engine`, `valid_result`) : le serveur n'appelle plus un détecteur directement ; un moteur qui plante ou rend un résultat hors contrat est remplacé par le détecteur classique, puis par la page entière. Variable `PANELS_ENGINE` (défaut `classic`, le seul livré : aucun moteur IA n'est ajouté ; un tel moteur ne serait activé qu'après mesure sur des planches annotées jamais vues). La détection est inchangée (`PANELS_VERSION` reste 20) : les 120 planches de contrôle donnent le même résultat et passent toutes la vérification du contrat. Non testé sur appareil réel (tablette, tactile) : seulement un Chromium de bureau.
- **Diagnostic des cases pour l'administrateur (v0.42.0)**. Touche `G` en case par case : la planche entière avec les cases gardées par le serveur (numéro occidental et rang en manga), les cadrages « grow » (orange pointillé) et les regroupements « join » (violet pointillé), la version du détecteur et celle du résultat, l'origine (détection gardée ou correction manuelle). Le bouton « Mesurer » lance à la demande une détection fraîche sans rien changer en base : dimensions réellement analysées, fond, second essai, temps par étape (découpage, ordre manga, textes), tests de couverture des cadres et budget épuisé ou non, comparaison avec ce qui est en base. Rien n'est calculé tant qu'on ne le demande pas (la lecture normale n'est pas ralentie ; `GET /api/panels/<album>/<page>/diag`, admin seulement). Mesure faite avec ce rapport sur 346 planches : le budget de recherche des cadres (`FRAME_BUDGET`, 150 000 tests) est épuisé sur 10 planches et dépassé jusqu'à 10 fois (jusqu'à 3,5 s sur la pire), parce que l'essentiel des tests a lieu après les boucles surveillées. Contrôler plus finement les boucles internes n'accélère rien et fait baisser le score (F1 94,9 → 94,5 % sur la validation) : le détecteur reste donc inchangé, le diagnostic signale ces planches. Aucun changement de la détection (`PANELS_VERSION` reste 20) ; mêmes cases avec ou sans rapport (testé).
- **Lecteur : largeurs, sens manga, mémoire (v0.41.1)**. (1) La correction manuelle des cases est réservée à l'administrateur (le serveur refuse les autres avec 403 ; le bouton crayon n'apparaît pas) ; tous les profils lisent les cases corrigées. (2) Les largeurs d'image demandées par le lecteur suivent les paliers du serveur (multiples de 100 px, de 300 à 3000) : avant, des paliers de 160 px jusqu'à 3840 donnaient des adresses différentes pour la même image servie à 3000 px (copies en double dans le cache du navigateur) ; aucune netteté perdue, le serveur plafonnait déjà à 3000. (3) Changer de sens de lecture (manga) pendant qu'une réponse des cases est en route : l'ancienne réponse, sans l'ordre de droite à gauche, écrasait la bonne et faisait lire les cases dans le mauvais ordre ; elle est maintenant écartée et redemandée. Défaut reproduit puis corrigé dans un navigateur de test. (4) Défilement continu : les pages lointaines sont libérées (au plus ~15 images chargées sur un album de 80 pages, au lieu de toutes celles parcourues) et reviennent quand on remonte. Les autres modes bornaient déjà leurs caches. Non testé sur appareil réel (tablette, téléphone) : tests dans un Chromium de bureau (`tools/test_reader_browser.py`, facultatif, hors workflow). Aucun changement de la détection (`PANELS_VERSION` reste 20).
- **Corriger les cases à la main (v0.41.0)**. Quand la détection se trompe (case avalée, encart dans une grande case, case en trop), le lecteur en mode case par case a un éditeur : bouton crayon à droite de la barre du bas, ou touche `E`. La planche s'affiche en entier avec ses cases numérotées ; « + Nouvelle case » (ou Maj + glisser) puis un glissé trace un rectangle, même sur une grande case ; toucher une case la choisit, on la déplace ou on tire ses poignées ; `Suppr` l'enlève ; `Entrée` enregistre, `Échap` annule. Bulle range les cases dans l'ordre de lecture (et de droite à gauche en manga), les garde pour cette planche à la place de la détection (elles ne sont jamais recalculées, même quand la détection change de version ; un ✎ le signale dans le compteur) et « Rétablir l'automatique » efface la correction. Une correction s'efface seule si le fichier de l'album change. Aucun changement de la détection elle-même (`PANELS_VERSION` reste 20).
- **Détection des cases : rangée posée sur une grande image (v0.40.1, `PANELS_VERSION` 20)**. Une planche coupée par la gouttière du bas gardait une grande zone (image + rangée de trois cases) dont les cadres dépassaient de 11 à 14 pixels le bord de la zone : un test d'alignement à 10 pixels les ignorait et la case de gauche de la rangée disparaissait (une régression du lot 2, repérée sur une planche de l'ancien banc). Le test accepte maintenant ce petit dépassement. Scores inchangés sur les 100 + 40 planches annotées, aucune planche parfaite perdue.
- **Détection des cases : gouttières de travers et gouttières noyées (v0.40.0, lot 2 de l'audit, `PANELS_VERSION` 19 : les cases gardées en base sont recalculées à la première lecture)**. Trois corrections dans le découpage par gouttières, sans toucher au reste : une gouttière légèrement de travers (planche numérisée un peu penchée) est reconnue quand chaque colonne a sa suite de fond bordée de dessin des deux côtés, même si aucune ligne n'est entièrement fond ; une gouttière noyée dans une bande plus large de lignes à moitié claires (ciel, intérieur pâle) est examinée à part ; une gouttière barrée dont les bords sont mordus par l'anticrénelage est jugée sur son cœur. Sur le jeu de validation (100 planches corrigées à la main) : F1 93,3 % → 94,9 %, 69 → 75 planches parfaites, cases manquantes 65 → 49, en trop 32 → 26 ; sur l'ancien banc (40 planches) : F1 90,1 % → 90,6 %, 24 → 25 parfaites ; aucune planche parfaite perdue. Temps médian inchangé.
- **Banc d'essai de la détection refondu (v0.39.2, lot 1 de l'audit)**. `tools/banc_cases.py score` mesure maintenant avec un appariement un-à-un (une case détectée ne valide qu'une case attendue : une fusion compte 1 juste + 1 manquante, une coupe 1 juste + 1 en trop), donne justes / en trop / manquantes, précision, rappel, F1 (global et moyen par planche), à plusieurs seuils d'IoU (`--iou`), l'ordre de lecture, le nombre de planches parfaites, les temps (médiane, p95, pire), et sépare un jeu de réglage (« dev ») d'un jeu de validation (« val ») par album ou par champ `set` des annotations ; `--raw` mesure les cases brutes au lieu de celles que le lecteur montre (grow/join) ; `--json` enregistre le relevé ; le score historique de l'ancien banc reste affiché pour comparer. `compare` signale aussi les planches ajoutées ou retirées. Les mesures sont dans `tools/banclib.py`, testées par `tools/test_banc.py` ; `tools/test_panels_contracts.py` fixe le contrat de `detect_panels` (panels, rtl, join, grow, v) sur des planches fabriquées ; les trois tests tournent sur GitHub à chaque poussée (`.github/workflows/tests.yml`). Correction sans effet sur les résultats : `_edge_ratios` renvoie 4 valeurs quand `blockers=True` même sur une bande vide (la détection ne change pas, `PANELS_VERSION` reste 18).
- **Recherche Bédéthèque comme sur le site (v0.39.1)**. Bulle cherche « dans la bedetheque » (le réglage du champ en haut à droite du site), puis « dans tout le site » si rien ne sort, et le lien « chercher sur le site » ouvre la même recherche. Une page de résultats vide (le site en renvoie parfois par erreur) n'est plus gardée : Bulle la redemande une fois.
- **Lots de planches à corriger (v0.39.0)**. Réglages → Tâches → « Préparer les deux lots » : deux lots de 50 planches tirées au hasard dans toute la bibliothèque (tous les styles, 10 de « Watchmen » par lot si l'album est présent, jamais deux fois la même page, rubrique Adulte exclue). Chaque planche : un PNG avec les cases détectées et numérotées, et le JPG de la page seule. Le ZIP contient un dossier par lot (à donner tel quel) et `index.json` (numéro → album, à garder). C'est la matière du lot de validation du banc d'essai. Tâche de fond visible, arrêtable, en lecture seule.
- **Trait bleu : sur le fichier ET sur le dossier (v0.38.5)**. Le trait bleu est revenu sous les one shots rangés dans un dossier « One shots » (fichiers trouvés sur Bédéthèque), en plus de celui des dossiers de v0.38.3 et v0.38.4.
- **Trait bleu : dossiers d'un seul album sans numéro de tome (v0.38.4)**. Un dossier qui contient un seul album dont le nom n'a pas de numéro de tome (« Ailefroide Altitude 3954 ») est reconnu comme un one shot même sans fiche Bédéthèque et reçoit le trait bleu. Un dossier lié à une série de plusieurs tomes (« Aimé Lacapelle 1/4 ») n'en a jamais.
- **Trait bleu des one shots sur le répertoire (v0.38.3)**. Le trait bleu n'est plus posé sur la carte du fichier (album) mais seulement sous la couverture du **dossier** d'un one shot (fiche Bédéthèque d'un tome unique).
- **Tâches : « Forcer l'arrêt » (v0.38.2)**. Quand une tâche ne s'arrête pas après « Arrêter » (elle passe en « Arrêt en cours… »), un bouton **Forcer l'arrêt…** apparaît sur sa ligne. Après un avertissement, il redémarre Bulle (Docker relance le conteneur tout seul) : toutes les tâches sont coupées net, le site est inaccessible quelques secondes et un scan reprend au démarrage. Les fichiers BD ne sont jamais modifiés. La page se recharge toute seule quand Bulle est revenu.
- **Tâches : les recherches faites à la main apparaissent (v0.38.1)**. Une recherche de série ou de one shot, ou la lecture d'un résumé, se fait en quelques secondes : elle ne « tourne » donc jamais assez longtemps pour figurer dans la liste. La page Tâches garde désormais un journal d'**Activité récente** (les 15 dernières actions : recherches, résumés, lots, avec l'heure) et la « dernière exécution » des lignes Bédéthèque et Résumés en est tirée. Le journal est en mémoire : il repart de zéro au redémarrage.
- **Page « Tâches » et trait bleu des one shots (v0.38.0)**. Réglages → **Tâches** (administrateur) : la liste de tout ce que Bulle fait en arrière-plan (scan, couvertures et nombre de pages, mesure HD/SD, résumés et fiches Bédéthèque), avec l'avancement, la dernière exécution et un bouton **Arrêter** par tâche (et « Tout arrêter »). L'arrêt est coopératif : la tâche termine l'élément en cours, puis s'interrompt, rien n'est laissé à moitié écrit. La page se rafraîchit toute seule toutes les 2 secondes. Côté grille, un dossier qui contient un one shot (fiche Bédéthèque d'un seul tome) reçoit le même **trait bleu** que les one shots d'un dossier « One shots ».
- **Détection des cases : cases collées, rectangles de texte, bords de planche (v0.37.0)**. Mise au point sur les
  21 premières planches de « La nuit des morts-vivants », corrigées case par case à la main et ajoutées au banc
  d'essai. Quatre défauts corrigés : deux cases **collées**, séparées par le seul trait de leur cadre (sans gouttière),
  sont maintenant séparées le long de ce trait ; une **bulle ou un cartouche rectangulaire** posé à côté des cases
  n'est plus une case, il est réuni à la case voisine (reconnu à ses lignes de lettres) ; la **marge de la page** qui
  traînait au bord d'une case ne la déborde plus ; et une case restée **cachée dans un cadre** (deux cases empilées
  dans un même rectangle) est redécoupée par ses gouttières. Une bande de planche qu'aucune case ne couvrait (la case
  large « RÉANIMATION ! » de la page 6, jamais montrée) redevient une case à part entière. Sur l'album : 162 cases
  justes sur 167 (135 avant) et 5 cases en trop (20 avant). Sur les 40 planches corrigées du banc : 265 justes sur
  315 (230 avant), 28 en trop (38 avant) ; aucune planche corrigée ne régresse. Les cases sont recalculées à la
  première lecture de chaque planche (PANELS_VERSION 18).
- **Lecture simple : l'application reste en plein écran (v0.36.1)**. Sur l'iPad 1, l'icône s'ouvrait bien en plein
  écran sur `/simple`, mais le premier lien touché rouvrait Safari, avec sa barre d'adresse. Avant iOS 11.3, dans une
  application de l'écran d'accueil, iOS envoie à Safari tout lien `<a href>` touché ; seuls un changement d'adresse par
  script ou l'envoi d'un formulaire restent dans l'application. La lecture simple n'ayant pas de JavaScript, toute sa
  navigation passe maintenant par de petits **formulaires GET** dont le bouton est ce que l'on touche : mêmes adresses
  qu'avec un lien (`?p=3`, `?l=S` deviennent des champs cachés), même aspect, **aucune balise `<a>`** dans les pages.
  Les deux zones tactiles de la lecture et le petit bouton ‹ sont des boutons vides (avec un libellé pour les lecteurs
  d'écran) ; dans une liste, la couverture et le titre sont chacun un bouton. Vérifié : 20 tests (aucune balise `<a>`
  sur aucune page, tous les formulaires GET vont vers `/simple`, mêmes adresses qu'avant), validateur W3C sans erreur,
  parcours dans Edge sans JavaScript (34 contrôles, dont « aucun lien `<a>` sur les pages visitées »), 18 mesures de
  tenue à l'écran inchangées. Pas essayé sur le vrai iPad ; si l'application en sortait encore, le plan B est le petit
  script habituel (`window.location` au toucher, en mode application seulement), ce qui demande de lever la règle
  « sans JavaScript ».
- **Lecture simple : plein écran et icône d'application (v0.36.0)**, d'après l'essai sur l'iPad 1. (1) La lecture
  n'affiche plus que la planche : plein écran, fond noir, **entière** (jamais coupée), centrée, sans défilement ni zoom,
  en paysage comme en portrait. Plus de titre ni de boutons « précédent / suivant » : seulement les deux grandes
  zones tactiles (moitié gauche de l'écran = page précédente, moitié droite = page suivante, sur toute la hauteur) et
  un petit bouton discret en haut à gauche (44 px, semi-transparent) qui ramène à l'album. À la dernière page, la zone
  de droite ouvre l'album suivant du dossier (ou ramène à la liste s'il n'y en a pas). La planche est l'image de fond
  d'une zone qui remplit l'écran, réglée sur « contain » : c'est le navigateur qui la fait tenir, sans dépendre de
  hauteurs en pourcentage (peu fiables sur un vieux Safari) ; une petite planche est agrandie. Le zoom est coupé dans
  la lecture (`maximum-scale=1`) : cela évite que Safari agrandisse la page quand on tourne l'iPad, et que deux
  touchers rapides soient pris pour un double-toucher de zoom. (2) **Icône sur l'écran d'accueil** : iOS 5 ne connaît
  pas le manifest web (iOS 11.3) ; toutes les pages `/simple` portent donc les balises propres à Apple
  (`apple-mobile-web-app-capable`, barre d'état noire, titre « Bulle », `apple-touch-icon` en 72 px et 144 px). Les
  icônes sont le logo de Bulle, carrées, sans transparence ni coins arrondis (iOS les ajoute ; `python
  tools/make_icons.py` les refait) et servies sans connexion sur `/simple/icone-72.png` et `/simple/icone-144.png`.
  Pour l'ajouter : ouvrir `/simple` sur l'iPad (c'est la page de départ de l'application), bouton « action » de Safari
  (la flèche) › « Sur l'écran d'accueil ». L'application s'ouvre sans barre d'adresse ; la navigation y reste (en
  v0.36.0 c'étaient de simples liens, qui font sortir d'une application iOS : corrigé en v0.36.1, voir plus haut) ;
  la session y reste connectée (cookies persistants : profil et
  code d'accès 10 ans, compte 30 jours). Vérifié : 19 tests (`python tools/test_simple.py`), validateur W3C sans erreur,
  18 mesures dans Edge (user-agent d'iPad iOS 5, JavaScript coupé : 6 tailles d'écran, paysage et portrait, plein écran
  d'application et avec les barres de Safari, × 3 formes de planche) : la planche tient entièrement, centrée à 1 px
  près, sans défilement. Pas essayé sur le vrai iPad.
- **Lecture simple pour un très vieil appareil (v0.35.0)** : un iPad 1 (iOS 5.1, Safari 5.1 de 2011, 256 Mo de
  mémoire vive) ne fait pas tourner l'application. Ouvrir `http://<adresse du NAS>:2205/simple` (par exemple
  `http://192.168.0.213:2205/simple`) : des pages HTML rendues par le serveur, **sans aucun JavaScript**, au style
  intégré (aucune ressource externe), HTML valide (validateur W3C), tableaux et blocs simples, CSS 2.1 (ni flexbox,
  ni grid, ni variables). « Qui lit ? » (mot de passe du profil ; ou code d'accès / compte selon la configuration),
  séries et dossiers en gros liens avec leur couverture, 20 par page avec un index alphabétique quand la liste est
  longue, puis la lecture : **une planche entière par page**, avec en haut et en bas « Précédente / Album /
  Suivante » et deux grandes zones sur l'image (moitié gauche : précédente, moitié droite : suivante), de simples
  liens ; la planche suivante est préchargée par une image invisible. Chaque planche est un JPEG de base (non
  progressif) tenant dans 1 024 × 1 024 px, jamais agrandi (44 à 155 Ko sur de vraies planches), gardé dans le cache
  des pages et servi avec des en-têtes de cache. La planche affichée est enregistrée comme page lue ; ouvrir un
  album reprend à la dernière page lue (un album terminé repart du début). À la dernière page, un bouton mène à
  l'album suivant du dossier. Mêmes règles que le reste : profil choisi obligatoire en mode « qui lit ? », mots de
  passe et blocage après 5 essais ratés, rubrique Adulte cachée tant que le code n'est pas entré ; rien
  d'administratif (ni réglages, ni scan, ni gestion des profils) et pas de case par case. Le réseau local reste
  exempté du HTTPS imposé (192.168.x.x, localhost, nom court) et le cookie de profil n'est « Secure » qu'en HTTPS.
  L'application ordinaire n'est pas touchée. Vérifié par `python tools/test_simple.py` (14 tests : routes, aucune
  balise script, aucune ressource externe, échappement des titres, images, progression, profils, code d'accès,
  comptes, Adulte, HTTPS ; validateur W3C : 0 erreur sur 26 pages) et dans Edge avec JavaScript désactivé,
  user-agent d'iPad iOS 5, en 1 024 × 768 puis 768 × 1 024. Pas essayé sur le vrai iPad 1.
- **Case par case : un rectangle avec du texte n'est pas une case (v0.34.11)**, signalé sur « La nuit des
  morts-vivants » p. 6. Une bulle rectangulaire ou un cartouche (petit cadre, moins de 4 % de la page, dont
  l'intérieur est surtout du fond : papier et lettres) était parfois lu comme une case à part entière. Il ne l'est
  plus : s'il est dans une case, il en fait partie ; s'il est entre deux cases, il est **rattaché** à la case qu'il
  touche (la case est élargie jusqu'à lui, sans grandir de plus de moitié ni mordre sur une autre), jamais lu seul.
  Banc d'essai (la page signalée ajoutée et annotée : 19 planches corrigées, 148 cases) : 92 justes avant comme
  après, cases en trop 26 → 24, 16 planches sur 225 changent (bulles et cartouches retirés ou rattachés, rien de
  moins bien) ; bibliothèque, 240 pages intérieures au hasard : 6 changent, toutes dans le même sens. Sur la page
  signalée, la case bandeau des yeux manque toujours : ses gouttières font 2 à 3 pixels sur une page à marges noires,
  c'est un autre chantier (noté). Les cases en base sont recalculées (`PANELS_VERSION` 17).
- **Case par case : moins d'attente au changement de planche (v0.34.10)**. Trois choses. (1) L'ordre de lecture
  manga (une seconde passe de découpage, de droite à gauche) n'est plus calculé que si le lecteur est en sens manga
  (il le demande avec `?rtl=1`) ; sinon le serveur s'en passe, et complète le résultat le jour où un lecteur en sens
  manga le demande. Les cases elles-mêmes sont les mêmes (banc : 0 changement sur 223 planches), temps moyen 158 →
  136 ms. (2) Le lecteur demande les cases de **six** planches d'avance (au lieu de deux), en priorité basse :
  mesuré dans Edge avec des cases ralenties à 1,5 s (NAS chargé) et des sauts de planche toutes les 0,4 s, l'attente
  moyenne au changement de planche passe de 792 à 365 ms, la pire de 2 s à 0,6 s ; à un rythme de lecture normal,
  plus d'attente du tout. (3) Après un raté du serveur, la réponse vide est marquée « error » et le lecteur ne la
  garde pas pour la séance.
- **Case par case encore un peu plus rapide (v0.34.9)**, sans rien changer aux cases : dans la recherche des cadres,
  l'union des bords à une position est calculée une fois pour toutes (au lieu d'être retriée à chaque test de
  couverture), et le test « ce rectangle est-il deux cases côte à côte ? » ne visite plus que les positions de bord
  comprises dans le rectangle, avec un rejet rapide par leur étendue. Banc d'essai : 192 → 153 ms de moyenne, pire
  planche 2,5 → 1,5 s, 0 planche changée. Mesuré aussi : la seconde passe (ordre manga) ne coûte que 16 % du
  temps, les cadres étant partagés ; pas de quoi justifier un calcul à la demande.
- **Case par case : mise en page en escalier (v0.34.8)**, idée qualité n° 2. Quand une case déborde un peu sur la
  gouttière de la rangée suivante (son cadre descend de quelques dizaines de pixels dans la bande, ou se pose sur la
  case du dessous), la gouttière n'était plus « traversante » et les deux rangées restaient soudées en un seul bloc.
  La coupe le long des bords de cadre accepte maintenant un bord interrompu, à condition que ce qui l'interrompt
  soit une case voisine qui déborde juste un peu (son cadre réapparaît à moins de 10 % de la zone) : une vraie case
  haute sur deux rangées n'est pas coupée. Et quand une rangée ainsi retrouvée ne se laisse pas redécouper, les cases
  que le découpage précédent y trouvait déjà sont gardées. Banc d'essai : 1 planche sur 223 change (b-12736 : 4 → 8
  cases justes sur 8), score 83 → 87 justes sur 139, 25 → 24 en trop ; bibliothèque : 240 pages intérieures au
  hasard, 1 change (mêmes 8 cases, cartouches au-dessus du cadre exclus comme sur les autres rangées) ; 160
  couvertures et pages de garde : 0. Les cases en base sont recalculées (`PANELS_VERSION` 16).
- **Réglage « remplir l'écran » retiré (v0.34.7)** : essayé sur la tablette, une case plus haute que l'écran devait
  défiler, et c'est justement ce qu'on ne veut pas en case par case ; sans défilement, l'option revenait au
  comportement normal (la case tient toujours entière). Le fond **Flou** reste. Un réglage « remplir l'écran »
  resté enregistré dans un profil est simplement ignoré.
- **Case par case : fond flou (v0.34.6)**, demandé par kermess et fusor : une case haute et étroite restait centrée
  entre deux grandes bandes noires. Réglages › Lecteur › « autour de la case » a une nouvelle valeur **Flou** : à la
  place du noir, la planche floutée et assombrie, comme une vidéo verticale (un seul calque fixe par planche, léger
  pour la tablette : le trou du masque bouge par-dessus). Vérifié dans Edge, PC et iPad émulé.
- **Case par case : second essai sur les planches claires sans cases (v0.34.5)**. Des gouttières blanches fines,
  salies par la réduction de la page (aquarelle, fond peint jusqu'aux bords, scan jauni), sortaient de la tolérance
  autour du blanc : la planche restait entière. Quand rien n'est trouvé sur une page claire, Bulle refait la
  détection avec une tolérance élargie, et ne garde le résultat que s'il donne de vraies cases (bordées de dessin des
  deux côtés, au moins deux, qui couvrent la planche). Banc d'essai : 2 planches sur 223 changent, toutes deux
  mieux découpées (une aquarelle : 0 → 3 cases justes sur 5 ; un scan jauni : 0 → 7 cases justes), score 80 → 83
  justes sur 139, toujours 25 en trop ; sur 120 pages intérieures de la bibliothèque, 1 change (0 → 6 cases, juste).
  Mais sur les couvertures, pages de garde et dernières pages, ce second essai inventait des cases (titre, dessin et
  texte séparés par du vide : 8 sur 160) : il n'y est pas fait. Les cases en base sont recalculées (`PANELS_VERSION`
  15).
- **Lecteur, case par case : moins d'images chargées, plus fluide sur tablette (v0.34.4)**. Pour une planche, le
  lecteur chargeait la version « page entière », puis la version nette (×2), puis encore une troisième largeur
  (« affinage ») une fois la première case cadrée : plus que les deux premières, la version ×2 étant la netteté des
  cases (l'affinage ne sert plus qu'au zoom manuel). Un redimensionnement (barre d'adresse du téléphone, clavier,
  fenêtre) jetait toutes les images chargées et rechargeait tout : elles sont gardées, et une version déjà là plus
  nette que celle voulue est conservée. Une page d'origine petite (vignette, dernière page) n'est plus redemandée
  à chaque visite. Un échec de demande des cases (réseau, serveur) n'est plus retenu pour toute la session : la
  planche est redemandée à la visite suivante. Sur téléphone et tablette (tactile, petit côté ≤ 1 100 px), l'image
  des cases est plafonnée à 2 560 px au lieu de 3 840 (la carte graphique n'avait pas le temps de la redessiner
  pendant le glissement : case noire) ; rien ne change sur PC. Le recadrage d'une case au doigt ou à la souris est
  recalculé une fois par image d'écran et non à chaque mouvement. Vérifié dans Edge (PC 1920×1080 et iPad Pro 11
  émulé, tactile) : une planche = 2 images au lieu de 3, redimensionnement en hauteur = 0 rechargement, aucune
  erreur.
- **Case par case : les cases restent dans le navigateur (v0.34.3)**. À chaque réouverture d'un album, le lecteur
  redemandait les cases de chaque planche au serveur (une requête, une lecture en base, par planche). L'adresse des
  cases porte maintenant la date du fichier et la version de la détection : le navigateur garde la réponse pour
  toujours, comme il le fait déjà pour les pages, et la redemande seulement si le fichier ou la détection change.
- **Case par case : le serveur ne se laisse plus engorger (v0.34.2)**. Quand la même planche était demandée deux
  fois en même temps (affichage + préchargement, deux lecteurs, un clic répété), elle était détectée deux fois : la
  seconde demande attend maintenant le résultat de la première. Et une demande qui ne trouve pas de place pour
  détecter (deux détections à la fois au plus) attendait sans limite en occupant un fil du serveur ; sur un serveur
  chargé, tous les fils pouvaient finir par attendre là et plus rien ne répondait, pas même le contrôle de santé
  de Docker. Elle attend au plus 12 secondes, puis répond « occupé » : le lecteur redemande 2 secondes plus tard
  (jusqu'à 4 fois), sans garder cette réponse. Vérifié en local : 8 demandes simultanées de la même planche = une
  seule détection, réponses identiques ; les demandes en trop reçoivent bien « occupé » et le serveur reste
  joignable.
- **Case par case : les mêmes cases à chaque fois (v0.34.1)**. Le serveur analysait la planche à 600 px, ou à la
  taille de la version qui traînait dans le cache (600 à 1 400 px) : d'une fois sur l'autre, la même planche pouvait
  donner d'autres cases, et surtout pas celles vérifiées sur le banc d'essai (qui travaille à 800 px). Il part
  maintenant toujours de la page rendue à 800 px, par le même chemin (gardée dans le cache des pages). Mesuré : entre
  600 et 800 px, 61 planches du banc sur 223 n'avaient pas le même nombre de cases et 29 des cases déplacées ; et
  même entre deux versions de plus de 800 px (1 200 px réduite, 2 400 px décodée en réduit), 9 planches sur 28 n'ont
  pas le même nombre de cases, la détection étant sensible au rééchantillonnage au pixel près. Les cases déjà en base
  sont recalculées à la prochaine ouverture (`PANELS_VERSION` 14). Et un raté passager (archive en cours d'extraction,
  cache plein) n'est plus gardé en base comme « pas de cases » : il est réessayé à la lecture suivante.
- **Case par case plus rapide (v0.34.0)**, sans rien changer aux cases trouvées : la recherche des cadres testait
  des milliers de fois les mêmes bords (le résultat est maintenant gardé), vérifiait « est-ce deux cases côte à
  côte ? » sur des milliers de rectangles quasi identiques avant de les dédoublonner (après, désormais), lisait les
  gouttières pixel par pixel en Python (Pillow s'en charge en C) et, pour le texte à cheval, retournait la planche
  entière pour chaque paire de cases l'une sous l'autre (une seule fois maintenant). Sur le banc d'essai de 223
  planches : temps moyen de 438 à 191 ms, pire planche de 6,7 à 2,3 s, **0 planche changée** (cases, ordre manga,
  cases réunies ou élargies). Le banc lui-même est dans le dépôt : `python tools/banc_cases.py base|compare|score
  <dossier des planches>` (les planches restent chez vous).
- One shots : bouton **« 📚 Tome d'une série »** sur la ligne d'un album qui n'est pas un one shot mais le tome d'une
  série : il est mis de côté (plus cherché ici), rangé dans « tomes de série mis de côté » avec « remettre ». Le
  bouton du haut s'appelle maintenant « Tout le dossier est une série » (il concerne tout le dossier, pas un album).
- **Sécurité (v0.33.4)**, suite à la relecture : en mode « qui lit ? », un visiteur sans profil choisi était traité
  comme le premier profil (l'administrateur) par l'API, et pouvait donc changer son mot de passe ou effacer sa
  progression ; dès que ce profil a un mot de passe (ou que « qui lit ? » est demandé), toute modification exige
  maintenant d'avoir choisi un profil. Changer ou supprimer son propre mot de passe demande l'ancien (l'administrateur
  peut toujours changer celui des autres). Le ↻ « Rescanner ce fichier » (qui vide le cache et ré-extrait l'archive)
  est réservé à l'administrateur. Le paramètre `n` des listes (récents, reprise, historique) est borné à 500.
- **Sécurité (v0.33.2)** : la vignette d'un profil n'accepte plus qu'une petite image PNG, JPEG, WebP ou GIF en
  base64 (ou quelques caractères) ; une valeur piégée, qui aurait pu lancer un script chez les autres lecteurs et
  l'administrateur, est refusée et les anciennes valeurs douteuses sont ignorées ; l'appli échappe aussi la
  vignette à l'affichage. Tous les cookies sont **HttpOnly** (illisibles par un script) et « Secure » en HTTPS.
  Nouveau réglage **Imposer le HTTPS** (Réglages › Accès, ou variable `FORCE_HTTPS=1`) : une visite en `http://`
  depuis Internet est renvoyée vers `https://` (redirection 308) et le navigateur retient de n'utiliser que le
  HTTPS (HSTS, 6 mois). Le certificat reste fourni par le proxy inverse, qui doit transmettre `X-Forwarded-Proto` ;
  les adresses de la maison (192.168…, localhost, nom court) ne sont jamais redirigées, et l'option ne s'active que
  depuis une page ouverte en `https://` pour ne pas vous enfermer dehors.
- **Recherche par auteur** : la barre de recherche trouve aussi les albums par leurs auteurs (scénario, dessin,
  couleurs), sans accents ni majuscules, dans l'ordre qu'on veut (« van hamme », « moebius », « mourier jean »). Les
  résultats sont regroupés par auteur, en tête de page. Seuls les albums liés à Bédéthèque (ou BDfugue) dont les
  auteurs sont connus sont concernés : pour une série, bouton « Auteurs et détails » du panneau Bédéthèque.
- **Habillage Fêtes** (Réglages › Apparence › Habillage) : couleurs et décor de la fête du calendrier, avec ce qui
  flotte dans l'air : jour de l'an (confettis et feux d'artifice), Saint-Valentin (cœurs qui montent), Pâques (œufs
  décorés et fleurs), fête de la musique (notes), 14 juillet (feux d'artifice bleu-blanc-rouge), grandes vacances
  (ballons de plage, papillons), Halloween (chauves-souris, citrouilles, fantômes, feuilles), Noël (neige, boules et
  étoiles). Entre deux fêtes, c'est la prochaine qui s'affiche. Le petit bouton à côté du champignon (comme pour
  Quatre saisons) les fait défiler ; revenir sur la fête du moment repasse en « selon la date ». La date de Pâques
  est calculée chaque année. Coupé en mode léger, sur téléphone et si l'appareil demande moins d'animations.
- One shots : un **trait bleu** sous la couverture d'un album déjà trouvé sur Bédéthèque (ou BDfugue).
- Les messages d'erreur (⚠) disparaissent tout seuls au bout de 5 secondes ; leur icône garde la taille d'une lettre
  (dans l'habillage Fanzine elle prenait tout l'écran).
- BDfugue refuse les lecteurs automatiques (code 403) : Bulle ne peut pas lire ses pages depuis le serveur. Une adresse
  BDfugue collée dans « Chercher… » est quand même acceptée : l'album est lié à la fiche, titre d'après l'adresse et le
  nom du fichier (sans auteurs, résumé ni couverture). Après un refus, Bulle ne redemande rien à BDfugue pendant
  6 heures (la recherche automatique continue sur Bédéthèque sans lui).
- **BDfugue en secours** (Réglages › Laboratoire › « Recherche BDfugue en secours », désactivé par défaut) : quand un
  album ou une série n'est pas sur Bédéthèque (rien trouvé ou rien de sûr), Bulle cherche aussi sur BDfugue, la
  librairie en ligne. Un one shot au titre identique est lié tout seul, avec ses auteurs, éditeur, date, résumé et
  couverture ; sinon les albums trouvés s'ajoutent aux propositions (pochette au survol). Une série trouvée sur BDfugue
  est comparée au dossier comme une série Bédéthèque (tomes présents, manquants). On peut aussi coller l'adresse d'une
  fiche BDfugue dans « Chercher… » ou dans le panneau d'une série. Mêmes règles de politesse que pour Bédéthèque (une
  requête à la fois, au même rythme, résultats gardés 7 jours, pages réservées du robots.txt jamais lues) ; un compte
  lecteur ne déclenche jamais de requête.
- Case par case : gouttières noires sur une page blanche (une colonne de cases encadrée de noir) reconnues, avec
  prudence (gouttière mince, bordée de dessin) ; gouttières de deux pixels entre deux cadres très rapprochés acceptées
  quand elles sont nettes. 153 planches d'essai : 4 changent (Pavillon noir, Expérience mort mieux découpées).
- Case par case, d'après les pages corrigées à la main (série 3) : le blanc à l'intérieur d'une case (cartouche, bulle,
  ciel pâle) n'est plus pris pour une gouttière quand le cadre de la case le ferme des deux côtés (un cartouche en bas
  d'une case n'est plus lu à part, un manga à grandes bulles n'est plus coupé en morceaux) ; un cartouche large posé
  sur une gouttière n'empêche plus de la voir ; une gouttière bordée d'un liseré gris est reconnue. **Bulle qui
  déborde un peu du cadre** : la case est agrandie juste assez pour la montrer en entier (la vue se dézoome
  légèrement) ; ce n'est fait que pour ce qui est clair (bulle, cartouche) et s'arrête dans la gouttière. 153
  planches d'essai : 23 changent, presque toutes mieux découpées, aucune nettement moins bien.
- **Mode « BD seules »** : le bouton planche (à côté du champignon) a maintenant trois crans, un clic passe au suivant :
  complet → léger → **BD seules** → complet. « BD seules » est le plus économe : plus de menu ni de barre de boutons
  (seuls restent l'accueil, la recherche et ce bouton), plus de « Reprendre la lecture » ni d'« Ajouts récents » (rien
  n'est demandé au serveur pour eux), plus de panneau Bédéthèque ni de boutons de série, couvertures à plat sur un
  fond uni, sans ombre, ni effet, ni animation. Mémorisé sur l'appareil.
- One shots : bouton **« ✕ Pas sur Bédéthèque »** pour un album à choisir ou introuvable qui n'existe pas sur le site :
  il disparaît de la liste et n'est plus jamais cherché (même en relançant tout). Les albums écartés sont rangés dans
  « albums écartés », avec « remettre » pour annuler.
- Case par case : un trait clair du décor (plafond, ligne de lumière) n'est plus pris pour une gouttière qui coupe
  une case en deux ; les bandes étroites de marge collées au bord de la page ne sont plus lues comme des cases.
  Une gouttière fine dont les bords sont mordus par le cadre (rideau blanc qui touche la gouttière) est reconnue
  (une case de Djinn coupée en deux à juste titre). 153 planches d'essai : 6 mieux découpées, aucune moins bien.
- One shots à choisir ou introuvables (panneau Bédéthèque) : petite couverture de l'album à droite de son nom,
  agrandie au survol, pour la comparer aux propositions (dont la pochette s'affiche aussi au survol).
- Case par case : rangées séparées par autre chose que du fond (gouttière fine chevauchée par un cartouche, décor
  peint entre les cases, couleur de fond qui change) : Bulle suit les bords de case bien droits qui traversent la
  page, puis découpe chaque rangée normalement. Cases de biais (gouttières blanches en oblique) trouvées. Vérifié sur
  132 planches (75 + 57 nouvelles, tirées au hasard dans la bibliothèque) : 7 mieux découpées, dont 2 qui n'avaient
  aucune case, aucune moins bien. Ordre de lecture : une grande case haute à droite de deux cases empilées est lue
  après elles (coupes successives, haut puis gauche).
- Case par case, détection améliorée sur 75 planches d'essai (7 planches mieux découpées, aucune moins bien) :
  cases aux bords tracés à main levée (traits qui ondulent : aucune gouttière droite) trouvées comme des blocs de
  dessin séparés par le fond ; rangée de cases posée sur une grande image sans gouttière entre les deux (la rangée est
  découpée, le reste devient une case, et une autre rangée plus bas est traitée pareil). Cases recalculées au fil de
  la lecture.
- **Case par case, texte à cheval sur deux cases** : quand un cartouche ou une bulle passe par-dessus la gouttière,
  le lire case par case le coupait en deux. Bulle repère maintenant ces passages (un cadre caché sous du papier, avec
  des lignes de lettres) : si le texte est vraiment partagé entre les deux cases, elles sont montrées **ensemble** ;
  s'il déborde seulement un peu, la case qui le porte est **élargie** jusqu'au bout de la bulle. Le découpage des cases
  ne change pas (vérifié : mêmes cases sur les 75 planches d'essai, dont 10 concernées par une bulle à cheval).
  Réglages › Lecteur › « Case par case : texte à cheval sur deux cases » pour revenir à des cases toujours seules.
  Les cases déjà calculées sont refaites au fil de la lecture.
- **Glissement réglable** d'une case à l'autre : Réglages › Lecteur › « Case par case : passage d'une case à
  l'autre » : instantané, rapide, normal, lent, très lent.
- **Pages de la bibliothèque** : jusqu'à 20 numéros de page affichés directement en bas (1 2 3 … 18 avant) ; au-delà,
  20 numéros autour de la page en cours, plus la première et la dernière.
- **Laboratoire › Recherche BDGest en secours** (désactivée par défaut) : quand l'index de Bédéthèque ne trouve rien de
  sûr, Bulle cherche aussi « dans tout le site » BDGest. C'est la même base, mais cette recherche trouve aussi les
  **albums par leur titre** ; l'année du fichier départage les homonymes (« Là-bas (2003) » → Là-bas (Sibran/Tronchet),
  paru en 2003, lié tout seul). Une requête de plus, au rythme prudent, pour chaque album ou série concerné. La
  recherche à la main (« Chercher… ») s'en sert toujours et propose aussi les albums trouvés (en choisir un lie
  directement la bonne fiche). L'ancienne recherche du site utilisée en secours ne renvoyait plus rien : réparée.
- Bédéthèque, adresse collée à la main : pour une série, on peut maintenant coller l'adresse d'**un de ses albums**
  (…/BD-Zombies-Peru-Cholet-Tome-1-La-Divine-Comedie-111890.html) : Bulle remonte tout seul à la série. Une page de
  **BDGest**, le site jumeau (critique « chronique-42-BD-… », preview…), est aussi acceptée, pour une série comme
  pour un one shot : Bulle y prend le lien vers la fiche Bédéthèque.
- Recherche Bédéthèque : un titre qui commence par « Là » (adverbe : « Là-bas », « Là où vont nos pères ») était
  traité comme l'article « La » et cherché à « Bas » dans la lettre B ; il est maintenant cherché à la lettre L, où
  le site le range.
- Bédéthèque, numéros de tome mieux compris : « 01 Résurrection », « 11 Marlowe chapitre I » (numéro en tête suivi
  directement du titre), « Androïdes 01 - Titre », « Série - 01 Titre », « 01_Titre », « 01-Titre » étaient « non
  reconnus » et tous les tomes affichés manquants. Un numéro en tête n'est pris que s'il a deux chiffres (« 01 »,
  « 11 ») : « 3 Fois rien », « 300 Grammes » ou « 20 000 lieues » restent des titres. Sur les 5 697 albums de la bibliothèque de
  référence, tous les numéros déjà reconnus restent les mêmes.
- Plus besoin de « Mettre à jour » pour ça : à l'ouverture d'un dossier déjà lié, les fichiers sont recomparés à la
  fiche de série enregistrée, **sans aucune requête** vers Bédéthèque (albums ajoutés, renommés ou mieux compris
  liés tout de suite). Les résumés déjà lus ne sont plus perdus lors d'une mise à jour de la série.
- **Télécharger des séries** : clic droit sur une série ou un album ›
  « Ajouter aux téléchargements » : un « +1 » s'envole et le compteur du bouton de téléchargement, en haut, augmente.
  Ce bouton ouvre le panier (liste, taille totale, « retirer ») ; « Tout télécharger » donne **un seul .zip**, chaque série
  dans son dossier, les fichiers tels quels (rien n'est recompressé ni modifié ; le .zip se fabrique au fil du
  téléchargement, sans fichier temporaire sur le serveur). Le même menu propose « Télécharger la série (.zip) » tout de
  suite. Le panier est gardé dans le navigateur ; un élément disparu depuis (renommé, supprimé) est simplement ignoré.
- **Zoom −** : boutons loupe − / + dans la barre du lecteur (et touches `-` / `+`). En dessous de 100 %, on dézoome
  jusqu'à voir la page entière, centrée (pratique en mode « Largeur ») ; un cran s'arrête à 100 % en passant. En case
  par case, le zoom − s'arrête à la case entière. Dans la bibliothèque, « Pochettes − / + » au-dessus de chaque grille
  change la taille des couvertures (même réglage que dans Réglages).
- **Pochette au survol** des propositions Bédéthèque (choix de la série, recherche album par album) : on voit la
  couverture avant de choisir. Bulle ne télécharge pas l'image : il donne son adresse au navigateur, qui l'affiche
  comme sur le site ; pour une série, la page de la série est lue une fois (au rythme prudent, puis gardée en cache).
- Scan : un nouveau dossier n'est plus compté comme un album ajouté (« 3 nouveaux albums (1 nouvelle série) » au lieu de
  « 4 nouveaux »), et les albums retirés ne comptent plus les dossiers disparus. Le panneau Bédéthèque d'un dossier
  pas encore analysé tient de nouveau sur une ligne.
- Habillages : Bande dessinée, Sobre, Bling-bling, Girly, Aquarium (bulles qui gonflent et éclatent au hasard, avec un
  petit « blop » grave et étouffé, synthétisé ; bouton haut-parleur pour couper le son, mémorisé sur l'appareil), Nuit étoilée (bleu nuit
  qui passe lentement du clair au foncé), Fanzine (papier, deux encres risographie, surligneur, scotch, tampons).
  Quatre saisons : couleurs et décor suivent la date (printemps : pétales de toutes les couleurs et petites fleurs ; été :
  lucioles, aigrettes de pissenlit et papillons ; automne : feuilles d'érable, de chêne et de bouleau qui tournoient ;
  hiver : vrais flocons à six branches et neige fine), saison réglable à la main dans Réglages › Affichage, ou d'un clic sur le
  bouton de saison en haut (🌸 ☀️ 🍂 ❄️ : il montre la saison affichée et passe à la suivante).
  L'habillage Néon a été retiré (ceux qui l'avaient repassent en Bande dessinée).
- Case par case, la case seule à l'écran : sur un écran large, une case haute et étroite remplit la hauteur mais pas la
  largeur, et ses voisines restaient visibles à côté ; la première case d'une rangée n'était même pas centrée (la planche
  était recalée contre le bord de l'écran), si bien que passer à la suivante donnait l'impression de simplement glisser
  vers la droite. Désormais la case est toujours centrée et tout le reste est masqué, de la couleur du fond choisi ; le
  masque suit la case et s'efface quand on glisse pour recadrer. Réglage « Case par case : autour de la case » :
  masquer (par défaut), assombrir beaucoup / un peu, ou laisser la planche visible.
- Case par case, détection des cases revue sur 74 planches réelles de 52 albums très différents : les bulles et
  cartouches à cheval sur deux cases ne les soudent plus (ils « barraient » la gouttière), une grande case sur deux
  rangées n'est plus coupée en deux, la grande image de fond avec des cases incrustées devient une case à part entière,
  les cases bien posées sur le blanc sont trouvées même quand une voisine déborde jusqu'au bord de la page, et une
  légende ou une ligne de crédits n'est plus prise pour une case. Sur l'échantillon, 32 planches sur 74 sont découpées
  autrement, presque toutes mieux ; les planches peintes sans cadre ni gouttière restent lues en page entière. Les cases
  déjà calculées sont refaites automatiquement, au fil de la lecture.
- Bédéthèque réservé à l'administrateur : un compte lecteur ne peut déclencher **aucune** requête vers Bédéthèque
  (recherche, analyse, résumés, one shots, diagnostic : refusés par le serveur, boutons cachés). Il voit les
  informations déjà récupérées (séries, auteurs, résumés déjà lus) ; un résumé pas encore lu affiche simplement un
  lien vers la fiche Bédéthèque.
- **Mettre Bulle sur Internet** : Réglages › Comptes et accès › « Se connecter avec un compte ». À l'ouverture, on
  tape le nom d'un compte et son mot de passe (8 caractères au moins) ; sans cela on ne voit rien, ni les BD, ni les
  couvertures, ni la liste des comptes. Un compte par personne, supprimable à tout moment ; un lecteur ne voit que son
  compte et ne peut pas en changer. Session de 30 jours (cookie protégé, « Secure » en HTTPS), coupée si le mot de
  passe change ou si le compte est supprimé. Après 5 essais ratés, l'adresse est bloquée 15 minutes (20 sur un même
  compte) ; fonctionne derrière Nginx Proxy Manager (adresse réelle du visiteur lue dans X-Real-IP). Le flux OPDS
  demande le nom du compte et son mot de passe. Le même blocage protège aussi le code d'accès, les mots de passe des
  profils et le code de la rubrique Adulte. Deux comptes ne peuvent plus porter le même nom.
- One shots : auteurs, éditeur et résumé. Sur Bédéthèque, la page d'une série d'un seul album n'a pas la petite liste
  des albums, seulement le bloc « Détail » : Bulle n'y trouvait donc aucun album et ne liait que la série (« album non
  repéré », sans auteurs ni résumé). L'album est maintenant lu dans ce bloc (scénario, dessin, éditeur, année).
  Pour les albums déjà liés, le bouton « Compléter N fiches » relit la page de la série, depuis la mémoire de Bulle
  la plupart du temps (sans requête). Corrige aussi les séries d'un seul tome analysées comme série (0 / 0 tomes).
- One shots, recherche album par album : « Chercher… » (sur un album à choisir, introuvable, ou « changer » sur un
  album trouvé) ouvre une vraie recherche sous l'album : titre modifiable, résultats de l'index et de la recherche du
  site réunis, tous les homonymes montrés ; on peut aussi coller l'adresse Bédéthèque de la **fiche de l'album**
  (…/BD-Titre-1234.html) ou de la série, et un lien ouvre la même recherche sur le site. Les homonymes distingués
  par une parenthèse (« Angela (Pecqueur/Vatine) », « Angela (Panini) », « Angela (1994) ») sont bien classés,
  l'année du fichier départage, et deux homonymes à égalité sont proposés « à choisir » au lieu d'être liés au hasard.
- Dossiers de **one shots** et Bédéthèque : un dossier fourre-tout (nommé « One shots », « 0 - ONE SHOTS »,
  « Oneshot »…, ou désigné à la main avec le bouton « Ce sont des one shots ») n'est plus pris pour une seule série :
  chaque album est cherché comme sa propre série (titre nettoyé : « Blast (Manu Larcenet) » → « Blast »,
  « Le photographe (2010) » → « Le photographe »), en tâche de fond, au même rythme prudent, une requête par album
  trouvé. Le dossier affiche les albums trouvés (avec « à vérifier » si le nom n'est pas identique), ceux « à
  choisir » entre plusieurs séries (un clic) et les introuvables (« Chercher… » sous un autre titre) ; chaque fiche
  d'album montre sa série, son genre et son lien Bédéthèque. Les albums ajoutés ensuite sont cherchés à la
  prochaine analyse, sans refaire les autres. La page Collection a une rubrique One shots. Un ancien lien erroné
  (le dossier entier rattaché à une série au nom proche) est oublié automatiquement.
- Case par case, mieux voir les cases (Réglages › Lecteur) : une **case large** (bandeau sur toute la largeur de la
  planche) ne peut pas être agrandie sur un écran étroit, elle restait minuscule sur un téléphone ; elle est
  maintenant lue **en deux ou trois temps** (gauche → droite, l'inverse en manga), chaque morceau grossi comme une
  case normale, le compteur indiquant « case 1/5 (2/3) » — seulement quand elle resterait petite, donc rarement
  sur PC ; réglage « Cases larges » pour la garder entière. Deux autres réglages : **marge autour de la case**
  (aucune, fine, large) et **assombrir le reste de la planche** autour de la case en cours (voile qui suit la case).
- Présentation téléphone, **dans l'appli Android seulement** (écran de 700 px ou moins ; dans un navigateur, même sur
  téléphone, rien ne change) : barre
  d'onglets en bas à portée du pouce (Bibliothèque, À lire, Recherche, Favoris — ou Hors ligne dans l'appli —,
  Plus), pochettes à trois par ligne, fiche d'album qui monte du bas avec de gros boutons, réglages en liste de
  rubriques puis rubrique plein écran, lettres en rangée horizontale sous la barre du haut (plus de barre
  latérale), décor animé coupé. Tout le reste (Listes, Historique, Activité,
  Collection, Au hasard, Adulte, Réglages, qualité HD/SD, scan, profil, laboratoire) est dans « Plus ».
  Sur tablette, PC et dans tout navigateur, rien ne change.
- Appli Android ([bulle-android](https://github.com/kermess14/bulle-android)) : dans l'appli, la fiche d'un album
  propose « Garder hors connexion » (pages copiées sur le téléphone, lisibles sans réseau, avec le lecteur
  habituel) et le menu gagne une rubrique « Hors connexion ». Dans un navigateur, rien ne change.
- Rogner les marges blanches (Réglages › Lecteur, ou touche `R` dans le lecteur) : le tour blanc ou crème des
  pages est coupé à l'affichage, pour une planche plus grande à l'écran, en une page, double page et défilement.
  Les numéros de page isolés dans la marge sont ignorés, un titre dans la marge est gardé ; une page blanche, un
  dessin à fond perdu ou un pourtour coloré restent entiers. Rien n'est jamais écrit dans les fichiers : seule
  l'image envoyée au lecteur est rognée (et gardée en cache à part). Pas en case par case, qui cadre déjà les cases.
- Case par case fluide : au passage de planche, l'ancienne case reste affichée (avec le petit rond de
  chargement si ça dure) pendant que Bulle prépare la suivante — image décodée et cases repérées — puis tout
  s'échange d'un seul coup : plus jamais de fond noir ni de planche mal cadrée, même sur un NAS lent. Les pages
  sans cases (garde, page blanche, titre) ne paient plus la détection : si les cases d'une planche jamais vue
  tardent, la planche s'affiche entière tout de suite puis glisse sur la première case dès qu'elles arrivent.
  La planche précédente est préchargée aussi (retour arrière immédiat), les préchargements passent en priorité
  réseau basse (la planche demandée garde la voie libre), et les appuis répétés pendant un chargement sont
  gardés (trois au plus) puis rejoués dans l'ordre.
  Pendant qu'une case glisse vers la suivante, l'image n'est jamais remplacée par sa version plus nette (elle
  attend la fin du glissement) : c'était la cause des cases noires passagères sur un NAS lent, la carte graphique
  devant redessiner une grande image en plein mouvement. Et sous l'image, la teinte moyenne de la planche remplace
  le noir si l'écran met un instant à la dessiner.
- Mode léger : le bouton « planche de BD » à côté du champignon coupe tout ce qui bouge en arrière-plan (mosaïque,
  verre dépoli, couvertures au hasard, bulles de l'aquarium, saisons, petits mots animés, ciel de la Nuit étoilée)
  pour un affichage plus fluide, sur tablette surtout. Mémorisé sur l'appareil (pas sur le profil).
- Un bouton « ‹ » devant le fil d'Ariane ramène en arrière (série → accueil, réglages → page d'avant), pratique sur
  tablette et téléphone où il n'y a pas de touche Échap.
- Cliquer sur une couverture : ouvre le dossier, ou lance la lecture de l'album (reprise automatique).
- Le petit « i » sur un album : fiche (taille, pages, progression, marquer lu / non lu,
  recommencer, télécharger, ouvrir le dossier). Un album illisible y explique pourquoi.
- Dans les gros dossiers (40 entrées et plus, ou toujours selon le réglage), une barre de lettres (grandes,
  à droite ; taille et côté réglables) permet de sauter directement à une lettre, même si la liste est
  découpée en pages.
- Qualité HD / SD : Bulle mesure la vraie taille des pages (deux pages par album, vers le tiers et les deux tiers ;
  le fichier n'est jamais modifié). Grand côté de 2400 px et plus = HD, en dessous = SD. Une pastille « HD » se pose
  en haut à gauche de la couverture (« HD 4/6 » sur une série mélangée ; en mode SD, la pastille compte les SD : « SD 2/6 »), la fiche « i » donne la résolution, et le sélecteur
  « Qualité : Tout / HD / SD » sous « Bibliothèque » filtre les vignettes (mémorisé par profil). La mesure se fait
  toute seule en arrière-plan après chaque scan (albums nouveaux ou modifiés, et tout le stock la première fois) ;
  Réglages › Bibliothèque › Qualité HD / SD : compteurs, « Mesurer maintenant », « Tout remesurer », arrêt, mesure
  automatique (variable QUALITY_AUTO) et seuil HD réglable (changer le seuil reclasse sans remesurer).
  API : `POST /api/quality/measure` (`{"limit": n}`, `{"ids": [...]}`, `{"remeasure": true}`), `POST /api/quality/stop`,
  `GET /api/quality`. Pendant la mesure, une bulle de notification montre l'avancement (avec « ■ Arrêter » pour
  l'administrateur) ; les journaux du conteneur donnent le début, l'avancement toutes les 20 s, la fin, les albums
  illisibles et l'état de la bibliothèque. `LOG_LEVEL=DEBUG` dans la stack détaille chaque album mesuré.
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
- Les boutons « Retirer de Bulle » et « Remettre » ont été enlevés de l'interface (v0.20). Les albums déjà retirés le
  restent ; l'API (`POST /api/ignore/<id>`, `DELETE /api/ignored`) existe toujours pour l'administrateur.
- Garde-fou : si le dossier des BD paraît vide ou injoignable (partage réseau pas monté, NAS en veille), ou si plus
  de la moitié des albums disparaît d'un coup, le scan est annulé et rien n'est effacé ; l'administrateur peut
  « Scanner quand même » (`POST /api/scan` avec `{"force": true}`) s'il les a vraiment supprimés.
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
  bulle/simple.py    pages « lecture simple » (/simple) : HTML sans JavaScript pour les très vieux appareils
  bulle/server.py    serveur web Flask (servi par waitress) + API JSON + scan périodique
  tools/             banc d'essai de la détection des cases (banc_cases.py), tests de /simple (test_simple.py), icônes de
                     l'écran d'accueil de l'iPad (make_icons.py)
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
| `GET /simple` · `/simple/series` · `/simple/serie/<id>` · `/simple/lire/<id>?p=N` · `/simple/img/<id>/<n>` · `/simple/icone-72.png` · `/simple/icone-144.png` (sans connexion) · `POST /simple/connexion` · `/simple/profil` · `/simple/deconnexion` | lecture simple, HTML sans JavaScript (pages et formulaires ; `p` compte à partir de 1) |
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
