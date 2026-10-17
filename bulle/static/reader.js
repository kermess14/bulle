/* Bulle — le lecteur : 1 page, 2 pages (double page) ou défilement continu */
(() => {
  "use strict";
  const $ = sel => document.querySelector(sel);
  const body = document.body, stage = $("#stage"), loading = $("#loading");
  const single = $("#single"), img = $("#page"), spread = $("#spread"), imgA = $("#pageA"), imgB = $("#pageB"), scrollEl = $("#scroll");
  const slider = $("#slider"), countEl = $("#rcount"), nameEl = $("#rname"), folderEl = $("#rfolder");
  const modeBtn = $("#mode"), fitBtn = $("#fit"), mangaBtn = $("#manga"), fsBtn = $("#fs"), backBtn = $("#back"), endEl = $("#end");

  const id = +(/\/read\/(\d+)/.exec(location.pathname) || [])[1];
  const params = new URLSearchParams(location.search);
  const FITS = ["page", "width", "original"], MODES = ["single", "double", "scroll"];
  const FIT_LABEL = { page: "Page", width: "Largeur", original: "1:1" };
  const MODE_LABEL = { single: "1 page", double: "2 pages", scroll: "Défilement" };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- réglages (profil, serveur) + mémoire par album (navigateur)
  const DEFAULTS = {
    reader_fit: "page", reader_manga: false, reader_bg: "black", reader_preload: 3, reader_quality: "normal",
    reader_bars_delay: 2.5, reader_tap_zones: true, reader_wheel: true, reader_night: 0, reader_remember_album: true,
    reader_mode: "single", reader_cover_alone: true, reader_scroll_width: 100,
  };
  const prefs = Object.assign({}, DEFAULTS);
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
  let loadToken = 0, hideTimer = null, saveTimer = null, lastSavedPage = -1;

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
    if (r.status === 401) { showMessage("Code d'accès requis", "Ouvrez d'abord la bibliothèque pour entrer le code.", `<a class="btn" href="/">Ouvrir Bulle</a>`); return; }
    if (s && s.profile) { Object.assign(prefs, pick(s.profile)); fit = prefs.reader_fit; manga = !!prefs.reader_manga; mode = MODES.includes(prefs.reader_mode) ? prefs.reader_mode : "single"; applyPrefs(); }
    if (s && s.global && s.global.img_tag) imgTag = s.global.img_tag;
    loadAlbumMemory();
    if (!r.ok) { showMessage("Introuvable", item.error || "", `<a class="btn" href="/">Retour</a>`); return; }
    nameEl.textContent = item.meta && item.meta.title ? `${item.meta.number != null ? "T" + item.meta.number + " · " : ""}${item.meta.title}` : item.name;
    document.title = `${item.name} — Bulle`;
    const crumbs = item.breadcrumb || [];
    folderEl.textContent = crumbs.slice(1).map(c => c.name).join(" › ");
    const parent = crumbs[crumbs.length - 1];
    folderHref = parent && parent.id ? `/#/f/${parent.id}` : "/";
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
    if (!document.fullscreenEnabled) fsBtn.hidden = true;
    go(Math.min(Math.max(0, start), pages - 1), { save: false });
    scheduleHide();
  }

  // ---------------------------------------------------------------- largeur d'image demandée au serveur
  function wantedWidth(n) {
    if (prefs.reader_quality === "original" || (mode === "single" && fit === "original")) return 0;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const vw = stage.clientWidth || window.innerWidth, vh = stage.clientHeight || window.innerHeight;
    const asp = aspects[n] || 0.7;
    let css;
    if (mode === "scroll") css = vw * (Math.max(30, Math.min(100, +prefs.reader_scroll_width || 100)) / 100);
    else if (mode === "double") css = Math.min(vw / 2, vh * asp);
    else css = fit === "width" ? vw : Math.min(vw, vh * asp);
    const factor = prefs.reader_quality === "high" ? 1.5 : 1;
    return Math.ceil(css * dpr * factor);
  }
  let imgTag = "";
  const pageUrl = n => `/api/page/${id}/${n}?w=${wantedWidth(n)}&v=${item.mtime}&t=${encodeURIComponent(imgTag)}`;

  function loadImage(n) {
    const url = pageUrl(n);
    const cached = images.get(n);
    if (cached && cached.src.endsWith(url)) return cached.decoded || (cached.decoded = waitFor(cached, n));
    const im = new Image();
    im.src = url;
    images.set(n, im);
    im.decoded = waitFor(im, n);
    return im.decoded;
  }
  function waitFor(im, n) {
    return new Promise(resolve => {
      const done = () => { if (im.naturalWidth) aspects[n] = im.naturalWidth / im.naturalHeight; resolve(im.naturalWidth ? im : null); };
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
  async function go(n, { save = true } = {}) {
    if (n < 0) { flash("Début de l'album"); return; }
    if (n >= pages) { showEnd(); return; }
    hideEnd();
    if (mode === "scroll") { scrollToPage(n, save); return; }
    const token = ++loadToken;
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
    } else {
      const a = await loadImage(n);
      if (token !== loadToken) return;
      list = [n];
      single.hidden = false; spread.hidden = true;
      if (a) img.src = a.src; else { img.removeAttribute("src"); reportError(n); }
    }
    clearTimeout(spin); loading.hidden = true;
    current = n; shown = list;
    stage.scrollTop = 0; stage.scrollLeft = 0;
    updateCounter();
    if (save) saveProgress(n);
    const u = new URL(location.href); u.searchParams.set("page", n); history.replaceState(null, "", u);
    preloadAround(list[list.length - 1]);
  }
  function updateCounter() {
    const label = shown.length === 2 ? `${shown[0] + 1}-${shown[1] + 1}` : `${current + 1}`;
    countEl.textContent = `${label} / ${pages}`;
    slider.value = current + 1;
  }
  function preloadAround(n) {
    const count = Math.max(0, Math.min(10, +prefs.reader_preload || 0));
    for (let k = 1; k <= count; k++) if (n + k < pages) loadImage(n + k);
    if (n - 1 >= 0) loadImage(n - 1);
    for (const k of [...images.keys()]) if (Math.abs(k - n) > count + 4) images.delete(k);
  }
  async function next() {
    if (mode === "scroll") { scrollStep(1); return; }
    go(shown.length ? shown[shown.length - 1] + 1 : current + 1);
  }
  async function prev() {
    if (mode === "scroll") { scrollStep(-1); return; }
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
    FITS.forEach(f => body.classList.toggle("fit-" + f, f === fit));
    fitBtn.textContent = FIT_LABEL[fit];
    fitBtn.disabled = mode !== "single";
  }
  function applyMode() {
    MODES.forEach(m => body.classList.toggle("mode-" + m, m === mode));
    modeBtn.textContent = MODE_LABEL[mode];
    single.hidden = mode !== "single"; spread.hidden = mode !== "double"; scrollEl.hidden = mode !== "scroll";
    if (mode === "scroll") buildScroll();
    applyFit();
  }
  function cycleFit() {
    if (mode !== "single") { flash("L'ajustement ne s'applique qu'en mode 1 page"); return; }
    fit = FITS[(FITS.indexOf(fit) + 1) % FITS.length];
    applyFit(); saveAlbumMemory();
    images.clear();
    flash({ page: "Page entière", width: "Pleine largeur", original: "Taille d'origine" }[fit]);
    if (current >= 0) go(current, { save: false });
  }
  function cycleMode() {
    const keep = current;
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    images.clear();
    applyMode(); saveAlbumMemory();
    flash({ single: "Une page", double: "Deux pages (planches larges et couverture seules)", scroll: "Défilement continu" }[mode]);
    if (keep >= 0) go(keep, { save: false });
  }
  function applyManga(announce = true) {
    mangaBtn.classList.toggle("on", manga);
    slider.style.direction = manga ? "rtl" : "ltr";
    spread.classList.toggle("rtl", manga);
    if (announce) flash(manga ? "Sens manga : lecture de droite à gauche" : "Sens occidental : lecture de gauche à droite");
  }
  function toggleManga() { manga = !manga; applyManga(); saveAlbumMemory(); }
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  }
  let flashEl = null;
  function flash(text) {
    if (flashEl) flashEl.remove();
    flashEl = document.createElement("div");
    flashEl.className = "hint"; flashEl.textContent = text;
    body.appendChild(flashEl);
    setTimeout(() => { if (flashEl) { flashEl.remove(); flashEl = null; } }, 1400);
  }

  // ---------------------------------------------------------------- barres : auto-masquage
  function scheduleHide() {
    clearTimeout(hideTimer);
    const delay = Math.max(500, (+prefs.reader_bars_delay || 2.5) * 1000);
    hideTimer = setTimeout(() => { if (!overBar && endEl.hidden) body.classList.add("hide-bars"); }, delay);
  }
  let overBar = false;
  for (const bar of document.querySelectorAll(".rbar")) {
    bar.addEventListener("mouseenter", () => { overBar = true; });
    bar.addEventListener("mouseleave", () => { overBar = false; scheduleHide(); });
  }
  let lastMove = 0;
  document.addEventListener("mousemove", e => {
    if (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents) return;
    const now = Date.now(); if (now - lastMove < 100) return; lastMove = now;
    body.classList.remove("hide-bars"); scheduleHide();
  });
  const toggleBars = () => { body.classList.toggle("hide-bars"); if (!body.classList.contains("hide-bars")) scheduleHide(); };

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
    if (mode !== "scroll" && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < 600 && fit !== "original") {
      dx < 0 ? forward() : backward();  // balayage vers la gauche = avancer (sens occidental)
      e.preventDefault();
    }
  });
  stage.addEventListener("click", e => {
    if (e.target.closest(".rmsg")) return;
    const w = stage.clientWidth, x = e.clientX;
    if (mode !== "scroll" && prefs.reader_tap_zones && x < w * 0.3) backward();
    else if (mode !== "scroll" && prefs.reader_tap_zones && x > w * 0.7) forward();
    else toggleBars();
  });
  let wheelLock = 0;
  stage.addEventListener("wheel", e => {
    if (mode === "scroll" || !prefs.reader_wheel || (mode === "single" && fit !== "page")) return;
    const now = Date.now(); if (now - wheelLock < 250) return; wheelLock = now;
    if (e.deltaY > 0) next(); else if (e.deltaY < 0) prev();
  }, { passive: true });

  // ---------------------------------------------------------------- clavier
  document.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (!endEl.hidden && e.key === "Enter" && item && item.next) { location.href = `/read/${item.next.id}?page=0`; return; }
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
      case "m": case "M": toggleManga(); break;
      case "p": case "P": toggleFullscreen(); break;
      case "Escape": if (!endEl.hidden) hideEnd(); else if (document.fullscreenElement) document.exitFullscreen(); else location.href = folderHref; break;
      case "b": case "B": toggleBars(); break;
      default: return;
    }
    e.preventDefault();
  });

  // ---------------------------------------------------------------- boutons
  $("#prev").addEventListener("click", e => { e.stopPropagation(); prev(); });
  $("#next").addEventListener("click", e => { e.stopPropagation(); next(); });
  modeBtn.addEventListener("click", cycleMode);
  fitBtn.addEventListener("click", cycleFit);
  mangaBtn.addEventListener("click", toggleManga);
  fsBtn.addEventListener("click", toggleFullscreen);
  slider.addEventListener("input", () => { countEl.textContent = `${slider.value} / ${pages}`; });
  slider.addEventListener("change", () => go(+slider.value - 1));
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (current >= 0 && mode !== "scroll" && fit !== "original") { images.clear(); go(current, { save: false }); } }, 300);
  });

  init();
})();
