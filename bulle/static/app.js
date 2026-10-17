/* Bulle — navigation dans la bibliothèque */
(() => {
  "use strict";
  const $ = (sel, el = document) => el.querySelector(sel);
  const main = $("#main"), crumbsEl = $("#crumbs"), modal = $("#modal"), toastEl = $("#toast");
  const searchInput = $("#search"), scanBtn = $("#scan-btn"), statsEl = $("#stats");

  const ICON = {
    folder: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 6a2 2 0 0 1 2-2h4.6a2 2 0 0 1 1.4.6L12.4 6H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z"/></svg>`,
    book: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 3h11a2 2 0 0 1 2 2v14.5a1.5 1.5 0 0 1-1.5 1.5H6.5A2.5 2.5 0 0 1 4 18.5v-13A2.5 2.5 0 0 1 6.5 3H6zm0 14a.5.5 0 0 0 0 1h11v-1H6z"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>`,
    play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5.5v13a1 1 0 0 0 1.5.9l11-6.5a1 1 0 0 0 0-1.8l-11-6.5A1 1 0 0 0 7 5.5z"/></svg>`,
    down: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12m0 0 5-5m-5 5-5-5M4 20h16"/></svg>`,
    warn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 8v5m0 3.5v.5"/><path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>`,
    close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
  };

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtSize = b => b >= 1e9 ? (b / 1e9).toFixed(2) + " Go" : b >= 1e6 ? (b / 1e6).toFixed(1) + " Mo" : Math.round(b / 1e3) + " Ko";
  const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "—";
  const fmtExt = p => { const m = /\.([a-z0-9]+)$/i.exec(p || ""); return m ? m[1].toUpperCase() : "?"; };
  const plural = (n, s, p) => n + " " + (n > 1 ? p : s);
  const norm = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).error || msg; } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  }

  // ---------------------------------------------------------------- toasts
  let toastTimer = null;
  function toast(html, { sticky = false } = {}) {
    toastEl.innerHTML = html;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    if (!sticky) toastTimer = setTimeout(() => { toastEl.hidden = true; }, 3500);
  }
  const hideToast = () => { toastEl.hidden = true; clearTimeout(toastTimer); };

  // ---------------------------------------------------------------- cartes
  function coverHtml(item, inner = "") {
    const id = item.kind === "folder" ? item.cover_id : item.id;
    const v = item.kind === "folder" ? ("f" + item.cover_id) : item.mtime;
    const ph = `<div class="ph">${item.kind === "folder" ? ICON.folder : ICON.book}</div>`;
    const img = id && !item.error
      ? `<img loading="lazy" decoding="async" alt="" src="/api/cover/${id}?v=${v}" onerror="this.remove()">`
      : "";
    return `<div class="cover ${item.kind === "folder" ? "folder" : ""} ${item.error ? "err" : ""}">${ph}${img}${inner}</div>`;
  }
  const FORMAT_EXT = { zip: ["CBZ", "ZIP"], rar: ["CBR", "RAR"], pdf: ["PDF"], "7z": ["CB7", "7Z"], tar: ["CBT", "TAR"] };
  function formatLabel(it) {
    const ext = fmtExt(it.path);
    if (!it.format) return ext;
    const expected = FORMAT_EXT[it.format] || [];
    return expected.includes(ext) ? ext : `${ext} (contenu ${it.format.toUpperCase()})`;
  }

  function progressHtml(p) {
    if (!p) return "";
    if (p.completed) return `<span class="badge ok" title="Lu">${ICON.check}</span>`;
    if (p.pages) {
      const pct = Math.max(2, Math.round(((p.page + 1) / p.pages) * 100));
      return `<span class="badge" title="En cours">p. ${p.page + 1}</span><div class="bar"><i style="width:${pct}%"></i></div>`;
    }
    return `<span class="badge" title="En cours">p. ${p.page + 1}</span>`;
  }

  function card(item, { sub } = {}) {
    if (item.kind === "folder") {
      const read = item.read_count ? `<div class="sub">${item.read_count}/${item.album_count} lus${item.reading_count ? " · " + plural(item.reading_count, "en cours", "en cours") : ""}</div>`
        : item.reading_count ? `<div class="sub">${plural(item.reading_count, "album en cours", "albums en cours")}</div>` : "";
      return `<a class="card" href="#/f/${item.id}" data-letter="${esc(letterOf(item.name))}">
        ${coverHtml(item, `<span class="badge count" title="${plural(item.album_count, "album", "albums")}">${ICON.folder}${item.album_count}</span>`)}
        <div class="title">${esc(item.name)}</div>${read || `<div class="sub">${plural(item.album_count, "album", "albums")}</div>`}
      </a>`;
    }
    const badge = item.error ? `<span class="badge warn" title="${esc(item.error)}">${ICON.warn}</span>` : progressHtml(item.progress);
    const href = item.error ? "#" : `/read/${item.id}`;
    return `<a class="card album" href="${href}" data-id="${item.id}" data-letter="${esc(letterOf(item.name))}">
      ${coverHtml(item, badge)}
      <button class="info" type="button" data-info="${item.id}" title="Fiche de l'album" aria-label="Fiche de l'album">i</button>
      <div class="title">${esc(item.name)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}
    </a>`;
  }

  function letterOf(name) {
    const c = norm(name).replace(/^(le |la |les |l'|the |un |une |des )/, "").trim()[0] || "#";
    return /[a-z]/.test(c) ? c.toUpperCase() : "#";
  }

  function lettersHtml(children) {
    if (children.length < 40) return "";
    const present = new Set(children.map(c => letterOf(c.name)));
    const all = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
    return `<div class="letters" id="letters">${all.map(l => `<button type="button" data-letter="${l}" class="${present.has(l) ? "on" : ""}" ${present.has(l) ? "" : "disabled"}>${l}</button>`).join("")}</div>`;
  }

  // ---------------------------------------------------------------- vues
  function setCrumbs(list, tail) {
    const parts = list.map((c, i) => i === list.length - 1 && !tail
      ? `<span class="cur">${esc(c.name)}</span>`
      : `<a href="${i === 0 ? "#/" : "#/f/" + c.id}">${esc(c.name)}</a>`);
    if (tail) parts.push(`<span class="cur">${esc(tail)}</span>`);
    crumbsEl.innerHTML = parts.join(`<span class="sep">›</span>`);
  }

  function renderEmpty(scan) {
    setCrumbs([]);
    const running = scan && scan.running;
    main.innerHTML = `<div class="empty">${running ? '<div class="spinner"></div>' : ""}
      <p><strong>${running ? "Premier scan de la bibliothèque en cours…" : "La bibliothèque est vide."}</strong></p>
      <p>${running ? `${scan.albums || 0} albums trouvés pour l'instant. La page se mettra à jour toute seule.` : "Vérifiez le dossier des BD (variable LIBRARY_ROOT) puis lancez un scan avec le bouton ↻."}</p></div>`;
    if (running) pollScan(true);
  }

  async function viewFolder(id) {
    const [data, cont, recent] = await Promise.all([
      api(id ? `/api/browse/${id}` : "/api/browse"),
      id ? null : api("/api/continue"),
      id ? null : api("/api/recent?n=18"),
    ]);
    if (data.empty) return renderEmpty(data.scan);
    setCrumbs(data.breadcrumb);
    document.title = (id ? data.folder.name + " — " : "") + "Bulle";
    const children = data.children;
    let html = "";
    if (!id) {
      if (cont && cont.length) {
        html += `<h2>Reprendre la lecture</h2><div class="row">${cont.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      }
      if (recent && recent.length && children.length) {
        html += `<h2>Ajouts récents</h2><div class="row">${recent.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      }
      html += `<h2>Bibliothèque <small class="muted">${plural(children.length, "entrée", "entrées")}</small></h2>`;
    } else {
      const folders = children.filter(c => c.kind === "folder").length, albums = children.length - folders;
      html += `<h1>${esc(data.folder.name)} <small class="muted" style="font-size:14px;font-weight:400">${[folders ? plural(folders, "dossier", "dossiers") : "", albums ? plural(albums, "album", "albums") : ""].filter(Boolean).join(" · ")}</small></h1>`;
    }
    html += lettersHtml(children);
    html += children.length ? `<div class="grid" id="grid">${children.map(c => card(c)).join("")}</div>` : `<div class="empty">Dossier vide</div>`;
    main.innerHTML = html;
  }

  async function viewSearch(q) {
    setCrumbs([{ id: 0, name: "Accueil" }], `Recherche : ${q}`);
    document.title = `« ${q} » — Bulle`;
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const res = await api(`/api/search?q=${encodeURIComponent(q)}`);
    if (!res.length) { main.innerHTML = `<div class="empty"><strong>Rien trouvé pour « ${esc(q)} »</strong><p>La recherche ignore les accents et les majuscules et porte sur les noms des dossiers et des fichiers.</p></div>`; return; }
    const folders = res.filter(r => r.kind === "folder"), albums = res.filter(r => r.kind === "album");
    let html = "";
    if (folders.length) html += `<h2>Séries / dossiers <small class="muted">${folders.length}</small></h2><div class="grid">${folders.map(f => card(f, {})).join("")}</div>`;
    if (albums.length) html += `<h2>Albums <small class="muted">${albums.length}</small></h2><div class="grid">${albums.map(a => card(a, { sub: a.folder })).join("")}</div>`;
    main.innerHTML = html;
  }

  // ---------------------------------------------------------------- fiche album
  async function openInfo(id) {
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop"><div class="sheet"><div class="empty"><div class="spinner"></div></div></div></div>`;
    let it;
    try { it = await api(`/api/item/${id}`); } catch (e) { modal.innerHTML = `<div class="backdrop"><div class="sheet"><div class="empty">${esc(e.message)}</div></div></div>`; return; }
    const p = it.progress;
    const pct = p && it.pages ? Math.round(((p.page + 1) / it.pages) * 100) : 0;
    const folder = it.breadcrumb.map(b => b.name).slice(1).join(" › ");
    const parent = it.breadcrumb.length ? it.breadcrumb[it.breadcrumb.length - 1] : null;
    const fmt = formatLabel(it);
    modal.innerHTML = `<div class="backdrop"><div class="sheet" role="dialog" aria-modal="true" aria-label="Fiche de l'album">
      <button class="iconbtn close" type="button" data-close title="Fermer">${ICON.close}</button>
      ${coverHtml(it)}
      <div>
        <h3>${esc(it.name)}</h3>
        <div class="path">${esc(folder || "Racine")}</div>
        ${it.error ? `<p class="error">${ICON.warn} ${esc(it.error)}</p>` : ""}
        <dl>
          <dt>Format</dt><dd>${esc(fmt)}</dd>
          <dt>Taille</dt><dd>${fmtSize(it.size)}</dd>
          <dt>Pages</dt><dd>${it.pages ?? "?"}</dd>
          <dt>Progression</dt><dd>${p ? (p.completed ? "Lu ✓" : `Page ${p.page + 1} sur ${it.pages ?? "?"} — ${pct} %`) : "Non lu"}
            ${p && !p.completed && it.pages ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}</dd>
          <dt>Fichier</dt><dd class="path">${esc(it.path.split("/").pop())}</dd>
        </dl>
        <div class="actions">
          ${it.error ? "" : `<a class="btn primary" href="/read/${it.id}${p && !p.completed ? "" : "?page=0"}">${ICON.play} ${p && !p.completed ? `Reprendre p. ${p.page + 1}` : (p ? "Relire" : "Lire")}</a>`}
          ${p && !p.completed && !it.error ? `<a class="btn" href="/read/${it.id}?page=0">Recommencer</a>` : ""}
          ${it.error ? "" : (p && p.completed
            ? `<button class="btn" type="button" data-unread="${it.id}">Marquer non lu</button>`
            : `<button class="btn" type="button" data-read="${it.id}">${ICON.check} Marquer comme lu</button>`)}
          ${p && !p.completed ? `<button class="btn" type="button" data-unread="${it.id}">Effacer la progression</button>` : ""}
          <a class="btn" href="/api/download/${it.id}">${ICON.down} Télécharger</a>
          ${parent && parent.id ? `<a class="btn" href="#/f/${parent.id}" data-close>Ouvrir le dossier</a>` : ""}
        </div>
      </div></div></div>`;
  }
  const closeModal = () => { modal.hidden = true; modal.innerHTML = ""; };

  modal.addEventListener("click", async e => {
    const t = e.target.closest("[data-close], [data-read], [data-unread], .backdrop");
    if (!t) return;
    if (t.matches(".backdrop") && e.target !== t) return;
    if (t.dataset.read !== undefined && t.dataset.read !== "") {
      try { await api(`/api/progress/${t.dataset.read}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ completed: true }) }); }
      catch (err) { toast(esc(err.message)); return; }
      closeModal(); route(); return;
    }
    if (t.dataset.unread !== undefined && t.dataset.unread !== "") {
      await api(`/api/progress/${t.dataset.unread}`, { method: "DELETE" });
      closeModal(); route(); return;
    }
    closeModal();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !modal.hidden) closeModal(); });

  // ---------------------------------------------------------------- scan
  let scanTimer = null;
  async function pollScan(refreshWhenDone) {
    clearTimeout(scanTimer);
    let s;
    try { s = await api("/api/scan"); } catch (_) { return; }
    scanBtn.classList.toggle("spin", !!s.running);
    if (s.running) {
      const txt = s.phase === "covers"
        ? `Couvertures : ${s.covers_done}/${s.covers_total}`
        : `Scan en cours… ${s.albums} albums`;
      toast(`<div class="spinner"></div>${txt}`, { sticky: true });
      scanTimer = setTimeout(() => pollScan(true), 1500);
    } else if (refreshWhenDone) {
      if (s.error) toast(`${ICON.warn} Scan impossible : ${esc(s.error)}`);
      else toast(`Scan terminé : ${s.albums} albums${s.added ? `, ${s.added} nouveaux` : ""}${s.removed ? `, ${s.removed} retirés` : ""}`);
      route(); loadStats();
    }
  }
  scanBtn.addEventListener("click", async () => {
    try { await fetch("/api/scan", { method: "POST" }); } catch (_) { /* ignore */ }
    pollScan(true);
  });

  async function loadStats() {
    try {
      const s = await api("/api/stats");
      statsEl.textContent = `${s.albums} albums · ${fmtSize(s.size)}`;
      statsEl.title = `${s.folders} dossiers · ${s.read} lus · dernier scan : ${fmtDate(s.last_scan)}`;
      if (s.scan && s.scan.running) pollScan(true);
    } catch (_) { /* ignore */ }
  }

  // ---------------------------------------------------------------- recherche
  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    searchTimer = setTimeout(() => {
      if (q.length >= 2) location.hash = "#/s/" + encodeURIComponent(q);
      else if (!q && location.hash.startsWith("#/s/")) location.hash = "#/";
    }, 250);
  });
  $("#search-form").addEventListener("submit", e => { e.preventDefault(); const q = searchInput.value.trim(); if (q.length >= 2) location.hash = "#/s/" + encodeURIComponent(q); searchInput.blur(); });

  // ---------------------------------------------------------------- clics dans la grille
  main.addEventListener("click", e => {
    const info = e.target.closest("[data-info]");
    if (info) { e.preventDefault(); openInfo(info.dataset.info); return; }
    const letter = e.target.closest(".letters button");
    if (letter) {
      const target = main.querySelector(`#grid .card[data-letter="${letter.dataset.letter}"]`);
      if (target) {
        const y = target.getBoundingClientRect().top + window.scrollY - 56 - 48;
        window.scrollTo({ top: y, behavior: "smooth" });
      }
      return;
    }
    const album = e.target.closest("a.card.album");
    if (album && album.getAttribute("href") === "#") { e.preventDefault(); openInfo(album.dataset.id); }
  });

  // ---------------------------------------------------------------- routeur (#/, #/f/<id>, #/s/<q>)
  const scrollMemory = new Map();
  let currentKey = null;
  async function route() {
    if (currentKey !== null) scrollMemory.set(currentKey, window.scrollY);
    const h = location.hash || "#/";
    currentKey = h;
    try {
      let m;
      if ((m = /^#\/f\/(\d+)/.exec(h))) {
        await viewFolder(+m[1]);
      } else if ((m = /^#\/s\/(.+)/.exec(h))) {
        const q = decodeURIComponent(m[1]);
        if (searchInput.value.trim() !== q) searchInput.value = q;
        await viewSearch(q);
      } else {
        if (!h.startsWith("#/s/")) searchInput.value = "";
        await viewFolder(0);
      }
    } catch (e) {
      main.innerHTML = `<div class="empty"><strong>Oups.</strong><p>${esc(e.message)}</p><p><a class="btn" href="#/">Retour à l'accueil</a></p></div>`;
    }
    const y = scrollMemory.get(h);
    requestAnimationFrame(() => window.scrollTo(0, y || 0));
  }
  window.addEventListener("hashchange", route);
  window.addEventListener("pageshow", e => { if (e.persisted) route(); });
  route();
  loadStats();
})();
