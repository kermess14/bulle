# Plugins de Bulle

Un **plugin** est un petit programme web empaqueté dans un fichier `.zip`. Bulle l'installe, le **lance à la
demande**, l'affiche dans le panneau du laboratoire (le champignon 🍄) et **l'arrête tout seul** après un moment sans
activité. Il tourne dans le conteneur de Bulle : rien à installer ailleurs, et il s'ouvre depuis n'importe quel
appareil (PC, iPad…).

- Seul l'**administrateur** de Bulle voit les plugins, les lance et y accède. Un lecteur n'y a pas accès, même en
  tapant l'adresse.
- Les plugins ne s'ouvrent que depuis le **réseau local** (`http://<serveur>:2205`). Par le nom de domaine public, ils
  n'existent pas (404, rien d'affiché). Variable `PLUGINS_INTERNET: "1"` dans la stack pour les ouvrir aussi depuis
  Internet (déconseillé).
- Le programme n'écoute que **dans le conteneur** (127.0.0.1). On y accède par Bulle, à l'adresse
  `http://<serveur>:2205/plugins/<id>/` : aucun port de plus à ouvrir.
- La bibliothèque reste en **lecture seule**. Un plugin écrit dans un **dossier de sortie** à part ; c'est vous qui
  copiez ensuite ce que vous voulez garder.

> ⚠️ Un plugin a les mêmes droits que Bulle dans le conteneur. N'installez que des plugins dont vous connaissez le code.

## 1. Préparer le dossier de sortie (une fois)

Dans la stack (`stack.yml`, dans Dockhand), sous `volumes:` du service `bulle`, décommentez la ligne du dossier de sortie
et mettez un dossier du serveur où vous voulez récupérer les fichiers :

```yaml
    volumes:
      - "/uncomp3/V3X.BD/00 - BD Français:/library:ro"
      - bulle-data:/data
      - "/srv/bulle-plugins-sortie:/plugins-out"   # ← ce que les plugins fabriquent
```

Redéployez. Chaque plugin y a son sous-dossier : `/srv/bulle-plugins-sortie/<id>/`.
Sans cette ligne, ça marche quand même, mais les fichiers restent dans le volume de Bulle (`/data/plugins-out`), moins
pratique à récupérer. Réglages › Laboratoire indique quel dossier est utilisé.

## 2. Installer un plugin

Réglages › **Laboratoire** › **Installer un plugin (.zip)…** et choisissez le paquet.

- S'il a des dépendances Python (`requirements.txt`), Bulle les installe en arrière-plan (une à deux minutes, il faut
  un accès Internet depuis le serveur). L'état affiche « Installation des dépendances… ».
- Envoyer un paquet qui a le **même id** qu'un plugin installé le **met à jour** (il est arrêté au passage).
- **Supprimer** désinstalle le programme et ses réglages, mais **garde le dossier de sortie** et vos fichiers.
- **Journal** montre ce que le programme a écrit (utile s'il ne démarre pas).

## 3. Utiliser un plugin

Cliquez sur le champignon 🍄 en haut à gauche (ou « Ouvrir » dans Réglages › Laboratoire). Le panneau a un onglet par
outil (BDConverter, puis vos plugins). Ouvrir l'onglet d'un plugin le démarre ; « ■ Arrêter » l'arrête tout de suite.

**Arrêt automatique** : après `idle_minutes` minutes (20 par défaut) sans aucune requête, Bulle arrête le programme.
Il n'est **pas** arrêté tant qu'une progression en direct est affichée, ni tant que le plugin répond « je travaille »
(voir `busy_url`). Un plugin lancé apparaît aussi dans Réglages › **Tâches**, où on peut l'arrêter.

## 4. Fabriquer un paquet

Un plugin, c'est un dossier avec votre programme et une fiche `plugin.json` :

```
mon-outil/
  plugin.json
  app.py
  requirements.txt     (facultatif : dépendances Python)
  static/ templates/…  (le reste de votre programme)
```

Puis, depuis le dossier de Bulle (sur votre PC, avec Python) :

```
python tools/make_plugin.py C:\chemin\vers\mon-outil
```

Le paquet `mon-outil-1.0.zip` est créé à côté du dossier. Les fichiers jetables ou personnels ne sont **jamais** mis
dedans : `__pycache__`, `.git`, `.venv`, `venv`, `.env`, `node_modules`, `*.zip`… et tout ce que vous listez dans
`exclude` (vos réglages, votre historique, vos téléchargements). `-l` affiche la liste des fichiers du paquet : vérifiez
qu'il n'y a rien de personnel avant de le partager.

Le plugin d'exemple `examples/plugins/bonjour` montre tout ce qui est utile (écrire dans la sortie, progression en
direct, `busy_url`), sans aucune dépendance.

