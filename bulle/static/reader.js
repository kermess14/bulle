/* Bulle — le lecteur : 1 page, 2 pages (double page), défilement continu ou case par case */
(() => {
  "use strict";
  const $ = sel => document.querySelector(sel);
  const body = document.body, stage = $("#stage"), loading = $("#loading");
  const single = $("#single"), img = $("#page"), spread = $("#spread"), imgA = $("#pageA"), imgB = $("#pageB"), scrollEl = $("#scroll");
  const slider = $("#slider"), countEl = $("#rcount"), nameEl = $("#rname"), folderEl = $("#rfolder");
  const modeBtn = $("#mode"), fitBtn = $("#fit"), mangaBtn = $("#manga"), fsBtn = $("#fs"), backBtn = $("#back"), endEl = $("#end");

  const id = +(/\/read\/(\d+)/.exec(location.pathname) || [])[1];
  const params = new URLSearchParams(location.search);
  const FITS = ["page", "width", "original"], MODES = ["single", "double", "scroll", "panels"];
  const FIT_LABEL = { page: "Page", width: "Largeur", original: "1:1" };
  const MODE_LABEL = { single: "1 page", double: "2 pages", scroll: "Défilement", panels: "Cases" };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- réglages (profil, serveur) + mémoire par album (navigateur)
  const DEFAULTS = {
    reader_fit: "page", reader_manga: false, reader_bg: "black", reader_preload: 3, reader_quality: "normal",
    reader_bars_delay: 2.5, reader_tap_zones: true, reader_wheel: true, reader_night: 0, reader_remember_album: true,
    reader_mode: "single", reader_cover_alone: true, reader_scroll_width: 100, reader_panels_full_first: false,
    reader_trim: false, reader_panels_wide: "split", reader_panels_margin: 3, reader_panels_dim: 100,
    reader_panels_speed: 0.55, reader_panels_join: true,
  };
  const prefs = Object.assign({}, DEFAULTS);
  // durée du glissement d'une case à l'autre (secondes ; 0 = instantané)
  const panelSpeed = () => { const v = +prefs.reader_panels_speed; return isFinite(v) ? Math.max(0, Math.min(2, v)) : 0.55; };
  function pick(o) { const out = {}; for (const k of Object.keys(DEFAULTS)) if (o && o[k] !== undefined) out[k] = o[k]; return out; }
  try { Object.assign(prefs, pick(JSON.parse(localStorage.getItem("bulle:profile") || "{}"))); } catch (_) { /* ignore */ }
  const store = {
    get(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (_) { return null; } },
    set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) { /* ignore */ } },
  };
  let fit = prefs.reader_fit, manga = !!prefs.reader_manga, mode = MODES.includes(prefs.reader_mode) ? prefs.reader_mode : "single";
  function applyPrefs() {
    body.classList.remove("bg-black", "bg-dark", "bg-gray", "bg-white");
    body.classList.add("bg-" + (prefs.reader_bg || "black"));
    body.style.setProperty("--night", String((+prefs.reader_night || 0) / 100));
    body.classList.toggle("night", (+prefs.reader_night || 0) > 0);
    body.style.setProperty("--dim", String(Math.max(0, Math.min(100, +prefs.reader_panels_dim || 0)) / 100));
    body.style.setProperty("--panel-speed", panelSpeed() + "s");
    body.style.setProperty("--scroll-w", String(Math.max(30, Math.min(100, +prefs.reader_scroll_width || 100))) + "%");
  }
  function loadAlbumMemory() {
    if (!prefs.reader_remember_album) return;
    const m = store.get(`bulle:reader:${id}`) || {};
    if (FITS.includes(m.fit)) fit = m.fit;
    if (MODES.includes(m.mode)) mode = m.mode;
    if (typeof m.manga === "boolean") manga = m.manga;
  }
  function saveAlbumMemory() { if (prefs.reader_remember_album) store.set(`bulle:reader:${id}`, { fit, manga, mode }); }
  applyPrefs();

  // ---------------------------------------------------------------- état
  let item = null, pages = 0, current = -1, shown = [], folderHref = "/";
  const aspects = {};            // n -> largeur/hauteur de la page (connue après chargement)
  const images = new Map();      // n -> Image (préchargées / chargées)
  let loadToken = 0, hideTimer = null, saveTimer = null, lastSavedPage = -1, navBusy = false, navSince = 0;
  const busy = () => navBusy && Date.now() - navSince < 4000;   // garde-fou : jamais bloqué plus de 4 s
  let panelIdx = -1;             // case par case : -1 = page entière, sinon index dans l'ordre de lecture
  const panelsCache = new Map(); // n -> {panels, rtl}

  function showMessage(title, text, actions = "") {
    const el = document.createElement("div");
    el.className = "rmsg";
    el.innerHTML = `<h2>${esc(title)}</h2><div>${esc(text)}</div>${actions}`;
    stage.appendChild(el);
    loading.hidden = true;
  }

  async function init() {
    if (!id) { showMessage("Album inconnu", "", `<a class="btn" href="/">Retour</a>`); return; }
    let r, s = null;
    try {
      [r, s] = await Promise.all([fetch(`/api/item/${id}`), fetch("/api/settings").then(x => x.ok ? x.json() : null).catch(() => null)]);
      item = await r.json();
    } catch (e) { showMessage("Impossible de charger l'album", String(e)); return; }
    if (r.status === 401) { showMessage("Connexion requise", "Ouvrez d'abord la bibliothèque pour vous connecter.", `<a class="btn" href="/">Ouvrir Bulle</a>`); return; }
    if (s && s.profile) { Object.assign(prefs, pick(s.profile)); fit = prefs.reader_fit; manga = !!prefs.reader_manga; mode = MODES.includes(prefs.reader_mode) ? prefs.reader_mode : "single"; applyPrefs(); }
    if (s && s.global && s.global.img_tag) imgTag = s.global.img_tag;
    loadAlbumMemory();
    if (!r.ok) { showMessage("Introuvable", item.error || "", `<a class="btn" href="/">Retour</a>`); return; }
    nameEl.textContent = item.meta && item.meta.title ? `${item.meta.number != null ? "T" + item.meta.number + " · " : ""}${item.meta.title}` : item.name;
    document.title = `${item.name} — Bulle`;
    const crumbs = item.breadcrumb || [];
    folderEl.textContent = crumbs.slice(1).map(c => c.name).join(" › ");
    const parent = crumbs[crumbs.length - 1];
    // dossier de l'album ; un album rangé à la racine ramène à l'accueil lui-même (pas à sa version « dossier »)
    folderHref = parent && parent.id && crumbs.length > 1 ? `/#/f/${parent.id}` : "/";
    backBtn.href = folderHref;
    if (item.error || !item.pages) {
      showMessage("Album illisible", item.error || "Aucune page", `<a class="btn" href="${folderHref}">Retour au dossier</a>`);
      return;
    }
    pages = item.pages;
    slider.max = pages;
    let start = 0;
    if (params.has("page")) start = +params.get("page") || 0;
    else if (item.progress && !item.progress.completed) start = item.progress.page || 0;
    applyFit(); applyMode(); applyManga(false);
    // iPad / iPhone : le plein écran de Safari ajoute une croix de fermeture impossible à masquer ; la vraie solution
    // est d'installer Bulle sur l'écran d'accueil (manifeste), donc pas de bouton plein écran sur iOS
    const isIOS = /iP(ad|hone|od)/.test(navigator.platform) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    if (!document.fullscreenEnabled || isIOS) fsBtn.hidden = true;
    go(Math.min(Math.max(0, start), pages - 1), { save: false });
    scheduleHide();
  }

  // ---------------------------------------------------------------- largeur d'image demandée au serveur
  const stepW = w => Math.min(3840, Math.ceil(w / 160) * 160);   // paliers de 160 px : URLs stables, caches réutilisés
  function wantedWidth(n) {
    if (prefs.reader_quality === "original" || (mode === "single" && fit === "original")) return 0;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const vw = stage.clientWidth || window.innerWidth, vh = stage.clientHeight || window.innerHeight;
    const asp = aspects[n] || 0.7;
    let css;
    if (mode === "scroll") css = vw * (Math.max(30, Math.min(100, +prefs.reader_scroll_width || 100)) / 100);
    else if (mode === "double") css = Math.min(vw / 2, vh * asp);
    else css = fit === "width" ? vw : Math.min(vw, vh * asp);
    const factor = mode === "panels" ? 2 : prefs.reader_quality === "high" ? 1.5 : 1;   // cases : nettes dès la première image, sans recharger
    return stepW(css * dpr * factor);
  }
  let imgTag = "";
  // marges blanches rognées (réglage) : pas en case par case, où les cases sont repérées sur la page entière
  const trimQ = () => (prefs.reader_trim && mode !== "panels" ? "&trim=1" : "");
  const pageUrl = n => `/api/page/${id}/${n}?w=${wantedWidth(n)}&v=${item.mtime}&t=${encodeURIComponent(imgTag)}${trimQ()}`;

  const lowImages = new Map();   // n -> Image à la largeur « page entière » (affichée en attendant la version nette)
  function loadImageAt(n, w, lazy) {
    const url = `/api/page/${id}/${n}?w=${w}&v=${item.mtime}&t=${encodeURIComponent(imgTag)}${trimQ()}`;
    const cached = lowImages.get(n);
    if (cached && cached.src.endsWith(url)) return cached.decoded;
    const im = new Image(); im.fetchPriority = lazy ? "low" : "high"; im.src = url; im.decoded = waitFor(im, n); lowImages.set(n, im);
    return im.decoded;
  }
  function baseWidth(n) {
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const vw = stage.clientWidth || window.innerWidth, vh = stage.clientHeight || window.innerHeight;
    return stepW(Math.min(vw, vh * (aspects[n] || 0.7)) * dpr);
  }
  function loadImage(n, lazy) {
    const url = pageUrl(n);
    const cached = images.get(n);
    if (cached && cached.src.endsWith(url)) return cached.decoded || (cached.decoded = waitFor(cached, n));
    const im = new Image();
    im.fetchPriority = lazy ? "low" : "high";
    im.src = url;
    images.set(n, im);
    im.decoded = waitFor(im, n);
    return im.decoded;
  }
  function waitFor(im, n) {
    return new Promise(resolve => {
      const done = () => {
        if (!im.naturalWidth) { resolve(null); return; }
        aspects[n] = im.naturalWidth / im.naturalHeight;
        // décodée AVANT d'être rendue : l'échange de src peint immédiatement, sans à-coup ni image vide
        (im.decode ? im.decode().catch(() => {}) : Promise.resolve()).then(() => resolve(im));
      };
      if (im.complete) done();
      else { im.onload = done; im.onerror = () => resolve(null); }
    });
  }
  function reportError(n) {
    fetch(pageUrl(n)).then(r => r.json()).then(j => flash(`Page ${n + 1} illisible : ${j.error || ""}`)).catch(() => flash(`Page ${n + 1} illisible`));
  }

  // ---------------------------------------------------------------- affichage
  const isWide = n => (aspects[n] || 0.7) > 1;
  /* Découpage en planches, du début à la fin : couverture seule (option), pages larges seules, sinon par deux. */
  function computeSpreads() {
    const out = [];
    let n = 0;
    while (n < pages) {
      if ((n === 0 && prefs.reader_cover_alone) || isWide(n) || n + 1 >= pages || isWide(n + 1)) { out.push([n]); n += 1; }
      else { out.push([n, n + 1]); n += 2; }
    }
    return out;
  }
  function spreadAt(n) {
    if (mode !== "double") return [n];
    return computeSpreads().find(sp => sp.includes(n)) || [n];
  }
  async function go(n, { save = true, panel = "first" } = {}) {
    if (n < 0) { pendingStep = 0; flash("Début de l'album"); return; }
    if (n >= pages) { pendingStep = 0; showEnd(); return; }
    hideEnd();
    if (mode === "scroll") { scrollToPage(n, save); return; }
    const token = ++loadToken;
    clearTimeout(refineTimer);   // l'affinage prévu pour l'ancienne planche ne doit pas écraser la nouvelle
    zoomBounds = null;
    navBusy = true; navSince = Date.now();
    const done = () => { if (token === loadToken) navBusy = false; };
    if (mode === "panels" && panelsCache.has(n)) getPanels(n);   // sinon : demandées après l'image de base (le serveur la réutilise)
    const spin = setTimeout(() => { if (token === loadToken) loading.hidden = false; }, 180);
    let list;
    if (mode === "double") {
      await Promise.all([loadImage(n), n + 1 < pages ? loadImage(n + 1) : null, n - 1 >= 0 ? loadImage(n - 1) : null]);
      if (token !== loadToken) return;
      list = spreadAt(n);
      const [a, b] = await Promise.all([loadImage(list[0]), list.length === 2 ? loadImage(list[1]) : null]);
      if (token !== loadToken) return;
      if (!a) reportError(list[0]);
      if (list.length === 2 && !b) reportError(list[1]);
      spread.hidden = false; single.hidden = true;
      imgA.src = a ? a.src : ""; imgA.hidden = !a;
      if (list.length === 2) { imgB.src = b ? b.src : ""; imgB.hidden = !b; } else { imgB.hidden = true; imgB.removeAttribute("src"); }
      n = list[0];
    } else if (mode === "panels") {
      // Case par case : l'ancienne case reste affichée, cadrée, pendant qu'on prépare la nouvelle planche
      // (image décodée + découpage en cases). L'échange image + cadrage se fait ensuite d'un seul coup, dans la
      // même image d'écran : jamais de planche mal cadrée ni de fond noir pendant le chargement.
      list = [n];
      const hi = images.get(n);
      const ready = hi && hi.complete && hi.naturalWidth && hi.src.endsWith(pageUrl(n));
      const imageP = ready ? loadImage(n) : loadImageAt(n, baseWidth(n));
      const panelsP = getPanels(n);
      const a = await imageP;
      if (token !== loadToken) return;
      // les cases arrivent en général avec l'image ; sinon (page jamais vue, NAS chargé) on n'attend que
      // 350 ms de plus : la planche s'affiche entière, puis glisse sur la première case dès qu'elles arrivent.
      // Une page sans cases (garde, page blanche, titre) ne paie ainsi jamais la détection.
      const data = await Promise.race([panelsP, new Promise(res => setTimeout(() => res(null), 350))]);
      if (token !== loadToken) return;
      single.hidden = false; spread.hidden = true;
      fxOff(true);
      pendingSwap = null; endMove();
      if (a) { img.src = a.src; img.style.backgroundColor = tintOf(a, n); } else { img.removeAttribute("src"); img.style.transform = ""; reportError(n); }
      resetZoom(false);
      clearTimeout(spin); loading.hidden = true;
      current = n; shown = list;
      fitImages();
      stage.scrollTop = 0; stage.scrollLeft = 0;
      const count = data ? viewsOf(data, n).length : 0;
      panelIdx = panel === "keep" ? Math.min(panelIdx, count - 1) : panel === "last" ? count - 1 : (prefs.reader_panels_full_first || !count ? -1 : 0);
      applyPanel(false);
      if (!data) panelsP.then(d => {        // cases arrivées après coup : on glisse sur la bonne case
        if (token !== loadToken || current !== n) return;
        const c2 = viewsOf(d, n).length;
        if (c2 && panelIdx < 0 && !prefs.reader_panels_full_first) { panelIdx = panel === "last" ? c2 - 1 : 0; applyPanel(true); }
        updateCounter();
        drainStep();
      });
      if (!ready && a) loadImage(n).then(full => { if (token === loadToken && current === n && full && full.src !== img.src) swapSrc(img, full.src, n); });
      updateCounter();
      done();
      drainStep();
      if (save) saveProgress(n);
      const u = new URL(location.href); u.searchParams.set("page", n); history.replaceState(null, "", u);
      preloadAround(n);
      return;
    } else {
      list = [n];
      const a = await loadImage(n);
      if (token !== loadToken) return;
      single.hidden = false; spread.hidden = true;
      if (a) img.src = a.src;
      if (!a) { img.removeAttribute("src"); reportError(n); }
    }
    resetZoom(false);
    clearTimeout(spin); loading.hidden = true;
    current = n; shown = list;
    fitImages();
    stage.scrollTop = 0; stage.scrollLeft = 0;
    updateCounter();
    done();
    if (mode === "panels") drainStep();
    if (save) saveProgress(n);
    const u = new URL(location.href); u.searchParams.set("page", n); history.replaceState(null, "", u);
    preloadAround(list[list.length - 1]);
  }
  function updateCounter() {
    const label = shown.length === 2 ? `${shown[0] + 1}-${shown[1] + 1}` : `${current + 1}`;
    let extra = "";
    if (mode === "panels") {
      const d = panelsCache.get(current);
      const v = d && d.panels instanceof Array && d.panels.length ? viewsOf(d)[panelIdx] : null;
      if (d && d.panels instanceof Array && d.panels.length) { const nb = d._count || d.panels.length; extra = !v ? ` · ${nb} cases` : ` · case ${v.p + 1}/${nb}` + (v.parts > 1 ? ` (${v.part + 1}/${v.parts})` : ""); }
    }
    countEl.textContent = `${label} / ${pages}${extra}`;
    slider.value = current + 1;
  }

  // ---------------------------------------------------------------- case par case
  async function getPanels(n, lazy, attempt = 0) {
    if (panelsCache.has(n)) return panelsCache.get(n);
    const p = (async () => {
      try {
        const r = await fetch(`/api/panels/${id}/${n}`, { priority: lazy ? "low" : "high" });
        if (r.status === 503 && attempt < 4) {
          // serveur occupé (cette planche déjà en cours ailleurs, ou trop de détections à la fois) : on redemande
          // un peu plus tard, sans garder cette réponse
          const wait = Math.max(500, 1000 * (+r.headers.get("Retry-After") || 2));
          await new Promise(res => setTimeout(res, wait));
          panelsCache.delete(n);
          return getPanels(n, lazy, attempt + 1);
        }
        return r.ok ? await r.json() : { panels: [], rtl: [] };
      } catch { return { panels: [], rtl: [] }; }
    })();
    panelsCache.set(n, p);
    const d = await p;
    panelsCache.set(n, d);
    return d;
  }
  const padOf = () => Math.max(0, Math.min(15, +prefs.reader_panels_margin || 0)) / 100;
  /* Texte à cheval sur deux cases (détecté par le serveur) : une case dont une bulle déborde est élargie (« grow ») ;
     deux cases qui se partagent un cartouche sont montrées ensemble (« join »), à la place de la première dans l'ordre
     de lecture. Réglage « texte à cheval sur deux cases » : désactivé, chaque case reste seule. */
  const joinOn = () => !(prefs.reader_panels_join === false || prefs.reader_panels_join === "false");
  function readingPanels(d) {
    let panels = d.panels.map(r => r.slice());
    const order = manga && d.rtl && d.rtl.length === d.panels.length ? d.rtl : d.panels.map((_, i) => i);
    if (!joinOn()) return { panels, order };
    if (d.grow) for (const [k, r] of Object.entries(d.grow)) if (panels[+k] && r && r.length === 4) panels[+k] = r.slice();
    if (!(d.join instanceof Array) || !d.join.length) return { panels, order };
    const parent = panels.map((_, i) => i);
    const find = i => (parent[i] === i ? i : (parent[i] = find(parent[i])));
    for (const [a, b] of d.join) if (panels[a] && panels[b]) parent[find(a)] = find(b);
    const union = new Map();
    panels.forEach((r, i) => {
      const g = find(i), u = union.get(g);
      union.set(g, u ? [Math.min(u[0], r[0]), Math.min(u[1], r[1]), Math.max(u[2], r[2]), Math.max(u[3], r[3])] : r.slice());
    });
    const seen = new Set(), merged = [];
    for (const i of order) {
      const g = find(i);
      if (seen.has(g)) continue;
      seen.add(g);
      merged.push(union.get(g));
    }
    return { panels: merged, order: merged.map((_, i) => i) };
  }
  /* Les « vues » d'une planche : une par case, dans l'ordre de lecture. Une case large (bandeau sur toute la
     largeur) ne peut pas être agrandie sur un écran étroit : réduite pour tenir en largeur, elle reste petite.
     Si l'option est active, elle est alors lue en deux ou trois temps (gauche → droite, l'inverse en manga),
     chaque partie grossie comme une case normale. Calcul refait si l'écran, le sens ou les réglages changent. */
  function viewsOf(d, n = current) {
    if (!d || !(d.panels instanceof Array)) return [];
    const vw = stage.clientWidth, vh = stage.clientHeight, asp = aspects[n] || 0.7, pad = padOf();
    const key = `${vw}x${vh}|${asp.toFixed(3)}|${manga}|${prefs.reader_panels_wide}|${pad}|${joinOn()}`;
    if (d._vkey === key) return d._views;
    const ih = Math.min(vh, vw / asp), iw = ih * asp;
    const { panels, order } = readingPanels(d);
    d._count = panels.length;
    const out = [];
    order.forEach((pi, i) => {
      const r = panels[pi];
      const pw = Math.max(1, (r[2] - r[0]) * iw), ph = Math.max(1, (r[3] - r[1]) * ih);
      const sw = vw * (1 - 2 * pad) / pw, sh = vh * (1 - 2 * pad) / ph, s = Math.max(1, Math.min(5, sw, sh));
      let k = 1;
      // bandeau : limité par la largeur, encore petit à l'écran (moins de 300 px de haut, soit un tiers d'un
      // écran de téléphone) et nettement plus grand si on le coupait → le moins de parties possible (3 au plus)
      const SMALL = 300;
      if (prefs.reader_panels_wide !== "fit" && sw < sh && ph * s < SMALL && sh / sw >= 1.4) {
        k = 2;
        while (k < 3 && Math.min(k * sw, sh) * ph < SMALL) k++;
      }
      if (k === 1) { out.push({ r, p: i, part: 0, parts: 1 }); return; }
      const ov = 0.05, w = r[2] - r[0];
      for (let j = 0; j < k; j++) {
        const part = manga ? k - 1 - j : j;
        const x0 = r[0] + w * Math.max(0, part / k - ov), x1 = r[0] + w * Math.min(1, (part + 1) / k + ov);
        out.push({ r: [x0, r[1], x1, r[3]], p: i, part: j, parts: k });   // numéroté dans l'ordre de lecture
      }
    });
    d._vkey = key; d._views = out;
    return out;
  }
  /* Cadre la case courante : l'image reste mise en page « page entière », on la déplace et on l'agrandit (transition CSS). */
  // Pendant qu'une case glisse vers la suivante (animation de la transformation), on ne change JAMAIS l'image
  // affichée : la carte graphique devrait redessiner une grande image en plein mouvement, et le temps qu'elle
  // le fasse, la case apparaît noire. La version plus nette attend la fin du glissement.
  let panelMoving = false, movingTimer = null, pendingSwap = null;
  function endMove() {
    clearTimeout(movingTimer); panelMoving = false;
    if (pendingSwap) { const { el, src, n } = pendingSwap; pendingSwap = null; if (shown.includes(n) && el.src !== src) el.src = src; }
  }
  img.addEventListener("transitionend", e => { if (e.propertyName === "transform") endMove(); });
  function startMove() {
    clearTimeout(movingTimer);
    if (!(panelSpeed() > 0)) { endMove(); return; }   // passage instantané : rien ne glisse, rien à attendre
    panelMoving = true; movingTimer = setTimeout(endMove, panelSpeed() * 1000 + 250);
  }
  function swapSrc(el, src, n) {
    if (el === img && panelMoving) { pendingSwap = { el, src, n }; return; }
    pendingSwap = null;
    el.src = src;
  }
  // couleur moyenne de la planche, posée sous l'image : si l'écran met un instant à dessiner une grande image,
  // on voit sa teinte plutôt qu'un trou noir
  const tints = new Map();
  function tintOf(im, n) {
    if (tints.has(n)) return tints.get(n);
    let c = "";
    try {
      const cv = document.createElement("canvas"); cv.width = cv.height = 1;
      const cx = cv.getContext("2d"); cx.drawImage(im, 0, 0, 1, 1);
      const [r, g, b] = cx.getImageData(0, 0, 1, 1).data; c = `rgb(${r},${g},${b})`;
    } catch (_) { /* ignore */ }
    tints.set(n, c);
    return c;
  }
  // Reste de la planche assombri autour de la case (réglage) : un voile sur toute la scène, troué à la case ;
  // le trou suit la case avec la même animation que l'image (clip-path, dessiné par la carte graphique).
  const dimEl = $("#dim");
  function placeDim(x0, y0, w, h) {
    if (!(+prefs.reader_panels_dim > 0)) { dimEl.hidden = true; return; }
    // recadrage à la main (case mal détectée) : le masque s'efface, on voit la planche autour
    dimEl.classList.toggle("loose", !!(panelOff.x || panelOff.y));
    const f = v => v.toFixed(1) + "px";
    // contour extérieur, puis aller-retour par le même segment jusqu'au trou : pas de pointe parasite entre les deux
    dimEl.style.clipPath = `polygon(evenodd, 0 0, 100% 0, 100% 100%, 0 100%, 0 0, ${f(x0)} ${f(y0)}, ${f(x0)} ${f(y0 + h)}, ${f(x0 + w)} ${f(y0 + h)}, ${f(x0 + w)} ${f(y0)}, ${f(x0)} ${f(y0)})`;
    dimEl.hidden = false;
  }
  const fxOff = on => { img.classList.toggle("nofx", on); dimEl.classList.toggle("nofx", on); };
  function applyPanel(animate = true) {
    const d = panelsCache.get(current);
    zoomBounds = null;
    fxOff(!animate);
    panelBox = null;
    const views = viewsOf(d);
    if (panelIdx >= views.length) panelIdx = views.length - 1;
    if (!views.length || panelIdx < 0 || !img.naturalWidth) {
      if (animate && img.style.transform) startMove();
      img.style.transform = "";
      dimEl.hidden = true;
      if (!animate) requestAnimationFrame(() => fxOff(false));
      return;
    }
    const r = views[panelIdx].r;
    const sr = stage.getBoundingClientRect(), ir = img.getBoundingClientRect();
    // position de l'image sans transformation : on retire la transformation courante
    const cur = img.style.transform ? new DOMMatrix(getComputedStyle(img).transform) : null;
    const scale0 = cur ? cur.a : 1;
    const ix = (ir.left - sr.left) - (cur ? cur.e : 0), iy = (ir.top - sr.top) - (cur ? cur.f : 0);
    const iw = ir.width / scale0, ih = ir.height / scale0;
    const px = r[0] * iw, py = r[1] * ih, pw = Math.max(1, (r[2] - r[0]) * iw), ph = Math.max(1, (r[3] - r[1]) * ih);
    const vw = sr.width, vh = sr.height, pad = padOf();
    let s = Math.min(vw * (1 - 2 * pad) / pw, vh * (1 - 2 * pad) / ph);
    s = Math.max(1, Math.min(5, s));
    const tx = vw / 2 - ix - s * (px + pw / 2), ty = vh / 2 - iy - s * (py + ph / 2);
    // recadrage à la main (glisser) : l'écart est oublié dès qu'on change de case ou de planche
    if (panelOff.page !== current || panelOff.idx !== panelIdx) Object.assign(panelOff, { x: 0, y: 0, page: current, idx: panelIdx });
    panelFrame = { tx, ty, s, ix, iy, iw, ih, vw, vh, px, py, pw, ph };
    panelScale = s;
    const before = img.style.transform;
    placePanel();
    if (animate && img.style.transform !== before) startMove();
    if (!animate) requestAnimationFrame(() => fxOff(false));
    scheduleRefine();   // une fois cadrée, la case est rechargée plus nette si besoin
  }
  let panelScale = 1, panelBox = null, pendingStep = 0;
  const queueStep = dir => { pendingStep = Math.max(-3, Math.min(3, pendingStep + dir)); };
  /* Recadrage à la main en case par case : la case est déplacée du doigt (ou à la souris) quand la détection l'a mal
     cadrée ou qu'un bout déborde ; on ne peut pas sortir de la planche. La case suivante repart d'un cadrage propre. */
  let panelFrame = null, panelDrag = null;
  const panelOff = { x: 0, y: 0, page: -1, idx: -1 };
  function clampPanelOff() {
    if (!panelFrame) return;
    const { tx, ty, s, ix, iy, iw, ih, vw, vh } = panelFrame;
    const x0 = ix + tx, x1 = x0 + iw * s, y0 = iy + ty, y1 = y0 + ih * s;
    // La case est toujours centrée, même au bord de la planche (avant, la planche était recalée contre le bord de l'écran :
    // la première case d'une rangée n'était pas centrée et ses voisines restaient à l'écran). Recadrage à la main : on peut
    // aller voir plus de planche, pas faire apparaître plus de vide qu'au départ (idem en hauteur).
    const range = (lo, hi, view, off) => (hi - lo <= view ? 0 : Math.max(Math.min(0, view - hi), Math.min(Math.max(0, -lo), off)));
    panelOff.x = range(x0, x1, vw, panelOff.x);
    panelOff.y = range(y0, y1, vh, panelOff.y);
  }
  function placePanel() {
    if (!panelFrame) return;
    clampPanelOff();
    const { tx, ty, s, ix, iy, iw, ih, px, py, pw, ph } = panelFrame;
    const fx = tx + panelOff.x, fy = ty + panelOff.y;
    img.style.transform = `translate(${fx.toFixed(1)}px, ${fy.toFixed(1)}px) scale(${s.toFixed(4)})`;
    placeDim(ix + fx + s * px, iy + fy + s * py, s * pw, s * ph);
    panelBox = { x0: ix + fx, y0: iy + fy, x1: ix + fx + iw * s, y1: iy + fy + ih * s };   // position finale (après l'animation)
    zoomBounds = null;
  }
  const canPanelDrag = () => mode === "panels" && panelIdx >= 0 && userZoom === 1 && !!panelFrame;
  function panelDragStart(x, y) { panelDrag = { x, y, ox: panelOff.x, oy: panelOff.y, moved: false }; }
  function panelDragMove(x, y) {
    if (!panelDrag) return;
    const dx = x - panelDrag.x, dy = y - panelDrag.y;
    if (!panelDrag.moved && Math.abs(dx) + Math.abs(dy) > 6) { panelDrag.moved = true; fxOff(true); }
    if (!panelDrag.moved) return;
    panelOff.x = panelDrag.ox + dx; panelOff.y = panelDrag.oy + dy;
    placePanel();
  }
  function panelDragEnd() {
    const moved = !!(panelDrag && panelDrag.moved);
    panelDrag = null;
    if (moved) { dragMoved = true; requestAnimationFrame(() => fxOff(false)); }
    return moved;
  }
  // Dépile un pas gardé pendant un chargement (appuis répétés) : un à la fois, dans l'ordre.
  function drainStep() {
    if (!pendingStep || busy()) return;
    const d = pendingStep > 0 ? 1 : -1;
    pendingStep -= d;
    setTimeout(() => panelStep(d), 60);
  }
  async function panelStep(dir) {
    const d = panelsCache.get(current);
    if (d && typeof d.then === "function") { queueStep(dir); return; }   // cases pas encore connues : pas gardé
    const count = d && d.panels instanceof Array ? viewsOf(d).length : 0;
    if (dir > 0) {
      if (count && panelIdx < count - 1) { panelIdx += 1; applyPanel(true); updateCounter(); drainStep(); return; }
      go(current + 1);
    } else {
      // en arrière : case précédente ; la page entière n'est une étape que si l'option « page entière d'abord » est active
      if (panelIdx > 0 || (panelIdx === 0 && prefs.reader_panels_full_first)) { panelIdx -= 1; applyPanel(true); updateCounter(); drainStep(); return; }
      if (current <= 0) { pendingStep = 0; flash("Début de l'album"); return; }
      go(current - 1, { panel: "last" });
    }
  }
  function preloadAround(n) {
    const count = Math.max(0, Math.min(10, +prefs.reader_preload || 0));
    for (const k of [...images.keys()]) if (Math.abs(k - n) > count + 4) images.delete(k);
    for (const k of [...lowImages.keys()]) if (Math.abs(k - n) > count + 4) lowImages.delete(k);
    // tout le spéculatif est en priorité réseau basse : le navigateur n'a que 6 connexions par hôte,
    // la planche qu'on demande vraiment garde la voie libre
    if (mode === "panels") {
      for (let k = 1; k <= Math.min(2, count); k++) if (n + k < pages) { const m = n + k; loadImageAt(m, baseWidth(m), true); getPanels(m, true); }
      if (n - 1 >= 0) { const m = n - 1; loadImageAt(m, baseWidth(m), true); getPanels(m, true); }
      if (n + 1 < pages) loadImage(n + 1, true);   // la version nette de la suivante seulement : le plein format ×2 est lourd
      return;
    }
    for (let k = 1; k <= count; k++) if (n + k < pages) loadImage(n + k, true);
    if (n - 1 >= 0) loadImage(n - 1, true);
  }
  async function next() {
    if (mode === "scroll") { scrollStep(1); return; }
    if (mode === "panels") { panelStep(1); return; }
    go(shown.length ? shown[shown.length - 1] + 1 : current + 1);
  }
  async function prev() {
    if (mode === "scroll") { scrollStep(-1); return; }
    if (mode === "panels") { panelStep(-1); return; }
    if (current <= 0) { flash("Début de l'album"); return; }
    if (mode !== "double") { go(current - 1); return; }
    // double page : on recule d'une planche dans le découpage calculé depuis le début
    await Promise.all([loadImage(current - 1), current - 2 >= 0 ? loadImage(current - 2) : null]);
    const spreads = computeSpreads();
    const i = spreads.findIndex(sp => sp.includes(current));
    go(i > 0 ? spreads[i - 1][0] : 0);
  }
  const forward = () => manga ? prev() : next();   // « vers la droite »
  const backward = () => manga ? next() : prev();  // « vers la gauche »

  // ---------------------------------------------------------------- défilement continu
  let scrollBuilt = false, scrollObserver = null, scrollTicking = false;
  function buildScroll() {
    if (scrollBuilt) return;
    scrollBuilt = true;
    scrollEl.innerHTML = "";
    for (let n = 0; n < pages; n++) {
      const d = document.createElement("div");
      d.className = "spage"; d.dataset.n = n;
      d.style.aspectRatio = String(aspects[n] || 0.7);
      const im = document.createElement("img");
      im.alt = ""; im.draggable = false; im.dataset.n = n;
      d.appendChild(im); scrollEl.appendChild(d);
    }
    scrollObserver = new IntersectionObserver(entries => {
      for (const e of entries) {
        const im = e.target.querySelector("img"), n = +e.target.dataset.n;
        if (e.isIntersecting && !im.src) {
          im.src = pageUrl(n);
          im.onload = () => { aspects[n] = im.naturalWidth / im.naturalHeight; e.target.style.aspectRatio = String(aspects[n]); };
        }
      }
    }, { root: stage, rootMargin: "150% 0px" });
    for (const d of scrollEl.children) scrollObserver.observe(d);
    stage.addEventListener("scroll", () => {
      if (mode !== "scroll" || scrollTicking) return;
      scrollTicking = true;
      requestAnimationFrame(() => { scrollTicking = false; trackScroll(); });
    }, { passive: true });
  }
  function trackScroll() {
    const mid = stage.scrollTop + stage.clientHeight / 2;
    let best = 0;
    for (const d of scrollEl.children) { if (d.offsetTop <= mid) best = +d.dataset.n; else break; }
    if (best !== current) { current = best; shown = [best]; updateCounter(); saveProgress(best); const u = new URL(location.href); u.searchParams.set("page", best); history.replaceState(null, "", u); }
    if (stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 2 && current === pages - 1) markEndReached();
  }
  function scrollToPage(n, save = true) {
    buildScroll();
    const d = scrollEl.children[n];
    if (!d) return;
    stage.scrollTo({ top: d.offsetTop, behavior: "auto" });
    current = n; shown = [n]; updateCounter();
    if (save) saveProgress(n);
  }
  function scrollStep(dir) {
    const atEnd = stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 2;
    if (dir > 0 && atEnd) { showEnd(); return; }
    if (dir < 0 && stage.scrollTop <= 0) { flash("Début de l'album"); return; }
    const target = Math.max(0, Math.min(pages - 1, current + dir));
    const d = scrollEl.children[target];
    if (d) stage.scrollTo({ top: d.offsetTop, behavior: "smooth" });
  }
  let endReached = false;
  function markEndReached() {
    if (endReached) return;
    endReached = true;
    clearTimeout(saveTimer);
    fetch(`/api/progress/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: pages - 1, completed: true }) }).catch(() => {});
    lastSavedPage = pages - 1;
  }

  // ---------------------------------------------------------------- progression
  function saveProgress(n) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      lastSavedPage = n;
      fetch(`/api/progress/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: n }), keepalive: true }).catch(() => {});
    }, 400);
  }
  window.addEventListener("pagehide", () => {
    if (current >= 0 && current !== lastSavedPage && navigator.sendBeacon) {
      navigator.sendBeacon(`/api/progress/${id}`, new Blob([JSON.stringify({ page: current })], { type: "application/json" }));
    }
  });

  // ---------------------------------------------------------------- fin d'album
  function showEnd() {
    if (current >= 0) markEndReached();
    const nxt = item.next;
    endEl.innerHTML = `<div class="box">
      <h2>Album terminé</h2>
      <p>${nxt ? `Suivant : <span class="nxt">${esc(nxt.name)}</span>` : "C'était le dernier album de ce dossier."}</p>
      <div class="actions">
        ${nxt ? `<a class="btn primary" id="end-next" href="/read/${nxt.id}?page=0">Lire la suite</a>` : ""}
        <a class="btn" href="${folderHref}">Retour au dossier</a>
        <button class="btn" type="button" id="end-close">Rester sur la dernière page</button>
      </div></div>`;
    endEl.hidden = false;
    body.classList.remove("hide-bars");
    $("#end-close").onclick = hideEnd;
  }
  const hideEnd = () => { endEl.hidden = true; };

  // ---------------------------------------------------------------- ajustement / mode / manga / plein écran
  function applyFit() {
    const eff = mode === "panels" ? "page" : fit;   // case par case : toujours à partir de la page entière
    FITS.forEach(f => body.classList.toggle("fit-" + f, f === eff));
    fitBtn.textContent = FIT_LABEL[fit];
    fitBtn.disabled = mode !== "single";
    fitImages();
  }
  /* « Page entière » : la hauteur de chaque image est fixée en pixels CSS d'après sa proportion, pour qu'elle remplisse
     l'écran même quand le fichier reçu est plus petit que l'écran (navigateur zoomé à 80 %, écran très dense) et pour que
     la mise en page ne bouge pas quand la version nette remplace la version floue. */
  function fitImages() {
    const eff = mode === "panels" ? "page" : fit;
    const vw = stage.clientWidth, vh = stage.clientHeight;
    const set = (el, n, maxW) => {
      const asp = aspects[n];
      if (!asp || !el || el.hidden || !el.src) { if (el) { el.style.height = ""; el.style.width = ""; } return; }
      el.style.height = Math.floor(Math.min(vh, maxW / asp)) + "px"; el.style.width = "auto";
    };
    if (mode === "double") {
      const both = shown.length === 2 && !imgA.hidden && !imgB.hidden;
      set(imgA, shown[0], both ? vw / 2 : vw); set(imgB, shown[1], both ? vw / 2 : vw);
    } else if (mode === "single" || mode === "panels") {
      if (eff === "page") set(img, current, vw); else { img.style.height = ""; img.style.width = ""; }
    }
  }
  function applyMode() {
    MODES.forEach(m => body.classList.toggle("mode-" + m, m === mode));
    modeBtn.textContent = MODE_LABEL[mode];
    single.hidden = mode !== "single" && mode !== "panels"; spread.hidden = mode !== "double"; scrollEl.hidden = mode !== "scroll";
    if (mode !== "panels") { img.style.transform = ""; panelIdx = -1; pendingStep = 0; dimEl.hidden = true; }
    if (mode === "scroll") buildScroll();
    applyFit();
  }
  function cycleFit() {
    if (mode !== "single") { flash("L'ajustement ne s'applique qu'en mode 1 page"); return; }
    resetZoom(false);
    fit = FITS[(FITS.indexOf(fit) + 1) % FITS.length];
    applyFit(); saveAlbumMemory();
    images.clear();
    flash({ page: "Page entière", width: "Pleine largeur", original: "Taille d'origine" }[fit]);
    if (current >= 0) go(current, { save: false });
  }
  function cycleMode() {
    resetZoom(false);
    const keep = current;
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    images.clear();
    applyMode(); saveAlbumMemory();
    flash({ single: "Une page", double: "Deux pages (planches larges et couverture seules)", scroll: "Défilement continu", panels: "Case par case : → case suivante, ← précédente ; glissez pour recadrer" }[mode]);
    if (keep >= 0) go(keep, { save: false });
  }
  function togglePanels() {
    const keep = current;
    mode = mode === "panels" ? "single" : "panels";
    images.clear();
    applyMode(); saveAlbumMemory();
    flash(mode === "panels" ? "Case par case : → case suivante, ← précédente ; glissez pour recadrer" : "Une page");
    if (keep >= 0) go(keep, { save: false });
  }
  function applyManga(announce = true) {
    mangaBtn.classList.toggle("on", manga);
    slider.style.direction = manga ? "rtl" : "ltr";
    spread.classList.toggle("rtl", manga);
    if (announce) flash(manga ? "Sens manga : lecture de droite à gauche" : "Sens occidental : lecture de gauche à droite");
  }
  // R : rogner (ou non) les marges blanches ; mémorisé dans le profil, comme la case des réglages
  function toggleTrim() {
    prefs.reader_trim = !prefs.reader_trim;
    flash((prefs.reader_trim ? "Marges blanches rognées" : "Pages entières (marges gardées)") + (mode === "panels" ? " — s'applique hors case par case" : ""));
    fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: { reader_trim: prefs.reader_trim } }) }).catch(() => {});
    try { const p = JSON.parse(localStorage.getItem("bulle:profile") || "{}"); p.reader_trim = prefs.reader_trim; localStorage.setItem("bulle:profile", JSON.stringify(p)); } catch (_) { /* ignore */ }
    images.clear(); lowImages.clear();
    if (mode === "scroll") {
      for (const im of scrollEl.querySelectorAll("img[src]")) im.src = pageUrl(+im.dataset.n);
    } else if (mode !== "panels") go(current, { save: false });
  }
  function toggleManga() { manga = !manga; applyManga(); saveAlbumMemory(); if (mode === "panels") applyPanel(true); }
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  }
  let flashEl = null, flashTimer = null;
  function flash(text) {
    if (!flashEl) { flashEl = document.createElement("div"); flashEl.className = "hint"; body.appendChild(flashEl); }
    flashEl.textContent = text;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => { if (flashEl) { flashEl.remove(); flashEl = null; } }, 1400);
  }

  // ---------------------------------------------------------------- barres : auto-masquage
  function scheduleHide() {
    clearTimeout(hideTimer);
    const delay = Math.max(500, (+prefs.reader_bars_delay || 2.5) * 1000);
    hideTimer = setTimeout(() => { if (!overBar && endEl.hidden) body.classList.add("hide-bars"); }, delay);
  }
  /* Sur tablette et téléphone, une tape fabrique aussi de faux événements souris (mousemove, mouseenter…) : si on les
     écoutait, chaque tape ferait apparaître les barres et la barre du bas, une fois touchée, ne se cacherait plus jamais
     (« mouseleave » n'arrive jamais). Seule la vraie souris compte ici ; au doigt, c'est la tape au centre qui décide. */
  let overBar = false;
  for (const bar of document.querySelectorAll(".rbar")) {
    bar.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") overBar = true; });
    bar.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") { overBar = false; scheduleHide(); } });
  }
  let lastMove = 0;
  document.addEventListener("pointermove", e => {
    if (e.pointerType !== "mouse") return;
    const now = Date.now(); if (now - lastMove < 100) return; lastMove = now;
    body.classList.remove("hide-bars"); scheduleHide();
  });
  const toggleBars = () => { body.classList.toggle("hide-bars"); if (!body.classList.contains("hide-bars")) scheduleHide(); };

  // ---------------------------------------------------------------- zoom libre (Ctrl + molette, pincement, +/-, double-clic) et déplacement
  let userZoom = 1, panX = 0, panY = 0, dragging = null, dragMoved = false;
  const zoomTarget = () => mode === "double" ? spread : single;
  /* Limite le déplacement aux images visibles (pas au cadre noir autour) : on ne peut pas « perdre » la page.
     Les bords de l'image sont mesurés une seule fois par zoom (zoomBounds), pas à chaque cran de molette : mesurer
     le DOM à chaque événement forçait une mise en page complète et faisait ramer le zoom. */
  let zoomBounds = null;
  function measureBounds() {
    const el = zoomTarget();
    const sr = stage.getBoundingClientRect();
    if (mode === "panels" && panelBox && !el.style.transform) {   // case cadrée : position connue sans mesurer (l'animation peut être en cours)
      zoomBounds = Object.assign({ vw: sr.width, vh: sr.height, left: sr.left, top: sr.top }, panelBox); return;
    }
    const m = el.style.transform ? new DOMMatrix(getComputedStyle(el).transform) : new DOMMatrix();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const im of el.querySelectorAll("img")) {
      if (im.hidden || !im.src || !im.naturalWidth) continue;
      const r = im.getBoundingClientRect();   // position actuelle (déjà transformée) → coordonnées sans transformation
      const ux = (r.left - sr.left - m.e) / (m.a || 1), uy = (r.top - sr.top - m.f) / (m.d || 1);
      x0 = Math.min(x0, ux); y0 = Math.min(y0, uy); x1 = Math.max(x1, ux + r.width / (m.a || 1)); y1 = Math.max(y1, uy + r.height / (m.d || 1));
    }
    if (!isFinite(x0)) { x0 = 0; y0 = 0; x1 = el.scrollWidth; y1 = el.scrollHeight; }
    zoomBounds = { x0, y0, x1, y1, vw: sr.width, vh: sr.height, left: sr.left, top: sr.top };
  }
  function clampPan() {
    if (!zoomBounds) measureBounds();
    const { x0, y0, x1, y1, vw, vh } = zoomBounds;
    const z = userZoom, cw = (x1 - x0) * z, ch = (y1 - y0) * z;
    // bornes : le bord gauche de l'image (x0*z + panX) ne doit pas dépasser 0, son bord droit pas descendre sous vw
    // image plus large que l'écran : pas de vide sur les côtés ; plus étroite : elle reste entière à l'écran (sans la recentrer de force,
    // pour que le zoom reste accroché au pointeur)
    panX = cw <= vw ? Math.min(vw - x1 * z, Math.max(-x0 * z, panX)) : Math.min(-x0 * z, Math.max(vw - x1 * z, panX));
    panY = ch <= vh ? Math.min(vh - y1 * z, Math.max(-y0 * z, panY)) : Math.min(-y0 * z, Math.max(vh - y1 * z, panY));
  }
  /* Une seule écriture de style par image affichée (requestAnimationFrame), même si la molette envoie dix événements entre deux. */
  let zoomRaf = 0;
  function applyZoom() {
    if (zoomRaf) return;
    zoomRaf = requestAnimationFrame(() => { zoomRaf = 0; applyZoomNow(); });
  }
  function applyZoomNow() {
    const el = zoomTarget();
    if (userZoom === 1) { el.style.transform = ""; body.classList.remove("zoomed"); zoomBounds = null; return; }
    clampPan();
    el.style.transform = `translate(${panX.toFixed(1)}px, ${panY.toFixed(1)}px) scale(${userZoom.toFixed(4)})`;
    body.classList.add("zoomed");
  }
  /* Zoom minimal : en dessous de 100 % seulement si la page ne tient pas entière à l'écran (ajustement « largeur » ou
     « taille d'origine ») — le zoom − permet alors de la voir en entier. En case par case, la case cadrée est le minimum. */
  function minZoom() {
    if (mode === "panels") return 1;
    if (!zoomBounds) measureBounds();
    const { x0, y0, x1, y1, vw, vh } = zoomBounds;
    const cw = x1 - x0, ch = y1 - y0;
    if (!(cw > 0 && ch > 0)) return 1;
    return Math.min(1, 0.98 * vw / cw, 0.98 * vh / ch);
  }
  function setZoom(z, cx, cy) {
    if (mode === "scroll") return;
    const zmin = minZoom();
    z = Math.max(zmin, Math.min(8, z));
    if (Math.abs(z - 1) < 0.04) z = 1;   // un zoom qui arrive presque à 100 % revient à 100 % (sinon on reste « zoomé » d'un poil)
    if (z === userZoom) { if (z <= zmin + 0.001) flash(mode === "panels" ? "Case entière (touche C pour la planche)" : "Page entière"); return; }
    const el = zoomTarget();
    if (userZoom === 1 && z !== 1) {   // on part de la position de défilement courante
      panX = -stage.scrollLeft; panY = -stage.scrollTop; stage.scrollLeft = 0; stage.scrollTop = 0;
      el.style.transformOrigin = "0 0";
      zoomBounds = null;
    }
    if (!zoomBounds) measureBounds();
    const { vw, vh, left, top } = zoomBounds;
    cx = (cx == null ? vw / 2 : cx - left); cy = (cy == null ? vh / 2 : cy - top);
    const k = z / userZoom;
    panX = cx - (cx - panX) * k; panY = cy - (cy - panY) * k;
    if (z < 1 && z <= zmin + 0.001) {   // dézoomé au maximum : la page entière, bien au milieu de l'écran
      const { x0, y0, x1, y1 } = zoomBounds;
      panX = (vw - (x0 + x1) * z) / 2; panY = (vh - (y0 + y1) * z) / 2;
    }
    const back = z === 1 && userZoom !== 1;
    userZoom = z;
    if (back) { cancelAnimationFrame(zoomRaf); zoomRaf = 0; const top = -panY; panX = 0; panY = 0; el.style.transform = ""; body.classList.remove("zoomed"); zoomBounds = null; stage.scrollTop = Math.max(0, top); }
    else applyZoom();
    if (z !== 1) flash(`Zoom ${Math.round(z * 100)} %`);
    scheduleRefine();
  }
  /* Quand on zoome, on va chercher une version plus nette de la page, une fois le geste terminé. Trois largeurs seulement
     (1400, 2000, 2600 px) : chaque largeur différente est une image à recalculer côté serveur, et une image trop grande
     rend le zoom poussif ; une seule demande à la fois, jamais une version moins nette que celle affichée. */
  const REFINE_LADDER = [1400, 2000, 2600];
  let refineTimer = null, refining = false, refineAgain = false;
  function scheduleRefine() { clearTimeout(refineTimer); refineTimer = setTimeout(refineZoom, mode === "panels" && userZoom === 1 ? 700 : 320); }
  async function refineZoom() {
    if (refining) { refineAgain = true; return; }
    if (navBusy) { scheduleRefine(); return; }   // une planche arrive : on affinera celle-là, plus tard
    const effective = userZoom * (mode === "panels" && panelIdx >= 0 ? panelScale : 1);
    if (effective <= 1.15 || mode === "scroll" || prefs.reader_quality === "original") return;
    const token = loadToken;
    const targets = mode === "double" ? shown.map((n, i) => [n, i === 0 ? imgA : imgB]) : [[current, img]];
    refining = true;
    try {
      for (const [n, el] of targets) {
        if (!el || el.hidden || !el.src) continue;
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        const want = Math.ceil(el.getBoundingClientRect().width * dpr);   // largeur affichée réelle en pixels physiques
        if (el.naturalWidth >= want * 0.8) continue;
        const ladder = mode === "panels" && userZoom === 1 ? REFINE_LADDER.slice(0, 2) : REFINE_LADDER;   // cases : 2000 px maxi, le serveur souffle
        const w = ladder.find(x => x >= want) || ladder[ladder.length - 1];
        if (el.naturalWidth >= w) continue;
        const better = await loadImageAt(n, w);
        if (token !== loadToken || !better || !shown.includes(n)) return;   // la page a changé entre-temps
        if (better.naturalWidth > el.naturalWidth) { swapSrc(el, better.src, n); zoomBounds = null; }
      }
    } finally {
      refining = false;
      if (refineAgain) { refineAgain = false; scheduleRefine(); }
    }
  }
  function resetZoom(announce = true) { if (userZoom !== 1) { cancelAnimationFrame(zoomRaf); zoomRaf = 0; userZoom = 1; panX = panY = 0; zoomBounds = null; zoomTarget().style.transform = ""; spread.style.transform = ""; single.style.transform = ""; body.classList.remove("zoomed"); if (announce) flash("Zoom 100 %"); } }
  stage.addEventListener("wheel", e => {
    if (mode === "scroll") return;
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const factor = Math.exp(-Math.max(-150, Math.min(150, e.deltaY)) * 0.0017);   // un cran de molette ≈ ×1,19
      setZoom(userZoom * factor, e.clientX, e.clientY);
      return;
    }
    if (userZoom > 1) { e.preventDefault(); panX -= e.deltaX; panY -= e.deltaY; applyZoom(); }
  }, { passive: false });
  stage.addEventListener("pointerdown", e => {
    if (e.button !== 0 || e.pointerType === "touch") return;
    if (userZoom <= 1) {
      if (canPanelDrag()) { panelDragStart(e.clientX, e.clientY); dragMoved = false; stage.setPointerCapture(e.pointerId); }
      return;
    }
    dragging = { x: e.clientX, y: e.clientY, px: panX, py: panY }; dragMoved = false;
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", e => {
    if (panelDrag && e.pointerType !== "touch") { panelDragMove(e.clientX, e.clientY); return; }
    if (!dragging) return;
    const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) dragMoved = true;
    panX = dragging.px + dx; panY = dragging.py + dy; applyZoom();
  });
  stage.addEventListener("pointerup", e => { dragging = null; if (e.pointerType !== "touch") panelDragEnd(); });
  stage.addEventListener("pointercancel", e => { dragging = null; if (e.pointerType !== "touch") panelDragEnd(); });
  stage.addEventListener("dblclick", e => {
    if (mode === "scroll" || e.target.closest(".rmsg")) return;
    e.preventDefault();
    setZoom(userZoom !== 1 ? 1 : 2.5, e.clientX, e.clientY);
  });
  // pincement à deux doigts
  let pinch = null;
  stage.addEventListener("touchstart", e => {
    if (e.touches.length === 2) {
      const [a, b] = e.touches;
      pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), z: userZoom, cx: (a.clientX + b.clientX) / 2, cy: (a.clientY + b.clientY) / 2 };
    } else if (e.touches.length === 1 && userZoom > 1) {
      pinch = null; dragging = { x: e.touches[0].clientX, y: e.touches[0].clientY, px: panX, py: panY }; dragMoved = false;
    } else if (e.touches.length === 1 && canPanelDrag()) {
      pinch = null; panelDragStart(e.touches[0].clientX, e.touches[0].clientY); dragMoved = false;
    }
  }, { passive: true });
  stage.addEventListener("touchmove", e => {
    if (pinch && e.touches.length === 2) {
      const [a, b] = e.touches;
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      setZoom(pinch.z * (d / pinch.d), pinch.cx, pinch.cy);
      e.preventDefault();
    } else if (dragging && e.touches.length === 1 && userZoom > 1) {
      const dx = e.touches[0].clientX - dragging.x, dy = e.touches[0].clientY - dragging.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) dragMoved = true;
      panX = dragging.px + dx; panY = dragging.py + dy; applyZoom();
      e.preventDefault();
    } else if (panelDrag && e.touches.length === 1) {
      panelDragMove(e.touches[0].clientX, e.touches[0].clientY);
      if (panelDrag.moved) e.preventDefault();
    } else if (e.touches.length === 2) { panelDrag = null; }
  }, { passive: false });
  stage.addEventListener("touchend", e => { if (e.touches.length < 2) pinch = null; if (!e.touches.length) dragging = null; }, { passive: true });

  // ---------------------------------------------------------------- bande des miniatures (clic droit)
  const strip = $("#strip"), stripRow = $("#strip-row");
  let stripBuilt = false, stripObserver = null;
  function buildStrip() {
    if (stripBuilt) return;
    stripBuilt = true;
    const thumbW = 300;
    stripRow.innerHTML = Array.from({ length: pages }, (_, n) => `<button type="button" class="sthumb" data-n="${n}"><img alt="" data-src="/api/page/${id}/${n}?w=${thumbW}&v=${item.mtime}&t=${encodeURIComponent(imgTag)}"><span>${n + 1}</span><i class="setcov" data-setcover="${n}" title="Utiliser cette page comme couverture de l'album">★ Couverture</i></button>`).join("");
    markCoverThumb();
    // miniature qui ne s'affiche pas : on montre la raison donnée par le serveur (quel fichier, quel format…)
    for (const im of stripRow.querySelectorAll("img")) im.addEventListener("error", async () => {
      const t = im.closest(".sthumb");
      if (!t || t.classList.contains("bad")) return;
      t.classList.add("bad");
      let msg = "Image illisible";
      try { const j = await (await fetch(im.src)).json(); msg = j.error || msg; } catch (_) { /* ignore */ }
      const em = document.createElement("em"); em.className = "sbad"; em.textContent = msg; em.title = msg;
      t.insertBefore(em, im); im.hidden = true;
    });
    stripObserver = new IntersectionObserver(entries => {
      for (const en of entries) if (en.isIntersecting) { const im = en.target.querySelector("img"); if (im && !im.src) im.src = im.dataset.src; stripObserver.unobserve(en.target); }
    }, { root: stripRow, rootMargin: "0px 600px" });
    for (const t of stripRow.children) stripObserver.observe(t);
  }
  function openStrip() {
    buildStrip();
    strip.hidden = false; body.classList.add("strip-open"); body.classList.remove("hide-bars");
    for (const t of stripRow.children) t.classList.toggle("cur", shown.includes(+t.dataset.n));
    const cur = stripRow.children[current];
    if (cur) stripRow.scrollLeft = cur.offsetLeft - stripRow.clientWidth / 2 + cur.offsetWidth / 2;
  }
  function closeStrip() { strip.hidden = true; body.classList.remove("strip-open"); scheduleHide(); }
  /* Couverture choisie à la main : n'importe quelle page de l'album (gardée dans la base de Bulle, le fichier n'est pas touché). */
  function coverPage() { return item && Number.isInteger(item.cover_page) ? item.cover_page : 0; }
  function markCoverThumb() {
    for (const t of stripRow.children) t.classList.toggle("iscover", +t.dataset.n === coverPage());
  }
  async function setCoverPage(n) {
    try {
      const r = await fetch(`/api/covers/page/${id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: n }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.statusText);
      item.cover_page = j.cover_page ?? 0;
      markCoverThumb();
      flash(n === 0 ? "Couverture : première page" : `Page ${n + 1} choisie comme couverture`);
    } catch (e) { flash(`Couverture non changée : ${e.message}`); }
  }
  const toggleStrip = () => strip.hidden ? openStrip() : closeStrip();
  stage.addEventListener("contextmenu", e => { if (e.target.closest(".rmsg")) return; e.preventDefault(); toggleStrip(); });
  strip.addEventListener("contextmenu", e => { e.preventDefault(); closeStrip(); });
  strip.addEventListener("wheel", e => { e.preventDefault(); stripRow.scrollLeft += (Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX) * (manga ? -1 : 1); }, { passive: false });
  strip.addEventListener("click", e => {
    const sc = e.target.closest("[data-setcover]");
    if (sc) { e.preventDefault(); e.stopPropagation(); setCoverPage(+sc.dataset.setcover); return; }
    const t = e.target.closest(".sthumb");
    if (t) { closeStrip(); go(+t.dataset.n); return; }
    if (e.target === strip) closeStrip();
  });

  // ---------------------------------------------------------------- souris / tactile sur la page
  let touch = null;
  stage.addEventListener("touchstart", e => {
    if (e.touches.length !== 1) { touch = null; return; }
    touch = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
  }, { passive: true });
  stage.addEventListener("touchend", e => {
    if (!touch || e.changedTouches.length !== 1) return;
    const dx = e.changedTouches[0].clientX - touch.x, dy = e.changedTouches[0].clientY - touch.y, dt = Date.now() - touch.t;
    touch = null;
    const reframed = panelDragEnd();
    const flick = Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < (reframed ? 350 : 600);
    if (reframed && !flick) return;   // recadrage à la main : on garde la case où elle est
    if (userZoom <= 1 && mode !== "scroll" && flick && (fit !== "original" || mode === "panels")) {
      if (reframed) { panelOff.x = panelDrag ? panelOff.x : 0; panelOff.y = 0; }
      dx < 0 ? forward() : backward();  // balayage vers la gauche = avancer (sens occidental)
      e.preventDefault();
    }
  });
  stage.addEventListener("click", e => {
    if (e.target.closest(".rmsg")) return;
    if (dragMoved) { dragMoved = false; return; }
    if (!strip.hidden) { closeStrip(); return; }
    const w = stage.clientWidth, x = e.clientX;
    if (mode !== "scroll" && prefs.reader_tap_zones && x < w * 0.3) backward();
    else if (mode !== "scroll" && prefs.reader_tap_zones && x > w * 0.7) forward();
    else toggleBars();
  });
  /* Molette : un cran = un pas, même si le navigateur (défilement lisse) ou le pavé tactile (inertie) envoient
     une rafale d'événements : tous les événements d'un même geste (espacés de moins de 200 ms) comptent pour un. */
  const wheelStream = { last: 0, used: false };
  stage.addEventListener("wheel", e => {
    if (e.ctrlKey || e.metaKey || userZoom > 1) return;
    if (mode === "scroll" || !prefs.reader_wheel || (mode === "single" && fit !== "page")) return;
    const now = Date.now();
    const sameGesture = now - wheelStream.last < 200;
    wheelStream.last = now;
    if (sameGesture && wheelStream.used) return;
    if (!sameGesture) wheelStream.used = false;
    if (Math.abs(e.deltaY) < 3) return;
    wheelStream.used = true;
    if (busy()) { if (mode === "panels") queueStep(e.deltaY > 0 ? 1 : -1); return; }   // planche en cours de chargement : le pas est gardé (3 maxi)
    if (mode === "panels") { panelStep(e.deltaY > 0 ? 1 : -1); return; }
    if (e.deltaY > 0) next(); else prev();
  }, { passive: true });

  // ---------------------------------------------------------------- clavier
  document.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.repeat && (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === " ")) { e.preventDefault(); return; }
    if (busy() && (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === " ") && mode === "panels") { queueStep((e.key === "ArrowLeft") !== manga ? -1 : 1); e.preventDefault(); return; }
    if (!endEl.hidden && e.key === "Enter" && item && item.next) { location.href = `/read/${item.next.id}?page=0`; return; }
    if (!strip.hidden && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
      e.preventDefault();
      const cur = +((stripRow.querySelector(".sel") || stripRow.children[current] || {}).dataset || {}).n || current;
      const n = Math.max(0, Math.min(pages - 1, cur + ((e.key === "ArrowRight") !== manga ? 1 : -1)));
      for (const t of stripRow.children) t.classList.toggle("sel", +t.dataset.n === n);
      const el = stripRow.children[n]; if (el) stripRow.scrollTo({ left: el.offsetLeft - stripRow.clientWidth / 2 + el.offsetWidth / 2, behavior: "smooth" });
      return;
    }
    if (!strip.hidden && e.key === "Enter") { const sel = stripRow.querySelector(".sel"); closeStrip(); if (sel) go(+sel.dataset.n); e.preventDefault(); return; }
    switch (e.key) {
      case "ArrowRight": forward(); break;
      case "ArrowLeft": backward(); break;
      case "PageDown": next(); break;
      case "PageUp": prev(); break;
      case " ": {
        if (mode === "scroll" || (mode === "single" && fit !== "page")) {
          const canScroll = stage.scrollHeight - stage.clientHeight - stage.scrollTop > 2;
          if (e.shiftKey ? stage.scrollTop > 2 : canScroll) { stage.scrollBy({ top: (e.shiftKey ? -1 : 1) * stage.clientHeight * 0.9, behavior: "smooth" }); break; }
          if (mode === "scroll" && !e.shiftKey) { showEnd(); break; }
        }
        e.shiftKey ? prev() : next(); break;
      }
      case "Home": go(0); break;
      case "End": go(pages - 1); break;
      case "f": case "F": cycleFit(); break;
      case "d": case "D": cycleMode(); break;
      case "c": case "C": togglePanels(); break;
      case "m": case "M": toggleManga(); break;
      case "r": case "R": toggleTrim(); break;
      case "p": case "P": toggleFullscreen(); break;
      case "Escape": if (!strip.hidden) closeStrip(); else if (userZoom !== 1) resetZoom(); else if (!endEl.hidden) hideEnd(); else if (document.fullscreenElement) document.exitFullscreen(); else location.href = folderHref; break;
      case "+": case "=": $("#zoomin").click(); break;
      case "-": $("#zoomout").click(); break;
      case "0": resetZoom(); break;
      case "t": case "T": toggleStrip(); break;
      case "b": case "B": toggleBars(); break;
      default: return;
    }
    e.preventDefault();
  });

  // ---------------------------------------------------------------- boutons
  $("#prev").addEventListener("click", e => { e.stopPropagation(); prev(); });
  $("#next").addEventListener("click", e => { e.stopPropagation(); next(); });
  modeBtn.addEventListener("click", cycleMode);
  $("#panels").addEventListener("click", togglePanels);
  $("#thumbs").addEventListener("click", e => { e.stopPropagation(); toggleStrip(); });
  fitBtn.addEventListener("click", cycleFit);
  mangaBtn.addEventListener("click", toggleManga);
  fsBtn.addEventListener("click", toggleFullscreen);
  // boutons − / + : un cran de 25 %, avec un arrêt à 100 % (la taille d'ajustement) quand on passe d'un côté à l'autre
  $("#zoomout").addEventListener("click", () => { const z = userZoom / 1.25; setZoom(userZoom > 1 && z < 1 ? 1 : z); });
  $("#zoomin").addEventListener("click", () => { const z = userZoom * 1.25; setZoom(userZoom < 1 && z > 1 ? 1 : z); });
  slider.addEventListener("input", () => { countEl.textContent = `${slider.value} / ${pages}`; });
  slider.addEventListener("change", () => go(+slider.value - 1));
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (current >= 0 && mode !== "scroll" && (fit !== "original" || mode === "panels")) { images.clear(); go(current, { save: false, panel: "keep" }); } }, 300);
  });

  init();
})();
