/* Bulle — le lecteur */
(() => {
  "use strict";
  const $ = sel => document.querySelector(sel);
  const body = document.body, stage = $("#stage"), img = $("#page"), loading = $("#loading");
  const slider = $("#slider"), countEl = $("#rcount"), nameEl = $("#rname"), folderEl = $("#rfolder");
  const fitBtn = $("#fit"), mangaBtn = $("#manga"), fsBtn = $("#fs"), backBtn = $("#back"), endEl = $("#end");

  const id = +(/\/read\/(\d+)/.exec(location.pathname) || [])[1];
  const params = new URLSearchParams(location.search);
  const FITS = ["page", "width", "original"];
  const FIT_LABEL = { page: "Page", width: "Largeur", original: "1:1" };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- réglages mémorisés (par album + défaut)
  const store = {
    get(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (_) { return null; } },
    set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) { /* ignore */ } },
  };
  const defaults = Object.assign({ fit: "page", manga: false }, store.get("bulle:reader:default") || {});
  const perAlbum = store.get(`bulle:reader:${id}`) || {};
  let fit = FITS.includes(perAlbum.fit) ? perAlbum.fit : defaults.fit;
  let manga = typeof perAlbum.manga === "boolean" ? perAlbum.manga : defaults.manga;
  function saveSettings() {
    store.set(`bulle:reader:${id}`, { fit, manga });
    store.set("bulle:reader:default", { fit, manga: defaults.manga });
  }

  // ---------------------------------------------------------------- état
  let item = null, pages = 0, current = -1, folderHref = "/";
  const preloaded = new Map(); // n -> Image
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
    let r;
    try {
      r = await fetch(`/api/item/${id}`);
      item = await r.json();
    } catch (e) { showMessage("Impossible de charger l'album", String(e)); return; }
    if (!r.ok) { showMessage("Introuvable", item.error || "", `<a class="btn" href="/">Retour</a>`); return; }
    nameEl.textContent = item.name;
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
    applyFit(); applyManga(false);
    if (!document.fullscreenEnabled) fsBtn.hidden = true;
    go(Math.min(Math.max(0, start), pages - 1), { save: false });
    scheduleHide();
  }

  // ---------------------------------------------------------------- largeur d'image demandée au serveur
  function wantedWidth() {
    if (fit === "original") return 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const vw = stage.clientWidth || window.innerWidth, vh = stage.clientHeight || window.innerHeight;
    const css = fit === "width" ? vw : Math.min(vw, vh * 0.75);
    return Math.ceil(css * dpr);
  }
  const pageUrl = n => `/api/page/${id}/${n}?w=${wantedWidth()}&v=${item.mtime}`;

  // ---------------------------------------------------------------- affichage d'une page
  function go(n, { save = true } = {}) {
    if (n < 0) { flash("Début de l'album"); return; }
    if (n >= pages) { showEnd(); return; }
    hideEnd();
    current = n;
    const token = ++loadToken;
    const url = pageUrl(n);
    const spin = setTimeout(() => { if (token === loadToken) loading.hidden = false; }, 180);
    const pre = preloaded.get(n);
    const show = () => {
      if (token !== loadToken) return;
      clearTimeout(spin); loading.hidden = true;
      img.src = url;
      stage.scrollTop = 0; stage.scrollLeft = 0;
      preloadAround(n);
    };
    if (pre && pre.complete && pre.naturalWidth && pre.src.endsWith(url)) {
      show();
    } else {
      const im = new Image();
      im.onload = show;
      im.onerror = () => {
        if (token !== loadToken) return;
        clearTimeout(spin); loading.hidden = true;
        img.removeAttribute("src");
        fetch(url).then(r => r.json()).then(j => flash(`Page ${n + 1} illisible : ${j.error || ""}`)).catch(() => flash(`Page ${n + 1} illisible`));
      };
      im.src = url;
      preloaded.set(n, im);
    }
    countEl.textContent = `${n + 1} / ${pages}`;
    slider.value = n + 1;
    if (save) saveProgress(n);
    const u = new URL(location.href); u.searchParams.set("page", n); history.replaceState(null, "", u);
  }

  function preloadAround(n) {
    for (const k of [n + 1, n + 2, n + 3, n - 1]) {
      if (k < 0 || k >= pages || preloaded.has(k)) continue;
      const im = new Image();
      im.src = pageUrl(k);
      preloaded.set(k, im);
    }
    for (const k of [...preloaded.keys()]) if (Math.abs(k - n) > 6) preloaded.delete(k);
  }
  const next = () => go(current + 1);
  const prev = () => go(current - 1);
  const forward = () => manga ? prev() : next();   // « vers la droite »
  const backward = () => manga ? next() : prev();  // « vers la gauche »

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
    if (current >= 0) {
      clearTimeout(saveTimer);
      fetch(`/api/progress/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: pages - 1, completed: true }) }).catch(() => {});
      lastSavedPage = pages - 1;
    }
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

  // ---------------------------------------------------------------- ajustement / manga / plein écran
  function applyFit() {
    FITS.forEach(f => body.classList.toggle("fit-" + f, f === fit));
    fitBtn.textContent = FIT_LABEL[fit];
  }
  function cycleFit() {
    fit = FITS[(FITS.indexOf(fit) + 1) % FITS.length];
    applyFit(); saveSettings();
    preloaded.clear();
    flash({ page: "Page entière", width: "Pleine largeur", original: "Taille d'origine" }[fit]);
    if (current >= 0) go(current, { save: false });
  }
  function applyManga(announce = true) {
    mangaBtn.classList.toggle("on", manga);
    slider.style.direction = manga ? "rtl" : "ltr";
    if (announce) flash(manga ? "Sens manga : lecture de droite à gauche" : "Sens occidental : lecture de gauche à droite");
  }
  function toggleManga() { manga = !manga; applyManga(); saveSettings(); }
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
    hideTimer = setTimeout(() => { if (!overBar && endEl.hidden) body.classList.add("hide-bars"); }, 2500);
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
    touch = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now(), sl: stage.scrollLeft };
  }, { passive: true });
  stage.addEventListener("touchend", e => {
    if (!touch || e.changedTouches.length !== 1) return;
    const dx = e.changedTouches[0].clientX - touch.x, dy = e.changedTouches[0].clientY - touch.y, dt = Date.now() - touch.t;
    touch = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < 600 && fit !== "original") {
      dx < 0 ? forward() : backward();  // balayage vers la gauche = avancer (sens occidental)
      e.preventDefault();
    }
  });
  stage.addEventListener("click", e => {
    if (e.target.closest(".rmsg")) return;
    const w = stage.clientWidth, x = e.clientX;
    if (x < w * 0.3) backward();
    else if (x > w * 0.7) forward();
    else toggleBars();
  });
  let wheelLock = 0;
  stage.addEventListener("wheel", e => {
    if (fit !== "page") return; // en largeur / 1:1, la molette fait défiler la page
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
        if (fit !== "page") {
          const canScroll = stage.scrollHeight - stage.clientHeight - stage.scrollTop > 2;
          if (e.shiftKey ? stage.scrollTop > 2 : canScroll) { stage.scrollBy({ top: (e.shiftKey ? -1 : 1) * stage.clientHeight * 0.9, behavior: "smooth" }); break; }
        }
        e.shiftKey ? prev() : next(); break;
      }
      case "Home": go(0); break;
      case "End": go(pages - 1); break;
      case "f": case "F": cycleFit(); break;
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
  fitBtn.addEventListener("click", cycleFit);
  mangaBtn.addEventListener("click", toggleManga);
  fsBtn.addEventListener("click", toggleFullscreen);
  slider.addEventListener("input", () => { countEl.textContent = `${slider.value} / ${pages}`; });
  slider.addEventListener("change", () => go(+slider.value - 1));
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (current >= 0 && fit !== "original") { preloaded.clear(); go(current, { save: false }); } }, 300);
  });

  init();
})();