### La fiche `plugin.json`

```json
{
  "id": "mon-outil",
  "name": "Mon outil",
  "version": "1.0",
  "description": "Ce que fait l'outil, en une phrase.",
  "command": ["{python}", "app.py"],
  "port": 5000,
  "idle_minutes": 20,
  "busy_url": "api/status",
  "keep": ["settings.json"],
  "exclude": ["settings.json", "downloads"],
  "icon": "icone.png"
}
```

| Clé | Obligatoire | Rôle |
|---|---|---|
| `id` | oui | Identifiant : minuscules, chiffres, tirets (ex. `mon-outil`). Sert dans l'adresse `/plugins/<id>/`. |
| `name`, `version` | oui | Nom affiché et version (texte libre, ex. `1.0`). |
| `description` | non | Une phrase affichée dans Réglages › Laboratoire. |
| `command` | oui | La commande qui lance le programme, en liste. `{python}` = le Python de Bulle ; `{port}`, `{output}`, `{data}` sont remplacés aussi. Le programme démarre **dans son dossier**. |
| `port` | non | Le port où le programme écoute, s'il est fixé dans son code (ex. une appli Flask lancée avec `app.run(port=5000)`). Sans `port`, Bulle en choisit un libre et le donne dans la variable `PORT`. |
| `idle_minutes` | non | Arrêt automatique après ce nombre de minutes sans activité (20 par défaut ; `0` = jamais). |
| `busy_url` | non | Adresse **relative** que Bulle interroge avant l'arrêt automatique. Si elle répond un JSON avec `"busy": true`, le plugin n'est pas arrêté (ex. un long travail lancé puis panneau fermé). |
| `start_timeout` | non | Secondes laissées au programme pour répondre au démarrage (30 par défaut). |
| `env` | non | Variables d'environnement en plus, ex. `{"MON_REGLAGE": "1"}`. |
| `keep` | non | Fichiers ou dossiers que le programme écrit **à côté de son code** et qui doivent survivre à une mise à jour du paquet (réglages, historique…). |
| `exclude` | non | Fichiers ou dossiers à ne **pas** mettre dans le paquet (jokers `*` acceptés). Mettez-y ce qui est personnel. |
| `requirements` | non | Nom du fichier de dépendances (par défaut `requirements.txt`, s'il existe). Flask, Pillow et BeautifulSoup sont déjà dans Bulle. |
| `icon` | non | Image du paquet (png, svg, jpg, webp) affichée dans la liste. |

### Ce que Bulle donne au programme (variables d'environnement)

| Variable | Contenu |
|---|---|
| `PORT`, `PLUGIN_PORT` | Le port où écouter (celui de `port` s'il est fixé). |
| `HOST` | `127.0.0.1` : n'écoutez que là. |
| `PLUGIN_OUTPUT` | Le dossier de sortie du plugin, en écriture (`/plugins-out/<id>`). |
| `PLUGIN_DATA` | Un dossier à lui, gardé lors des mises à jour (`/data/plugins/<id>/data`). |
| `PLUGIN_BASE` | L'adresse publique du plugin : `/plugins/<id>/`. |
| `PLUGIN_ID` | Son id. |

Le programme ne voit pas les autres variables de Bulle ni ses cookies de session.

### Programme écrit pour être servi « à la racine »

Beaucoup de petites applis utilisent des adresses comme `/api/...` ou `/static/...`. Bulle s'en occupe : dans les
pages HTML et CSS relayées, ces adresses sont réécrites en `/plugins/<id>/...`, et un petit script ajouté en tête de
page fait de même pour `fetch`, `EventSource`, `XMLHttpRequest`, `window.open` et les liens créés en JavaScript.
Les redirections et les cookies du programme sont adaptés, et les en-têtes `Origin` / `Referer` sont traduits (le
programme se croit appelé sur `http://127.0.0.1:<port>`). Dans la plupart des cas, il n'y a **rien à changer** au
programme.

Limites : les **WebSockets** ne sont pas relayés (les flux Server-Sent Events, eux, oui) ; une adresse fabriquée d'une
façon inhabituelle peut échapper à la réécriture — des adresses **relatives** (`api/files` plutôt que `/api/files`)
restent le plus sûr. Un seul exemplaire du programme tourne à la fois.

## Désactiver complètement les plugins

Variable `PLUGINS: "0"` dans la stack : plus de section Plugins, plus de route `/plugins/`.
