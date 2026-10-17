/* Bulle — navigation dans la bibliothèque + page Réglages */
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
      let msg = r.statusText, body = null;
      try { body = await r.json(); msg = body.error || msg; } catch (_) { /* ignore */ }
      if (r.status === 401 && body && body.auth_required) showPinScreen();
      throw new Error(msg);
    }
    return r.json();
  }

  // ================================================================ code d'accès (écran)
  let pinShown = false;
  function showPinScreen() {
    if (pinShown) return;
    pinShown = true;
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop locked"><form class="sheet pin" id="pin-form">
      <h3>Code d'accès</h3><p class="muted">Cette bibliothèque est protégée. Entrez le code pour continuer.</p>
      <input type="password" inputmode="numeric" autocomplete="current-password" name="pin" placeholder="Code" autofocus>
      <div class="actions"><button class="btn primary" type="submit">Entrer</button></div><p class="error" hidden></p></form></div>`;
    $("#pin-form").addEventListener("submit", async e => {
      e.preventDefault();
      const f = e.target, err = f.querySelector(".error");
      try {
        const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin: f.elements.pin.value }) });
        if (!r.ok) { err.textContent = (await r.json()).error || "Code incorrect"; err.hidden = false; f.elements.pin.select(); return; }
        location.reload();
      } catch (_) { err.textContent = "Serveur injoignable"; err.hidden = false; }
    });
  }

  // ================================================================ profils (« qui lit ? »)
  const initial = n => (n || "?").trim()[0].toUpperCase();
  function profileTile(p, current) {
    return `<button type="button" class="ptile ${p.id === current ? "on" : ""}" data-profile="${p.id}" data-haspin="${p.has_pin ? 1 : 0}" data-name="${esc(p.name)}">
      <span class="pavatar">${esc(p.avatar || initial(p.name))}</span><span class="pname">${esc(p.name)}</span>${p.has_pin ? `<span class="plock" title="Protégé par un code">🔒</span>` : ""}</button>`;
  }
  async function openProfiles({ locked = false } = {}) {
    let data;
    try { data = await api("/api/profiles"); } catch (_) { return; }
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop ${locked ? "locked" : ""}"><div class="sheet profiles" role="dialog" aria-modal="true">
      ${locked ? "" : `<button class="iconbtn close" type="button" data-close title="Fermer">${ICON.close}</button>`}
      <h3>Qui lit ?</h3>
      <div class="ptiles">${data.profiles.map(p => profileTile(p, data.selected ? data.current : 0)).join("")}
        <button type="button" class="ptile add" data-profile-add><span class="pavatar">+</span><span class="pname">Nouveau profil</span></button></div>
      <p class="muted">Chaque profil a sa propre progression de lecture et ses réglages d'affichage.${locked ? "" : ` <a href="#/settings" data-close>Gérer les profils</a>`}</p>
      <form class="pin-inline" id="profile-pin" hidden><span></span><input type="password" inputmode="numeric" name="pin" placeholder="Code PIN"><button class="btn primary" type="submit">OK</button><p class="error" hidden></p></form>
      <form class="pin-inline" id="profile-new" hidden><input type="text" name="name" placeholder="Prénom" maxlength="40" required><input type="password" inputmode="numeric" name="pin" placeholder="Code PIN (facultatif)"><button class="btn primary" type="submit">Créer</button></form>
    </div></div>`;
    const sheet = $(".sheet.profiles");
    sheet.addEventListener("click", e => {
      const t = e.target.closest("[data-profile], [data-profile-add]");
      if (!t) return;
      if (t.hasAttribute("data-profile-add")) { $("#profile-new").hidden = false; $("#profile-pin").hidden = true; $("#profile-new input[name=name]").focus(); return; }
      const id = +t.dataset.profile;
      if (t.dataset.haspin === "1") {
        const f = $("#profile-pin"); f.hidden = false; f.dataset.id = id; f.querySelector("span").textContent = t.dataset.name + " :"; f.querySelector(".error").hidden = true; f.elements.pin.value = ""; f.elements.pin.focus();
        $("#profile-new").hidden = true;
      } else selectProfile(id, "");
    });
    $("#profile-pin").addEventListener("submit", e => { e.preventDefault(); selectProfile(+e.target.dataset.id, e.target.elements.pin.value, e.target); });
    $("#profile-new").addEventListener("submit", async e => {
      e.preventDefault();
      const f = e.target;
      try {
        const p = await api("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: f.elements.name.value, pin: f.elements.pin.value }) });
        await selectProfile(p.id, f.elements.pin.value);
      } catch (err) { toast(`${ICON.warn} ${esc(err.message)}`); }
    });
  }
  async function selectProfile(id, pin, form) {
    try {
      const r = await api("/api/profiles/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, pin }) });
      closeModal(); toast(`Bonjour ${esc(r.name)} !`);
      listsCache = null;
      await loadSettings(); updateProfileButton(); route(); renderSidebar();
    } catch (e) {
      if (form) { const err = form.querySelector(".error"); err.textContent = e.message; err.hidden = false; form.elements.pin.select(); }
      else toast(`${ICON.warn} ${esc(e.message)}`);
    }
  }
  function updateProfileButton() {
    const btn = $("#profile-btn");
    if (!btn) return;
    const list = settings.meta.profiles || [];
    const cur = list.find(p => p.id === settings.meta.profile_id);
    btn.innerHTML = `<span class="pavatar small">${esc(cur ? (cur.avatar || initial(cur.name)) : "?")}</span>`;
    btn.title = cur ? `Profil : ${cur.name} (changer)` : "Profil";
    btn.hidden = list.length < 2 && !settings.global.require_profile;
  }
  document.addEventListener("click", e => { if (e.target.closest("#profile-btn")) openProfiles(); });
  const putJson = (url, body) => api(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  // ================================================================ réglages
  const PROFILE_DEFAULTS = {
    thumb_size: "m", hover_zoom: "light", per_page: 48, letters: "auto", letters_side: "right", letters_size: "large",
    tabs_side: "left", cover_style: "book", sort: "natural", hide_read: false,
    show_pages: false, show_continue: true, show_recent: true, recent_count: 18, theme: "dark",
    remember_folder: false,
    reader_fit: "page", reader_manga: false, reader_bg: "black", reader_preload: 3, reader_quality: "normal",
    reader_bars_delay: 2.5, reader_tap_zones: true, reader_wheel: true, reader_night: 0, reader_remember_album: true,
    reader_mode: "single", reader_cover_alone: true, reader_scroll_width: 100,
    bdt_ghosts: true, bdt_titles: false,
  };
  const THUMB = { s: 118, m: 156, l: 200, xl: 250 };
  const HOVER = { none: 1, light: 1.05, strong: 1.12 };
  const settings = { profile: Object.assign({}, PROFILE_DEFAULTS), global: {}, meta: {} };
  try { Object.assign(settings.profile, JSON.parse(localStorage.getItem("bulle:profile") || "{}")); } catch (_) { /* ignore */ }

  function applyAppearance() {
    const p = settings.profile, root = document.documentElement;
    root.style.setProperty("--thumb", (THUMB[p.thumb_size] || THUMB.m) + "px");
    root.style.setProperty("--hover-scale", String(HOVER[p.hover_zoom] ?? 1.05));
    const theme = p.theme === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : p.theme;
    root.dataset.theme = theme === "light" ? "light" : "dark";
    root.dataset.tabs = p.tabs_side === "top" || window.innerWidth <= 700 ? "top" : "left";
    root.dataset.covers = ["book", "glow", "flat"].includes(p.cover_style) ? p.cover_style : "book";
    $('meta[name="theme-color"]').setAttribute("content", theme === "light" ? "#f4f5f8" : "#0f1115");
  }
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyAppearance);
  let resizeTimer = null;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(applyAppearance, 120); });
  applyAppearance();

  async function loadSettings() {
    try {
      const s = await api("/api/settings");
      settings.global = s.global; settings.meta = s;
      settings.profile = Object.assign({}, PROFILE_DEFAULTS, s.profile || {});
      try { localStorage.setItem("bulle:profile", JSON.stringify(settings.profile)); } catch (_) { /* ignore */ }
      applyAppearance();
    } catch (_) { /* hors ligne : on garde la copie locale */ }
  }
  let saveTimer = null, pendingProfile = {}, pendingGlobal = {};
  function saveSettings(profilePatch, globalPatch) {
    if (profilePatch) { Object.assign(settings.profile, profilePatch); Object.assign(pendingProfile, profilePatch); }
    if (globalPatch) { Object.assign(settings.global, globalPatch); Object.assign(pendingGlobal, globalPatch); }
    try { localStorage.setItem("bulle:profile", JSON.stringify(settings.profile)); } catch (_) { /* ignore */ }
    applyAppearance();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const body = {};
      if (Object.keys(pendingProfile).length) body.profile = pendingProfile;
      if (Object.keys(pendingGlobal).length) body.global = pendingGlobal;
      pendingProfile = {}; pendingGlobal = {};
      try {
        const s = await putJson("/api/settings", body);
        settings.global = s.global; settings.meta = s;
        toast("Réglages enregistrés");
      } catch (e) { toast(`${ICON.warn} Réglage non enregistré : ${esc(e.message)}`); }
    }, 500);
  }

  // ================================================================ toasts
  let toastTimer = null;
  function toast(html, { sticky = false } = {}) {
    toastEl.innerHTML = html;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    if (!sticky) toastTimer = setTimeout(() => { toastEl.hidden = true; }, 3500);
  }

  // ================================================================ cartes
  /* Largeur de couverture à demander au serveur : la largeur affichée (en pixels physiques), arrondie à 50 px. */
  function coverWidth(cssWidth) {
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    return Math.max(100, Math.min(1200, Math.ceil((cssWidth * 1.25 * dpr) / 50) * 50));
  }
  function coverUrl(item, cssWidth) {
    const id = item.kind === "folder" ? item.cover_id : item.id;
    const v = item.kind === "folder" ? ("f" + item.cover_id) : item.mtime;
    return `/api/cover/${id}?w=${coverWidth(cssWidth)}&v=${v}&t=${encodeURIComponent(settings.global.img_tag || "")}`;
  }
  function coverHtml(item, inner = "", cssWidth) {
    const id = item.kind === "folder" ? item.cover_id : item.id;
    const ph = `<div class="ph">${item.kind === "folder" ? ICON.folder : ICON.book}</div>`;
    const img = id && !item.error
      ? `<img loading="lazy" decoding="async" alt="" src="${coverUrl(item, cssWidth || (THUMB[settings.profile.thumb_size] || THUMB.m))}" onerror="this.remove()">`
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

  function letterOf(name) {
    const c = norm(name).replace(/^(le |la |les |l'|the |un |une |des )/, "").trim()[0] || "#";
    return /[a-z]/.test(c) ? c.toUpperCase() : "#";
  }

  const colorStyle = item => /^#[0-9a-f]{6}$/i.test(item.color || "") ? ` style="--c:${item.color}"` : "";
  const FAV = `<span class="fav" title="Favori"><b>★</b></span>`;
  function card(item, { sub } = {}) {
    if (item.kind === "ghost") return ghostCard(item);
    const letter = esc(letterOf(item.name));
    if (item.kind === "folder") {
      let read = item.read_count ? `<div class="sub">${item.read_count}/${item.album_count} lus${item.reading_count ? " · " + plural(item.reading_count, "en cours", "en cours") : ""}</div>`
        : item.reading_count ? `<div class="sub">${plural(item.reading_count, "album en cours", "albums en cours")}</div>` : "";
      const done = item.album_count && item.read_count >= item.album_count ? `<span class="badge ok" title="Tout lu">${ICON.check}</span>` : "";
      let bdt = "";
      if (item.bdt && item.bdt.total) {
        const pct = Math.round((item.bdt.present / item.bdt.total) * 100);
        const full = item.bdt.present >= item.bdt.total;
        bdt = `<div class="sub bdt ${full ? "full" : ""}" title="Bédéthèque : ${esc(item.bdt.title || "")}${item.bdt.status ? " · " + esc(item.bdt.status) : ""}">${full ? "Série complète" : `${item.bdt.present}/${item.bdt.total} tomes`}<i style="width:${pct}%"></i></div>`;
      }
      return `<a class="card folder" href="#/f/${item.id}" data-letter="${letter}" data-id="${item.id}" draggable="true"${colorStyle(item)}>
        ${coverHtml(item, `<span class="badge count" title="${plural(item.album_count, "album", "albums")}">${ICON.folder}${item.album_count}</span>${done}${item.fav ? FAV : ""}`)}
        <div class="title">${esc(item.name)}</div>${read || (bdt ? "" : `<div class="sub">${plural(item.album_count, "album", "albums")}</div>`)}${bdt}
      </a>`;
    }
    const badge = (item.error ? `<span class="badge warn" title="${esc(item.error)}">${ICON.warn}</span>` : progressHtml(item.progress)) + (item.fav ? FAV : "");
    const href = item.error ? "#" : `/read/${item.id}`;
    let title = item.name, line2 = sub ? esc(sub) : (settings.profile.show_pages && item.pages ? plural(item.pages, "page", "pages") : "");
    if (settings.profile.bdt_titles && item.meta && item.meta.title) {
      title = (item.meta.number != null ? (item.meta.kind === "hs" ? "HS" : item.meta.kind === "int" ? "INT" : "T") + item.meta.number + " · " : "") + item.meta.title;
      if (!sub) line2 = esc(item.name);
    }
    const tip = item.meta && item.meta.summary ? ` title="${esc(item.meta.summary.length > 320 ? item.meta.summary.slice(0, 320) + "…" : item.meta.summary)}"` : "";
    return `<a class="card album" href="${href}" data-id="${item.id}" data-letter="${letter}" draggable="true"${colorStyle(item)}${tip}>
      ${coverHtml(item, badge + `<button class="info" type="button" data-info="${item.id}" title="Fiche de l'album" aria-label="Fiche de l'album">i</button>`)}
      <div class="title">${esc(title)}</div>${line2 ? `<div class="sub">${line2}</div>` : ""}
    </a>`;
  }

  function ghostCard(g) {
    return `<a class="card ghost" href="${esc(g.url)}" target="_blank" rel="noopener" title="Tome manquant · voir sur Bédéthèque" data-letter="#">
      <div class="cover ghost"><div class="gnum">T${g.number}</div><div class="glabel">manquant</div></div>
      <div class="title">${esc(g.title || "Tome " + g.number)}</div><div class="sub">${g.year || ""}</div>
    </a>`;
  }

  /* Insère les tomes manquants (fantômes) à leur place dans la liste des albums (tri naturel seulement). */
  function withGhosts(list, bdt) {
    if (!bdt || !bdt.missing || !bdt.missing.length || !settings.profile.bdt_ghosts || settings.profile.sort !== "natural") return list;
    const ghosts = bdt.missing.slice().sort((a, b) => a.number - b.number).map(m => Object.assign({ kind: "ghost", name: "T" + m.number }, m));
    const out = [];
    let gi = 0;
    for (const c of list) {
      const n = c.kind === "album" && bdt.matches && bdt.matches[c.id] ? bdt.matches[c.id].number : null;
      if (n != null) while (gi < ghosts.length && ghosts[gi].number < n) out.push(ghosts[gi++]);
      out.push(c);
    }
    while (gi < ghosts.length) out.push(ghosts[gi++]);
    return out;
  }

  // ================================================================ tri, filtre, pages, lettres
  function arrange(children) {
    const p = settings.profile;
    let list = children.slice();
    if (p.hide_read) {
      list = list.filter(c => c.kind === "folder" ? !(c.album_count && c.read_count >= c.album_count) : !(c.progress && c.progress.completed));
    }
    if (p.sort === "recent") {
      list.sort((a, b) => (a.kind !== b.kind ? (a.kind === "folder" ? -1 : 1) : a.kind === "folder" ? 0 : (b.added - a.added) || (b.mtime - a.mtime)));
    } else if (p.sort === "unread") {
      const rank = c => c.kind === "folder" ? (c.album_count && c.read_count >= c.album_count ? 2 : 0) : !c.progress ? 0 : c.progress.completed ? 2 : 1;
      list.sort((a, b) => (a.kind !== b.kind ? (a.kind === "folder" ? -1 : 1) : rank(a) - rank(b)));
    }
    return list;
  }

  function pagerHtml(page, pages, total) {
    if (pages <= 1) return "";
    const btn = (n, label = n, cls = "") => `<button type="button" class="pg ${cls} ${n === page ? "on" : ""}" data-page="${n}" ${n < 1 || n > pages ? "disabled" : ""}>${label}</button>`;
    const nums = new Set([1, pages, page - 1, page, page + 1, page - 2, page + 2].filter(n => n >= 1 && n <= pages));
    const sorted = [...nums].sort((a, b) => a - b);
    let items = "", prev = 0;
    for (const n of sorted) { if (n - prev > 1) items += `<span class="dots">…</span>`; items += btn(n); prev = n; }
    return `<nav class="pager" aria-label="Pages">${btn(page - 1, "‹", "arrow")}${items}${btn(page + 1, "›", "arrow")}
      <span class="pginfo">Page ${page} sur ${pages} · ${plural(total, "entrée", "entrées")}</span></nav>`;
  }

  function lettersHtml(list, mode) {
    const pref = settings.profile.letters;
    if (pref === "never" || settings.profile.sort !== "natural") return "";
    if (pref === "auto" && list.length < 40) return "";
    const present = new Set(list.map(c => letterOf(c.name)));
    const all = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
    const side = settings.profile.letters_side || "right";
    const size = settings.profile.letters_size === "normal" ? " size-normal" : "";
    return `<div class="letters ${side === "top" ? "" : "rail " + side + size}" id="letters">${all.map(l => `<button type="button" data-letter="${l}" class="${present.has(l) ? "on" : ""}" ${present.has(l) ? "" : "disabled"}>${l}</button>`).join("")}</div>`;
  }

  // ================================================================ vues
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

  let view = { children: [], list: [], page: 1, pages: 1, id: 0 };
  function gridFor(list, page) {
    const per = +settings.profile.per_page || 0;
    const pages = per ? Math.max(1, Math.ceil(list.length / per)) : 1;
    page = Math.min(Math.max(1, page), pages);
    const slice = per ? list.slice((page - 1) * per, page * per) : list;
    view.page = page; view.pages = pages; view.list = list;
    return `${pagerHtml(page, pages, list.length)}
      ${list.length ? `<div class="grid" id="grid">${slice.map(c => card(c)).join("")}</div>` : `<div class="empty">${settings.profile.hide_read ? "Tout est lu ici (les albums lus sont masqués dans les réglages)." : "Dossier vide"}</div>`}
      ${pages > 1 ? pagerHtml(page, pages, list.length) : ""}`;
  }

  async function viewFolder(id, page) {
    const p = settings.profile;
    const [data, cont, recent] = await Promise.all([
      api(id ? `/api/browse/${id}` : "/api/browse"),
      id || !p.show_continue ? null : api("/api/continue"),
      id || !p.show_recent ? null : api(`/api/recent?n=${+p.recent_count || 18}`),
    ]);
    if (data.empty) return renderEmpty(data.scan);
    setCrumbs(data.breadcrumb);
    document.title = (id ? data.folder.name + " — " : "") + "Bulle";
    view.children = data.children; view.id = id; view.folderName = id ? data.folder.name : "";
    const list = arrange(data.children);
    let html = "";
    if (!id) {
      if (cont && cont.length) html += `<h2>Reprendre la lecture</h2><div class="row">${cont.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      if (recent && recent.length && data.children.length) html += `<h2>Ajouts récents</h2><div class="row">${recent.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      html += `<h2>Bibliothèque <small class="muted">${plural(list.length, "entrée", "entrées")}</small></h2>`;
    } else {
      const folders = list.filter(c => c.kind === "folder").length, albums = list.length - folders;
      html += `<h1>${esc(data.folder.name)} <small class="muted h1sub">${[folders ? plural(folders, "dossier", "dossiers") : "", albums ? plural(albums, "album", "albums") : ""].filter(Boolean).join(" · ")}</small>
        <span class="h1tools"><button class="btn ${data.folder.fav ? "fav-on" : ""}" type="button" data-fav="${data.folder.id}" title="Série favorite">${data.folder.fav ? "★ Favori" : "☆ Favori"}</button>
        <button class="btn" type="button" data-addlist="${data.folder.id}" title="Ajouter cette série à une liste">+ Liste</button></span></h1>`;
      html += bdtPanelHtml(data);
    }
    html += lettersHtml(list);
    html += gridFor(id ? withGhosts(list, data.bdt) : list, page || 1);
    main.innerHTML = html;
  }

  // ================================================================ Bédéthèque
  function bdtPanelHtml(data, extra) {
    const hasAlbums = data.children.some(c => c.kind === "album");
    if (!hasAlbums || data.bdt_enabled === false) return "";
    const b = data.bdt;
    if (!b) {
      return `<div class="bdt-panel" id="bdt-panel"><div class="bdt-row"><span class="bdt-logo">BD</span>
        <span>Comparer ce dossier avec <b>Bédéthèque</b> : tomes présents, manquants, auteurs.</span>
        <button class="btn" type="button" data-bdt="analyze" data-folder="${data.folder.id}">Analyser</button></div>${extra || ""}</div>`;
    }
    const sr = b.series, pct = b.total ? Math.round((b.present / b.total) * 100) : 0;
    const full = b.total && b.present >= b.total;
    return `<div class="bdt-panel ${full ? "full" : ""}" id="bdt-panel">
      <div class="bdt-row">
        <span class="bdt-logo">BD</span>
        <div class="bdt-main">
          <div><b>${esc(sr.title || "Série")}</b>${sr.genre ? ` · ${esc(sr.genre)}` : ""}${sr.status ? ` · ${esc(sr.status)}` : ""}${sr.years ? ` · ${esc(sr.years)}` : ""}
            <a class="ext" href="${esc(sr.url)}" target="_blank" rel="noopener">voir sur Bédéthèque ↗</a>
            ${sr.score != null && sr.score < 0.9 && !sr.manual ? `<span class="warnlabel" title="La correspondance automatique n'est pas certaine">à vérifier</span>` : ""}</div>
          <div class="bdt-progress"><span>${full ? "Série complète" : `${b.present} / ${b.total} tomes présents`}</span><div class="pbar"><i style="width:${pct}%"></i></div></div>
          ${b.missing.length ? `<div class="bdt-missing">Manquants : ${b.missing.slice(0, 40).map(m => `<a href="${esc(m.url)}" target="_blank" rel="noopener" class="chip">T${m.number}${m.title ? " · " + esc(m.title) : ""}${m.year ? ` <small>${m.year}</small>` : ""}</a>`).join(" ")}${b.missing.length > 40 ? ` … (+${b.missing.length - 40})` : ""}</div>` : ""}
          ${b.unmatched.length ? `<div class="bdt-unmatched">Non reconnus : ${b.unmatched.map(u => `<span class="chip gray" title="Ce fichier n'a pas pu être rattaché à un tome">${esc(u.name)}</span>`).join(" ")}</div>` : ""}
          ${b.duplicates.length ? `<div class="bdt-unmatched">${plural(b.duplicates.length, "doublon", "doublons")} (plusieurs fichiers pour le même tome)</div>` : ""}
        </div>
        <div class="bdt-actions">
          <button class="btn" type="button" data-bdt="refresh" data-folder="${data.folder.id}" title="Relire la fiche sur Bédéthèque">↻ Mettre à jour</button>
          ${sr.detailed ? "" : `<button class="btn" type="button" data-bdt="details" data-folder="${data.folder.id}" title="Lire les auteurs, éditeur, ISBN de chaque tome (une page Bédéthèque par 10 tomes)">Auteurs et détails</button>`}
          <button class="btn" type="button" data-bdt="summaries" data-folder="${data.folder.id}" title="Lire le début du résumé de chaque album (une page Bédéthèque par album, en tâche de fond)">Résumés</button>
          <button class="btn" type="button" data-bdt="change" data-folder="${data.folder.id}">Changer de série</button>
          <button class="btn" type="button" data-bdt="forget" data-folder="${data.folder.id}">Oublier</button>
        </div>
      </div>${extra || ""}</div>`;
  }

  function bdtChooserHtml(folderId, report) {
    const cands = (report && report.candidates) || [];
    return `<div class="bdt-choose">
      ${report && report.message ? `<p>${esc(report.message)}</p>` : ""}
      ${cands.length ? `<div class="cands">${cands.map(c => `<button type="button" class="cand" data-bdt="pick" data-folder="${folderId}" data-url="${esc(c.url)}">
          <b>${esc(c.name)}</b><small>${[c.genre, c.tomes ? plural(c.tomes, "tome", "tomes") : "", c.exact ? "correspondance exacte" : ""].filter(Boolean).join(" · ")}</small></button>`).join("")}</div>` : ""}
      <form class="bdt-search" data-bdt="search" data-folder="${folderId}"><input type="search" name="q" placeholder="Chercher une série sur Bédéthèque…" value="${esc(report && report.query || "")}"><button class="btn" type="submit">Chercher</button></form>
      <form class="bdt-search" data-bdt="url" data-folder="${folderId}"><input type="url" name="url" placeholder="…ou coller l'adresse de la série (https://www.bedetheque.com/serie-…html)"><button class="btn" type="submit">Utiliser</button></form>
      <div class="bdt-results" id="bdt-results"></div>
    </div>`;
  }

  async function bdtAction(action, el) {
    const folderId = +el.dataset.folder;
    const panel = $("#bdt-panel");
    const busy = msg => { if (panel) panel.innerHTML = `<div class="bdt-row"><div class="spinner" style="margin:0"></div><span>${msg}</span></div>`; };
    try {
      if (action === "analyze" || action === "refresh" || action === "details" || action === "pick" || action === "url-submit") {
        busy(action === "details" ? "Lecture des fiches détaillées sur Bédéthèque (quelques secondes par page)…" : "Interrogation de Bédéthèque…");
        const body = {};
        if (action === "refresh") body.force = true;
        if (action === "details") body.details = true;
        if (action === "pick" || action === "url-submit") body.url = el.dataset.url;
        const r = await api(`/api/bdt/analyze/${folderId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (r.status === "ok") { toast(`Bédéthèque : ${esc(r.series.title)} — ${r.present}/${r.total} tomes`); route(); return; }
        if (r.status === "no_albums") { toast(esc(r.message)); route(); return; }
        const data = { folder: { id: folderId }, children: [{ kind: "album" }], bdt: null, bdt_enabled: true };
        if (panel) { panel.outerHTML = bdtPanelHtml(data, bdtChooserHtml(folderId, r)); }
        return;
      }
      if (action === "summaries") {
        const r = await fetch(`/api/bdt/summaries/${folderId}`, { method: "POST" });
        if (r.status === 409) { toast("Des résumés sont déjà en cours de lecture, patientez."); return; }
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || r.statusText); }
        pollSummaries();
        return;
      }
      if (action === "change") {
        const data = { folder: { id: folderId }, children: [{ kind: "album" }], bdt: null, bdt_enabled: true };
        if (panel) panel.outerHTML = bdtPanelHtml(data, bdtChooserHtml(folderId, { query: view.folderName || "" }));
        return;
      }
      if (action === "forget") {
        if (!confirm("Oublier le lien Bédéthèque de ce dossier ?")) return;
        await api(`/api/bdt/series/${folderId}`, { method: "DELETE" });
        toast("Lien Bédéthèque oublié"); route(); return;
      }
    } catch (e) {
      toast(`${ICON.warn} ${esc(e.message)}`, { sticky: true });
      route();
    }
  }
  main.addEventListener("submit", async e => {
    const form = e.target.closest("form[data-bdt]");
    if (!form) return;
    e.preventDefault();
    const folderId = +form.dataset.folder;
    if (form.dataset.bdt === "url") {
      const url = form.elements.url.value.trim();
      if (!url) return;
      bdtAction("url-submit", { dataset: { folder: folderId, url } });
      return;
    }
    const q = form.elements.q.value.trim();
    if (q.length < 2) return;
    const res = $("#bdt-results");
    res.innerHTML = `<div class="spinner" style="margin:8px 0"></div>`;
    try {
      const cands = await api(`/api/bdt/search?q=${encodeURIComponent(q)}`);
      res.innerHTML = cands.length ? `<div class="cands">${cands.map(c => `<button type="button" class="cand" data-bdt="pick" data-folder="${folderId}" data-url="${esc(c.url)}">
          <b>${esc(c.name)}</b><small>${[c.genre, c.tomes ? plural(c.tomes, "tome", "tomes") : "", c.exact ? "correspondance exacte" : ""].filter(Boolean).join(" · ")}</small></button>`).join("")}</div>`
        : `<p class="muted">Aucune série trouvée pour « ${esc(q)} ».</p>`;
    } catch (err) { res.innerHTML = `<p class="error">${esc(err.message)}</p>`; }
  });

  let summariesTimer = null;
  async function pollSummaries() {
    clearTimeout(summariesTimer);
    try {
      const j = await api("/api/bdt/summaries");
      if (j.running) {
        toast(`<div class="spinner"></div> Résumés de « ${esc(j.folder || "")} » : ${j.done} / ${j.total} <button class="btn mini" type="button" data-summaries="stop">Arrêter</button>`, { sticky: true });
        summariesTimer = setTimeout(pollSummaries, 1500);
      } else {
        toast(j.total ? `Résumés lus : ${j.done} / ${j.total}${j.errors.length ? ` · ${plural(j.errors.length, "erreur", "erreurs")} (${esc(j.errors[0])})` : ""}` : "Tous les résumés de ce dossier sont déjà connus.");
        if (location.hash.startsWith("#/f/")) route();
      }
    } catch (_) { /* ignore */ }
  }
  toastEl.addEventListener("click", e => {
    if (e.target.closest("[data-summaries]")) api("/api/bdt/summaries", { method: "DELETE" }).then(() => toast("Arrêt demandé")).catch(() => {});
  });

  // ================================================================ page Collection
  let batchTimer = null;
  async function viewCollection(filter) {
    setCrumbs([{ id: 0, name: "Accueil" }], "Collection");
    document.title = "Collection — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const [col, st] = await Promise.all([api("/api/bdt/collection"), api("/api/bdt/status")]);
    filter = filter || "all";
    const rows = col.series.map(r => Object.assign({}, r, { pct: r.total ? Math.round((r.present / r.total) * 100) : 0, full: r.total && r.present >= r.total }));
    const shown = rows.filter(r => filter === "all" || (filter === "incomplete" && !r.full) || (filter === "complete" && r.full) || (filter === "ongoing" && /cours/i.test(r.status || "")));
    const totals = { series: rows.length, full: rows.filter(r => r.full).length, missing: rows.reduce((n, r) => n + Math.max(0, (r.total || 0) - (r.present || 0)), 0) };
    const job = st.job;
    const tab = (key, label) => `<a class="tab ${filter === key ? "on" : ""}" href="#/collection/${key}">${label}</a>`;
    main.innerHTML = `<h1>Collection <small class="muted h1sub">${plural(totals.series, "série liée à Bédéthèque", "séries liées à Bédéthèque")} · ${totals.full} complètes · ${plural(totals.missing, "tome manquant", "tomes manquants")}</small></h1>
      <div class="bdt-panel" id="batch-panel">${batchHtml(job, col.unlinked.length, st)}</div>
      <div class="tabs">${tab("all", "Toutes")}${tab("incomplete", "Incomplètes")}${tab("complete", "Complètes")}${tab("ongoing", "En cours de parution")}</div>
      ${shown.length ? `<table class="coltable"><thead><tr><th>Dossier</th><th>Série Bédéthèque</th><th>Statut</th><th>Tomes</th><th></th></tr></thead><tbody>
        ${shown.map(r => `<tr><td><a href="#/f/${r.folder_id}">${esc(r.folder_name)}</a></td><td><a class="ext" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || "")}</a>${r.score != null && r.score < 0.9 && !r.manual ? ` <span class="warnlabel">à vérifier</span>` : ""}</td>
          <td>${esc(r.status || "")}${r.years ? ` <small class="muted">${esc(r.years)}</small>` : ""}</td>
          <td class="num ${r.full ? "ok" : ""}">${r.present ?? "?"} / ${r.total ?? "?"}<div class="pbar"><i style="width:${r.pct}%"></i></div></td>
          <td>${r.full ? "✓" : plural(Math.max(0, (r.total || 0) - (r.present || 0)), "manquant", "manquants")}</td></tr>`).join("")}
      </tbody></table>` : `<div class="empty">${rows.length ? "Rien dans cette catégorie." : "Aucune série analysée pour l'instant. Ouvrez un dossier d'albums et cliquez « Analyser », ou lancez l'analyse de tous les dossiers ci-dessus."}</div>`}
      ${col.unlinked.length ? `<details class="unlinked"><summary>${plural(col.unlinked.length, "dossier pas encore analysé", "dossiers pas encore analysés")}</summary><div class="chips">${col.unlinked.slice(0, 400).map(u => `<a class="chip gray" href="#/f/${u.id}">${esc(u.name)} <small>${u.albums}</small></a>`).join(" ")}</div></details>` : ""}`;
    if (job.running) pollBatch();
  }
  function batchHtml(job, unlinkedCount, st) {
    if (!st.enabled) return `<div class="bdt-row"><span class="bdt-logo">BD</span><span>Les requêtes vers Bédéthèque sont désactivées dans les <a href="#/settings">réglages</a>.</span></div>`;
    if (job.running) {
      return `<div class="bdt-row"><div class="spinner" style="margin:0"></div><div class="bdt-main">Analyse en cours : ${job.done} / ${job.total}${job.current ? ` — <i>${esc(job.current)}</i>` : ""}
        <div class="pbar"><i style="width:${job.total ? Math.round(job.done / job.total * 100) : 0}%"></i></div>
        <small class="muted">${job.linked} liées · ${job.ambiguous} à choisir · ${job.not_found} introuvables · ${job.errors.length} erreurs</small></div>
        <button class="btn" type="button" data-batch="stop">Arrêter</button></div>`;
    }
    const last = job.total ? `<small class="muted">Dernière analyse groupée : ${job.done}/${job.total} dossiers — ${job.linked} liées, ${job.ambiguous} à choisir à la main, ${job.not_found} introuvables${job.errors.length ? `, ${job.errors.length} erreurs (${esc(job.errors[0].error)})` : ""}.</small>` : "";
    return `<div class="bdt-row"><span class="bdt-logo">BD</span><div class="bdt-main">${unlinkedCount ? `${plural(unlinkedCount, "dossier d'albums n'est pas encore comparé", "dossiers d'albums ne sont pas encore comparés")} à Bédéthèque. L'analyse groupée fait une requête toutes les ${st.interval} s (environ ${Math.ceil(unlinkedCount * st.interval * 2 / 60)} min) et s'arrête quand vous voulez.` : "Tous les dossiers d'albums ont été comparés à Bédéthèque."}${last ? "<br>" + last : ""}</div>
      ${unlinkedCount ? `<button class="btn primary" type="button" data-batch="start">Analyser les ${unlinkedCount} dossiers</button>` : ""}</div>`;
  }
  async function pollBatch() {
    clearTimeout(batchTimer);
    try {
      const [job, st, col] = await Promise.all([api("/api/bdt/batch"), api("/api/bdt/status"), api("/api/bdt/collection")]);
      const p = $("#batch-panel");
      if (p) p.innerHTML = batchHtml(job, col.unlinked.length, st);
      if (job.running) batchTimer = setTimeout(pollBatch, 2000);
      else if (location.hash.startsWith("#/collection")) route();
    } catch (_) { /* ignore */ }
  }
  async function batchAction(action) {
    try {
      if (action === "start") { await api("/api/bdt/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); pollBatch(); }
      else if (action === "stop") { await api("/api/bdt/batch", { method: "DELETE" }); toast("Arrêt demandé (après le dossier en cours)"); }
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); }
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

  // ================================================================ page Réglages
  function field(label, control, help = "") {
    return `<div class="field"><div class="flabel"><span>${label}</span>${help ? `<small>${help}</small>` : ""}</div>${control}</div>`;
  }
  const sel = (scope, key, opts, val) => `<select data-scope="${scope}" data-key="${key}">${opts.map(([v, l]) => `<option value="${v}" ${String(v) === String(val) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const chk = (scope, key, val) => `<label class="switch"><input type="checkbox" data-scope="${scope}" data-key="${key}" ${val ? "checked" : ""}><i></i></label>`;
  const num = (scope, key, val, min, max, step = 1) => `<input type="number" data-scope="${scope}" data-key="${key}" value="${val}" min="${min}" max="${max}" step="${step}">`;

  async function viewSettings() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Réglages");
    document.title = "Réglages — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    await loadSettings();
    let cache = {}, stats = {};
    try { [cache, stats] = await Promise.all([api("/api/cache"), api("/api/stats")]); } catch (_) { /* ignore */ }
    const p = settings.profile, g = settings.global;
    main.innerHTML = `<h1>Réglages</h1>
    <div class="settings">
      <section>
        <h2>Bibliothèque</h2>
        ${field("Taille des vignettes", sel("p", "thumb_size", [["s", "Petites"], ["m", "Moyennes"], ["l", "Grandes"], ["xl", "Très grandes"]], p.thumb_size))}
        ${field("Zoom au survol", sel("p", "hover_zoom", [["none", "Aucun"], ["light", "Léger"], ["strong", "Prononcé"]], p.hover_zoom))}
        ${field("Vignettes par page", sel("p", "per_page", [[24, "24"], [48, "48"], [96, "96"], [192, "192"], [0, "Toutes (pas de pages)"]], p.per_page), "Au-delà, la liste est découpée en pages.")}
        ${field("Accès par lettre", sel("p", "letters", [["auto", "Automatique (dossiers de 40 entrées et plus)"], ["always", "Toujours"], ["never", "Jamais"]], p.letters))}
        ${field("Position des lettres", sel("p", "letters_side", [["right", "Sur le côté droit"], ["left", "Sur le côté gauche"], ["top", "En haut de la liste"]], p.letters_side))}
        ${field("Taille des lettres", sel("p", "letters_size", [["large", "Grandes"], ["normal", "Normales"]], p.letters_size))}
        ${field("Onglets (À lire, Favoris, Listes…)", sel("p", "tabs_side", [["left", "Colonne à gauche"], ["top", "Rangée en haut"]], p.tabs_side), "Sur mobile, toujours en haut.")}
        ${field("Style des pochettes", sel("p", "cover_style", [["book", "Livre (dos, tranche, bordure colorée, piles pour les séries)"], ["glow", "Halo coloré"], ["flat", "Simple"]], p.cover_style), "La couleur vient de la couverture elle-même.")}
        ${field("Tri", sel("p", "sort", [["natural", "Alphabétique naturel (T2 avant T10)"], ["recent", "Ajouts récents d'abord"], ["unread", "Non lus d'abord"]], p.sort))}
        ${field("Masquer les albums lus", chk("p", "hide_read", p.hide_read))}
        ${field("Nombre de pages sur les cartes", chk("p", "show_pages", p.show_pages))}
        ${field("« Reprendre la lecture » sur l'accueil", chk("p", "show_continue", p.show_continue))}
        ${field("« Ajouts récents » sur l'accueil", chk("p", "show_recent", p.show_recent))}
        ${field("Nombre d'ajouts récents", num("p", "recent_count", p.recent_count, 6, 60, 6))}
        ${field("Thème", sel("p", "theme", [["dark", "Sombre"], ["light", "Clair"], ["auto", "Comme l'appareil"]], p.theme))}
        ${field("Rouvrir le dernier dossier au démarrage", chk("p", "remember_folder", p.remember_folder))}
      </section>
      <section>
        <h2>Lecteur</h2>
        ${field("Affichage par défaut", sel("p", "reader_mode", [["single", "Une page"], ["double", "Deux pages (double page)"], ["scroll", "Défilement continu"]], p.reader_mode), "Touche D dans le lecteur pour changer.")}
        ${field("Double page : couverture seule", chk("p", "reader_cover_alone", p.reader_cover_alone), "Les planches larges (paysage) sont toujours affichées seules.")}
        ${field("Défilement continu : largeur", sel("p", "reader_scroll_width", [[100, "Toute la largeur"], [80, "80 %"], [60, "60 %"], [45, "45 %"]], p.reader_scroll_width))}
        ${field("Ajustement par défaut (une page)", sel("p", "reader_fit", [["page", "Page entière"], ["width", "Pleine largeur"], ["original", "Taille d'origine"]], p.reader_fit))}
        ${field("Sens manga par défaut", chk("p", "reader_manga", p.reader_manga), "Lecture de droite à gauche.")}
        ${field("Mémoriser l'ajustement et le sens par album", chk("p", "reader_remember_album", p.reader_remember_album))}
        ${field("Fond", sel("p", "reader_bg", [["black", "Noir"], ["dark", "Gris foncé"], ["gray", "Gris"], ["white", "Blanc"]], p.reader_bg))}
        ${field("Qualité des pages", sel("p", "reader_quality", [["normal", "Adaptée à l'écran"], ["high", "Haute (1,5× l'écran)"], ["original", "Fichier d'origine (le plus net, le plus lourd)"]], p.reader_quality))}
        ${field("Pages préchargées", num("p", "reader_preload", p.reader_preload, 0, 10))}
        ${field("Délai avant de cacher les barres (s)", num("p", "reader_bars_delay", p.reader_bars_delay, 0.5, 10, 0.5))}
        ${field("Zones de tape sur les bords", chk("p", "reader_tap_zones", p.reader_tap_zones), "Un clic / une tape sur le bord gauche ou droit tourne la page.")}
        ${field("Molette = tourner la page (mode page entière)", chk("p", "reader_wheel", p.reader_wheel))}
        ${field("Mode nuit : assombrir les pages", sel("p", "reader_night", [[0, "Non"], [15, "Un peu (15 %)"], [30, "Moyen (30 %)"], [50, "Beaucoup (50 %)"]], p.reader_night))}
      </section>
      <section>
        <h2>Images (serveur)</h2>
        ${field("Qualité JPEG", sel("g", "quality", [["eco", "Économique (80, plus rapide sur mobile)"], ["normal", "Normale (90, couleurs intactes)"], ["max", "Maximale (95)"]], g.quality), "Les pages déjà en cache gardent leur ancienne qualité jusqu'à ce qu'on vide le cache.")}
        ${field("Renforcer la netteté après réduction", chk("g", "sharpen", g.sharpen))}
        ${field("Largeur des couvertures (px)", sel("g", "cover_width", [[400, "400"], [600, "600"], [800, "800"], [1000, "1000"]], g.cover_width), "Après changement, utilisez « Régénérer les couvertures ».")}
        ${field("Album considéré lu", sel("g", "read_threshold", [[1, "À la dernière page"], [0.95, "À partir de 95 %"], [0.9, "À partir de 90 %"], [0.8, "À partir de 80 %"]], g.read_threshold))}
      </section>
      <section>
        <h2>Scan et cache (serveur)</h2>
        ${field("Rescan automatique", sel("g", "scan_interval_hours", [[0, "Jamais (bouton ↻ seulement)"], [1, "Toutes les heures"], [6, "Toutes les 6 h"], [12, "Toutes les 12 h"], [24, "Une fois par jour"], [168, "Une fois par semaine"]], g.scan_interval_hours))}
        ${field("Couvertures générées après un scan", chk("g", "preload_covers", g.preload_covers))}
        ${field("Couvertures générées en parallèle", num("g", "preload_threads", g.preload_threads, 1, 8), "Baisser à 1 sur un petit serveur.")}
        ${field("Taille maximale du cache des pages (Go)", num("g", "cache_max_gb", g.cache_max_gb, 0, 1000), "0 = sans limite. Les pages les moins récentes sont supprimées en premier.")}
        <div class="field"><div class="flabel"><span>Cache actuel</span><small id="cache-size">${cache.total != null ? `pages ${fmtSize(cache.pages)} · couvertures ${fmtSize(cache.covers)} · archives décompressées ${fmtSize(cache.extract)}` : "—"}</small></div>
          <div class="actions"><button class="btn" type="button" data-action="scan">↻ Scanner maintenant</button>
          <button class="btn" type="button" data-action="clear-cache">Vider le cache des pages</button>
          <button class="btn" type="button" data-action="rebuild-covers">Régénérer les couvertures</button></div></div>
      </section>
      <section>
        <h2>Profils et accès</h2>
        ${field("Demander « qui lit ? » à l'ouverture", chk("g", "require_profile", g.require_profile), "Chaque profil a sa progression et ses réglages d'affichage.")}
        <div class="field"><div class="flabel"><span>Profils</span><small>Un code PIN par profil est facultatif.</small></div>
          <div class="plist">${(settings.meta.profiles || []).map(p => `<span class="prow"><span class="pavatar small">${esc(p.avatar || initial(p.name))}</span> ${esc(p.name)}${p.has_pin ? " 🔒" : ""}
            <button class="btn mini" type="button" data-action="profile-edit" data-id="${p.id}" data-name="${esc(p.name)}">Modifier</button>${p.id === 1 ? "" : `<button class="btn mini" type="button" data-action="profile-delete" data-id="${p.id}" data-name="${esc(p.name)}">Supprimer</button>`}</span>`).join("")}
            <button class="btn mini" type="button" data-action="profile-add">+ Ajouter un profil</button></div></div>
        <div class="field"><div class="flabel"><span>Code d'accès à Bulle</span><small>${g.access_pin_set ? "Un code est demandé à l'ouverture (et pour le flux OPDS : mot de passe = ce code)." : "Aucun code : tout le réseau local peut ouvrir Bulle."}</small></div>
          <div class="actions"><button class="btn" type="button" data-action="access-pin-set">${g.access_pin_set ? "Changer le code" : "Définir un code"}</button>${g.access_pin_set ? `<button class="btn" type="button" data-action="access-pin-clear">Supprimer le code</button>` : ""}</div></div>
        ${field("Flux OPDS pour les applis mobiles", chk("g", "opds_enabled", g.opds_enabled), `Adresse à donner à l'appli (Panels, Chunky, Moon+, Mihon…) : <code>${esc(location.origin)}/opds</code>`)}
      </section>
      <section>
        <h2>Bédéthèque</h2>
        ${field("Autoriser les requêtes vers bedetheque.com", chk("g", "bdt_enabled", g.bdt_enabled), "Uniquement quand vous cliquez « Analyser » (ou l'analyse groupée de la page Collection).")}
        ${field("Délai entre deux requêtes (s)", num("g", "bdt_interval", g.bdt_interval, 1, 30, 0.5), "Par politesse envers le site ; 2,5 s par défaut.")}
        ${field("Afficher les tomes manquants dans les dossiers", chk("p", "bdt_ghosts", p.bdt_ghosts), "Cartes grisées à leur place dans la série (tri naturel).")}
        ${field("Noms des albums d'après Bédéthèque", chk("p", "bdt_titles", p.bdt_titles), "« T3 · Titre officiel » au lieu du nom du fichier, quand il est connu. Les fichiers ne sont jamais renommés.")}
        ${field("Résumé lu à l'ouverture d'une fiche", chk("g", "bdt_auto_summary", g.bdt_auto_summary), "Une requête vers la fiche de l'album, une seule fois ; le bouton « Résumés » d'une série les lit tous en tâche de fond.")}
        <p class="muted">Rien n'est jamais écrit dans vos fichiers : les informations Bédéthèque restent dans la base de Bulle. <a href="#/collection">Voir la collection</a>.</p>
      </section>
      <section>
        <h2>À propos</h2>
        <p class="muted">Bulle ${esc(settings.meta.version || "")} · ${plural(stats.albums || 0, "album", "albums")} dans ${plural(stats.folders || 0, "dossier", "dossiers")} (${fmtSize(stats.size || 0)}) · dernier scan : ${fmtDate(stats.last_scan)}<br>
        Dossier des BD : <code>${esc(settings.meta.library_root || "")}</code> · <a href="https://github.com/kermess14/bulle" target="_blank" rel="noopener">github.com/kermess14/bulle</a></p>
        <p><button class="btn" type="button" data-action="reset-profile">Réglages d'affichage par défaut</button></p>
      </section>
    </div>`;
  }

  main.addEventListener("change", e => {
    const el = e.target.closest("[data-key]");
    if (!el) return;
    let val = el.type === "checkbox" ? el.checked : el.value;
    if (el.type === "number" || (el.tagName === "SELECT" && /^-?\d+(\.\d+)?$/.test(val))) val = Number(val);
    if (el.dataset.scope === "g") saveSettings(null, { [el.dataset.key]: val });
    else saveSettings({ [el.dataset.key]: val }, null);
  });

  async function settingsAction(action, btn) {
    btn.disabled = true;
    try {
      if (action === "scan") { await fetch("/api/scan", { method: "POST" }); pollScan(true); }
      else if (action === "clear-cache") {
        const r = await api("/api/cache/clear", { method: "POST" });
        toast(`Cache des pages vidé (${fmtSize(r.cache.total)} restants : couvertures)`);
        const el = $("#cache-size"); if (el) el.textContent = `pages ${fmtSize(r.cache.pages)} · couvertures ${fmtSize(r.cache.covers)} · archives décompressées ${fmtSize(r.cache.extract)}`;
      } else if (action === "rebuild-covers") {
        if (!confirm("Régénérer toutes les couvertures ? Cela peut prendre un moment sur une grande bibliothèque (elles réapparaissent au fur et à mesure).")) return;
        const r = await fetch("/api/covers/rebuild", { method: "POST" });
        if (r.status === 409) toast("Un scan est déjà en cours, réessayez après.");
        else pollScan(true);
      } else if (action === "profile-add") {
        const name = prompt("Prénom du nouveau profil :"); if (!name) return;
        const pin = prompt("Code PIN (laisser vide pour aucun) :") || "";
        await api("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, pin }) });
        await loadSettings(); updateProfileButton(); route();
      } else if (action === "profile-edit") {
        const name = prompt("Nom du profil :", btn.dataset.name); if (name === null) return;
        const pin = prompt("Nouveau code PIN (vide = aucun code) :"); if (pin === null) return;
        await putJson(`/api/profiles/${btn.dataset.id}`, { name, pin });
        await loadSettings(); updateProfileButton(); route();
      } else if (action === "profile-delete") {
        if (!confirm(`Supprimer le profil « ${btn.dataset.name} » et sa progression de lecture ?`)) return;
        await api(`/api/profiles/${btn.dataset.id}`, { method: "DELETE" });
        await loadSettings(); updateProfileButton(); route();
      } else if (action === "access-pin-set") {
        const pin = prompt("Code d'accès (chiffres ou mot de passe) :"); if (!pin) return;
        await putJson("/api/settings", { global: { access_pin: pin } }); toast("Code d'accès enregistré"); route();
      } else if (action === "access-pin-clear") {
        if (!confirm("Supprimer le code d'accès ?")) return;
        await putJson("/api/settings", { global: { access_pin: "" } }); toast("Code d'accès supprimé"); route();
      } else if (action === "list-new") {
        const name = prompt("Nom de la nouvelle liste :"); if (!name) return;
        await api("/api/lists", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
        listsCache = null; renderSidebar(); route();
      } else if (action === "list-rename") {
        const name = prompt("Nouveau nom :", btn.dataset.name); if (!name) return;
        await putJson(`/api/lists/${btn.dataset.id}`, { name }); listsCache = null; renderSidebar(); route();
      } else if (action === "list-delete") {
        if (!confirm(`Supprimer la liste « ${btn.dataset.name} » ? (les albums ne sont pas touchés)`)) return;
        await api(`/api/lists/${btn.dataset.id}`, { method: "DELETE" }); listsCache = null; renderSidebar(); location.hash = "#/lists";
      } else if (action === "reset-profile") {
        const patch = {}; for (const k of Object.keys(PROFILE_DEFAULTS)) patch[k] = null;
        await putJson("/api/settings", { profile: patch });
        settings.profile = Object.assign({}, PROFILE_DEFAULTS);
        try { localStorage.setItem("bulle:profile", JSON.stringify(settings.profile)); } catch (_) { /* ignore */ }
        applyAppearance(); toast("Réglages d'affichage remis par défaut"); route();
      }
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); }
    finally { btn.disabled = false; }
  }

  // ================================================================ fiche album
  async function openInfo(id) {
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop"><div class="sheet"><div class="empty"><div class="spinner"></div></div></div></div>`;
    let it;
    try { it = await api(`/api/item/${id}`); } catch (e) { modal.innerHTML = `<div class="backdrop"><div class="sheet"><div class="empty">${esc(e.message)}</div></div></div>`; return; }
    const p = it.progress;
    const pct = p && it.pages ? Math.round(((p.page + 1) / it.pages) * 100) : 0;
    const folder = it.breadcrumb.map(b => b.name).slice(1).join(" › ");
    const parent = it.breadcrumb.length ? it.breadcrumb[it.breadcrumb.length - 1] : null;
    modal.innerHTML = `<div class="backdrop"><div class="sheet" role="dialog" aria-modal="true" aria-label="Fiche de l'album">
      <button class="iconbtn close" type="button" data-close title="Fermer">${ICON.close}</button>
      ${coverHtml(it, "", 220)}
      <div>
        <h3>${esc(it.name)}</h3>
        <div class="path">${esc(folder || "Racine")}</div>
        ${it.error ? `<p class="error">${ICON.warn} ${esc(it.error)}</p>` : ""}
        <dl>
          <dt>Format</dt><dd>${esc(formatLabel(it))}</dd>
          <dt>Taille</dt><dd>${fmtSize(it.size)}</dd>
          <dt>Pages</dt><dd>${it.pages ?? "?"}</dd>
          <dt>Progression</dt><dd>${p ? (p.completed ? "Lu ✓" : `Page ${p.page + 1} sur ${it.pages ?? "?"} — ${pct} %`) : "Non lu"}
            ${p && !p.completed && it.pages ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}</dd>
          <dt>Fichier</dt><dd class="path">${esc(it.path.split("/").pop())}</dd>
          ${it.meta ? `<dt>Bédéthèque</dt><dd>${it.meta.number != null ? `<b>Tome ${it.meta.number}</b> · ` : ""}${esc(it.meta.title || "")}${it.meta.year ? ` (${it.meta.year})` : ""} <a class="ext" href="${esc(it.meta.url)}" target="_blank" rel="noopener">↗</a></dd>` : (it.series ? `<dt>Bédéthèque</dt><dd class="muted">tome non reconnu dans « ${esc(it.series.title)} »</dd>` : "")}
          ${it.meta && it.meta.writers.length ? `<dt>Scénario</dt><dd>${esc(it.meta.writers.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.pencillers.length ? `<dt>Dessin</dt><dd>${esc(it.meta.pencillers.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.colorists.length ? `<dt>Couleurs</dt><dd>${esc(it.meta.colorists.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.publisher ? `<dt>Éditeur</dt><dd>${esc(it.meta.publisher)}${it.meta.collection ? ` · ${esc(it.meta.collection)}` : ""}${it.meta.date ? ` · ${esc(it.meta.date)}` : ""}</dd>` : ""}
          ${it.meta && it.meta.isbn ? `<dt>ISBN</dt><dd>${esc(it.meta.isbn)}${it.meta.pages ? ` · ${it.meta.pages} planches` : ""}</dd>` : ""}
        </dl>
        <div class="summary-slot" id="sheet-summary" data-id="${it.id}"></div>
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
        <div class="lists-row" id="sheet-lists" data-id="${it.id}"></div>
      </div></div></div>`;
    renderSheetLists($("#sheet-lists"), it.id, it.lists || []);
    renderSummary($("#sheet-summary"), it);
  }
  function summaryHtml(text, url) {
    if (!text) return `<p class="summary muted">Pas de résumé sur Bédéthèque pour cet album.</p>`;
    const cut = /[.…]$/.test(text) ? text : text + "…";
    return `<p class="summary">${esc(cut)} ${url ? `<a class="ext" href="${esc(url)}" target="_blank" rel="noopener">lire la suite sur Bédéthèque ↗</a>` : ""}</p>`;
  }
  async function renderSummary(slot, it) {
    if (!slot || !it.meta || !it.meta.url) return;
    if (it.meta.summary_at) { slot.innerHTML = summaryHtml(it.meta.summary, it.meta.url); return; }
    if (!settings.global.bdt_enabled || settings.global.bdt_auto_summary === false) {
      slot.innerHTML = `<p class="summary muted"><button class="btn mini" type="button" data-summary="${it.id}">Lire le résumé sur Bédéthèque</button></p>`;
      return;
    }
    fetchSummary(slot, it);
  }
  async function fetchSummary(slot, it) {
    slot.innerHTML = `<p class="summary muted"><span class="spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;margin:0 6px -2px 0"></span>Résumé en cours de lecture sur Bédéthèque…</p>`;
    try {
      const r = await api(`/api/bdt/album/${it.id}/summary`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (+slot.dataset.id === +it.id) slot.innerHTML = summaryHtml(r.summary, it.meta.url);
    } catch (e) {
      if (+slot.dataset.id === +it.id) slot.innerHTML = `<p class="summary muted">Résumé indisponible : ${esc(e.message)}</p>`;
    }
  }
  modal.addEventListener("click", e => {
    const b = e.target.closest("[data-summary]");
    if (!b) return;
    e.preventDefault();
    const slot = $("#sheet-summary");
    if (slot) fetchSummary(slot, { id: +b.dataset.summary, meta: { url: "" } });
  });
  const closeModal = () => { modal.hidden = true; modal.innerHTML = ""; };

  // ================================================================ listes, favoris
  let listsCache = null;
  async function getLists(force) {
    if (!listsCache || force) listsCache = await api("/api/lists");
    return listsCache;
  }
  async function renderSheetLists(container, nodeId, membership) {
    const lists = await getLists();
    const favList = lists.find(l => l.kind === "favorites");
    const isFav = favList && membership.includes(favList.id);
    const others = lists.filter(l => l.kind !== "favorites");
    container.innerHTML = `<button class="btn ${isFav ? "fav-on" : ""}" type="button" data-fav="${nodeId}">${isFav ? "★ Favori" : "☆ Favori"}</button>
      <select data-listsel="${nodeId}" aria-label="Ajouter à une liste"><option value="">Ajouter à une liste…</option>
        ${others.map(l => `<option value="${l.id}">${membership.includes(l.id) ? "✓ " : ""}${esc(l.name)}${membership.includes(l.id) ? " (retirer)" : ""}</option>`).join("")}
        <option value="new">+ Nouvelle liste…</option></select>`;
  }
  async function toggleFav(nodeId, btn) {
    try {
      const r = await api("/api/favorites/toggle", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId }) });
      if (btn) { btn.classList.toggle("fav-on", r.fav); btn.textContent = r.fav ? "★ Favori" : "☆ Favori"; }
      toast(r.fav ? "Ajouté aux favoris ★" : "Retiré des favoris");
      listsCache = null;
      renderSidebar();
      if (!location.hash.startsWith("#/f/") || btn && btn.closest(".sheet")) { /* la grille se rafraîchit à la prochaine navigation */ }
      if (modal.hidden) route();
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); }
  }
  async function addToList(nodeId, listId, selectEl) {
    try {
      if (listId === "new") {
        const name = prompt("Nom de la nouvelle liste :"); if (!name) { if (selectEl) selectEl.value = ""; return; }
        const l = await api("/api/lists", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
        listId = l.id; listsCache = null;
      }
      const lists = await getLists();
      const it = await api(`/api/item/${nodeId}`).catch(() => null);
      const membership = it ? it.lists : [];
      let r;
      if (membership.includes(+listId)) { r = await api(`/api/lists/${listId}/items/${nodeId}`, { method: "DELETE" }); toast("Retiré de la liste"); }
      else { r = await api(`/api/lists/${listId}/items`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId }) }); toast(`Ajouté à « ${esc((lists.find(l => l.id === +listId) || {}).name || "la liste")} »`); }
      listsCache = null;
      renderSidebar();
      const box = $("#sheet-lists"); if (box && +box.dataset.id === +nodeId) renderSheetLists(box, nodeId, r.lists);
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); }
  }
  async function pickListFor(nodeId) {
    const lists = (await getLists()).filter(l => l.kind !== "favorites");
    const choice = prompt("Ajouter à quelle liste ?\n" + lists.map((l, i) => `${i + 1}. ${l.name}`).join("\n") + `\n${lists.length + 1}. Nouvelle liste…`, "1");
    if (!choice) return;
    const n = parseInt(choice, 10);
    if (n >= 1 && n <= lists.length) addToList(nodeId, lists[n - 1].id);
    else if (n === lists.length + 1) addToList(nodeId, "new");
  }
  document.addEventListener("click", e => {
    const fav = e.target.closest("[data-fav]");
    if (fav) { e.preventDefault(); toggleFav(+fav.dataset.fav, fav); return; }
    const add = e.target.closest("[data-addlist]");
    if (add) { e.preventDefault(); pickListFor(+add.dataset.addlist); }
  });
  document.addEventListener("change", e => {
    const sel = e.target.closest("[data-listsel]");
    if (sel && sel.value) { addToList(+sel.dataset.listsel, sel.value, sel); sel.value = ""; }
  });

  // ------------------------------------------------ barre latérale : listes et compteurs
  async function renderSidebar() {
    let lists = [];
    try { lists = await getLists(); } catch (_) { return; }
    for (const el of document.querySelectorAll("#maintabs [data-count]")) {
      const l = lists.find(x => x.kind === el.dataset.count);
      el.textContent = l && l.count ? String(l.count) : "";
    }
    const box = $("#side-lists");
    if (box) {
      box.innerHTML = lists.filter(l => l.kind === "custom").map(l => `<a class="sub" href="#/list/${l.id}" data-tab="list-${l.id}" data-drop="${l.id}" title="${esc(l.name)} — déposez ici un album ou une série">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16v13H4z"/><path d="M8 3v3M16 3v3M4 11h16"/></svg>
        <span class="lbl">${esc(l.name)}</span><span class="cnt">${l.count || ""}</span></a>`).join("");
    }
    markTab();
  }
  function markTab() {
    const h = location.hash || "#/";
    let m;
    const tab = (m = /^#\/list\/(\d+)/.exec(h)) ? "list-" + m[1] : h.startsWith("#/list/favorites") ? "favorites" : h.startsWith("#/list/readlater") ? "readlater" : h.startsWith("#/list") ? "lists" : h.startsWith("#/history") ? "history" : h.startsWith("#/collection") ? "collection" : h.startsWith("#/settings") ? "settings" : h.startsWith("#/s/") ? "" : "home";
    for (const a of document.querySelectorAll("#maintabs a")) a.classList.toggle("on", a.dataset.tab === tab);
  }

  // ------------------------------------------------ glisser-déposer un album ou une série sur une liste
  let dragId = null;
  main.addEventListener("dragstart", e => {
    const c = e.target.closest(".card[data-id]");
    if (!c || c.classList.contains("ghost")) return;
    dragId = +c.dataset.id;
    try { e.dataTransfer.setData("text/plain", String(dragId)); e.dataTransfer.effectAllowed = "copyLink"; } catch (_) { /* ignore */ }
    c.classList.add("dragging");
    document.body.classList.add("dragging");
  });
  document.addEventListener("dragend", () => {
    dragId = null;
    document.body.classList.remove("dragging");
    for (const el of document.querySelectorAll(".over, .card.dragging")) el.classList.remove("over", "dragging");
  });
  document.addEventListener("dragover", e => {
    const t = e.target.closest("[data-drop]");
    if (!t || dragId == null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    if (!t.classList.contains("over")) { for (const el of document.querySelectorAll(".over")) el.classList.remove("over"); t.classList.add("over"); }
  });
  document.addEventListener("dragleave", e => {
    const t = e.target.closest("[data-drop]");
    if (t && !t.contains(e.relatedTarget)) t.classList.remove("over");
  });
  document.addEventListener("drop", async e => {
    const t = e.target.closest("[data-drop]");
    if (!t) return;
    e.preventDefault();
    const id = dragId != null ? dragId : parseInt(e.dataTransfer.getData("text/plain"), 10);
    t.classList.remove("over");
    document.body.classList.remove("dragging");
    if (!id) return;
    dropOn(t.dataset.drop, id);
  });
  async function dropOn(target, nodeId) {
    try {
      const lists = await getLists();
      let list = null;
      if (target === "favorites" || target === "readlater") list = lists.find(l => l.kind === target);
      else if (target === "new") { addToList(nodeId, "new"); return; }
      else list = lists.find(l => l.id === +target);
      if (!list) throw new Error("Liste introuvable");
      await api(`/api/lists/${list.id}/items`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId }) });
      toast(list.kind === "favorites" ? "Ajouté aux favoris ★" : `Ajouté à « ${esc(list.name)} »`);
      listsCache = null;
      renderSidebar();
      if (list.kind === "favorites" || location.hash.startsWith("#/list")) route();
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); }
  }

  async function viewList(key) {
    const lists = await getLists(true);
    const l = /^\d+$/.test(key) ? lists.find(x => x.id === +key) : lists.find(x => x.kind === key);
    if (!l) { main.innerHTML = `<div class="empty">Liste introuvable.</div>`; return; }
    setCrumbs([{ id: 0, name: "Accueil" }], l.name);
    document.title = `${l.name} — Bulle`;
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const data = await api(`/api/lists/${l.id}`);
    const icon = l.kind === "favorites" ? "★" : l.kind === "readlater" ? "🔖" : "📚";
    const empty = l.kind === "favorites" ? "Aucun favori pour l'instant : le bouton ☆ se trouve dans la fiche d'un album (« i ») ou en haut d'une série."
      : l.kind === "readlater" ? "Rien à lire pour l'instant : « Ajouter à une liste » dans la fiche d'un album ou en haut d'une série."
        : "Liste vide : « Ajouter à une liste » dans la fiche d'un album ou en haut d'une série.";
    main.innerHTML = `<div class="listhead"><h1>${icon} ${esc(l.name)} <small class="muted h1sub">${plural(data.items.length, "élément", "éléments")}</small></h1>
      ${l.kind === "custom" ? `<button class="btn mini" type="button" data-action="list-rename" data-id="${l.id}" data-name="${esc(l.name)}">Renommer</button><button class="btn mini" type="button" data-action="list-delete" data-id="${l.id}" data-name="${esc(l.name)}">Supprimer</button>` : ""}</div>
      ${data.items.length ? `<div class="grid" id="grid">${data.items.map(it => card(it, { sub: it.folder }).replace("</a>", `<button class="remove" type="button" data-unlist="${l.id}" data-node="${it.id}" title="Retirer de la liste">×</button></a>`)).join("")}</div>` : `<div class="empty">${empty}</div>`}`;
  }
  async function viewLists() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Listes");
    document.title = "Listes — Bulle";
    const lists = await getLists(true);
    const icon = l => l.kind === "favorites" ? "★" : l.kind === "readlater" ? "🔖" : "📚";
    main.innerHTML = `<div class="listhead"><h1>Listes</h1><button class="btn" type="button" data-action="list-new">+ Nouvelle liste</button></div>
      <div class="listgrid">${lists.map(l => `<a class="listcard" href="#/list/${l.kind === "custom" ? l.id : l.kind}" data-drop="${l.kind === "custom" ? l.id : l.kind}"><span class="lic">${icon(l)}</span><span><b>${esc(l.name)}</b><small>${plural(l.count, "élément", "éléments")}</small></span></a>`).join("")}</div>
      <p class="muted" style="margin-top:16px">Les listes et les favoris sont propres à chaque profil. Ajoutez un album depuis sa fiche (« i »), une série depuis le haut de sa page, ou glissez-déposez une vignette sur une liste de la colonne de gauche.</p>`;
  }
  async function viewHistory() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Historique");
    document.title = "Historique — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const items = await api("/api/history");
    main.innerHTML = `<h1>Historique <small class="muted h1sub">${plural(items.length, "album lu", "albums lus")}, les plus récents d'abord</small></h1>
      ${items.length ? `<div class="grid" id="grid">${items.map(it => card(it, { sub: `${it.folder}${it.progress && it.progress.updated_at ? " · " + new Date(it.progress.updated_at * 1000).toLocaleDateString("fr-FR") : ""}` })).join("")}</div>` : `<div class="empty">Aucun album terminé pour l'instant.</div>`}`;
  }
  async function viewRandom() {
    try {
      const a = await api("/api/random");
      toast(`Au hasard : ${esc(a.name)}`);
      location.href = `/read/${a.id}?page=0`;
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); location.hash = "#/"; }
  }

  modal.addEventListener("click", async e => {
    const t = e.target.closest("[data-close], [data-read], [data-unread], .backdrop");
    if (!t) return;
    if (t.matches(".backdrop") && e.target !== t) return;
    if (t.dataset.read) {
      try { await putJson(`/api/progress/${t.dataset.read}`, { completed: true }); }
      catch (err) { toast(esc(err.message)); return; }
      closeModal(); route(); return;
    }
    if (t.dataset.unread) {
      await api(`/api/progress/${t.dataset.unread}`, { method: "DELETE" });
      closeModal(); route(); return;
    }
    closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !modal.hidden) { closeModal(); return; }
    if (e.target.matches("input, select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (view.pages > 1 && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
      const n = view.page + (e.key === "ArrowRight" ? 1 : -1);
      if (n >= 1 && n <= view.pages) goPage(n);
    }
  });

  // ================================================================ scan
  let scanTimer = null;
  async function pollScan(refreshWhenDone) {
    clearTimeout(scanTimer);
    let s;
    try { s = await api("/api/scan"); } catch (_) { return; }
    scanBtn.classList.toggle("spin", !!s.running);
    if (s.running) {
      const txt = s.phase === "covers" ? `Couvertures : ${s.covers_done}/${s.covers_total}` : `Scan en cours… ${s.albums} albums`;
      toast(`<div class="spinner"></div>${txt}`, { sticky: true });
      scanTimer = setTimeout(() => pollScan(true), 1500);
    } else if (refreshWhenDone) {
      if (s.error) toast(`${ICON.warn} Scan impossible : ${esc(s.error)}`);
      else toast(`Terminé : ${s.albums} albums${s.added ? `, ${s.added} nouveaux` : ""}${s.removed ? `, ${s.removed} retirés` : ""}`);
      if (!location.hash.startsWith("#/settings")) route();
      loadStats();
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

  // ================================================================ recherche
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

  // ================================================================ clics dans la page
  function goPage(n, scrollToLetter) {
    const base = view.id ? `#/f/${view.id}` : "#/";
    const target = n > 1 ? `${base}${base.endsWith("/") ? "" : "/"}p${n}` : base;
    pendingLetter = scrollToLetter || null;
    if (location.hash === target || (target === "#/" && (location.hash === "" || location.hash === "#"))) route();
    else location.hash = target;
  }
  let pendingLetter = null;
  function scrollToCard(el, smooth) {
    const y = el.getBoundingClientRect().top + window.scrollY - 56 - 52;
    window.scrollTo({ top: y, behavior: smooth ? "smooth" : "auto" });
  }
  main.addEventListener("click", e => {
    const info = e.target.closest("[data-info]");
    if (info) { e.preventDefault(); openInfo(info.dataset.info); return; }
    const action = e.target.closest("[data-action]");
    if (action) { settingsAction(action.dataset.action, action); return; }
    const unl = e.target.closest("[data-unlist]");
    if (unl) {
      e.preventDefault();
      api(`/api/lists/${unl.dataset.unlist}/items/${unl.dataset.node}`, { method: "DELETE" }).then(() => { listsCache = null; renderSidebar(); route(); }).catch(err => toast(esc(err.message)));
      return;
    }
    const bdtEl = e.target.closest("[data-bdt]:not(form)");
    if (bdtEl) { bdtAction(bdtEl.dataset.bdt, bdtEl); return; }
    const batch = e.target.closest("[data-batch]");
    if (batch) { batchAction(batch.dataset.batch); return; }
    const pg = e.target.closest(".pager .pg");
    if (pg) { goPage(+pg.dataset.page); return; }
    const letter = e.target.closest(".letters button");
    if (letter) {
      const L = letter.dataset.letter;
      const idx = view.list.findIndex(c => letterOf(c.name) === L);
      if (idx < 0) return;
      const per = +settings.profile.per_page || 0;
      const page = per ? Math.floor(idx / per) + 1 : 1;
      if (page !== view.page) { goPage(page, L); return; }
      const target = main.querySelector(`#grid .card[data-letter="${L}"]`);
      if (target) scrollToCard(target, true);
      return;
    }
    const album = e.target.closest("a.card.album");
    if (album && album.getAttribute("href") === "#") { e.preventDefault(); openInfo(album.dataset.id); }
  });

  // ================================================================ routeur (#/, #/p2, #/f/<id>, #/f/<id>/p2, #/s/<q>, #/settings)
  const scrollMemory = new Map();
  let currentKey = null;
  async function route() {
    if (currentKey !== null) scrollMemory.set(currentKey, window.scrollY);
    const h = location.hash || "#/";
    currentKey = h;
    markTab();
    try { if (!h.startsWith("#/s/")) localStorage.setItem("bulle:lastHash", h); } catch (_) { /* ignore */ }
    try {
      let m;
      if ((m = /^#\/f\/(\d+)(?:\/p(\d+))?/.exec(h))) {
        await viewFolder(+m[1], m[2] ? +m[2] : 1);
      } else if ((m = /^#\/s\/(.+)/.exec(h))) {
        const q = decodeURIComponent(m[1]);
        if (searchInput.value.trim() !== q) searchInput.value = q;
        await viewSearch(q);
      } else if (h.startsWith("#/settings")) {
        await viewSettings();
      } else if ((m = /^#\/collection(?:\/(\w+))?/.exec(h))) {
        await viewCollection(m[1]);
      } else if ((m = /^#\/list\/(\w+)/.exec(h))) {
        await viewList(m[1]);
      } else if (h.startsWith("#/lists")) {
        await viewLists();
      } else if (h.startsWith("#/history")) {
        await viewHistory();
      } else if (h.startsWith("#/random")) {
        await viewRandom(); return;
      } else {
        searchInput.value = "";
        m = /^#\/p(\d+)/.exec(h);
        await viewFolder(0, m ? +m[1] : 1);
      }
    } catch (e) {
      main.innerHTML = `<div class="empty"><strong>Oups.</strong><p>${esc(e.message)}</p><p><a class="btn" href="#/">Retour à l'accueil</a></p></div>`;
    }
    if (pendingLetter) {
      const L = pendingLetter; pendingLetter = null;
      requestAnimationFrame(() => { const t = main.querySelector(`#grid .card[data-letter="${L}"]`); if (t) scrollToCard(t, false); });
      return;
    }
    const y = scrollMemory.get(h);
    requestAnimationFrame(() => window.scrollTo(0, y || 0));
  }
  window.addEventListener("hashchange", route);
  window.addEventListener("pageshow", e => { if (e.persisted) route(); });

  (async () => {
    await loadSettings();
    updateProfileButton();
    if (settings.global.require_profile && settings.meta.profile_selected === false) openProfiles({ locked: true });
    try {
      if (settings.profile.remember_folder && !sessionStorage.getItem("bulle:visited") && (location.hash === "" || location.hash === "#/")) {
        const last = localStorage.getItem("bulle:lastHash");
        if (last && last.startsWith("#/f/")) location.replace(last);
      }
      sessionStorage.setItem("bulle:visited", "1");
    } catch (_) { /* ignore */ }
    route();
    loadStats();
    renderSidebar();
  })();
})();
