"""Plugin d'exemple pour Bulle, sans aucune dépendance (bibliothèque standard de Python seulement).

Ce que Bulle lui donne (variables d'environnement) :
    PORT           le port où écouter (sur 127.0.0.1)
    PLUGIN_OUTPUT  le dossier de sortie, en écriture : c'est là qu'on dépose ce qu'on fabrique
    PLUGIN_DATA    un dossier à soi, gardé lors des mises à jour
    PLUGIN_BASE    l'adresse publique du plugin (/plugins/bonjour/) — pas besoin de s'en servir : Bulle réécrit les
                   adresses « /… » des pages, mais des adresses relatives (« api/files ») restent le plus sûr.

Il montre les trois choses utiles à un plugin : écrire dans le dossier de sortie, suivre une tâche en direct
(Server-Sent Events) et dire à Bulle qu'il travaille encore (api/status → {"busy": true}) pour ne pas être arrêté
pendant une tâche.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse

PORT = int(os.environ.get("PORT", "5050"))
OUT = os.environ.get("PLUGIN_OUTPUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "sortie")
os.makedirs(OUT, exist_ok=True)
COUNTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compteur.txt")   # gardé lors des mises à jour (« keep »)
job = {"running": False, "done": 0, "total": 0}
lock = threading.Lock()

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bonjour</title><link rel="stylesheet" href="/static/style.css"></head><body>
<h1>Bonjour 👋</h1>
<p>Ce plugin tourne dans le conteneur de Bulle. Il a été ouvert <b id="n">…</b> fois.</p>
<h2>Dossier de sortie</h2><p><code id="out"></code></p>
<p><button id="write">Écrire un fichier test</button> <button id="task">Lancer une tâche de 10 s</button></p>
<p id="prog"></p>
<ul id="files"></ul>
<script>
async function load() {
  const j = await (await fetch("/api/files")).json();
  document.getElementById("out").textContent = j.output;
  document.getElementById("n").textContent = j.visits;
  document.getElementById("files").innerHTML = j.files.map(f =>
    `<li><a href="/api/download/${encodeURIComponent(f.name)}">${f.name}</a> (${f.size} octets)</li>`).join("") || "<li>(vide)</li>";
}
document.getElementById("write").onclick = async () => { await fetch("/api/write", {method: "POST"}); load(); };
document.getElementById("task").onclick = async () => {
  await fetch("/api/task", {method: "POST"});
  const es = new EventSource("/api/stream");
  es.onmessage = e => { const d = JSON.parse(e.data); document.getElementById("prog").textContent = `Tâche : ${d.done} / ${d.total}`;
    if (!d.running) { es.close(); document.getElementById("prog").textContent += " — terminée"; load(); } };
};
load();
</script></body></html>"""
CSS = "body{font:16px system-ui,sans-serif;margin:2em;background:#fffaf0;color:#14110e}button{font:inherit;padding:.4em .9em}"


def visits():
    try:
        with open(COUNTER) as f:
            return int(f.read() or 0)
    except (OSError, ValueError):
        return 0


def run_task():
    with lock:
        job.update(running=True, done=0, total=10)
    for i in range(10):
        time.sleep(1)
        job["done"] = i + 1
    with open(os.path.join(OUT, f"tache-{time.strftime('%Y%m%d-%H%M%S')}.txt"), "w", encoding="utf-8") as f:
        f.write("Tâche terminée.\n")
    job["running"] = False


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            n = visits() + 1
            with open(COUNTER, "w") as f:
                f.write(str(n))
            return self.send(200, PAGE, "text/html")
        if path == "/static/style.css":
            return self.send(200, CSS, "text/css")
        if path == "/api/status":   # pour Bulle : ne pas m'arrêter pendant une tâche
            return self.send(200, {"busy": job["running"]})
        if path == "/api/files":
            files = [{"name": n, "size": os.path.getsize(os.path.join(OUT, n))} for n in sorted(os.listdir(OUT))
                     if os.path.isfile(os.path.join(OUT, n))]
            return self.send(200, {"output": OUT, "files": files, "visits": visits()})
        if path.startswith("/api/download/"):
            name = os.path.basename(unquote(path[len("/api/download/"):]))
            full = os.path.join(OUT, name)
            if not name or not os.path.isfile(full):
                return self.send(404, {"error": "introuvable"})
            with open(full, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        if path == "/api/stream":   # progression en direct (Server-Sent Events)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while True:
                self.wfile.write(f"data: {json.dumps(job)}\n\n".encode())
                self.wfile.flush()
                if not job["running"]:
                    return None
                time.sleep(0.5)
        return self.send(404, {"error": "introuvable"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/write":
            name = f"bonjour-{time.strftime('%Y%m%d-%H%M%S')}.txt"
            with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
                f.write("Bonjour depuis un plugin de Bulle !\n")
            return self.send(200, {"written": name})
        if path == "/api/task":
            if not job["running"]:
                threading.Thread(target=run_task, daemon=True).start()
            return self.send(202, {"started": True})
        return self.send(404, {"error": "introuvable"})

    def log_message(self, fmt, *args):   # journal du plugin (visible dans Bulle : Réglages › Laboratoire › Journal)
        print("[bonjour] " + fmt % args, flush=True)


if __name__ == "__main__":
    print(f"[bonjour] écoute sur 127.0.0.1:{PORT}, sortie : {OUT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
