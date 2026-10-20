# Bulle — lecteur de BD maison (v0.32.0)

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
