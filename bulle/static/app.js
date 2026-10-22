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
      if (r.status === 401 && body && body.auth_required) showPinScreen(body.mode);
      if (r.status === 403 && body && body.adult_locked && !(opts && opts.noAdultPrompt)) {
        if (await adultPrompt()) return api(url, opts);
      }
      throw new Error(msg);
    }
    return r.json();
  }

  // ================================================================ code d'accès (écran)
  let pinShown = false;
  function showPinScreen(mode) {
    if (pinShown) return;
    pinShown = true;
    modal.hidden = false;
    if (mode === "accounts") {
      // connexion par compte : nom + mot de passe (Bulle mis en ligne sur Internet)
      modal.innerHTML = `<div class="backdrop locked"><form class="sheet pin login" id="login-form">
        <h3>Bulle</h3><p class="muted">Connectez-vous avec votre compte.</p>
        <input type="text" name="name" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Nom du compte" autofocus required>
        <input type="password" name="password" autocomplete="current-password" placeholder="Mot de passe" required>
        <div class="actions"><button class="btn primary" type="submit">Se connecter</button></div><p class="error" hidden></p></form></div>`;
      $("#login-form").addEventListener("submit", async e => {
        e.preventDefault();
        const f = e.target, err = f.querySelector(".error");
        try {
          const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: f.elements.name.value, password: f.elements.password.value }) });
          if (!r.ok) { err.textContent = (await r.json().catch(() => ({}))).error || "Connexion refusée"; err.hidden = false; f.elements.password.select(); return; }
          try { localStorage.removeItem("bulle:profile"); } catch (_) { /* ignore */ }
          location.reload();
        } catch (_) { err.textContent = "Serveur injoignable"; err.hidden = false; }
      });
      return;
    }
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

  // ================================================================ rubrique Adulte : invite du code
  let adultPromise = null;
  function adultPrompt() {
    if (adultPromise) return adultPromise;
    adultPromise = new Promise(resolve => {
      modal.hidden = false;
      modal.innerHTML = `<div class="backdrop"><form class="sheet pin adult" id="adult-form">
        <button class="iconbtn close" type="button" data-adult-cancel title="Annuler">${ICON.close}</button>
        <h3>Rubrique Adulte</h3><p class="muted">Cette série fait partie de la rubrique Adulte (18+). Entrez le code pour la voir ; elle reste visible 12 heures sur cet appareil.</p>
        <input type="password" inputmode="numeric" autocomplete="off" name="pin" placeholder="Code" autofocus>
        <div class="actions"><button class="btn primary" type="submit">Déverrouiller</button></div><p class="error" hidden></p></form></div>`;
      const f = $("#adult-form"), done = ok => { adultPromise = null; closeModal(); resolve(ok); };
      f.querySelector("[data-adult-cancel]").addEventListener("click", () => done(false));
      f.parentElement.addEventListener("click", e => { if (e.target === f.parentElement) done(false); });
      f.addEventListener("submit", async e => {
        e.preventDefault();
        const err = f.querySelector(".error");
        try {
          await api("/api/adult/unlock", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin: f.elements.pin.value }), noAdultPrompt: true });
          settings.global.adult_unlocked = true; updateAdultTab(); pow(powFor("adult"), lastPointer.x, lastPointer.y);
          done(true);
        } catch (e2) { err.textContent = e2.message || "Code incorrect"; err.hidden = false; f.elements.pin.select(); }
      });
      f.elements.pin.focus();
    });
    return adultPromise;
  }
  function updateAdultTab() {
    const a = $("#tab-adult");
    if (!a) return;
    const g = settings.global;
    // case « cacher » cochée : jamais ; sinon visible dès qu'un code existe (verrouillée ou non) ou qu'une série est 18+
    a.hidden = !!g.adult_hide_tab || !(g.adult_pin_set || g.adult_count > 0);
    a.classList.toggle("unlocked", !!g.adult_unlocked);
    a.title = g.adult_unlocked ? "Rubrique Adulte (déverrouillée)" : "Rubrique Adulte (code demandé)";
  }

  // ================================================================ profils (« qui lit ? »)
  const initial = n => (n || "?").trim()[0].toUpperCase();
  const isAdmin = () => settings.meta.role === "admin";
  /* Vignette d'un profil : une petite image choisie par l'utilisateur, sinon un emoji ou l'initiale. */
  const AVATAR_IMG = /^data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$/;
  function avatarHtml(p, cls = "") {
    const a = p && p.avatar;
    // seules les petites images PNG/JPEG/WebP/GIF en base64 sont acceptées (jamais de HTML), et tout est échappé
    if (a && AVATAR_IMG.test(a)) return `<img class="pavatar ${esc(cls)}" src="${esc(a)}" alt="">`;
    if (a && a.startsWith("data:")) return `<span class="pavatar ${esc(cls)}">${esc(initial(p ? p.name : "?"))}</span>`;
    return `<span class="pavatar ${esc(cls)}">${esc(a || initial(p ? p.name : "?"))}</span>`;
  }
  function profileTile(p, current) {
    return `<button type="button" class="ptile ${p.id === current ? "on" : ""}" data-profile="${p.id}" data-haspin="${p.has_pin ? 1 : 0}" data-name="${esc(p.name)}">
      ${avatarHtml(p)}<span class="pname">${esc(p.name)}</span>${p.has_pin ? `<span class="plock" title="Protégé par un mot de passe">🔒</span>` : ""}${p.role === "admin" ? `<span class="prole" title="Administrateur">admin</span>` : ""}</button>`;
  }
  async function openProfiles({ locked = false } = {}) {
    if (settings.global && settings.global.account_login) { location.hash = "#/settings/account"; return; }   // un compte = une connexion
    let data;
    try { data = await api("/api/profiles"); } catch (_) { return; }
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop ${locked ? "locked" : ""}"><div class="sheet profiles" role="dialog" aria-modal="true">
      ${locked ? "" : `<button class="iconbtn close" type="button" data-close title="Fermer">${ICON.close}</button>`}
      <h3>Qui lit ?</h3>
      <div class="ptiles">${data.profiles.map(p => profileTile(p, data.selected ? data.current : 0)).join("")}
        ${isAdmin() || data.profiles.length < 2 ? `<button type="button" class="ptile add" data-profile-add><span class="pavatar">+</span><span class="pname">Nouveau profil</span></button>` : ""}</div>
      <p class="muted">Chaque profil a sa propre progression de lecture et ses réglages d'affichage.${locked ? "" : ` <a href="#/settings/account" data-close>Mon compte</a>${isAdmin() ? ` · <a href="#/settings/access" data-close>Gérer les comptes</a>` : ""}`}</p>
      <form class="pin-inline" id="profile-pin" hidden><span></span><input type="password" autocomplete="current-password" name="pin" placeholder="Mot de passe"><button class="btn primary" type="submit">OK</button><p class="error" hidden></p></form>
      <form class="pin-inline" id="profile-new" hidden><input type="text" name="name" placeholder="Prénom" maxlength="40" required><input type="password" autocomplete="new-password" name="pin" placeholder="Mot de passe (facultatif)"><button class="btn primary" type="submit">Créer</button></form>
      ${data.selected ? `<p class="actions"><button class="btn" type="button" data-logout>Se déconnecter</button></p>` : ""}
    </div></div>`;
    const lo = $("[data-logout]");
    if (lo) lo.addEventListener("click", async () => {
      try { await api("/api/profiles/logout", { method: "POST" }); } catch (_) { /* ignore */ }
      try { localStorage.removeItem("bulle:profile"); } catch (_) { /* ignore */ }
      location.reload();
    });
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
    btn.innerHTML = avatarHtml(cur || { name: "?" }, "small");
    btn.title = cur ? `${cur.name}${cur.role === "admin" ? " (administrateur)" : ""} — profil, mon compte, déconnexion` : "Profil";
    btn.hidden = !settings.global.account_login && list.length < 2 && !settings.global.require_profile && !settings.meta.profile_selected;
    const scan = $("#scan-btn"); if (scan) scan.hidden = !isAdmin();
  }
  document.addEventListener("click", e => { if (e.target.closest("#profile-btn")) openProfiles(); });
  const putJson = (url, body) => api(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  // ================================================================ réglages
  const PROFILE_DEFAULTS = {
    thumb_size: "m", hover_zoom: "light", per_page: 48, letters: "auto", letters_side: "right", letters_size: "large",
    tabs_side: "left", cover_style: "book", skin: "bd", settings_layout: "tabs", mosaic: "drift", side_covers: true, mosaic_opacity: 45, mosaic_brightness: 70, mosaic_glass: true, sort: "natural", hide_read: false,
    show_pages: false, show_continue: true, show_recent: true, recent_count: 18, theme: "dark",
    remember_folder: false,
    reader_fit: "page", reader_manga: false, reader_bg: "black", reader_preload: 3, reader_quality: "normal",
    reader_bars_delay: 2.5, reader_tap_zones: true, reader_wheel: true, reader_night: 0, reader_remember_album: true,
    reader_mode: "single", reader_cover_alone: true, reader_scroll_width: 100, reader_panels_full_first: false, reader_trim: false,
    reader_panels_wide: "split", reader_panels_margin: 3, reader_panels_dim: 100, reader_panels_speed: 0.55, reader_panels_join: true,
    bdt_ghosts: true, bdt_titles: false, quality: "all",
  };
  const THUMB = { s: 118, m: 156, l: 200, xl: 250 };
  const SKINS = ["bd", "sobre", "bling", "girly", "ocean", "stars", "riso", "seasons", "fetes"];   // « neon » retiré : retombe sur « bd »
  /* Onomatopées de la colonne de gauche et des petits éclats, par habillage */
  const ONO = {
    bd: ["WIZZ !", "Zzz…", "PAF !", "CLAC", "BOUM", "TADAM !", "ZOU !"],
    bling: ["BLING !", "$$$", "CHA-CHING", "WOW", "DE LUXE", "VIP", "CASH !"],
    girly: ["Trop mignon", "♥ ♥ ♥", "Oh la la", "Youpi !", "Bisous", "Chouette !", "Hihi"],
    ocean: ["BLOUP !", "PLOUF", "GLOU GLOU", "SPLASH !", "BLUB…", "><((°>", "OHÉ !"],
    stars: ["Waouh…", "Fais un vœu", "Scintille", "Ooooh", "Filante !", "Shhh…", "Zénith"],
    riso: ["PHOTOCOPIE", "N° 0", "AGRAFE !", "SCOTCH", "50 EX.", "FAIT MAIN", "ZINE !"],
    spring: ["Ça bourgeonne", "Cui-cui", "Floraison", "Brise", "Pâquerette", "Éclosion", "Printemps !"],
    summer: ["Soleil !", "Glaces", "Farniente", "Plouf", "Cigales", "Sieste", "Été !"],
    autumn: ["Crounch", "Châtaignes", "Feuilles", "Bruine", "Champignons", "Cocooning", "Automne !"],
    winter: ["Brrr…", "Flocons", "Chocolat chaud", "Bonhomme", "Givre", "Plaid", "Hiver !"],
    newyear: ["Bonne année !", "Pop !", "Champagne", "Minuit !", "Bonnes résolutions", "Cotillons", "Meilleurs vœux"],
    valentine: ["♥ ♥ ♥", "Bisous", "Mon cœur", "Coup de foudre", "Je t'aime", "Mamour", "Saint-Valentin"],
    easter: ["Cloches !", "Chocolat", "Chasse aux œufs", "Lapin !", "Cot cot", "Miam", "Joyeuses Pâques"],
    music: ["Do ré mi", "Tchic boum", "Lalala", "Rock !", "Ouh ouh", "Bis !", "Fête de la musique"],
    bastille: ["Boum !", "Bal !", "Cocarde", "Pschiii", "Défilé", "Lampions", "14 juillet"],
    holidays: ["Vacances !", "Plouf", "Crème solaire", "Pétanque", "Sieste", "Glace !", "Farniente"],
    halloween: ["Bouh !", "Mouahaha", "Des bonbons !", "Brrr…", "Sorcière", "Citrouille", "Halloween"],
    christmas: ["Ho ho ho !", "Joyeux Noël", "Guirlandes", "Cadeaux !", "Sapin", "Papillotes", "Ding dong"],
  };
  const POWS = {
    bd: { fav: ["HOP !", "YES !", "TOP !"], list: ["PAF !", "TCHAC !", "HOP !"], read: ["FINI !", "BRAVO !"], random: ["ZOU !", "TADAM !"], adult: ["CHUT…", "PSSST"] },
    bling: { fav: ["BLING !", "WOW !"], list: ["CHA-CHING", "VIP !"], read: ["JACKPOT !", "BRAVO !"], random: ["CASH !", "TADAM !"], adult: ["PRIVÉ", "VIP"] },
    girly: { fav: ["♥ ♥ ♥", "Trop bien !"], list: ["Hop !", "Youpi !"], read: ["Bravo !", "Fini !"], random: ["Surprise !", "Tadam !"], adult: ["Chut…", "Oh !"] },
    ocean: { fav: ["BLOUP !", "PÊCHÉ !"], list: ["PLOUF !", "SPLASH !"], read: ["REMONTÉE !", "BRAVO !"], random: ["À L'EAU !", "PLOUF !"], adult: ["ABYSSES", "GLOU…"] },
    stars: { fav: ["✦ Étoile !", "Brille !"], list: ["Rangé !", "Constellé"], read: ["Bravo !", "Fin…"], random: ["Vœu !", "Filante !"], adult: ["Nuit noire", "Shhh…"] },
    riso: { fav: ["COUP DE CŒUR", "TAMPONNÉ"], list: ["AGRAFÉ !", "CLAC !"], read: ["LU & APPROUVÉ", "FIN"], random: ["AU PIF !", "TIRAGE !"], adult: ["CENSURÉ", "X"] },
    seasons: { fav: ["Coup de cœur !", "Chouette !"], list: ["Rangé !", "Hop !"], read: ["Bravo !", "Fini !"], random: ["Surprise !", "Au hasard !"], adult: ["Chut…", "Psst"] },
  };
  /* Habillage Fêtes : la fête du moment (sinon la prochaine), affichée avec la mise en page de « Quatre saisons »
     (data-skin="seasons", data-season=<la fête>) ; chaque fête emprunte des motifs à une saison (FETE_BASE). */
  const FETES = {
    newyear: { label: "Jour de l'an", emoji: "🎆" }, valentine: { label: "Saint-Valentin", emoji: "💘" },
    easter: { label: "Pâques", emoji: "🥚" }, music: { label: "Fête de la musique", emoji: "🎵" },
    bastille: { label: "14 juillet", emoji: "🎇" }, holidays: { label: "Grandes vacances", emoji: "🏖️" },
    halloween: { label: "Halloween", emoji: "🎃" }, christmas: { label: "Noël", emoji: "🎄" },
  };
  const FETE_ORDER = ["newyear", "valentine", "easter", "music", "bastille", "holidays", "halloween", "christmas"];
  const FETE_BASE = { christmas: "winter", newyear: "winter", valentine: "spring", easter: "spring", music: "summer", holidays: "summer", bastille: "summer", halloween: "autumn" };
  function easterDay(y) {   // dimanche de Pâques (calendrier grégorien)
    const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3);
    const h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(y, month - 1, day);
  }
  /* Périodes de chaque fête pour une année : [début, fin] inclus (le 14 juillet passe avant les grandes vacances). */
  function feteRanges(y) {
    const D = (m, d) => new Date(y, m - 1, d), e = easterDay(y), add = (dt, n) => new Date(dt.getFullYear(), dt.getMonth(), dt.getDate() + n);
    return [["newyear", new Date(y - 1, 11, 27), D(1, 7)], ["valentine", D(2, 7), D(2, 15)], ["easter", add(e, -10), add(e, 1)],
      ["music", D(6, 17), D(6, 22)], ["bastille", D(7, 10), D(7, 15)], ["holidays", D(7, 1), D(8, 31)],
      ["halloween", D(10, 15), D(11, 2)], ["christmas", D(12, 1), D(12, 26)], ["newyear", D(12, 27), new Date(y + 1, 0, 7)]];
  }
  /* La fête en cours, sinon la prochaine : { key, now: vrai si on est dedans } */
  function currentFete(d = new Date()) {
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    for (const [k, a, b] of feteRanges(d.getFullYear())) if (day >= a && day <= b) return { key: k, now: true };
    const next = [...feteRanges(d.getFullYear()), ...feteRanges(d.getFullYear() + 1)].filter(([, a]) => a > day).sort((x, y) => x[1] - y[1])[0];
    return { key: next ? next[0] : "christmas", now: false };
  }
  const feteMode = () => settings.profile.skin === "fetes";
  /* Saison du moment (hémisphère nord, dates des équinoxes et solstices arrondies) ; réglable à la main */
  function currentSeason(d = new Date()) {
    const md = (d.getMonth() + 1) * 100 + d.getDate();
    return md >= 1221 || md < 320 ? "winter" : md < 621 ? "spring" : md < 922 ? "summer" : "autumn";
  }
  /* Mode léger (bouton « planche de BD » à côté du champignon) : coupe tout ce qui bouge en arrière-plan (mosaïque,
     verre dépoli, couvertures au hasard, bulles, saisons, petits mots animés). Mémorisé sur l'appareil, pas sur le
     profil : léger sur la tablette, complet sur le PC. */
  /* Trois niveaux, un clic passe au suivant : complet → léger → « BD seules » → complet.
     « BD seules » (le plus économe) : en plus du mode léger, plus de menu ni de barre de boutons, plus de « Reprendre
     la lecture » ni d'« Ajouts récents » (rien n'est demandé au serveur pour eux), plus de panneau Bédéthèque ni de
     boutons de série : juste le fil d'Ariane, la recherche et les couvertures, sur un fond uni, sans ombre ni effet. */
  function liteLevel() { try { const v = localStorage.getItem("bulle:lite"); return v === "2" ? 2 : v === "1" ? 1 : 0; } catch (_) { return 0; } }
  function liteMode() { return liteLevel() > 0; }
  function ultraMode() { return liteLevel() === 2; }
  // Présentation téléphone : barre d'onglets en bas, pochettes à trois, fiche qui monte du bas, réglages en liste,
  // rien qui bouge en arrière-plan. SEULEMENT dans l'appli « Bulle pour Android » (elle se signale dans son
  // identifiant de navigateur) et sur un écran de 700 px ou moins. Dans un navigateur, même sur téléphone, et sur
  // tablette comme sur PC, Bulle garde sa présentation habituelle.
  const inApp = /BulleAndroid\//.test(navigator.userAgent);
  const isPhone = () => inApp && window.innerWidth <= 700;
  function updateLiteBtn() {
    const b = $("#lite-btn"); if (!b) return;
    const lvl = liteLevel();
    b.classList.toggle("on", lvl > 0); b.classList.toggle("ultra", lvl === 2); b.setAttribute("aria-pressed", lvl ? "true" : "false");
    b.title = lvl === 2 ? "Mode « BD seules » : rien que les albums, le plus économe (cliquer pour revenir au mode complet)"
      : lvl === 1 ? "Mode léger : rien ne bouge en arrière-plan (cliquer pour le mode « BD seules », encore plus économe)"
      : "Mode léger : couper les animations et effets de fond pour un affichage plus fluide";
  }
  document.addEventListener("click", e => {
    if (!e.target.closest("#lite-btn")) return;
    const next = (liteLevel() + 1) % 3;
    try { localStorage.setItem("bulle:lite", String(next)); } catch (_) { /* ignore */ }
    applyAppearance(); updateLiteBtn();
    toast(next === 2 ? "Mode « BD seules » : rien que les albums, le plus économe (le même bouton pour revenir)"
      : next === 1 ? "Mode léger : animations et effets de fond coupés sur cet appareil"
      : "Mode complet : menus, animations et effets rétablis");
    if (!location.hash.startsWith("#/settings")) route();
  });
  const SEASON_LABEL = { spring: "printemps", summer: "été", autumn: "automne", winter: "hiver" };
  const SEASON_ORDER = ["spring", "summer", "autumn", "winter"], SEASON_EMOJI = { spring: "🌸", summer: "☀️", autumn: "🍂", winter: "❄️" };
  /* Bouton de saison : il affiche l'emblème de la saison en cours (🍂 en automne…) ; un clic passe à la suivante.
     En revenant à la saison du calendrier, on repasse en « selon la date ». */
  function updateSeasonBtn() {
    const b = $("#season-btn"); if (!b) return;
    if (feteMode()) {
      const cur = document.documentElement.dataset.season, cf = currentFete();
      const next = FETE_ORDER[(FETE_ORDER.indexOf(cur) + 1) % FETE_ORDER.length];
      b.textContent = (FETES[cur] || FETES.christmas).emoji;
      b.title = `Fête : ${(FETES[cur] || FETES.christmas).label}${!FETES[settings.profile.fete] ? (cf.now ? " (selon la date)" : " (la prochaine)") : ""} — cliquer pour voir : ${FETES[next].label}`;
      return;
    }
    const cur = document.documentElement.dataset.season || currentSeason();
    const next = SEASON_ORDER[(SEASON_ORDER.indexOf(cur) + 1) % 4];
    const auto = !["spring", "summer", "autumn", "winter"].includes(settings.profile.season);
    b.textContent = SEASON_EMOJI[cur];
    b.title = `Saison : ${SEASON_LABEL[cur]}${auto ? " (selon la date)" : ""} — cliquer pour passer ${next === "autumn" ? "à l'" : next === "summer" ? "à l'" : next === "winter" ? "à l'" : "au "}${SEASON_LABEL[next]}`;
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("#season-btn"); if (!b) return;
    if (feteMode()) {
      const cur = document.documentElement.dataset.season, auto = currentFete().key;
      const next = FETE_ORDER[(FETE_ORDER.indexOf(cur) + 1) % FETE_ORDER.length];
      b.classList.remove("turn"); void b.offsetWidth; b.classList.add("turn");
      saveSettings({ fete: next === auto ? "auto" : next }, null, { quiet: true });
      toast(`${FETES[next].emoji} ${FETES[next].label}${next === auto ? (currentFete().now ? " (la fête du moment)" : " (la prochaine fête)") : ""}`);
      if (location.hash.startsWith("#/settings")) route();
      return;
    }
    const cur = document.documentElement.dataset.season || currentSeason();
    const next = SEASON_ORDER[(SEASON_ORDER.indexOf(cur) + 1) % 4];
    b.classList.remove("turn"); void b.offsetWidth; b.classList.add("turn");
    saveSettings({ season: next === currentSeason() ? "auto" : next }, null, { quiet: true });
    toast(`${SEASON_EMOJI[next]} ${SEASON_LABEL[next][0].toUpperCase() + SEASON_LABEL[next].slice(1)}${next === currentSeason() ? " (la saison du calendrier)" : ""}`);
    if (location.hash.startsWith("#/settings")) route();
  });
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
    root.dataset.phone = isPhone() ? "on" : "off";
    root.dataset.covers = ultraMode() ? "flat" : ["book", "glow", "flat"].includes(p.cover_style) ? p.cover_style : "book";
    const fete = p.skin === "fetes";
    root.dataset.skin = fete ? "seasons" : SKINS.includes(p.skin) ? p.skin : "bd";   // Fêtes : la mise en page de Quatre saisons
    const season = fete ? (FETES[p.fete] ? p.fete : currentFete().key)
      : ["spring", "summer", "autumn", "winter"].includes(p.season) ? p.season : currentSeason();
    if (root.dataset.skin === "seasons") root.dataset.season = season; else delete root.dataset.season;
    if (fete) root.dataset.fete = "on"; else delete root.dataset.fete;
    const words = root.dataset.skin === "seasons" ? ONO[season] : ONO[root.dataset.skin];
    if (words) document.querySelectorAll("#maintabs .ono").forEach((el, i) => { el.textContent = words[i % words.length]; });
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lite = liteMode() || isPhone();   // sur téléphone, le décor animé est toujours coupé
    root.dataset.lite = liteMode() ? "on" : "off";
    root.dataset.ultra = ultraMode() ? "on" : "off";
    root.dataset.mosaic = lite || p.mosaic === "off" ? "off" : (p.mosaic === "fixed" || reduce) ? "fixed" : "drift";
    root.dataset.glass = !lite && p.mosaic_glass !== false && root.dataset.mosaic !== "off" ? "on" : "off";
    root.style.setProperty("--mosaic-opacity", String(Math.max(5, Math.min(100, +p.mosaic_opacity || 45)) / 100));
    root.style.setProperty("--mosaic-brightness", String(Math.max(10, Math.min(150, +p.mosaic_brightness || 70)) / 100));
    $('meta[name="theme-color"]').setAttribute("content", theme === "light" ? "#f4f5f8" : "#0f1115");
    setupMosaic();
    setupSideCovers();
    setupBubbles();
    setupSeasonFx();
    updateSeasonBtn();
    updateLiteBtn();
  }

  // ================================================================ quatre saisons : ce qui flotte dans l'air
  /* Une seule toile (canvas) derrière le contenu, animée image par image. Les motifs sont dessinés une fois pour
     toutes dans de petites images (« sprites ») puis recopiés à chaque image, pour rester fluide même avec beaucoup
     d'éléments : printemps, pétales de toutes les couleurs et petites fleurs ; été, lucioles, aigrettes de pissenlit
     et papillons ; automne, feuilles d'érable, de chêne et de bouleau qui tournoient ; hiver, vrais flocons à six
     branches et neige fine. Le nombre s'adapte à la taille de l'écran ; tout s'arrête quand l'onglet est caché, et
     rien n'est animé si l'appareil demande moins d'animations. */
  let seasonFx = null;
  function setupSeasonFx() {
    const root = document.documentElement, want = root.dataset.skin === "seasons" && !liteMode() && !isPhone() && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    const kind = want ? root.dataset.season : null;
    const theme = root.dataset.theme;
    if (seasonFx && seasonFx.kind === kind && seasonFx.theme === theme) return;
    if (seasonFx) { cancelAnimationFrame(seasonFx.raf); window.removeEventListener("resize", seasonFx.resize); seasonFx.canvas.remove(); seasonFx = null; }
    if (!kind) return;
    const canvas = document.createElement("canvas"); canvas.id = "seasonfx"; canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);
    const ctx = canvas.getContext("2d");
    const fx = seasonFx = { kind, theme, canvas, raf: 0, parts: [], w: 0, h: 0, last: performance.now(), resize: null };
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    fx.resize = () => { fx.w = innerWidth; fx.h = innerHeight; canvas.width = fx.w * dpr; canvas.height = fx.h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    fx.resize(); window.addEventListener("resize", fx.resize);
    const light = theme === "light";
    const R = (a, b) => a + Math.random() * (b - a), pick = a => a[Math.floor(Math.random() * a.length)];
    const area = Math.max(.45, Math.min(1.4, (fx.w * fx.h) / (1400 * 900)));

    // -------- petites images préparées une fois (taille S × S, centrées)
    function sprite(S, draw) {
      const c = document.createElement("canvas"); c.width = c.height = Math.ceil(S * dpr);
      const g = c.getContext("2d"); g.scale(dpr, dpr); g.translate(S / 2, S / 2); draw(g, S / 2); return { c, S };
    }
    // flocon à six branches, chaque branche avec ses petites ramifications (comme ❄️), un peu différent à chaque fois
    function flake(g, r) {
      const col = light ? "#6f9ccc" : "#ffffff";
      g.strokeStyle = col; g.lineCap = "round"; g.lineJoin = "round";
      g.shadowColor = light ? "rgba(80, 130, 190, .5)" : "rgba(190, 230, 255, .9)"; g.shadowBlur = r * .35;
      const L = r * .82, b1 = R(.32, .45), b2 = R(.58, .7), l1 = R(.22, .32), l2 = R(.14, .22), tip = Math.random() < .5;
      g.lineWidth = Math.max(1, r * .1);
      for (let k = 0; k < 6; k++) {
        g.save(); g.rotate(k * Math.PI / 3);
        g.beginPath(); g.moveTo(0, 0); g.lineTo(0, -L);
        for (const [at, len] of [[b1, l1], [b2, l2]]) {
          g.moveTo(0, -L * at); g.lineTo(-L * len, -L * at - L * len * .9);
          g.moveTo(0, -L * at); g.lineTo(L * len, -L * at - L * len * .9);
        }
        if (tip) { g.moveTo(0, -L * .88); g.lineTo(-L * .08, -L * .96); g.moveTo(0, -L * .88); g.lineTo(L * .08, -L * .96); }
        g.stroke(); g.restore();
      }
      g.lineWidth = Math.max(1, r * .08); g.beginPath();
      for (let k = 0; k <= 6; k++) { const a = k * Math.PI / 3 + Math.PI / 6, x = Math.cos(a) * r * .2, y = Math.sin(a) * r * .2; k ? g.lineTo(x, y) : g.moveTo(x, y); }
      g.stroke();
    }
    // pétale de cerisier : goutte arrondie avec la petite encoche au bout, dégradé du cœur vers le bord
    function petalPath(g, r) {
      g.beginPath(); g.moveTo(0, r);
      g.bezierCurveTo(r * .95, r * .45, r * .78, -r * .72, r * .3, -r * .95);
      g.quadraticCurveTo(r * .12, -r * .98, 0, -r * .74);
      g.quadraticCurveTo(-r * .12, -r * .98, -r * .3, -r * .95);
      g.bezierCurveTo(-r * .78, -r * .72, -r * .95, r * .45, 0, r); g.closePath();
    }
    const PETAL_COLORS = [["#ff8fb8", "#ffd6e6"], ["#ffb7d0", "#fff0f6"], ["#ffffff", "#ffe3ee"], ["#d4b4ff", "#f1e6ff"], ["#ffc49a", "#ffecdc"], ["#fff1a0", "#fffbe0"], ["#ff9e9e", "#ffe0e0"], ["#f7a6e0", "#ffe6f7"], ["#b9e3ff", "#eef8ff"]];
    function petal(g, r, [deep, pale]) {
      const gr = g.createLinearGradient(0, r, 0, -r); gr.addColorStop(0, deep); gr.addColorStop(1, pale);
      g.fillStyle = gr; g.shadowColor = "rgba(0, 0, 0, .18)"; g.shadowBlur = r * .3; petalPath(g, r); g.fill();
      g.shadowBlur = 0; g.strokeStyle = "rgba(255, 255, 255, .55)"; g.lineWidth = Math.max(.6, r * .06);
      g.beginPath(); g.moveTo(0, r * .8); g.quadraticCurveTo(r * .08, 0, 0, -r * .6); g.stroke();
    }
    function blossom(g, r, colors) {
      for (let k = 0; k < 5; k++) { g.save(); g.rotate(k * Math.PI * 2 / 5); g.translate(0, -r * .5); petal(g, r * .5, colors); g.restore(); }
      g.fillStyle = "#ffd84a"; g.beginPath(); g.arc(0, 0, r * .17, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#e89a1a"; for (let k = 0; k < 7; k++) { const a = k * Math.PI * 2 / 7; g.beginPath(); g.arc(Math.cos(a) * r * .24, Math.sin(a) * r * .24, r * .04, 0, Math.PI * 2); g.fill(); }
    }
    // feuilles d'automne : érable, chêne, bouleau, en dégradé de deux couleurs de saison, avec leurs nervures
    const LEAF_COLORS = [["#e8641b", "#f7b23b"], ["#b7311b", "#e5682a"], ["#d9a21f", "#f3d35a"], ["#a8521d", "#d98b3a"], ["#c1271b", "#f0773a"], ["#8f5b1a", "#c99a3e"], ["#e07a1f", "#c23b1c"]];
    const MAPLE = [[0, -1], [.14, -.62], [.4, -.8], [.33, -.46], [.82, -.58], [.62, -.24], [.98, -.06], [.56, .1], [.66, .38], [.26, .26], [.1, .52]];
    function leafFill(g, r, [a, b]) { const gr = g.createLinearGradient(-r, -r, r, r); gr.addColorStop(0, a); gr.addColorStop(1, b); g.fillStyle = gr; g.shadowColor = "rgba(40, 15, 0, .3)"; g.shadowBlur = r * .25; }
    function maple(g, r, cols) {
      leafFill(g, r, cols); g.beginPath();
      MAPLE.forEach(([x, y], i) => i ? g.lineTo(x * r, y * r) : g.moveTo(x * r, y * r));
      for (let i = MAPLE.length - 1; i >= 0; i--) g.lineTo(-MAPLE[i][0] * r, MAPLE[i][1] * r);
      g.closePath(); g.fill(); g.shadowBlur = 0;
      g.strokeStyle = "rgba(70, 25, 5, .45)"; g.lineWidth = Math.max(.8, r * .05); g.beginPath();
      for (const [x, y] of [[0, -1], [.82, -.58], [-.82, -.58], [.98, -.06], [-.98, -.06]]) { g.moveTo(0, r * .5); g.lineTo(x * r * .9, y * r * .9); }
      g.moveTo(0, r * .5); g.lineTo(0, r * 1.05); g.stroke();
    }
    function oak(g, r, cols) {
      leafFill(g, r, cols); g.beginPath();
      const N = 40, side = s => { for (let i = 0; i <= N; i++) { const t = i / N, y = -r + t * 1.8 * r, w = r * .42 * Math.sin(Math.PI * t) * (1 + .38 * Math.sin(t * Math.PI * 9)); s === 1 ? g.lineTo(w, y) : g.lineTo(-w, -r + (1 - t) * 1.8 * r); } };
      g.moveTo(0, -r); side(1); side(-1); g.closePath(); g.fill(); g.shadowBlur = 0;
      g.strokeStyle = "rgba(70, 25, 5, .45)"; g.lineWidth = Math.max(.8, r * .05); g.beginPath(); g.moveTo(0, -r * .9); g.lineTo(0, r); g.stroke();
    }
    function birch(g, r, cols) {
      leafFill(g, r, cols); g.beginPath(); g.moveTo(0, -r);
      g.bezierCurveTo(r * .75, -r * .45, r * .62, r * .5, 0, r * .8); g.bezierCurveTo(-r * .62, r * .5, -r * .75, -r * .45, 0, -r);
      g.fill(); g.shadowBlur = 0; g.strokeStyle = "rgba(70, 25, 5, .4)"; g.lineWidth = Math.max(.7, r * .045); g.beginPath();
      g.moveTo(0, -r * .85); g.lineTo(0, r);
      for (let k = 1; k <= 4; k++) { const y = -r * .55 + k * r * .25; g.moveTo(0, y); g.lineTo(r * .4, y - r * .22); g.moveTo(0, y); g.lineTo(-r * .4, y - r * .22); }
      g.stroke();
    }
    function glow(g, r, c) { const gr = g.createRadialGradient(0, 0, 0, 0, 0, r); gr.addColorStop(0, `rgba(${c}, 1)`); gr.addColorStop(.25, `rgba(${c}, .55)`); gr.addColorStop(1, `rgba(${c}, 0)`); g.fillStyle = gr; g.beginPath(); g.arc(0, 0, r, 0, Math.PI * 2); g.fill(); }
    function seed(g, r) {   // aigrette de pissenlit : une petite tige et une ombrelle de fils
      g.strokeStyle = light ? "rgba(120, 100, 70, .8)" : "rgba(255, 255, 255, .85)"; g.lineWidth = .8;
      g.beginPath(); g.moveTo(0, r * .9); g.lineTo(0, -r * .1); g.stroke();
      g.lineWidth = .6; g.beginPath();
      for (let k = 0; k < 14; k++) { const a = -Math.PI + k * Math.PI / 13; g.moveTo(0, -r * .1); g.lineTo(Math.cos(a) * r * .8, -r * .1 + Math.sin(a) * r * .7); }
      g.stroke();
    }

    const sprites = { flakes: [], dots: [], petals: [], flowers: [], leaves: [], fly: null, seeds: [], fete: {} };
    const base = FETE_BASE[kind] || kind;   // une fête emprunte les motifs d'une saison (neige à Noël, feuilles à Halloween…)
    if (base === "winter") {
      for (let i = 0; i < 8; i++) sprites.flakes.push(sprite(40, (g, r) => flake(g, r)));
      sprites.dots.push(sprite(10, (g, r) => glow(g, r, light ? "130, 165, 205" : "255, 255, 255")));
    } else if (base === "spring") {
      for (const c of PETAL_COLORS) { sprites.petals.push(sprite(28, (g, r) => petal(g, r * .8, c))); sprites.petals.push(sprite(28, (g, r) => petal(g, r * .8, c))); }
      for (const c of PETAL_COLORS.slice(0, 6)) sprites.flowers.push(sprite(46, (g, r) => blossom(g, r * .9, c)));
    } else if (base === "autumn") {
      for (const c of LEAF_COLORS) { sprites.leaves.push(sprite(48, (g, r) => maple(g, r * .85, c))); sprites.leaves.push(sprite(48, (g, r) => oak(g, r * .85, c))); sprites.leaves.push(sprite(40, (g, r) => birch(g, r * .85, c))); }
    } else {
      sprites.fly = sprite(36, (g, r) => glow(g, r, light ? "242, 159, 5" : "255, 214, 90"));
      for (let i = 0; i < 3; i++) sprites.seeds.push(sprite(30, (g, r) => seed(g, r)));
    }

    // -------- motifs des fêtes (habillage Fêtes)
    function bauble(g, r, c) {
      const gr = g.createRadialGradient(-r * .3, -r * .2, r * .1, 0, r * .1, r * .85); gr.addColorStop(0, "#fff"); gr.addColorStop(.25, c); gr.addColorStop(1, "rgba(0, 0, 0, .55)");
      g.fillStyle = gr; g.shadowColor = c; g.shadowBlur = r * .4; g.beginPath(); g.arc(0, r * .12, r * .78, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
      g.fillStyle = "#d9b44a"; g.fillRect(-r * .2, -r * .82, r * .4, r * .22);
      g.strokeStyle = "#d9b44a"; g.lineWidth = Math.max(1, r * .07); g.beginPath(); g.arc(0, -r * .9, r * .1, 0, Math.PI * 2); g.stroke();
    }
    function star(g, r, c) {
      g.fillStyle = c; g.shadowColor = c; g.shadowBlur = r * .5; g.beginPath();
      for (let k = 0; k < 10; k++) { const a = -Math.PI / 2 + k * Math.PI / 5, q = k % 2 ? r * .42 : r * .95; g.lineTo(Math.cos(a) * q, Math.sin(a) * q); }
      g.closePath(); g.fill();
    }
    function heart(g, r, [a, b]) {
      const gr = g.createLinearGradient(0, -r, 0, r); gr.addColorStop(0, b); gr.addColorStop(1, a);
      g.fillStyle = gr; g.shadowColor = "rgba(0, 0, 0, .2)"; g.shadowBlur = r * .3; g.beginPath(); g.moveTo(0, r * .85);
      g.bezierCurveTo(-r * 1.1, r * .05, -r * .75, -r * .95, 0, -r * .38); g.bezierCurveTo(r * .75, -r * .95, r * 1.1, r * .05, 0, r * .85); g.fill();
      g.shadowBlur = 0; g.fillStyle = "rgba(255, 255, 255, .45)"; g.beginPath(); g.ellipse(-r * .35, -r * .3, r * .15, r * .1, -.6, 0, Math.PI * 2); g.fill();
    }
    function egg(g, r, [a, b, c]) {
      g.save(); g.beginPath(); g.ellipse(0, r * .05, r * .64, r * .88, 0, 0, Math.PI * 2); g.clip();
      g.fillStyle = a; g.fillRect(-r, -r, 2 * r, 2 * r);
      g.fillStyle = b; g.beginPath(); g.moveTo(-r, -r * .05);
      for (let k = 0; k <= 8; k++) g.lineTo(-r + k * r / 4, k % 2 ? -r * .25 : -r * .05);
      g.lineTo(r, r * .2); for (let k = 8; k >= 0; k--) g.lineTo(-r + k * r / 4, k % 2 ? r * .2 : r * .4); g.fill();
      g.fillStyle = c; for (const [x, y] of [[-.3, -.55], [.25, -.6], [0, -.75], [-.25, .6], [.25, .62], [0, .78]]) { g.beginPath(); g.arc(x * r, y * r, r * .08, 0, Math.PI * 2); g.fill(); }
      g.restore(); g.strokeStyle = "rgba(0, 0, 0, .18)"; g.lineWidth = 1; g.beginPath(); g.ellipse(0, r * .05, r * .64, r * .88, 0, 0, Math.PI * 2); g.stroke();
    }
    function note(g, r, ch, c) { g.fillStyle = c; g.shadowColor = c; g.shadowBlur = r * .4; g.font = `bold ${r * 1.7}px serif`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(ch, 0, 0); }
    function pumpkin(g, r, face) {
      g.shadowColor = "rgba(255, 140, 0, .5)"; g.shadowBlur = r * .4;
      for (const [dx, w, col] of [[-.42, .42, "#d9620f"], [.42, .42, "#d9620f"], [-.18, .45, "#f07c18"], [.18, .45, "#f07c18"], [0, .4, "#ff9324"]]) { g.fillStyle = col; g.beginPath(); g.ellipse(dx * r, r * .1, w * r, r * .68, 0, 0, Math.PI * 2); g.fill(); }
      g.shadowBlur = 0; g.fillStyle = "#4d7a1f"; g.fillRect(-r * .07, -r * .78, r * .14, r * .26);
      if (face) {
        g.fillStyle = "#2a1200";
        g.beginPath(); g.moveTo(-r * .38, -r * .05); g.lineTo(-r * .18, -r * .05); g.lineTo(-r * .28, -r * .25); g.fill();
        g.beginPath(); g.moveTo(r * .38, -r * .05); g.lineTo(r * .18, -r * .05); g.lineTo(r * .28, -r * .25); g.fill();
        g.beginPath(); g.moveTo(-r * .4, r * .2); for (let k = 0; k <= 6; k++) g.lineTo(-r * .4 + k * r * .8 / 6, r * (k % 2 ? .3 : .45)); g.lineTo(r * .4, r * .2); g.quadraticCurveTo(0, r * .55, -r * .4, r * .2); g.fill();
      }
    }
    function ghost(g, r) {
      g.fillStyle = light ? "rgba(255, 255, 255, .95)" : "rgba(245, 245, 255, .85)"; g.shadowColor = "rgba(200, 200, 255, .8)"; g.shadowBlur = r * .4;
      g.beginPath(); g.moveTo(-r * .6, r * .8); g.lineTo(-r * .6, -r * .1); g.arc(0, -r * .1, r * .6, Math.PI, 0); g.lineTo(r * .6, r * .8);
      for (let k = 0; k < 4; k++) g.quadraticCurveTo(r * (.45 - k * .3), r * (k % 2 ? .95 : .6), r * (.3 - k * .3), r * .8);
      g.closePath(); g.fill(); g.shadowBlur = 0;
      g.fillStyle = "#222"; g.beginPath(); g.ellipse(-r * .22, -r * .15, r * .09, r * .14, 0, 0, Math.PI * 2); g.ellipse(r * .22, -r * .15, r * .09, r * .14, 0, 0, Math.PI * 2); g.fill();
    }
    function ball(g, r) {
      const cols = ["#ff4d4d", "#ffffff", "#2f8cff", "#ffffff", "#ffd23f", "#ffffff"];
      for (let k = 0; k < 6; k++) { g.fillStyle = cols[k]; g.beginPath(); g.moveTo(0, 0); g.arc(0, 0, r * .9, k * Math.PI / 3, (k + 1) * Math.PI / 3); g.fill(); }
      const gr = g.createRadialGradient(-r * .3, -r * .35, r * .05, 0, 0, r * .9); gr.addColorStop(0, "rgba(255, 255, 255, .55)"); gr.addColorStop(1, "rgba(0, 0, 0, .25)");
      g.fillStyle = gr; g.beginPath(); g.arc(0, 0, r * .9, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#fff"; g.beginPath(); g.arc(0, 0, r * .14, 0, Math.PI * 2); g.fill();
    }
    function confetti(g, r, c) { g.fillStyle = c; g.fillRect(-r * .28, -r * .6, r * .56, r * 1.2); }
    const F = sprites.fete, CONF = ["#ff4d6d", "#ffd23f", "#3ddc97", "#4dabff", "#b26bff", "#ff8c42", "#ffffff"];
    if (kind === "christmas") {
      F.fall = [...["#d62828", "#2a9d4b", "#e9c46a", "#4361ee", "#c0c0c0"].map(c => sprite(40, (g, r) => bauble(g, r * .9, c))), ...["#ffd84a", "#fff3b0"].map(c => sprite(36, (g, r) => star(g, r * .85, c)))];
    } else if (kind === "newyear") {
      F.fall = CONF.flatMap(c => [sprite(20, (g, r) => confetti(g, r, c)), sprite(20, (g, r) => confetti(g, r * .7, c))]);
      F.fall.push(sprite(30, (g, r) => star(g, r * .8, "#ffd84a")));
      F.colors = ["255, 210, 63", "255, 77, 109", "77, 171, 255", "61, 220, 151", "178, 107, 255", "255, 255, 255"];
    } else if (kind === "valentine") {
      F.rise = [["#e63973", "#ff8fb8"], ["#c9184a", "#ff4d6d"], ["#ff8fab", "#ffc2d1"], ["#b5179e", "#f72585"]].map(c => sprite(40, (g, r) => heart(g, r * .9, c)));
    } else if (kind === "easter") {
      F.fall = [["#ffd6e8", "#8fd3ff", "#ff8fb8"], ["#fff3b0", "#b5e48c", "#ff9f1c"], ["#cdb4db", "#ffffff", "#7b2cbf"], ["#a0e7e5", "#ffaebc", "#ffffff"], ["#ffcad4", "#ffd23f", "#4dabff"]].map(c => sprite(40, (g, r) => egg(g, r * .9, c)));
    } else if (kind === "music") {
      F.rise = ["♪", "♫", "♬", "♩"].flatMap(ch => ["#ffd23f", "#ff6b9e", "#5ce1e6", "#b388ff"].map(c => sprite(36, (g, r) => note(g, r * .8, ch, c))));
    } else if (kind === "bastille") {
      F.fall = ["#0055a4", "#ffffff", "#ef4135"].flatMap(c => [sprite(20, (g, r) => confetti(g, r, c)), sprite(20, (g, r) => confetti(g, r * .7, c))]);
      F.colors = ["0, 85, 164", "255, 255, 255", "239, 65, 53", "120, 170, 255", "255, 120, 110"];
    } else if (kind === "holidays") {
      F.rise = [sprite(56, (g, r) => ball(g, r))];
    } else if (kind === "halloween") {
      F.fall = [sprite(48, (g, r) => pumpkin(g, r * .9, true)), sprite(48, (g, r) => pumpkin(g, r * .9, false)), sprite(48, (g, r) => pumpkin(g, r * .9, true))];
      F.rise = [sprite(48, (g, r) => ghost(g, r * .9))];
    }

    // -------- les éléments
    const BUTTERFLY = [["#ffb347", "#ff7a1a"], ["#7fc8ff", "#2f7fd6"], ["#ffe066", "#f2a900"], ["#ff8fc6", "#e64c9a"], ["#b6f08a", "#4fae3a"]];
    function make(initial, type) {
      const y0 = initial ? R(-fx.h * .1, fx.h) : R(-90, -30);
      const F = sprites.fete;
      if (type === "fall") {
        const conf = kind === "newyear" || kind === "bastille";   // confettis : petits, tournoient et se retournent
        const s = conf ? R(12, 20) : R(26, 44);                  // boules, étoiles, œufs, citrouilles : plus gros, ne se retournent pas
        return { t: "leaf", sp: pick(F.fall), x: R(0, fx.w), y: y0, s, vy: conf ? R(26, 55) : R(22, 40), vx: R(-12, 16), a: conf ? R(0, 6.3) : R(-.4, .4), va: conf ? R(-2, 2) : R(-.5, .5), flip: conf ? R(0, 6.3) : undefined, fs: R(1, 3), al: R(.85, 1), ph: R(0, 6.3) };
      }
      if (type === "rise") { const s = kind === "holidays" ? R(30, 50) : R(18, 38); return { t: "rise", sp: pick(F.rise), x: R(0, fx.w), y: initial ? R(0, fx.h) : fx.h + 40, s, vy: -R(14, 34), vx: R(-8, 8), a: R(-.3, .3), va: R(-.4, .4), al: R(.75, 1), ph: R(0, 6.3) }; }
      if (type === "bat") return { t: "bat", x: R(0, fx.w), y: R(fx.h * .1, fx.h * .7), s: R(14, 26), vx: R(-40, 40) || 20, vy: R(-14, 14), ph: R(0, 6.3), turn: R(1.5, 4) };
      if (type === "rocket") return { t: "rocket", wait: R(.3, 3) };
      if (base === "winter") {
        if (type === "dot") return { t: "dot", x: R(0, fx.w), y: y0, s: R(3, 9), vy: R(20, 45), vx: R(-6, 6), al: R(.35, .8), ph: R(0, 6.3) };
        const s = R(10, 30);
        return { t: "flake", sp: pick(sprites.flakes), x: R(0, fx.w), y: y0, s, vy: R(14, 30) + s * .8, vx: R(-8, 8), a: R(0, 6.3), va: R(-.7, .7), al: R(.6, 1), ph: R(0, 6.3) };
      }
      if (base === "spring") {
        if (type === "flower") { const s = R(26, 42); return { t: "petal", sp: pick(sprites.flowers), x: R(0, fx.w), y: y0, s, vy: R(18, 34), vx: R(4, 18), a: R(0, 6.3), va: R(-1, 1), flip: R(0, 6.3), fs: R(.6, 1.2), al: .95, ph: R(0, 6.3) }; }
        const s = R(15, 28);
        return { t: "petal", sp: pick(sprites.petals), x: R(-fx.w * .2, fx.w), y: y0, s, vy: R(22, 44), vx: R(10, 34), a: R(0, 6.3), va: R(-2.4, 2.4), flip: R(0, 6.3), fs: R(1.5, 3), al: R(.8, 1), ph: R(0, 6.3) };
      }
      if (base === "autumn") {
        const s = R(20, 42);
        return { t: "leaf", sp: pick(sprites.leaves), x: R(0, fx.w), y: y0, s, vy: R(30, 62), vx: R(-14, 22), a: R(0, 6.3), va: R(-1.8, 1.8), flip: R(0, 6.3), fs: R(1, 2.2), al: R(.85, 1), ph: R(0, 6.3) };
      }
      // été
      if (type === "seed") return { t: "seed", sp: pick(sprites.seeds), x: R(-50, fx.w), y: initial ? R(0, fx.h) : fx.h + 20, s: R(18, 30), vy: -R(8, 18), vx: R(10, 26), a: R(-.4, .4), va: R(-.3, .3), al: R(.6, .9), ph: R(0, 6.3) };
      if (type === "butterfly") { const c = pick(BUTTERFLY); return { t: "bfly", c, x: R(0, fx.w), y: R(fx.h * .15, fx.h * .85), s: R(12, 20), vx: R(-30, 30) || 12, vy: R(-12, 12), ph: R(0, 6.3), turn: R(2, 6) }; }
      return { t: "fly", x: R(0, fx.w), y: initial ? R(0, fx.h) : fx.h + 10, s: R(10, 22), vy: -R(5, 15), vx: R(-6, 6), ph: R(0, 6.3), sp2: R(.8, 1.8) };
    }
    const plan = {
      winter: [["flake", 70], ["dot", 110]],
      spring: [["petal", 85], ["flower", 12]],
      autumn: [["leaf", 70]],
      summer: [["fly", 65], ["seed", 20], ["butterfly", 9]],
      christmas: [["flake", 45], ["dot", 70], ["fall", 16]],
      newyear: [["fall", 90], ["rocket", 3]],
      valentine: [["rise", 34], ["petal", 30]],
      easter: [["fall", 22], ["flower", 12], ["petal", 30]],
      music: [["rise", 40], ["fly", 25]],
      bastille: [["fall", 60], ["rocket", 4]],
      holidays: [["rise", 7], ["fly", 40], ["butterfly", 6]],
      halloween: [["bat", 10], ["fall", 10], ["rise", 5], ["leaf", 22]],
    }[kind] || [];
    const spawn = (initial, type) => { const p = make(initial, type); p.kindType = type; return p; };
    for (const [type, n] of plan) for (let i = 0; i < (type === "rocket" ? n : Math.max(1, Math.round(n * area))); i++) fx.parts.push(spawn(true, type));
    fx.sparks = [];

    function drawSprite(p, t) {
      const sx = p.flip !== undefined ? Math.cos(t * p.fs + p.flip) : 1;   // pétales et feuilles se retournent en tombant
      ctx.save(); ctx.globalAlpha = p.al; ctx.translate(p.x, p.y); ctx.rotate(p.a || 0);
      ctx.scale(Math.max(.18, Math.abs(sx)), 1);
      ctx.drawImage(p.sp.c, -p.s / 2, -p.s / 2, p.s, p.s);
      ctx.restore();
    }
    function butterfly(p, t) {
      const flap = Math.abs(Math.sin(t * 9 + p.ph)) * .85 + .15, [a, b] = p.c, s = p.s;
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(Math.atan2(p.vy, p.vx) + Math.PI / 2); ctx.globalAlpha = .9;
      for (const side of [-1, 1]) {
        ctx.save(); ctx.scale(side * flap, 1);
        const gr = ctx.createLinearGradient(0, -s, s, s); gr.addColorStop(0, a); gr.addColorStop(1, b); ctx.fillStyle = gr;
        ctx.beginPath(); ctx.ellipse(s * .55, -s * .35, s * .55, s * .45, -.5, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(s * .42, s * .35, s * .38, s * .32, .5, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
      ctx.fillStyle = light ? "#3a2a10" : "#2a1d10"; ctx.beginPath(); ctx.ellipse(0, 0, s * .1, s * .55, 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
    function frame(now) {
      fx.raf = requestAnimationFrame(frame);
      const dt = Math.min(.05, (now - fx.last) / 1000); fx.last = now;
      if (document.hidden) return;
      const t = now / 1000;
      ctx.clearRect(0, 0, fx.w, fx.h);
      for (let i = 0; i < fx.parts.length; i++) {
        const p = fx.parts[i];
        if (p.t === "fly") {   // lucioles : montent doucement, s'allument et s'éteignent
          p.x += (p.vx + Math.sin(t * .8 + p.ph) * 12) * dt; p.y += p.vy * dt;
          const on = Math.max(0, Math.sin(t * p.sp2 + p.ph)) ** 2;
          if (on > .02) { ctx.globalAlpha = on; ctx.drawImage(sprites.fly.c, p.x - p.s, p.y - p.s, p.s * 2, p.s * 2); ctx.globalAlpha = 1; }
          if (p.y < -30) { fx.parts[i] = spawn(false, "fly"); }
          continue;
        }
        if (p.t === "bfly") {   // papillons : vol en zigzag qui change de cap de temps en temps
          p.turn -= dt;
          if (p.turn <= 0) { p.turn = R(1.5, 5); p.vx = R(-40, 40); p.vy = R(-22, 22); }
          p.x += (p.vx + Math.sin(t * 3 + p.ph) * 18) * dt; p.y += (p.vy + Math.cos(t * 2.4 + p.ph) * 14) * dt;
          if (p.x < -40) p.x = fx.w + 30; if (p.x > fx.w + 40) p.x = -30; if (p.y < 20) p.vy = Math.abs(p.vy); if (p.y > fx.h - 20) p.vy = -Math.abs(p.vy);
          butterfly(p, t); continue;
        }
        if (p.t === "rise") {   // cœurs, notes, fantômes, ballons : montent en se balançant
          p.x += (p.vx + Math.sin(t * .9 + p.ph) * 22) * dt; p.y += p.vy * dt; p.a = Math.sin(t * .8 + p.ph) * .25;
          drawSprite(p, t);
          if (p.y < -60) fx.parts[i] = spawn(false, "rise");
          continue;
        }
        if (p.t === "bat") {   // chauves-souris : vol en zigzag, ailes qui battent
          p.turn -= dt;
          if (p.turn <= 0) { p.turn = R(1, 3.5); p.vx = R(-70, 70); p.vy = R(-30, 30); }
          p.x += (p.vx + Math.sin(t * 4 + p.ph) * 25) * dt; p.y += (p.vy + Math.cos(t * 3 + p.ph) * 20) * dt;
          if (p.x < -40) p.x = fx.w + 30; if (p.x > fx.w + 40) p.x = -30; if (p.y < 20) p.vy = Math.abs(p.vy); if (p.y > fx.h * .85) p.vy = -Math.abs(p.vy);
          const flap = Math.sin(t * 14 + p.ph), s = p.s;
          ctx.save(); ctx.translate(p.x, p.y); ctx.fillStyle = light ? "#2b1f3a" : "#3a2452"; ctx.shadowColor = "rgba(255, 140, 40, .55)"; ctx.shadowBlur = 8; ctx.globalAlpha = .95;
          for (const side of [-1, 1]) {
            ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(side * s * .6, -s * (.2 + .5 * flap), side * s * 1.2, -s * .1 * flap);
            ctx.quadraticCurveTo(side * s * .9, s * .25, side * s * .7, s * .15); ctx.quadraticCurveTo(side * s * .5, s * .35, side * s * .3, s * .15); ctx.quadraticCurveTo(side * s * .15, s * .3, 0, s * .2); ctx.fill();
          }
          ctx.beginPath(); ctx.ellipse(0, s * .05, s * .16, s * .24, 0, 0, Math.PI * 2); ctx.fill();
          ctx.beginPath(); ctx.moveTo(-s * .12, -s * .12); ctx.lineTo(-s * .06, -s * .3); ctx.lineTo(0, -s * .14); ctx.lineTo(s * .06, -s * .3); ctx.lineTo(s * .12, -s * .12); ctx.fill();
          ctx.restore(); continue;
        }
        if (p.t === "rocket") {   // feux d'artifice : de temps en temps, une gerbe d'étincelles quelque part en haut
          p.wait -= dt;
          if (p.wait <= 0) {
            p.wait = R(1.2, 3.5);
            const cx = R(fx.w * .1, fx.w * .9), cy = R(fx.h * .1, fx.h * .45), col = pick(sprites.fete.colors), n = Math.round(R(36, 60)), sp = R(90, 170);
            for (let k = 0; k < n; k++) { const a = k * Math.PI * 2 / n + R(-.05, .05), v = sp * R(.75, 1.05); fx.sparks.push({ x: cx, y: cy, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: R(1.1, 1.8), age: 0, col }); }
          }
          continue;
        }
        if (p.t === "dot") {
          p.x += (p.vx + Math.sin(t * .7 + p.ph) * 8) * dt; p.y += p.vy * dt;
          ctx.globalAlpha = p.al; ctx.drawImage(sprites.dots[0].c, p.x - p.s / 2, p.y - p.s / 2, p.s, p.s); ctx.globalAlpha = 1;
          if (p.y > fx.h + 10) fx.parts[i] = spawn(false, "dot");
          continue;
        }
        if (p.t === "seed") {
          p.x += (p.vx + Math.sin(t * .6 + p.ph) * 14) * dt; p.y += (p.vy + Math.cos(t * .9 + p.ph) * 6) * dt; p.a += p.va * dt;
          drawSprite(p, t);
          if (p.y < -40 || p.x > fx.w + 40) fx.parts[i] = spawn(false, "seed");
          continue;
        }
        const sway = Math.sin(t * (p.t === "flake" ? .8 : 1.3) + p.ph) * (p.t === "flake" ? 14 : 34);
        p.x += (p.vx + sway) * dt; p.y += p.vy * dt; p.a += p.va * dt;
        drawSprite(p, t);
        if (p.y > fx.h + 50 || p.x < -80 || p.x > fx.w + 80) fx.parts[i] = spawn(false, p.kindType || p.t);
      }
      if (fx.sparks.length) {   // étincelles des feux d'artifice : freinées, retombent, s'éteignent
        ctx.globalCompositeOperation = "lighter";
        for (let i = fx.sparks.length - 1; i >= 0; i--) {
          const k = fx.sparks[i]; k.age += dt;
          if (k.age >= k.life) { fx.sparks.splice(i, 1); continue; }
          k.vx *= 1 - 1.4 * dt; k.vy = k.vy * (1 - 1.4 * dt) + 55 * dt; k.x += k.vx * dt; k.y += k.vy * dt;
          ctx.fillStyle = `rgba(${k.col}, ${(1 - k.age / k.life).toFixed(3)})`; ctx.beginPath(); ctx.arc(k.x, k.y, 2.6, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalCompositeOperation = "source-over";
      }
    }
    fx.raf = requestAnimationFrame(frame);
  }

  // ================================================================ aquarium : bulles qui éclatent (et leur « blop »)
  /* Les bulles montent du bas de l'écran ; environ une sur trois, tirée au sort, gonfle puis éclate en route avec un
     petit bruit synthétisé (pas de fichier son). Le son ne joue qu'après un premier clic ou toucher sur la page
     (règle des navigateurs) et se coupe avec le bouton haut-parleur, mémorisé sur l'appareil. */
  let bubbleTimer = null, audioCtx = null, lastPop = 0;
  const bubbleMuted = () => { try { return localStorage.getItem("bulle:bubbles_mute") === "1"; } catch (_) { return false; } };
  function updateMuteBtn() {
    const b = $("#bubble-mute"); if (!b) return;
    const m = bubbleMuted();
    b.classList.toggle("off", m);
    b.title = m ? "Son des bulles coupé (cliquer pour l'activer)" : "Son des bulles (cliquer pour couper)";
  }
  document.addEventListener("click", e => {
    if (!e.target.closest("#bubble-mute")) return;
    try { localStorage.setItem("bulle:bubbles_mute", bubbleMuted() ? "0" : "1"); } catch (_) { /* ignore */ }
    updateMuteBtn(); unlockAudio();
    toast(bubbleMuted() ? "Bulles en sourdine" : "Blop ! Le son des bulles est activé");
  });
  function unlockAudio() {
    if (audioCtx || bubbleMuted()) { if (audioCtx && audioCtx.state === "suspended") audioCtx.resume(); return; }
    try { const AC = window.AudioContext || window.webkitAudioContext; if (AC) audioCtx = new AC(); } catch (_) { audioCtx = null; }
  }
  ["pointerdown", "keydown", "touchstart"].forEach(t => document.addEventListener(t, () => { if (document.documentElement.dataset.skin === "ocean") unlockAudio(); }, { passive: true }));
  /* « Blop » de bulle : une vraie bulle qui éclate sous l'eau monte un peu en hauteur au lieu de descendre (sinon on
     entend un tir de pistolet laser). Son grave et rond : une sinusoïde basse (environ 180 à 420 Hz selon la taille,
     plus grave pour les grosses) qui glisse vers le haut, une attaque douce et un filtre passe-bas qui l'étouffe,
     plus un tout petit « pof » d'air feutré. */
  function blop(size) {
    if (bubbleMuted() || !audioCtx || audioCtx.state !== "running" || document.hidden) return;
    if (performance.now() - lastPop < 140) return;   // pas de rafale
    lastPop = performance.now();
    const ctx = audioCtx, now = ctx.currentTime + 0.005;
    const big = Math.max(0, Math.min(1, (size - 5) / 15));
    const f0 = 420 - big * 240 + (Math.random() - .5) * 60, dur = 0.16 + big * 0.08;
    const out = ctx.createGain(); out.gain.value = 0.5;
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 700 + (1 - big) * 300; lp.Q.value = 0.6;
    lp.connect(out).connect(ctx.destination);
    // la bulle : sinusoïde qui remonte en hauteur, enveloppe arrondie
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine";
    o.frequency.setValueAtTime(f0, now);
    o.frequency.exponentialRampToValueAtTime(f0 * 1.9, now + dur * 0.7);
    g.gain.setValueAtTime(0.0001, now);
    g.gain.linearRampToValueAtTime(0.22, now + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    o.connect(g).connect(lp);
    o.start(now); o.stop(now + dur + 0.02);
    // un léger écho d'octave, très bas, pour l'arrondi
    const o2 = ctx.createOscillator(), g2 = ctx.createGain();
    o2.type = "sine"; o2.frequency.setValueAtTime(f0 * 0.5, now); o2.frequency.exponentialRampToValueAtTime(f0 * 0.95, now + dur * 0.7);
    g2.gain.setValueAtTime(0.0001, now); g2.gain.linearRampToValueAtTime(0.08, now + 0.015); g2.gain.exponentialRampToValueAtTime(0.0001, now + dur * 0.8);
    o2.connect(g2).connect(lp); o2.start(now); o2.stop(now + dur);
    // le « pof » : un souffle très court et très étouffé
    const len = Math.floor(ctx.sampleRate * 0.03), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const n = ctx.createBufferSource(), nf = ctx.createBiquadFilter(), ng = ctx.createGain();
    nf.type = "lowpass"; nf.frequency.value = 450; ng.gain.value = 0.12;
    n.buffer = buf; n.connect(nf).connect(ng).connect(out); n.start(now);
  }
  function spawnBubble(box) {
    if (document.hidden || box.childElementCount > 22) return;
    const el = document.createElement("span"), size = 5 + Math.random() * 15, dur = 9 + Math.random() * 9;
    el.className = "bub";
    el.style.setProperty("--x", (Math.random() * 100).toFixed(1) + "vw");
    el.style.setProperty("--s", size.toFixed(1) + "px");
    el.style.setProperty("--d", dur.toFixed(1) + "s");
    el.style.animationDelay = `0s, ${(-Math.random() * 2.6).toFixed(2)}s`;
    el.innerHTML = "<i></i>";
    box.appendChild(el);
    const kill = () => el.remove();
    if (Math.random() < 0.35) {   // celle-ci éclatera en route
      const at = dur * (0.25 + Math.random() * 0.5) * 1000;
      el.style.setProperty("--g", (1.8 + Math.random() * 1.2).toFixed(2));
      setTimeout(() => { if (!el.isConnected) return; el.classList.add("grow");
        setTimeout(() => { if (!el.isConnected) return; el.classList.add("pop"); blop(size); setTimeout(kill, 420); }, 700 + Math.random() * 900);
      }, at);
    }
    setTimeout(kill, dur * 1000 + 200);
  }
  function setupBubbles() {
    const want = document.documentElement.dataset.skin === "ocean" && !liteMode() && !isPhone() && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    let box = $("#bubbles");
    updateMuteBtn();
    if (!want) { clearInterval(bubbleTimer); bubbleTimer = null; if (box) box.remove(); return; }
    if (!box) { box = document.createElement("div"); box.id = "bubbles"; box.setAttribute("aria-hidden", "true"); document.body.prepend(box); }
    if (!bubbleTimer) { for (let i = 0; i < 4; i++) setTimeout(() => spawnBubble(box), i * 500); bubbleTimer = setInterval(() => spawnBubble(box), 850); }
  }

  // ================================================================ couvertures au hasard en bas de la colonne de gauche
  /* Jusqu'à deux couvertures posées au hasard dans l'espace libre ; une nouvelle arrive toutes les 6 à 8 s avec une
     transition tirée au sort (fondu, glissé, bascule, zoom, chute, flou, toupie) et remplace la plus ancienne.
     Cliquer dessus ouvre la fiche de l'album. */
  const SIDE_FX = ["fade", "slide-left", "slide-up", "flip", "zoom", "drop", "blur", "spin"];
  let sidePool = [], sideTimer = null, sideBusy = false, sideLastFx = "";
  function sideWanted() {
    const el = $("#side-covers");
    if (!el) return false;
    const p = settings.profile;
    return !liteMode() && p.side_covers !== false && document.documentElement.dataset.tabs === "left" && window.innerWidth > 1000 && el.clientHeight >= 110;
  }
  async function setupSideCovers() {
    const el = $("#side-covers");
    if (!el) return;
    if (!sideWanted()) { clearTimeout(sideTimer); sideTimer = null; el.innerHTML = ""; el.classList.remove("on"); return; }
    if (sideTimer) return;
    el.classList.add("on");
    if (!sidePool.length) {
      try { sidePool = await api("/api/covers/sample?n=120"); } catch (_) { sidePool = []; }
      if (!sidePool.length || !sideWanted()) return;
    }
    nextSideCover();
  }
  function nextSideCover() {
    clearTimeout(sideTimer);
    const el = $("#side-covers");
    if (!el || !sideWanted() || !sidePool.length) { sideTimer = null; return; }
    sideTimer = setTimeout(nextSideCover, 6000 + Math.random() * 2000);
    if (document.hidden || sideBusy) return;
    const c = sidePool[Math.floor(Math.random() * sidePool.length)];
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let fx = reduce ? "fade" : SIDE_FX[Math.floor(Math.random() * SIDE_FX.length)];
    if (fx === sideLastFx && !reduce) fx = SIDE_FX[(SIDE_FX.indexOf(fx) + 1) % SIDE_FX.length];
    sideLastFx = fx;
    const img = new Image();
    img.className = "sc"; img.alt = ""; img.decoding = "async"; img.draggable = false;
    img.dataset.id = String(c.id);
    img.src = `/api/cover/${c.id}?w=300&v=${c.mtime}&t=${encodeURIComponent(settings.global.img_tag || "")}`;
    sideBusy = true;
    img.onerror = () => { sidePool = sidePool.filter(x => x.id !== c.id); sideBusy = false; };
    img.onload = () => {
      sideBusy = false;
      if (!sideWanted()) return;
      const zw = el.clientWidth, zh = el.clientHeight;
      // taille au hasard (deux couvertures doivent tenir), position au hasard dans la zone libre
      const w = Math.round(Math.min(zw * 0.62, Math.max(90, Math.min(150, zh * 0.5 / 1.5)) * (0.85 + Math.random() * 0.3)));
      const h = Math.round(w * 1.5);
      img.style.width = w + "px";
      img.style.left = Math.round(Math.random() * Math.max(0, zw - w)) + "px";
      img.style.top = Math.round(Math.random() * Math.max(0, zh - h)) + "px";
      img.dataset.fx = fx;
      img.style.setProperty("--tilt", (Math.random() * 12 - 6).toFixed(1) + "deg");
      const shown = [...el.querySelectorAll("img.sc.in")];
      const old = shown.length >= 2 ? shown[0] : null;   // la plus ancienne s'en va quand il y en a déjà deux
      el.appendChild(img);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        img.classList.add("in");
        if (old) { old.classList.remove("in"); old.classList.add("out"); setTimeout(() => old.remove(), 1700); }
      }));
    };
  }
  document.addEventListener("click", e => {
    const sc = e.target.closest("#side-covers img.sc.in");
    if (sc) openInfo(sc.dataset.id);
  });

  // ================================================================ mosaïque de couvertures en fond
  const TILE_W = 120, TILE_H = 180;
  let mosaicEl = null, mosaicPool = [], mosaicTimer = null, mosaicCols = 0, mosaicRows = 0;
  const mosaicUrl = c => `/api/cover/${c.id}?w=150&v=${c.mtime}&t=${encodeURIComponent(settings.global.img_tag || "")}`;
  async function setupMosaic() {
    const want = document.documentElement.dataset.mosaic !== "off";
    if (!want) { clearInterval(mosaicTimer); mosaicTimer = null; if (mosaicEl) { mosaicEl.remove(); mosaicEl = null; } return; }
    const cols = Math.ceil(window.innerWidth / TILE_W) + 2, rows = Math.ceil(window.innerHeight / TILE_H) + 2;
    if (mosaicEl && cols === mosaicCols && rows === mosaicRows) return;
    mosaicCols = cols; mosaicRows = rows;
    if (!mosaicPool.length) {
      try { mosaicPool = await api(`/api/covers/sample?n=${Math.min(200, cols * rows * 2)}`); } catch (_) { mosaicPool = []; }
      if (!mosaicPool.length) return;
    }
    if (!mosaicEl) {
      mosaicEl = document.createElement("div"); mosaicEl.id = "mosaic"; mosaicEl.setAttribute("aria-hidden", "true");
      document.body.prepend(mosaicEl);
    }
    const tiles = [];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const k = (r * cols + c) % mosaicPool.length;
      // décalage d'une demi-tuile une ligne sur deux, comme un mur de briques
      tiles.push(`<img class="mt" alt="" loading="lazy" decoding="async" src="${mosaicUrl(mosaicPool[k])}" style="left:${c * TILE_W - (r % 2 ? TILE_W / 2 : 0)}px;top:${r * TILE_H}px">`);
    }
    mosaicEl.innerHTML = `<div class="mz" style="width:${cols * TILE_W}px;height:${rows * TILE_H}px">${tiles.join("")}</div>`;
    mosaicEl.addEventListener("error", e => {
      const im = e.target;
      if (!im.matches || !im.matches("img.mt")) return;
      const bad = im.src;
      mosaicPool = mosaicPool.filter(c => !bad.includes(`/api/cover/${c.id}?`));
      const tries = +(im.dataset.tries || 0);
      if (!mosaicPool.length || tries > 4) { im.remove(); return; }
      im.dataset.tries = tries + 1;
      im.src = mosaicUrl(mosaicPool[Math.floor(Math.random() * mosaicPool.length)]);
    }, true);
    clearInterval(mosaicTimer);
    mosaicTimer = setInterval(swapTile, 2600);
  }
  let swapCount = 0;
  async function swapTile() {
    if (!mosaicEl || document.hidden || !mosaicPool.length) return;
    const imgs = mosaicEl.querySelectorAll("img.mt");
    if (!imgs.length) return;
    if (++swapCount % 40 === 0) { try { const more = await api(`/api/covers/sample?n=60`); if (more.length) mosaicPool = more; } catch (_) { /* ignore */ } }
    const im = imgs[Math.floor(Math.random() * imgs.length)];
    const c = mosaicPool[Math.floor(Math.random() * mosaicPool.length)];
    im.classList.add("fade");
    setTimeout(() => { im.src = mosaicUrl(c); im.onload = () => im.classList.remove("fade"); }, 900);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && mosaicEl) setupMosaic(); });

  // ================================================================ le laboratoire (menu caché : BDConverter dans un panneau)
  const lab = $("#lab"), labFrame = $("#lab-frame"), shroom = $("#shroom-btn");
  function toolsUrl() {
    const u = settings.global.tools_url;
    if (u === undefined || u === "auto") return `${location.protocol}//${location.hostname}:3111/`;
    return (u || "").trim();
  }
  function updateShroom() { if (shroom) shroom.hidden = !toolsUrl(); }
  function openLab() {
    const url = toolsUrl(); if (!url) return;
    if (labFrame.getAttribute("src") !== url) labFrame.src = url;
    $("#lab-open").href = url;
    lab.hidden = false; document.body.classList.add("lab-open");
    pow("TADAM !", shroom.getBoundingClientRect().left + 20, 80);
  }
  function closeLab() { lab.hidden = true; document.body.classList.remove("lab-open"); }
  if (shroom) shroom.addEventListener("click", () => lab.hidden ? openLab() : closeLab());
  $("#lab-close").addEventListener("click", closeLab);

  // ================================================================ onomatopées (habillage BD)
  function pow(text, x, y) {
    if (document.documentElement.dataset.skin === "sobre" || !text) return;
    const el = document.createElement("div");
    el.className = "pow"; el.textContent = text;
    if (x == null) { x = window.innerWidth / 2; y = window.innerHeight / 2; }
    el.style.left = x + "px"; el.style.top = y + "px";
    el.style.setProperty("--rot", (Math.random() * 16 - 8).toFixed(1) + "deg");
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1100);
  }
  const powFor = kind => { const t = (POWS[document.documentElement.dataset.skin] || POWS.bd)[kind] || POWS.bd[kind]; return t[Math.floor(Math.random() * t.length)]; };
  let lastPointer = { x: null, y: null };
  document.addEventListener("pointerdown", e => { lastPointer = { x: e.clientX, y: e.clientY }; }, { passive: true });
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
      applyAppearance(); updateShroom(); updateAdultTab();
    } catch (_) { /* hors ligne : on garde la copie locale */ }
  }
  let saveTimer = null, pendingProfile = {}, pendingGlobal = {};
  let quietSave = false;   // pas de « Réglages enregistrés » (bouton saison / fête : son propre message suffit)
  function saveSettings(profilePatch, globalPatch, { quiet = false } = {}) {
    quietSave = quiet;
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
        settings.global = s.global; settings.meta = s; updateShroom(); updateAdultTab();
        if (!quietSave) toast("Réglages enregistrés");
        quietSave = false;
      } catch (e) { toast(`${ICON.warn} Réglage non enregistré : ${esc(e.message)}`); }
    }, 500);
  }

  // ================================================================ toasts
  let toastTimer = null;
  function toast(html, { sticky = false } = {}) {
    toastEl.innerHTML = html;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    // un message d'erreur (⚠) s'en va tout seul au bout de 5 s, même s'il était prévu pour rester ; les messages de
    // progression (scan, résumés…) restent jusqu'à la fin de leur tâche
    const error = html.startsWith(ICON.warn);
    if (!sticky || error) toastTimer = setTimeout(() => { toastEl.hidden = true; }, error ? 5000 : 3500);
  }

  // ================================================================ cartes
  /* Largeur de couverture à demander au serveur : la largeur affichée (en pixels physiques), arrondie à 50 px. */
  function coverWidth(cssWidth) {
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    return Math.max(100, Math.min(1200, Math.ceil((cssWidth * 1.25 * dpr) / 50) * 50));
  }
  function coverUrl(item, cssWidth) {
    const id = item.kind === "folder" ? item.cover_id : item.id;
    const v = (item.kind === "folder" ? "f" + item.cover_id + "-" : "") + (item.cover_ver || item.mtime);   // cover_ver : refaite = nouvelle adresse
    return `/api/cover/${id}?w=${coverWidth(cssWidth)}&v=${v}&t=${encodeURIComponent(settings.global.img_tag || "")}${item.bust ? "&r=" + item.bust : ""}`;
  }
  function coverHtml(item, inner = "", cssWidth) {
    const id = item.kind === "folder" ? item.cover_id : item.id;
    const ph = `<div class="ph">${item.kind === "folder" ? ICON.folder : ICON.book}</div>`;
    const img = id && !item.error
      ? `<img loading="lazy" decoding="async" alt="" src="${coverUrl(item, cssWidth || (THUMB[settings.profile.thumb_size] || THUMB.m))}" onerror="this.parentNode.classList.add('fail');this.remove()">`
      : "";
    const retry = item.kind === "album" && isAdmin() ? `<button class="retry" type="button" data-retry="${item.id}" title="Rescanner ce fichier : relu sur le disque, couverture refaite" aria-label="Rescanner ce fichier">↻</button>` : "";
    return `<div class="cover ${item.kind === "folder" ? "folder" : ""} ${item.error ? "err" : ""}">${ph}${img}${retry}${inner}</div>`;
  }
  const FORMAT_EXT = { zip: ["CBZ", "ZIP"], rar: ["CBR", "RAR"], pdf: ["PDF"], "7z": ["CB7", "7Z"], tar: ["CBT", "TAR", "TGZ"], ace: ["ACE"] };
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
  // ------------------------------------------------ qualité HD / SD (mesurée sur les pages, voir /api/quality)
  const QUALITY_LABEL = { all: "Tout", hd: "HD", sd: "SD" };
  function qualityOk(item) {
    const q = settings.profile.quality;
    if (!q || q === "all" || item.kind === "ghost") return true;
    if (item.kind === "album") return item.q === q;
    if (item.hd_count == null && item.sd_count == null) return true;   // dossier sans album mesuré dedans : on ne sait pas
    return (q === "hd" ? item.hd_count : item.sd_count) > 0;
  }
  const qf = list => (list || []).filter(qualityOk);
  function resLabel(it) { return it.res ? `${it.res[0]} × ${it.res[1]} px` : ""; }
  /* Pastille de qualité : en mode « Tout » et « HD », on signale le HD ; en mode « SD », c'est le SD qui compte
     (une série mélangée y est affichée pour ses albums SD : la pastille dit combien). */
  function qualityBadge(item) {
    const sdMode = settings.profile.quality === "sd";
    if (item.kind === "album") {
      if (sdMode) return item.q === "sd" ? `<span class="qtag sd" title="Album SD : pages de ${resLabel(item)}">SD</span>` : "";
      return item.q === "hd" ? `<span class="qtag hd" title="Album HD : pages de ${resLabel(item)}">HD</span>` : "";
    }
    const hd = item.hd_count || 0, sd = item.sd_count || 0, n = hd + sd;
    if (sdMode) {
      if (!sd) return "";
      return !hd ? `<span class="qtag sd" title="Tous les albums mesurés sont en SD">SD</span>`
        : `<span class="qtag sd part" title="${sd} albums SD sur ${n} mesurés (les ${hd} autres sont HD) : seuls les SD sont affichés dans la série">SD ${sd}/${n}</span>`;
    }
    if (!hd) return "";
    return !sd ? `<span class="qtag hd" title="Tous les albums mesurés sont en HD">HD</span>`
      : `<span class="qtag hd part" title="${hd} albums HD sur ${n} mesurés${settings.profile.quality === "hd" ? " : seuls les HD sont affichés dans la série" : ""}">HD ${hd}/${n}</span>`;
  }
  function renderQualitySwitch() {
    const box = $("#side-quality");
    if (!box) return;
    const cur = settings.profile.quality || "all", px = settings.global.hd_min_px || 2400;
    box.title = `Qualité des albums (mesurée sur les pages : HD à partir de ${px} px)`;
    const hdB = box.querySelector('[data-quality="hd"]'), sdB = box.querySelector('[data-quality="sd"]');
    if (hdB) hdB.title = `Albums HD seulement (pages de ${px} px et plus)`;
    if (sdB) sdB.title = `Albums SD seulement (pages de moins de ${px} px)`;
    for (const b of box.querySelectorAll("button[data-quality]")) {
      b.classList.toggle("on", b.dataset.quality === cur);
      b.setAttribute("aria-pressed", b.dataset.quality === cur ? "true" : "false");
    }
  }
  function card(item, { sub } = {}) {
    if (item.kind === "ghost") return ghostCard(item);
    const letter = esc(letterOf(item.name));
    if (item.kind === "folder") {
      let read = item.read_count ? `<div class="sub">${item.read_count}/${item.album_count} lus${item.reading_count ? " · " + plural(item.reading_count, "en cours", "en cours") : ""}</div>`
        : item.reading_count ? `<div class="sub">${plural(item.reading_count, "album en cours", "albums en cours")}</div>` : "";
      const done = item.album_count && item.read_count >= item.album_count ? `<span class="badge ok" title="Tout lu">${ICON.check}</span>` : "";
      let bdt = "";
      const oneShot = !!item.oneshot;   // décidé par le serveur : fiche Bédéthèque d'un tome unique, ou dossier d'un seul album sans numéro de tome
      if (item.bdt && item.bdt.total > 1) {
        const pct = Math.round((item.bdt.present / item.bdt.total) * 100);
        const full = item.bdt.present >= item.bdt.total;
        bdt = `<div class="sub bdt ${full ? "full" : ""}" title="Bédéthèque : ${esc(item.bdt.title || "")}${item.bdt.status ? " · " + esc(item.bdt.status) : ""}">${full ? "Série complète" : `${item.bdt.present}/${item.bdt.total} tomes`}<i style="width:${pct}%"></i></div>`;
      }
      return `<a class="card folder${oneShot ? " os-linked" : ""}" href="#/f/${item.id}" data-letter="${letter}" data-id="${item.id}" draggable="true"${colorStyle(item)}>
        ${coverHtml(item, `<span class="badge count" title="${plural(item.album_count, "album", "albums")}">${ICON.folder}${item.album_count}</span>${done}${qualityBadge(item)}${item.adult ? `<span class="badge adult" title="Rubrique Adulte">18+</span>` : ""}${item.fav ? FAV : ""}`)}
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
      ${coverHtml(item, badge + qualityBadge(item) + `<button class="info" type="button" data-info="${item.id}" title="Fiche de l'album" aria-label="Fiche de l'album">i</button>${item.meta ? `<button class="info sum" type="button" data-sum="${item.id}" title="Résumé" aria-label="Résumé">…</button>` : ""}`)}
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
    let list = qf(children);
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
    // jusqu'à 20 numéros affichés d'un coup ; au-delà, une fenêtre de 20 autour de la page en cours, plus la première et la dernière
    const SHOW = 20;
    const lo = Math.max(1, Math.min(page - Math.floor(SHOW / 2) + 1, pages - SHOW + 1)), hi = Math.min(pages, lo + SHOW - 1);
    const nums = new Set([1, pages]);
    for (let n = lo; n <= hi; n++) nums.add(n);
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
    const side = isPhone() ? "top" : (settings.profile.letters_side || "right");   // téléphone : rangée horizontale, jamais la barre latérale
    const size = settings.profile.letters_size === "normal" ? " size-normal" : "";
    return `<div class="letters ${side === "top" ? "" : "rail " + side + size}" id="letters">${all.map(l => `<button type="button" data-letter="${l}" class="${present.has(l) ? "on" : ""}" ${present.has(l) ? "" : "disabled"}>${l}</button>`).join("")}</div>`;
  }

  // ================================================================ vues
  function setCrumbs(list, tail) {
    const parts = list.map((c, i) => i === list.length - 1 && !tail
      ? `<span class="cur">${esc(c.name)}</span>`
      : `<a href="${c.href || (i === 0 ? "#/" : "#/f/" + c.id)}">${esc(c.name)}</a>`);
    if (tail) parts.push(`<span class="cur">${esc(tail)}</span>`);
    // bouton « retour » devant le fil d'Ariane, dès qu'on n'est pas à l'accueil : sur tablette et téléphone, il n'y a
    // ni touche Échap ni forcément de bouton « précédent » (Bulle installé sur l'écran d'accueil)
    const back = list.length > 1 || tail ? `<button class="iconbtn crumb-back" type="button" data-crumb-back title="Retour (Échap)" aria-label="Retour">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>` : "";
    crumbsEl.innerHTML = back + parts.join(`<span class="sep">›</span>`);
  }
  crumbsEl.addEventListener("click", e => { if (e.target.closest("[data-crumb-back]")) { e.preventDefault(); escapeBack(); } });

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
    const sizes = ["s", "m", "l", "xl"], si = sizes.indexOf(settings.profile.thumb_size || "m");
    const tools = list.length ? `<div class="gridtools" title="Taille des pochettes"><button type="button" data-thumb="-" ${si <= 0 ? "disabled" : ""} aria-label="Pochettes plus petites">−</button><span>Pochettes</span><button type="button" data-thumb="+" ${si >= sizes.length - 1 ? "disabled" : ""} aria-label="Pochettes plus grandes">+</button></div>` : "";
    return `${tools}${pagerHtml(page, pages, list.length)}
      ${list.length ? `<div class="grid" id="grid">${slice.map(c => card(c)).join("")}</div>` : `<div class="empty">${settings.profile.quality && settings.profile.quality !== "all" && view.children.length ? `Aucun album ${QUALITY_LABEL[settings.profile.quality]} ici (seuls les albums déjà mesurés sont classés). Filtre « Tout » dans le menu pour tout revoir.` : settings.profile.hide_read ? "Tout est lu ici (les albums lus sont masqués dans les réglages)." : "Dossier vide"}</div>`}
      ${pages > 1 ? pagerHtml(page, pages, list.length) : ""}`;
  }

  async function viewFolder(id, page) {
    const p = settings.profile;
    const [data, cont, recent] = await Promise.all([
      api(id ? `/api/browse/${id}` : "/api/browse"),
      id || !p.show_continue || ultraMode() ? null : api("/api/continue"),
      id || !p.show_recent || ultraMode() ? null : api(`/api/recent?n=${+p.recent_count || 18}`),
    ]);
    if (data.empty) return renderEmpty(data.scan);
    setCrumbs(data.breadcrumb);
    document.title = (id ? data.folder.name + " — " : "") + "Bulle";
    view.children = data.children; view.id = id; view.folderName = id ? data.folder.name : "";
    const list = arrange(data.children);
    let html = "";
    if (!id) {
      const contQ = qf(cont), recentQ = qf(recent);
      if (contQ.length) html += `<h2>Reprendre la lecture</h2><div class="row">${contQ.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      if (recentQ.length && data.children.length) html += `<h2>Ajouts récents</h2><div class="row">${recentQ.map(a => card(a, { sub: a.folder })).join("")}</div>`;
      html += `<h2>Bibliothèque <small class="muted">${plural(list.length, "entrée", "entrées")}${p.quality && p.quality !== "all" ? ` · filtre ${QUALITY_LABEL[p.quality]}` : ""}</small></h2>`;
    } else {
      const folders = list.filter(c => c.kind === "folder").length, albums = list.length - folders;
      html += `<h1>${esc(data.folder.name)} <small class="muted h1sub">${[folders ? plural(folders, "dossier", "dossiers") : "", albums ? plural(albums, "album", "albums") : ""].filter(Boolean).join(" · ")}</small>
        <span class="h1tools"><button class="btn ${data.folder.fav ? "fav-on" : ""}" type="button" data-fav="${data.folder.id}" title="Série favorite">${data.folder.fav ? "★ Favori" : "☆ Favori"}</button>
        <button class="btn" type="button" data-addlist="${data.folder.id}" title="Ajouter cette série à une liste">+ Liste</button>
        ${!isAdmin() ? "" : settings.global.adult_hide_tab && settings.global.adult_pin_set && !settings.global.adult_unlocked ? "" : `<button class="btn ${data.folder.adult ? "adult-on" : ""}" type="button" data-action="adult-toggle" data-id="${data.folder.id}" data-adult="${data.folder.adult ? 1 : 0}" title="${data.folder.adult ? "Retirer de la rubrique Adulte" : "Mettre cette série dans la rubrique Adulte (cachée tant que le code n'est pas entré)"}">18+</button>`}
        ${isAdmin() ? `<button class="btn" type="button" data-action="rebuild-folder" data-id="${data.folder.id}" data-name="${esc(data.folder.name)}" title="Relire cette série sur le disque : fichiers ajoutés ou jetés, format, pages, couvertures">↻ Rescanner</button>` : ""}</span></h1>`;
      if (!ultraMode()) html += bdtPanelHtml(data);
    }
    html += lettersHtml(list);
    html += gridFor(id && !ultraMode() ? withGhosts(list, data.bdt) : list, page || 1);
    main.innerHTML = html;
    if (data.bdt_oneshots && data.bdt_oneshots.running) pollOneshots(data.folder.id);
  }

  // ================================================================ Bédéthèque
  function bdtPanelHtml(data, extra) {
    const hasAlbums = data.children.some(c => c.kind === "album");
    if (!hasAlbums || data.bdt_enabled === false) return "";
    if (data.bdt_oneshots) return oneshotsPanelHtml(data);
    const b = data.bdt;
    if (!b && !isAdmin()) return "";   // un lecteur ne lance pas d'analyse : rien à proposer
    const osBtn = isAdmin() ? `<button class="btn" type="button" data-bdt="os-mode" data-mode="oneshots" data-folder="${data.folder.id}" title="Ce dossier rassemble des albums sans rapport entre eux : chacun sera cherché comme sa propre série">Ce sont des one shots</button>` : "";
    if (!b) {
      return `<div class="bdt-panel" id="bdt-panel"><div class="bdt-row"><span class="bdt-logo">BD</span>
        <div class="bdt-main"><span>Comparer ce dossier avec <b>Bédéthèque</b> : tomes présents, manquants, auteurs.</span></div>
        <div class="bdt-actions"><button class="btn" type="button" data-bdt="analyze" data-folder="${data.folder.id}">Analyser</button>${osBtn}</div></div>${extra || ""}</div>`;
    }
    const sr = b.series, pct = b.total ? Math.round((b.present / b.total) * 100) : 0;
    const full = b.total && b.present >= b.total;
    return `<div class="bdt-panel ${full ? "full" : ""}" id="bdt-panel">
      <div class="bdt-row">
        <span class="bdt-logo">BD</span>
        <div class="bdt-main">
          <div><b>${esc(sr.title || "Série")}</b>${sr.genre ? ` · ${esc(sr.genre)}` : ""}${sr.status ? ` · ${esc(sr.status)}` : ""}${sr.years ? ` · ${esc(sr.years)}` : ""}
            <a class="ext" href="${esc(sr.url)}" target="_blank" rel="noopener">voir sur ${siteOf(sr.url)} ↗</a>
            ${sr.score != null && sr.score < 0.9 && !sr.manual ? `<span class="warnlabel" title="La correspondance automatique n'est pas certaine">à vérifier</span>` : ""}</div>
          <div class="bdt-progress"><span>${full ? "Série complète" : `${b.present} / ${b.total} tomes présents`}</span><div class="pbar"><i style="width:${pct}%"></i></div></div>
          ${b.missing.length ? `<div class="bdt-missing">Manquants : ${b.missing.slice(0, 40).map(m => `<a href="${esc(m.url)}" target="_blank" rel="noopener" class="chip">T${m.number}${m.title ? " · " + esc(m.title) : ""}${m.year ? ` <small>${m.year}</small>` : ""}</a>`).join(" ")}${b.missing.length > 40 ? ` … (+${b.missing.length - 40})` : ""}</div>` : ""}
          ${b.unmatched.length ? `<div class="bdt-unmatched">Non reconnus : ${b.unmatched.map(u => `<span class="chip gray" title="Ce fichier n'a pas pu être rattaché à un tome">${esc(u.name)}</span>`).join(" ")}</div>` : ""}
          ${b.duplicates.length ? `<div class="bdt-unmatched">${plural(b.duplicates.length, "doublon", "doublons")} (plusieurs fichiers pour le même tome)</div>` : ""}
        </div>
        ${!isAdmin() ? "" : `<div class="bdt-actions">
          <button class="btn" type="button" data-bdt="refresh" data-folder="${data.folder.id}" title="Relire la fiche sur Bédéthèque">↻ Mettre à jour</button>
          ${sr.detailed ? "" : `<button class="btn" type="button" data-bdt="details" data-folder="${data.folder.id}" title="Lire les auteurs, éditeur, ISBN de chaque tome (une page Bédéthèque par 10 tomes)">Auteurs et détails</button>`}
          <button class="btn" type="button" data-bdt="summaries" data-folder="${data.folder.id}" title="Lire le début du résumé de chaque album (une page Bédéthèque par album, en tâche de fond)">Résumés</button>
          <button class="btn" type="button" data-bdt="change" data-folder="${data.folder.id}">Changer de série</button>
          <button class="btn" type="button" data-bdt="forget" data-folder="${data.folder.id}">Oublier</button>
          ${osBtn}
        </div>`}
      </div>${extra || ""}</div>`;
  }

  /* Dossier de one shots : chaque album est sa propre série sur Bédéthèque. */
  function oneshotsPanelHtml(data) {
    const o = data.bdt_oneshots, c = o.counts, fid = data.folder.id;
    const done = c.ok + c.ambiguous + c.not_found + (c.skip || 0) + (c.series || 0), pct = c.total ? Math.round(done / c.total * 100) : 0;
    const amb = o.albums.filter(a => a.status === "ambiguous"), nf = o.albums.filter(a => a.status === "not_found"), ok = o.albums.filter(a => a.status === "ok");
    const skipped = o.albums.filter(a => a.status === "skip"), aside = o.albums.filter(a => a.status === "series");
    const admin = isAdmin();
    const other = a => admin ? `<button class="btn mini" type="button" data-bdt="os-open" data-album="${a.id}" data-q="${esc(a.query || "")}" title="Chercher cet album sur Bédéthèque : autre titre, homonymes, ou adresse de la fiche">Chercher…</button>
      <button class="btn mini os-skip" type="button" data-bdt="os-skip" data-album="${a.id}" title="Cet album n'existe pas sur Bédéthèque : l'enlever de la liste (il ne sera plus cherché ; « remettre » plus bas pour annuler)">✕ Pas sur Bédéthèque</button>
      <button class="btn mini os-skip" type="button" data-bdt="os-aside" data-album="${a.id}" title="Cet album n'est pas un one shot mais le tome d'une série : le mettre de côté (il ne sera plus cherché ici ; à ranger dans le dossier de sa série ; « remettre » plus bas pour annuler)">📚 Tome d'une série</button>` : "";
    // petite couverture de l'album à droite de son nom ; agrandie au survol (pour la comparer aux propositions)
    const kids = new Map((data.children || []).map(ch => [ch.id, ch]));
    const thumb = a => { const ch = kids.get(a.id) || { id: a.id, kind: "album", mtime: 0 };
      return `<span class="os-thumb" data-os-thumb="${esc(coverUrl(ch, 260))}"><img src="${esc(coverUrl(ch, 40))}" alt="" loading="lazy"></span>`; };
    const ambHtml = amb.map(a => `<div class="os-item"><div class="os-name">${esc(a.name)}${thumb(a)}</div>
        <div class="os-cands">${a.candidates.map(cd => `<button type="button" class="chip gray" ${admin ? `data-bdt="os-pick" data-album="${a.id}" data-url="${esc(cd.url)}"` : "disabled"} title="Choisir cette série">${esc(cd.name)}</button>`).join("")}${other(a)}</div></div>`).join("");
    const nfHtml = nf.map(a => `<div class="os-item"><div class="os-name">${esc(a.name)}${thumb(a)}</div><div class="os-cands">${other(a)}</div></div>`).join("");
    const okHtml = ok.map(a => `<li><span>${esc(a.name)}</span> → <a class="ext" href="${esc(a.series_url)}" target="_blank" rel="noopener">${esc(a.series_title || "")}</a>${siteOf(a.series_url) === "BDfugue" ? ` <span class="srctag">BDfugue</span>` : ""}${a.manual ? "" : a.score != null && a.score < 0.95 ? ` <span class="warnlabel">à vérifier</span>` : ""}${admin ? ` <button class="linkbtn" type="button" data-bdt="os-open" data-album="${a.id}" data-q="${esc(a.query || "")}" title="Choisir une autre série">changer</button> <button class="linkbtn" type="button" data-bdt="os-forget" data-album="${a.id}" title="Oublier ce lien (l'album sera recherché de nouveau)">oublier</button>` : ""}</li>`).join("");
    return `<div class="bdt-panel oneshots ${c.total && c.ok === c.total ? "full" : ""}" id="bdt-panel" data-folder="${fid}">
      <div class="bdt-row">
        <span class="bdt-logo">BD</span>
        <div class="bdt-main">
          <div><b>One shots</b> · chaque album est cherché sur Bédéthèque comme sa propre série</div>
          <div class="bdt-progress"><span>${plural(c.ok, "trouvé", "trouvés")} · ${c.ambiguous} à choisir · ${plural(c.not_found, "introuvable", "introuvables")}${c.skip ? ` · ${plural(c.skip, "écarté", "écartés")}` : ""}${c.series ? ` · ${plural(c.series, "tome de série mis de côté", "tomes de série mis de côté")}` : ""}${c.todo ? ` · <b>${c.todo} pas encore cherchés</b>` : ""}${c.incomplete ? ` · ${plural(c.incomplete, "fiche à compléter", "fiches à compléter")}` : ""}</span><div class="pbar"><i style="width:${pct}%"></i></div></div>
          <div id="os-job" class="muted">${o.running ? `<div class="spinner" style="margin:0;display:inline-block;vertical-align:middle;width:14px;height:14px"></div> Recherche en cours…` : ""}</div>
        </div>
        <div class="bdt-actions">
          ${!admin ? "" : o.running ? `<button class="btn" type="button" data-bdt="os-stop" data-folder="${fid}">Arrêter</button>`
            : c.todo ? `<button class="btn primary" type="button" data-bdt="analyze" data-folder="${fid}" title="Une requête Bédéthèque par album trouvé, au rythme prudent habituel, en tâche de fond">Chercher les ${c.todo} albums</button>`
            : c.incomplete ? `<button class="btn primary" type="button" data-bdt="analyze" data-folder="${fid}" title="Ces albums sont liés à leur série mais leur fiche (auteurs, éditeur, résumé) n'a pas été lue : la page de la série est relue, le plus souvent depuis la mémoire de Bulle, sans requête">Compléter ${plural(c.incomplete, "fiche", "fiches")}</button>` : ""}
          ${c.ok && admin ? `<button class="btn" type="button" data-bdt="summaries" data-folder="${fid}" title="Lire le début du résumé de chaque album trouvé (une page Bédéthèque par album, en tâche de fond)">Résumés</button>` : ""}
          ${admin && !o.running ? `<button class="btn" type="button" data-bdt="os-mode" data-mode="series" data-folder="${fid}" title="Tout ce dossier est une seule série (pas un album en particulier : pour un album, bouton « 📚 Tome d'une série » sur sa ligne)">Tout le dossier est une série</button>` : ""}
        </div>
      </div>
      ${amb.length && admin ? `<details class="os-sec" open><summary>${plural(amb.length, "album à choisir", "albums à choisir")} : plusieurs séries possibles</summary>${ambHtml}</details>` : ""}
      ${nf.length && admin ? `<details class="os-sec"${amb.length ? "" : " open"}><summary>${plural(nf.length, "album introuvable", "albums introuvables")} sous ce titre</summary>${nfHtml}</details>` : ""}
      ${ok.length ? `<details class="os-sec"><summary>${plural(ok.length, "album trouvé", "albums trouvés")}</summary><ul class="os-ok">${okHtml}</ul></details>` : ""}
      ${aside.length && admin ? `<details class="os-sec"><summary>${plural(aside.length, "tome de série mis de côté", "tomes de série mis de côté")} (à ranger dans le dossier de leur série)</summary><ul class="os-ok">${aside.map(a => `<li><span>${esc(a.name)}</span> <button class="linkbtn" type="button" data-bdt="os-forget" data-album="${a.id}" title="Le remettre dans les albums à chercher">remettre</button></li>`).join("")}</ul></details>` : ""}
      ${skipped.length && admin ? `<details class="os-sec"><summary>${plural(skipped.length, "album écarté", "albums écartés")} (pas sur Bédéthèque)</summary><ul class="os-ok">${skipped.map(a => `<li><span>${esc(a.name)}</span> <button class="linkbtn" type="button" data-bdt="os-forget" data-album="${a.id}" title="Le remettre dans les albums à chercher">remettre</button></li>`).join("")}</ul></details>` : ""}
    </div>`;
  }
  let osTimer = null;
  async function pollOneshots(fid) {
    clearTimeout(osTimer);
    let job;
    try { job = await api("/api/bdt/batch"); } catch (_) { return; }
    const el = $("#os-job"), panel = $("#bdt-panel");
    if (!panel || +panel.dataset.folder !== fid) return;
    if (job.running && job.folder_id === fid) {
      if (el) el.innerHTML = `<div class="spinner" style="margin:0;display:inline-block;vertical-align:middle;width:14px;height:14px"></div> ${job.sub_done} / ${job.sub_total} — <i>${esc((job.current || "").split(" › ").pop())}</i> · ${job.os_found} trouvés, ${job.os_ambiguous} à choisir, ${job.os_not_found} introuvables`;
      osTimer = setTimeout(() => pollOneshots(fid), 2500);
    } else if (el && el.textContent.trim()) {
      route();   // fini : on recharge la page (comptes, listes, fiches des albums)
    }
  }

  function bdtChooserHtml(folderId, report) {
    const cands = (report && report.candidates) || [];
    return `<div class="bdt-choose">
      ${report && report.message ? `<p>${esc(report.message)}</p>` : ""}
      ${cands.length ? `<div class="cands">${cands.map(c => `<button type="button" class="cand" data-bdt="pick" data-folder="${folderId}" data-url="${esc(c.url)}">
          <b>${esc(c.name)}</b><small>${[c.genre, c.tomes ? plural(c.tomes, "tome", "tomes") : "", c.exact ? "correspondance exacte" : ""].filter(Boolean).join(" · ")}</small></button>`).join("")}</div>` : ""}
      <form class="bdt-search" data-bdt="search" data-folder="${folderId}"><input type="search" name="q" placeholder="Chercher une série sur Bédéthèque…" value="${esc(report && report.query || "")}"><button class="btn" type="submit">Chercher</button></form>
      <form class="bdt-search" data-bdt="url" data-folder="${folderId}"><input type="url" name="url" placeholder="…ou coller l'adresse de la série ou d'un de ses albums (Bédéthèque, ou BDfugue)"><button class="btn" type="submit">Utiliser</button></form>
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
        if (r.status === "oneshots_started") { toast("Recherche des one shots lancée en tâche de fond"); await route(); pollOneshots(folderId); return; }
        if (r.status === "busy") { toast(esc(r.message)); route(); return; }
        const data = { folder: { id: folderId }, children: [{ kind: "album" }], bdt: null, bdt_enabled: true };
        if (panel) { panel.outerHTML = bdtPanelHtml(data, bdtChooserHtml(folderId, r)); }
        return;
      }
      if (action === "os-mode") {
        if (el.dataset.mode === "series" && !confirm("TOUT ce dossier est une seule série ? Les liens trouvés pour TOUS ses albums seront oubliés.\n\n(Pour un seul album qui est le tome d'une série, annulez et utilisez le bouton « 📚 Tome d'une série » sur sa ligne.)")) return;
        await api(`/api/bdt/mode/${folderId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: el.dataset.mode }) });
        toast(el.dataset.mode === "oneshots" ? "Dossier de one shots : chaque album sera cherché à part" : "Dossier traité comme une série");
        route(); return;
      }
      if (action === "os-stop") { await api("/api/bdt/batch", { method: "DELETE" }); toast("Arrêt demandé (après l'album en cours)"); return; }
      if (action === "os-forget") { await api(`/api/bdt/oneshot/${el.dataset.album}`, { method: "DELETE" }); route(); return; }
      if (action === "os-aside") {
        await api(`/api/bdt/oneshot/${el.dataset.album}/skip`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ why: "series" }) });
        const y = window.scrollY; await route(); window.scrollTo(0, y);
        toast("Mis de côté : tome d'une série, il n'est plus cherché ici (« remettre » dans « tomes de série mis de côté » pour annuler)");
        return;
      }
      if (action === "os-skip") {
        await api(`/api/bdt/oneshot/${el.dataset.album}/skip`, { method: "POST" });
        const y = window.scrollY; await route(); window.scrollTo(0, y);
        toast("Album écarté : il n'est plus cherché sur Bédéthèque (« remettre » dans « albums écartés » pour annuler)");
        return;
      }
      if (action === "os-open") {
        const item = el.closest(".os-item, .os-ok li");
        const old = item.querySelector(".os-search");
        if (old) { old.remove(); return; }
        const box = document.createElement("div");
        box.className = "os-search";
        box.innerHTML = `<form class="bdt-search" data-os="q" data-album="${el.dataset.album}"><input type="search" name="q" value="${esc(el.dataset.q || "")}" placeholder="Titre de l'album ou de la série"><button class="btn" type="submit">Chercher</button></form>
          <form class="bdt-search" data-os="url" data-album="${el.dataset.album}"><input type="url" name="url" placeholder="…ou coller l'adresse de la fiche (Bédéthèque, ou BDfugue si l'album n'est pas sur Bédéthèque)"><button class="btn" type="submit">Utiliser</button></form>
          <div class="os-results"></div>`;
        item.appendChild(box);
        box.querySelector("form").requestSubmit();
        return;
      }
      if (action === "os-pick" || action === "os-query") {
        const body = {};
        if (action === "os-pick") body.url = el.dataset.url;
        else {
          const q = prompt("Titre à chercher sur Bédéthèque :", el.dataset.q || "");
          if (!q || q.trim().length < 2) return;
          body.query = q.trim();
        }
        el.disabled = true;
        const r = await api(`/api/bdt/oneshot/${el.dataset.album}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        toast(r.status === "ok" ? `Trouvé : ${esc(r.series.title)}` : r.status === "ambiguous" ? "Plusieurs séries possibles : choisissez dans la liste" : `Rien trouvé pour « ${esc(r.query)} »`);
        route(); return;
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
    const osf = e.target.closest("form[data-os]");
    if (osf) {
      e.preventDefault();
      const album = osf.dataset.album, box = osf.closest(".os-search"), res = box.querySelector(".os-results");
      if (osf.dataset.os === "url") {
        const url = osf.elements.url.value.trim();
        if (!/bedetheque\.com\/(serie-\d+-BD|BD-)|bdgest\.com\/|bdfugue\.com\/./.test(url)) { toast("Collez l'adresse d'une série (…/serie-1234-BD-…) ou d'un album (…/BD-…-1234.html) de Bédéthèque, une page BDGest, ou la fiche d'un album sur BDfugue"); return; }
        bdtAction("os-pick", { dataset: { album, url } });
        return;
      }
      const q = osf.elements.q.value.trim();
      if (q.length < 2) return;
      res.innerHTML = `<div class="spinner" style="margin:8px 0"></div>`;
      try {
        const r = await api(`/api/bdt/oneshot/${album}/search?q=${encodeURIComponent(q)}`);
        res.innerHTML = (r.results.length ? `<div class="cands">${r.results.map(c => `<button type="button" class="cand" data-bdt="os-pick" data-album="${album}" data-url="${esc(c.url)}">
            <b>${esc(c.name)}</b><small>${[c.genre, c.tomes ? plural(c.tomes, "tome", "tomes") : "", c.exact ? "correspondance exacte" : ""].filter(Boolean).join(" · ")}</small></button>`).join("")}</div>`
          : `<p class="muted">Aucune série trouvée pour « ${esc(q)} ».</p>`)
          + `<p class="muted small">Pas la bonne ? <a class="ext" href="${esc(r.web)}" target="_blank" rel="noopener">Chercher « ${esc(q)} » sur Bédéthèque ↗</a>, puis collez l'adresse de la fiche ci-dessus.${r.site_error ? ` (Recherche du site indisponible : ${esc(r.site_error)})` : ""}</p>`;
      } catch (err) { res.innerHTML = `<p class="error">${esc(err.message)}</p>`; }
      return;
    }
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
      <div class="bdt-panel" id="batch-panel">${batchHtml(job, col, st)}</div>
      <div class="tabs">${tab("all", "Toutes")}${tab("incomplete", "Incomplètes")}${tab("complete", "Complètes")}${tab("ongoing", "En cours de parution")}</div>
      ${shown.length ? `<table class="coltable"><thead><tr><th>Dossier</th><th>Série Bédéthèque</th><th>Statut</th><th>Tomes</th><th></th></tr></thead><tbody>
        ${shown.map(r => `<tr><td><a href="#/f/${r.folder_id}">${esc(r.folder_name)}</a></td><td><a class="ext" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || "")}</a>${r.score != null && r.score < 0.9 && !r.manual ? ` <span class="warnlabel">à vérifier</span>` : ""}</td>
          <td>${esc(r.status || "")}${r.years ? ` <small class="muted">${esc(r.years)}</small>` : ""}</td>
          <td class="num ${r.full ? "ok" : ""}">${r.present ?? "?"} / ${r.total ?? "?"}<div class="pbar"><i style="width:${r.pct}%"></i></div></td>
          <td>${r.full ? "✓" : plural(Math.max(0, (r.total || 0) - (r.present || 0)), "manquant", "manquants")}</td></tr>`).join("")}
      </tbody></table>` : `<div class="empty">${rows.length ? "Rien dans cette catégorie." : "Aucune série analysée pour l'instant. Ouvrez un dossier d'albums et cliquez « Analyser », ou lancez l'analyse de tous les dossiers ci-dessus."}</div>`}
      ${(col.oneshots || []).length ? `<h2>One shots <small class="muted">chaque album est une série à part</small></h2><table class="coltable"><thead><tr><th>Dossier</th><th>Trouvés</th><th>À choisir</th><th>Introuvables</th><th>Pas encore cherchés</th></tr></thead><tbody>
        ${col.oneshots.map(o => `<tr><td><a href="#/f/${o.folder_id}">${esc(o.folder_name)}</a></td><td class="num ${o.ok === o.total ? "ok" : ""}">${o.ok} / ${o.total}<div class="pbar"><i style="width:${o.total ? Math.round(o.ok / o.total * 100) : 0}%"></i></div></td><td class="num">${o.ambiguous || ""}</td><td class="num">${o.not_found || ""}</td><td class="num">${o.todo || ""}</td></tr>`).join("")}
      </tbody></table>` : ""}
      ${col.unlinked.length ? `<details class="unlinked"><summary>${plural(col.unlinked.length, "dossier pas encore analysé", "dossiers pas encore analysés")}</summary><div class="chips">${col.unlinked.slice(0, 400).map(u => `<a class="chip gray" href="#/f/${u.id}">${esc(u.name)} <small>${u.albums}</small></a>`).join(" ")}</div></details>` : ""}`;
    if (job.running) pollBatch();
  }
  function batchHtml(job, col, st) {
    const unlinkedCount = col.unlinked.length;
    const osTodo = (col.oneshots || []).reduce((n, o) => n + (o.todo || 0), 0);
    const osFolders = new Set((col.oneshots || []).filter(o => o.todo).map(o => o.folder_id));
    const requests = col.unlinked.filter(u => !osFolders.has(u.id)).length + osTodo;
    if (!st.enabled) return `<div class="bdt-row"><span class="bdt-logo">BD</span><span>Les requêtes vers Bédéthèque sont désactivées dans les <a href="#/settings">réglages</a>.</span></div>`;
    if (job.running) {
      return `<div class="bdt-row"><div class="spinner" style="margin:0"></div><div class="bdt-main">Analyse en cours : ${job.done} / ${job.total}${job.current ? ` — <i>${esc(job.current)}</i>` : ""}${job.sub_total ? ` <small class="muted">(one shot ${job.sub_done} / ${job.sub_total})</small>` : ""}
        <div class="pbar"><i style="width:${job.total ? Math.round(job.done / job.total * 100) : 0}%"></i></div>
        <small class="muted">${job.linked} liées · ${job.ambiguous} à choisir · ${job.not_found} introuvables${job.os_found + job.os_ambiguous + job.os_not_found ? ` · one shots : ${job.os_found} trouvés, ${job.os_ambiguous} à choisir, ${job.os_not_found} introuvables` : ""} · ${job.errors.length} erreurs</small></div>
        ${isAdmin() ? `<button class="btn" type="button" data-batch="stop">Arrêter</button>` : ""}</div>`;
    }
    const last = job.total ? `<small class="muted">Dernière analyse groupée : ${job.done}/${job.total} dossiers — ${job.linked} liées, ${job.ambiguous} à choisir à la main, ${job.not_found} introuvables${job.errors.length ? `, ${job.errors.length} erreurs (${esc(job.errors[0].error)})` : ""}.</small>` : "";
    return `<div class="bdt-row"><span class="bdt-logo">BD</span><div class="bdt-main">${unlinkedCount ? `${plural(unlinkedCount, "dossier d'albums n'est pas encore comparé", "dossiers d'albums ne sont pas encore comparés")} à Bédéthèque. ${osTodo ? ` Dont ${plural(osTodo, "one shot", "one shots")} à chercher un par un.` : ""} L'analyse groupée fait environ une requête par série, une toutes les ${st.interval} s (environ ${Math.max(1, Math.ceil(requests * st.interval * 1.15 / 60))} min, pauses comprises) et s'arrête quand vous voulez.` : "Tous les dossiers d'albums ont été comparés à Bédéthèque."}${last ? "<br>" + last : ""}</div>
      ${unlinkedCount && isAdmin() ? `<button class="btn primary" type="button" data-batch="start">Analyser les ${unlinkedCount} dossiers</button>` : ""}</div>`;
  }
  async function pollBatch() {
    clearTimeout(batchTimer);
    try {
      const [job, st, col] = await Promise.all([api("/api/bdt/batch"), api("/api/bdt/status"), api("/api/bdt/collection")]);
      const p = $("#batch-panel");
      if (p) p.innerHTML = batchHtml(job, col, st);
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
    if (!res.length) { main.innerHTML = `<div class="empty"><strong>Rien trouvé pour « ${esc(q)} »</strong><p>La recherche ignore les accents et les majuscules et porte sur les noms des dossiers et des fichiers, et sur les auteurs des albums liés à Bédéthèque.</p></div>`; return; }
    const all = qf(res);
    const byAuthor = all.filter(r => r.kind === "album" && r.by && r.by.length);
    const folders = all.filter(r => r.kind === "folder"), albums = all.filter(r => r.kind === "album" && !(r.by && r.by.length));
    let html = "";
    if (byAuthor.length) {
      // regroupés par auteur : « Jean Van Hamme (scénario) — 12 albums »
      const groups = new Map();
      for (const a of byAuthor) { const k = a.by[0]; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(a); }
      html += `<h2>Par auteur <small class="muted">${byAuthor.length}</small></h2>`;
      for (const [who, list] of groups) html += `<h3 class="byauthor">${esc(who)} <small class="muted">${plural(list.length, "album", "albums")}</small></h3><div class="grid">${list.map(a => card(a, { sub: a.folder })).join("")}</div>`;
    }
    if (folders.length) html += `<h2>Séries / dossiers <small class="muted">${folders.length}</small></h2><div class="grid">${folders.map(f => card(f, {})).join("")}</div>`;
    if (albums.length) html += `<h2>Albums <small class="muted">${albums.length}</small></h2><div class="grid">${albums.map(a => card(a, { sub: a.folder })).join("")}</div>`;
    main.innerHTML = html;
  }

  // ================================================================ page Réglages
  function field(label, control, help = "") {
    const inline = control.startsWith('<label class="switch"') ? " inline" : "";
    return `<div class="field${inline}"><div class="flabel"><span>${label}</span>${help ? `<small>${help}</small>` : ""}</div>${control}</div>`;
  }
  const sel = (scope, key, opts, val) => `<select data-scope="${scope}" data-key="${key}">${opts.map(([v, l]) => `<option value="${v}" ${String(v) === String(val) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const chk = (scope, key, val) => `<label class="switch"><input type="checkbox" data-scope="${scope}" data-key="${key}" ${val ? "checked" : ""}><i></i></label>`;
  const num = (scope, key, val, min, max, step = 1) => `<input type="number" data-scope="${scope}" data-key="${key}" value="${val}" min="${min}" max="${max}" step="${step}">`;
  const txt = (scope, key, val, placeholder = "") => `<input type="text" data-scope="${scope}" data-key="${key}" value="${esc(val ?? "")}" placeholder="${esc(placeholder)}" style="width:min(360px,100%)">`;
  const range = (scope, key, val, min, max, unit = "%") => `<span class="rangewrap"><input type="range" data-scope="${scope}" data-key="${key}" value="${val}" min="${min}" max="${max}" step="5" oninput="this.nextElementSibling.textContent=this.value+'${unit}'"><output>${val}${unit}</output></span>`;

  const ALL_SETTINGS_GROUPS = [
    ["look", "Affichage"], ["library", "Bibliothèque"], ["reader", "Lecteur"], ["account", "Mon compte"], ["images", "Images et cache"],
    ["bdt", "Bédéthèque"], ["access", "Comptes et accès"], ["adult", "Adulte"], ["lab", "Laboratoire"], ["tasks", "Tâches"], ["about", "À propos"],
  ];
  const ADMIN_GROUPS = ["images", "bdt", "access", "adult", "lab", "tasks"];
  let SETTINGS_GROUPS = ALL_SETTINGS_GROUPS;
  async function viewSettings(group) {
    const openedGroup = !!group;   // téléphone : « #/settings » = liste des rubriques, « #/settings/xxx » = la rubrique
    setCrumbs([{ id: 0, name: "Accueil" }], "Réglages");
    document.title = "Réglages — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    if (!Object.keys(pendingProfile).length && !Object.keys(pendingGlobal).length) await loadSettings();   // pas pendant qu'un réglage part vers le serveur
    let cache = {}, stats = {}, adult = {}, quality = null;
    try { [cache, stats, adult] = await Promise.all([api("/api/cache"), api("/api/stats"), api("/api/adult")]); } catch (_) { /* ignore */ }
    try { quality = await api("/api/quality"); } catch (_) { /* ignore */ }
    const p = settings.profile, g = settings.global;
    const tabs = p.settings_layout !== "bricks";
    const admin = isAdmin();
    SETTINGS_GROUPS = ALL_SETTINGS_GROUPS.filter(([k]) => admin || !ADMIN_GROUPS.includes(k));
    if (!SETTINGS_GROUPS.some(([k]) => k === group)) group = "look";
    const me = (settings.meta.profiles || []).find(x => x.id === settings.meta.profile_id) || { id: settings.meta.profile_id, name: "Moi" };
    const cacheLine = cache.total != null ? `pages ${fmtSize(cache.pages)} · couvertures ${fmtSize(cache.covers)} · archives décompressées ${fmtSize(cache.extract)}` : "—";
    const sections = {
      look: () => `
        ${field("Habillage", sel("p", "skin", [["bd", "Bande dessinée (ligne claire : contours, bulles, lettrage)"], ["bling", "Bling-bling (noir et or, paillettes)"], ["girly", "Girly (rose pastel, cœurs, tout en rondeur)"], ["ocean", "Aquarium (grand bleu, poissons, bulles qui éclatent)"], ["stars", "Nuit étoilée (bleu nuit qui respire, étoiles filantes)"], ["riso", "Fanzine (papier, deux encres risographie, scotch, tampons)"], ["seasons", "Quatre saisons (suit la date : pétales, lucioles, feuilles mortes, neige)"], ["fetes", "Fêtes (suit le calendrier : jour de l'an, Saint-Valentin, Pâques, fête de la musique, 14 juillet, vacances, Halloween, Noël)"], ["sobre", "Sobre"]], p.skin), "Pour tout le site ; le lecteur reste sobre.")}
        ${field("Thème", sel("p", "theme", [["dark", "Sombre"], ["light", "Clair"], ["auto", "Comme l'appareil"]], p.theme))}
        ${p.skin === "fetes" ? field("Fête", sel("p", "fete", [["auto", `Selon la date (${currentFete().now ? "en ce moment" : "la prochaine"} : ${FETES[currentFete().key].label})`], ...FETE_ORDER.map(k => [k, `${FETES[k].emoji} ${FETES[k].label}`])], p.fete || "auto"), "Habillage Fêtes : couleurs et décor de la fête (le bouton à côté du champignon les fait défiler). Entre deux fêtes, c'est la prochaine qui s'affiche.") : ""}
        ${p.skin === "seasons" ? field("Saison", sel("p", "season", [["auto", `Selon la date (en ce moment : ${SEASON_LABEL[currentSeason()]})`], ["spring", "Printemps (pétales)"], ["summer", "Été (lucioles)"], ["autumn", "Automne (feuilles mortes)"], ["winter", "Hiver (neige)"]], p.season || "auto"), "Habillage Quatre saisons : couleurs et ce qui flotte dans l'air changent avec la saison.") : ""}
        ${field("Réglages : présentation", sel("p", "settings_layout", [["tabs", "Signets (une rubrique à la fois)"], ["bricks", "Briques (tout sur une page)"]], p.settings_layout), "Cette page.")}
        ${field("Style des pochettes", sel("p", "cover_style", [["book", "Livre (dos, tranche, bordure colorée, piles pour les séries)"], ["glow", "Halo coloré"], ["flat", "Simple"]], p.cover_style), "La couleur vient de la couverture elle-même.")}
        ${field("Taille des vignettes", sel("p", "thumb_size", [["s", "Petites"], ["m", "Moyennes"], ["l", "Grandes"], ["xl", "Très grandes"]], p.thumb_size))}
        ${field("Zoom au survol", sel("p", "hover_zoom", [["none", "Aucun"], ["light", "Léger"], ["strong", "Prononcé"]], p.hover_zoom))}
        ${field("Onglets (À lire, Favoris, Listes…)", sel("p", "tabs_side", [["left", "Colonne à gauche"], ["top", "Rangée en haut"]], p.tabs_side), "Sur mobile, toujours en haut.")}
        ${field("Accès par lettre", sel("p", "letters", [["auto", "Automatique (dossiers de 40 entrées et plus)"], ["always", "Toujours"], ["never", "Jamais"]], p.letters))}
        ${field("Position des lettres", sel("p", "letters_side", [["right", "Sur le côté droit"], ["left", "Sur le côté gauche"], ["top", "En haut de la liste"]], p.letters_side))}
        ${field("Taille des lettres", sel("p", "letters_size", [["large", "Grandes"], ["normal", "Normales"]], p.letters_size))}
        ${field("Couvertures au hasard en bas de la colonne", chk("p", "side_covers", p.side_covers !== false), "Jusqu'à deux couvertures posées au hasard dans l'espace libre, une nouvelle toutes les 6 à 8 secondes avec une transition différente. Un clic ouvre sa fiche.")}
        ${field("Mosaïque de couvertures en fond", sel("p", "mosaic", [["drift", "Oui, qui dérive lentement"], ["fixed", "Oui, fixe"], ["off", "Non"]], p.mosaic), "Pas dans le lecteur. Les couvertures changent doucement en fondu.")}
        ${field("Mosaïque : opacité", range("p", "mosaic_opacity", p.mosaic_opacity, 5, 100), "Plus c'est bas, plus la mosaïque s'efface derrière le contenu.")}
        ${field("Mosaïque : luminosité", range("p", "mosaic_brightness", p.mosaic_brightness, 10, 150))}
        ${field("Mosaïque : effet transparence", chk("p", "mosaic_glass", p.mosaic_glass), "Les panneaux, la colonne et les fiches deviennent translucides (verre dépoli). Un peu plus lourd pour le navigateur.")}
        <p><button class="btn" type="button" data-action="reset-profile">Réglages d'affichage par défaut</button></p>`,
      library: () => `
        ${field("Tri", sel("p", "sort", [["natural", "Alphabétique naturel (T2 avant T10)"], ["recent", "Ajouts récents d'abord"], ["unread", "Non lus d'abord"]], p.sort))}
        ${field("Vignettes par page", sel("p", "per_page", [[24, "24"], [48, "48"], [96, "96"], [192, "192"], [0, "Toutes (pas de pages)"]], p.per_page), "Au-delà, la liste est découpée en pages.")}
        ${field("Masquer les albums lus", chk("p", "hide_read", p.hide_read))}
        ${field("Nombre de pages sur les cartes", chk("p", "show_pages", p.show_pages))}
        ${field("« Reprendre la lecture » sur l'accueil", chk("p", "show_continue", p.show_continue))}
        ${field("« Ajouts récents » sur l'accueil", chk("p", "show_recent", p.show_recent))}
        ${field("Nombre d'ajouts récents", num("p", "recent_count", p.recent_count, 6, 60, 6))}
        ${field("Rouvrir le dernier dossier au démarrage", chk("p", "remember_folder", p.remember_folder))}
        ${field("Afficher les tomes manquants dans les dossiers", chk("p", "bdt_ghosts", p.bdt_ghosts), "Cartes grisées à leur place dans la série (tri naturel), d'après Bédéthèque.")}
        ${field("Noms des albums d'après Bédéthèque", chk("p", "bdt_titles", p.bdt_titles), "« T3 · Titre officiel » au lieu du nom du fichier, quand il est connu. Les fichiers ne sont jamais renommés.")}
        ${admin ? `<h3 class="setsub">Qualité HD / SD</h3>
        ${field("Mesurer automatiquement", chk("g", "quality_auto", g.quality_auto !== false), "Après chaque scan, Bulle mesure en arrière-plan la taille des pages des albums nouveaux ou modifiés (deux pages par album, lecture seule : les fichiers ne sont jamais modifiés).")}
        ${field("Seuil HD", num("g", "hd_min_px", g.hd_min_px || 2400, 800, 8000, 100) + ` <span class="muted">px</span>`, "Grand côté des pages à partir duquel un album compte comme HD. Repères : 1920 × 2650 ≈ 2650 px, 2560 × 3450 ≈ 3450 px, 3184 × 4200 = 4200 px. Changer le seuil reclasse tout de suite, sans remesurer.")}
        <div class="field"><div class="flabel"><span>Albums mesurés</span><small>Le filtre « Qualité » du menu ne classe que les albums déjà mesurés.</small></div>
          <div id="quality-box">${qualityBoxHtml(quality)}</div></div>
        ${field("Album considéré lu", sel("g", "read_threshold", [[1, "À la dernière page"], [0.95, "À partir de 95 %"], [0.9, "À partir de 90 %"], [0.8, "À partir de 80 %"]], g.read_threshold))}` : ""}`,
      account: () => `
        <div class="field"><div class="flabel"><span>Vignette</span><small>Une photo ou une image (réduite à 96 px, gardée dans Bulle), ou un emoji / des initiales.</small></div>
          <div class="actions avatar-edit">${avatarHtml(me, "big")}
            <label class="btn">Choisir une image<input type="file" accept="image/*" data-avatar-file="${me.id}" hidden></label>
            <button class="btn" type="button" data-action="avatar-text" data-id="${me.id}">Emoji ou lettres</button>
            ${me.avatar ? `<button class="btn" type="button" data-action="avatar-clear" data-id="${me.id}">Retirer</button>` : ""}</div></div>
        <div class="field"><div class="flabel"><span>Nom</span><small>Affiché sur l'écran « Qui lit ? ».</small></div>
          <div class="actions"><button class="btn" type="button" data-action="account-name" data-id="${me.id}" data-name="${esc(me.name)}">${esc(me.name)} — changer</button></div></div>
        <div class="field"><div class="flabel"><span>Mot de passe</span><small>${me.has_pin ? "Demandé pour ouvrir ce profil." : "Aucun : n'importe qui peut ouvrir ce profil."} Il est gardé chiffré (jamais en clair). 4 caractères au moins.</small></div>
          <div class="actions"><button class="btn" type="button" data-action="account-pin" data-id="${me.id}">${me.has_pin ? "Changer le mot de passe" : "Définir un mot de passe"}</button>${me.has_pin ? `<button class="btn" type="button" data-action="account-pin-clear" data-id="${me.id}">Supprimer</button>` : ""}</div></div>
        <div class="field"><div class="flabel"><span>Rôle</span><small>${me.role === "admin" ? "Administrateur : réglages, scans, comptes, rubrique Adulte." : "Lecteur : lecture, progression, listes, réglages d'affichage. Les réglages du serveur sont réservés à l'administrateur."}</small></div>
          <div class="actions"><span class="prole">${me.role === "admin" ? "Administrateur" : "Lecteur"}</span></div></div>
        <p class="muted">Pour que la déconnexion serve à quelque chose, mettez un mot de passe sur les comptes qui comptent${isAdmin() ? ` et activez « Demander qui lit ? à l'ouverture » (<a href="#/settings/access">Comptes et accès</a>)` : ""} : sans cela, Bulle rouvre directement sur le premier profil.</p>
        <p class="actions"><button class="btn" type="button" data-action="logout">Se déconnecter</button></p>`,
      reader: () => `
        ${field("Affichage par défaut", sel("p", "reader_mode", [["single", "Une page"], ["double", "Deux pages (double page)"], ["scroll", "Défilement continu"], ["panels", "Case par case"]], p.reader_mode), "Touche D dans le lecteur pour changer.")}
        ${field("Double page : couverture seule", chk("p", "reader_cover_alone", p.reader_cover_alone), "Les planches larges (paysage) sont toujours affichées seules.")}
        ${field("Case par case : montrer la page entière avant les cases", chk("p", "reader_panels_full_first", p.reader_panels_full_first), "Désactivé : après la dernière case, on enchaîne directement sur la première case de la planche suivante. Touche C dans le lecteur ; une planche sans cases reconnues s'affiche entière.")}
        ${field("Case par case : cases larges (bandeaux)", sel("p", "reader_panels_wide", [["split", "Lues en deux ou trois temps quand elles restent petites"], ["fit", "Toujours entières, réduites pour tenir dans l'écran"]], p.reader_panels_wide), "Une case qui fait toute la largeur de la planche ne peut pas être agrandie sur un écran étroit (téléphone) : elle est alors lue par morceaux, de gauche à droite (l'inverse en manga), chaque morceau grossi comme une case normale. Le compteur indique « case 3/7 (1/2) ».")}
        ${field("Case par case : marge autour de la case", sel("p", "reader_panels_margin", [[0, "Aucune : la case touche les bords"], [3, "Fine"], [8, "Large"]], p.reader_panels_margin))}
        ${field("Case par case : autour de la case", sel("p", "reader_panels_dim", [[100, "Masquer : seule la case est visible"], ["blur", "Flou : la planche floutée autour de la case"], [70, "Assombrir beaucoup"], [40, "Assombrir un peu"], [0, "Laisser la planche visible"]], p.reader_panels_dim), "Sur un écran large, une case haute et étroite ne peut pas remplir l'écran : ses voisines apparaissent à côté. Masquée, seule la case en cours est visible ; le masque la suit quand on passe à la suivante, et s'efface quand on glisse pour recadrer. Flou : à la place du noir, la planche floutée, comme une vidéo verticale.")}
        ${field("Case par case : passage d'une case à l'autre", sel("p", "reader_panels_speed", [[0, "Instantané (pas de glissement)"], [0.3, "Glissement rapide"], [0.55, "Glissement normal"], [0.9, "Glissement lent"], [1.4, "Glissement très lent"]], p.reader_panels_speed), "Vitesse à laquelle l'image glisse et zoome d'une case vers la suivante.")}
        ${field("Case par case : texte à cheval sur deux cases", chk("p", "reader_panels_join", p.reader_panels_join), "Quand un cartouche ou une bulle déborde d'une case sur sa voisine, les deux cases sont montrées ensemble pour lire le texte en entier. Désactivé : chaque case seule (le texte peut être coupé).")}
        ${field("Rogner les marges blanches", chk("p", "reader_trim", p.reader_trim), "Le tour blanc des pages est coupé à l'affichage, pour une planche plus grande à l'écran (une page, double page, défilement). Les fichiers ne sont jamais modifiés ; une page blanche ou un dessin à fond perdu restent entiers. Touche R dans le lecteur.")}
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
        ${field("Mode nuit : assombrir les pages", sel("p", "reader_night", [[0, "Non"], [15, "Un peu (15 %)"], [30, "Moyen (30 %)"], [50, "Beaucoup (50 %)"]], p.reader_night))}`,
      images: () => `
        ${field("Qualité JPEG", sel("g", "quality", [["eco", "Économique (80, plus rapide sur mobile)"], ["normal", "Normale (90, couleurs intactes)"], ["max", "Maximale (95)"]], g.quality), "Les pages déjà en cache gardent leur ancienne qualité jusqu'à ce qu'on vide le cache.")}
        ${field("Renforcer la netteté après réduction", chk("g", "sharpen", g.sharpen))}
        ${field("Largeur des couvertures (px)", sel("g", "cover_width", [[400, "400"], [600, "600"], [800, "800"], [1000, "1000"]], g.cover_width), "Après changement, utilisez « Régénérer les couvertures ».")}
        ${field("Scan", sel("g", "scan_mode", [["fast", "Rapide : liste des fichiers seulement, couvertures faites à l'affichage"], ["normal", "Normal : liste + couvertures manquantes en tâche de fond"], ["thorough", "Minutieux : à CHAQUE scan, tous les albums rouverts et toutes les couvertures refaites"]], g.scan_mode || "normal"), "Minutieux refait tout à chaque scan (y compris le scan automatique) : très long sur un NAS. À utiliser une fois pour réparer, puis revenir en Normal. La couverture est toujours la première page, dans l'ordre naturel des noms de fichiers.")}
        ${field("Scan au démarrage", chk("g", "scan_on_start", g.scan_on_start !== false), "Après une mise à jour ou un redémarrage du conteneur, Bulle repasse sur tous les dossiers. Désactivé : rien au démarrage, les nouvelles BD arrivent avec le bouton ↻ ou le rescan automatique ci-dessous. Ce réglage l'emporte sur la variable SCAN_ON_START de la stack.")}
        ${field("Rescan automatique", sel("g", "scan_interval_hours", [[0, "Jamais (bouton ↻ seulement)"], [1, "Toutes les heures"], [6, "Toutes les 6 h"], [12, "Toutes les 12 h"], [24, "Une fois par jour"], [168, "Une fois par semaine"]], g.scan_interval_hours))}
        ${field("Couvertures générées en parallèle", num("g", "preload_threads", g.preload_threads, 1, 8), "Baisser à 1 sur un petit serveur.")}
        ${field("Taille maximale du cache des pages (Go)", num("g", "cache_max_gb", g.cache_max_gb, 0, 1000), "0 = sans limite. Les pages les moins récentes sont supprimées en premier.")}
        <div class="field"><div class="flabel"><span>Cache actuel</span><small id="cache-size">${cacheLine}</small></div>
          <div class="actions"><button class="btn" type="button" data-action="scan">↻ Scanner maintenant</button>
          <button class="btn" type="button" data-action="clear-cache">Vider le cache des pages</button>
          <button class="btn" type="button" data-action="rebuild-covers">Régénérer toutes les couvertures</button>
          ${stats.errors ? `<button class="btn" type="button" data-action="retry-errors">↻ Réessayer les ${plural(stats.errors, "album en échec", "albums en échec")}</button>` : ""}</div></div>
        <p class="muted">Pour une seule série : bouton « ↻ Rescanner » en haut de sa page. Pour un seul fichier : le petit ↻ en bas à droite de sa pochette (au survol), ou « Rescanner ce fichier » dans sa fiche — il est relu sur le disque (format, taille, pages, couverture).</p>`,
      bdt: () => `
        ${field("Autoriser les requêtes vers bedetheque.com", chk("g", "bdt_enabled", g.bdt_enabled), "Uniquement quand vous cliquez « Analyser » (ou l'analyse groupée de la page Collection).")}
        ${field("Requêtes par minute (maximum)", num("g", "bdt_per_minute", g.bdt_per_minute, 1, 60), "Intervalle irrégulier autour de 60 / ce nombre, jamais plus dans une minute glissante. 10 par défaut.")}
        ${field("Pause toutes les N requêtes (tâches de fond)", num("g", "bdt_pause_every", g.bdt_pause_every, 0, 1000, 10), "Analyse groupée et résumés en série ; 0 = pas de pause. Vos clics ne sont jamais mis en pause.")}
        ${field("Durée de la pause (min)", num("g", "bdt_pause_minutes", g.bdt_pause_minutes, 0.5, 30, 0.5), "± 20 % au hasard.")}
        ${field("Délai minimum entre deux requêtes (s)", num("g", "bdt_interval", g.bdt_interval, 1, 30, 0.5))}
        ${field("Résumé lu à l'ouverture d'une fiche", chk("g", "bdt_auto_summary", g.bdt_auto_summary), "Une requête vers la fiche de l'album, une seule fois ; le bouton « Résumés » d'une série les lit tous en tâche de fond.")}
        <p class="muted">Rien n'est jamais écrit dans vos fichiers : les informations Bédéthèque restent dans la base de Bulle. <a href="#/collection">Voir la collection</a>.</p>`,
      access: () => `
        ${field("Imposer le HTTPS", chk("g", "force_https", g.force_https), `Une visite en http:// depuis Internet est renvoyée vers https://, et le navigateur retient de n'utiliser que le HTTPS. Le certificat vient de votre proxy (Nginx Proxy Manager…), qui doit transmettre l'en-tête X-Forwarded-Proto. L'accès par l'adresse du réseau local (192.168…) reste possible en http. ${location.protocol === "https:" ? "" : "<b>À activer depuis une page ouverte en https://</b> (sinon Bulle refuse, pour ne pas vous enfermer dehors)."}`)}
        ${field("Se connecter avec un compte", chk("g", "account_login", g.account_login), "Pour mettre Bulle sur Internet : à l'ouverture, on tape le nom d'un compte et son mot de passe, sinon on ne voit rien (ni les BD, ni la liste des comptes). Chaque personne a son compte, que vous pouvez supprimer à tout moment. Après 5 essais ratés, l'adresse est bloquée 15 minutes. On reste connecté 30 jours. Le flux OPDS demande aussi le nom du compte et son mot de passe. Avant d'activer : donnez un mot de passe à votre compte (Mon compte), c'est avec lui que vous vous connecterez.")}
        ${g.account_login ? "" : field("Demander « qui lit ? » à l'ouverture", chk("g", "require_profile", g.require_profile), "Chaque profil a sa progression et ses réglages d'affichage.")}
        <div class="field"><div class="flabel"><span>Comptes</span><small>${g.account_login ? "Chaque compte a un mot de passe (8 caractères au moins, gardé chiffré) : on se connecte avec le nom du compte et ce mot de passe." : "Un mot de passe par compte est facultatif (4 caractères au moins, gardé chiffré)."} Administrateur : réglages, scans, comptes, rubrique Adulte ; lecteur : lecture et listes seulement. Il faut garder au moins un administrateur.</small></div>
          <div class="plist">${(settings.meta.profiles || []).map(pr => `<span class="prow">${avatarHtml(pr, "small")} ${esc(pr.name)}${pr.has_pin ? " 🔒" : ""}
            <select data-role="${pr.id}" title="Rôle"><option value="reader" ${pr.role !== "admin" ? "selected" : ""}>Lecteur</option><option value="admin" ${pr.role === "admin" ? "selected" : ""}>Administrateur</option></select>
            <button class="btn mini" type="button" data-action="profile-edit" data-id="${pr.id}" data-name="${esc(pr.name)}">Modifier</button>${pr.id === 1 ? "" : `<button class="btn mini" type="button" data-action="profile-delete" data-id="${pr.id}" data-name="${esc(pr.name)}">Supprimer</button>`}</span>`).join("")}
            <button class="btn mini" type="button" data-action="profile-add">+ Ajouter un compte</button></div></div>
        ${g.account_login ? "" : `<div class="field"><div class="flabel"><span>Code d'accès à Bulle</span><small>${g.access_pin_set ? "Un code est demandé à l'ouverture (et pour le flux OPDS : mot de passe = ce code)." : "Aucun code : tout le réseau local peut ouvrir Bulle."}</small></div>
          <div class="actions"><button class="btn" type="button" data-action="access-pin-set">${g.access_pin_set ? "Changer le code" : "Définir un code"}</button>${g.access_pin_set ? `<button class="btn" type="button" data-action="access-pin-clear">Supprimer le code</button>` : ""}</div></div>`}
        ${field("Flux OPDS pour les applis mobiles", chk("g", "opds_enabled", g.opds_enabled), `Adresse à donner à l'appli (Panels, Chunky, Moon+, Mihon…) : <code>${esc(location.origin)}/opds</code>`)}`,
      adult: () => `
        <p class="muted">Les séries marquées « 18+ » (bouton en haut de leur page) disparaissent de partout — accueil, recherche, hasard, mosaïque, OPDS — tant que le code n'est pas entré. Une fois entré, elles restent visibles 12 heures sur l'appareil. Rien n'est déplacé ni modifié dans vos fichiers.</p>
        <div class="field"><div class="flabel"><span>Code de la rubrique</span><small>${g.adult_pin_set ? (g.adult_unlocked ? "Code défini · rubrique déverrouillée sur cet appareil." : "Code défini · rubrique verrouillée.") : "Aucun code : les séries 18+ sont visibles par tout le monde. Définissez un code pour les cacher."}</small></div>
          <div class="actions">${g.adult_pin_set && !g.adult_unlocked ? `<button class="btn primary" type="button" data-action="adult-unlock">Déverrouiller</button>` : ""}
          ${g.adult_pin_set && g.adult_unlocked ? `<button class="btn" type="button" data-action="adult-lock">Verrouiller maintenant</button>` : ""}
          <button class="btn" type="button" data-action="adult-pin-set">${g.adult_pin_set ? "Changer le code" : "Définir un code"}</button>
          ${g.adult_pin_set ? `<button class="btn" type="button" data-action="adult-pin-clear">Supprimer le code</button>` : ""}</div></div>
        ${g.adult_pin_set && !g.adult_unlocked ? "" : field("Cacher l'entrée « Adulte » du menu", chk("g", "adult_hide_tab", g.adult_hide_tab), "Plus rien dans la colonne de gauche, et le bouton « 18+ » des séries n'apparaît que rubrique déverrouillée. Accès : Réglages › Adulte, ou l'adresse #/adult.")}
        <div class="field"><div class="flabel"><span>Séries dans la rubrique</span><small>${plural(g.adult_count || 0, "série", "séries")}${g.adult_count && !adult.folders ? " · entrez le code pour voir la liste" : ""}</small></div>
          <div class="plist">${(adult.folders || []).map(f => `<span class="prow"><a href="#/f/${f.id}">${esc(f.name)}</a> <button class="btn mini" type="button" data-action="adult-toggle" data-id="${f.id}" data-adult="1" data-stay="1">Retirer</button></span>`).join("")}
            ${adult.folders && !adult.folders.length ? `<span class="muted">Aucune pour l'instant : ouvrez une série et cliquez « 18+ ».</span>` : ""}</div></div>
        <p class="muted"><a href="#/adult">Ouvrir la rubrique Adulte</a> (aussi dans la colonne de gauche dès qu'une série y est).</p>`,
      lab: () => `
        ${field("Adresse de BDConverter", txt("g", "tools_url", g.tools_url, "auto"), `Le petit champignon en haut à gauche ouvre BDConverter dans un panneau. « auto » = même machine que Bulle, port 3111 (${esc(location.protocol + "//" + location.hostname + ":3111/")}) ; vide = champignon masqué.`)}
        ${field("Recherche BDGest en secours", chk("g", "bdt_bdgest", g.bdt_bdgest), "Quand l'index de Bédéthèque ne trouve rien de sûr (nom approchant, homonymes), Bulle cherche aussi « dans tout le site » BDGest : c'est la même base, mais cette recherche trouve aussi les albums par leur titre, et l'année du fichier départage les homonymes (« Là-bas (2003) »). Une requête de plus, au rythme prudent, pour chaque album ou série concerné. La recherche à la main (« Chercher… ») l'utilise toujours.")}
        ${field("Recherche BDfugue en secours", chk("g", "bdt_bdfugue", g.bdt_bdfugue), "Quand un album ou une série n'est pas sur Bédéthèque (rien trouvé, ou rien de sûr), Bulle cherche aussi sur BDfugue, la librairie en ligne : titre, auteurs, éditeur, date, résumé et couverture. Un album au titre identique est lié tout seul ; sinon il s'ajoute aux propositions. Une requête de plus par album ou série concerné, au même rythme prudent. On peut aussi coller l'adresse d'une fiche BDfugue dans « Chercher… ».")}`,
      tasks: () => `<p class="muted">Tout ce que Bulle fait en arrière-plan : scan, couvertures, mesure HD/SD, résumés et fiches Bédéthèque. « Arrêter » laisse la tâche finir l'élément en cours, puis elle s'interrompt : rien n'est laissé à moitié écrit.</p><div id="tasks-box"><div class="spinner"></div></div>
        <h3 class="setsub">Lots de planches à corriger</h3>
        <p class="muted">Prépare deux lots de 50 planches tirées dans toute la bibliothèque (tous les styles, dont 10 de « Watchmen » par lot si l'album est là), sans doublon d'un lot à l'autre. Pour chaque planche : un JPG avec les cases détectées et numérotées, et la page seule. Le ZIP contient un dossier par lot, à donner tel quel à un ami, et un fichier index.json à garder pour soi. La rubrique Adulte est exclue, aucun album n'est modifié.</p>
        <p><button class="btn" type="button" data-lots="start">Préparer les deux lots</button> <a class="btn" id="lots-dl" href="/api/lots/download" hidden>Télécharger le ZIP</a> <small class="muted" id="lots-info"></small></p>`,
      about: () => `
        <p class="muted">Bulle ${esc(settings.meta.version || "")} · ${plural(stats.albums || 0, "album", "albums")} dans ${plural(stats.folders || 0, "dossier", "dossiers")} (${fmtSize(stats.size || 0)}) · dernier scan : ${fmtDate(stats.last_scan)}<br>
        Dossier des BD : <code>${esc(settings.meta.library_root || "")}</code> · <a href="https://github.com/kermess14/bulle" target="_blank" rel="noopener">github.com/kermess14/bulle</a></p>
        <p class="muted">Raccourcis : Échap revient en arrière ; dans le lecteur, D change l'affichage, C le case par case, T les miniatures, + / − / 0 le zoom.</p>`,
    };
    const section = ([k, name]) => `<section data-group="${k}"><h2>${name}</h2>${sections[k]()}</section>`;
    const head = `<div class="listhead"><h1>Réglages</h1><button class="btn" type="button" data-action="back" title="Revenir à la page précédente (Échap)">✕ Fermer</button></div>`;
    if (isPhone()) {
      // téléphone : d'abord la liste des rubriques (comme les réglages d'Android), puis la rubrique seule
      const ICONS = { look: "🎨", library: "📚", reader: "📖", account: "👤", images: "🖼️", bdt: "🏷️", access: "🔐", adult: "🔞", lab: "🍄", tasks: "⏱️", about: "ℹ️" };
      const HELP = { look: "Habillage, thème, pochettes, mode léger", library: "Scan, tri, classement, qualité HD/SD", reader: "Affichage, case par case, marges, zoom", account: "Profil, mot de passe, déconnexion", images: "Qualité des pages, cache", bdt: "Fiches et résumés Bédéthèque", access: "Comptes, code d'accès", adult: "Rubrique verrouillée", lab: "BDConverter, recherche BDGest et BDfugue", tasks: "Ce qui tourne en arrière-plan, et l'arrêter", about: `Bulle ${esc(settings.meta.version || "")}` };
      if (!openedGroup) {
        setCrumbs([{ id: 0, name: "Accueil" }], "Réglages");
        main.innerHTML = `<h1>Réglages</h1><nav class="smenu">${SETTINGS_GROUPS.map(([k, name]) => `<a href="#/settings/${k}"><span class="ico">${ICONS[k] || "•"}</span><span>${name}<small>${HELP[k] || ""}</small></span></a>`).join("")}</nav>`;
        return;
      }
      const cur = SETTINGS_GROUPS.find(([k]) => k === group);
      setCrumbs([{ id: 0, name: "Accueil" }, { id: -1, name: "Réglages", href: "#/settings" }], cur[1]);
      main.innerHTML = `<div class="settings tabbed"><div class="spane">${section(cur)}</div></div>`;
      if (quality && quality.job && quality.job.running) pollQuality();
      pollTasks();
      return;
    }
    if (tabs) {
      main.innerHTML = `${head}<div class="settings tabbed">
        <nav class="stabs" aria-label="Rubriques">${SETTINGS_GROUPS.map(([k, name]) => `<a class="tab ${k === group ? "on" : ""}" href="#/settings/${k}">${name}</a>`).join("")}</nav>
        <div class="spane">${section(SETTINGS_GROUPS.find(([k]) => k === group))}</div></div>`;
    } else {
      main.innerHTML = `${head}<div class="settings">${SETTINGS_GROUPS.map(section).join("")}</div>`;
    }
    if (quality && quality.job && quality.job.running) pollQuality();
    pollTasks();
  }

  /* Page « Tâches » : liste des tâches de fond, rafraîchie toutes les 2 s tant qu'elle est à l'écran. */
  let tasksTimer = null;
  function taskRow(t) {
    const running = t.state === "running" || t.state === "stopping";
    const pct = running && t.total ? Math.min(100, Math.round((t.done || 0) / t.total * 100)) : 0;
    const prog = running ? (t.total ? `${t.done || 0} / ${t.total}<div class="pbar"><i style="width:${pct}%"></i></div>` : `<div class="pbar indet"><i></i></div>`) : "";
    const when = running ? (t.started_at ? "depuis " + fmtDate(t.started_at) : "en cours") : t.finished_at ? "terminée " + fmtDate(t.finished_at) : "pas encore lancée";
    const state = t.state === "stopping" ? "Arrêt en cours…" : running ? "En cours" : "Au repos";
    const btn = t.state === "running" ? `<button class="btn" type="button" data-task-stop="${t.id}">Arrêter</button>`
      : t.state === "stopping" ? `<button class="btn danger" type="button" data-task-kill title="La tâche ne s'arrête pas ? Redémarre Bulle pour la couper net">Forcer l'arrêt…</button>` : "";
    return `<tr class="${running ? "run" : ""}"><td><b>${esc(t.label)}</b>${t.detail ? `<br><small class="muted">${esc(t.detail)}</small>` : ""}</td><td>${state}</td><td class="num">${prog}</td><td>${esc(when)}</td><td class="act">${btn}</td></tr>`;
  }
  function renderLots(l) {
    const a = document.getElementById("lots-dl"), i = document.getElementById("lots-info");
    if (!a || !l) return;
    a.hidden = !l.ready;
    if (i) i.textContent = l.ready ? `Dernier ZIP : ${fmtSize(l.size)}, préparé ${fmtDate(l.at)}` : "";
  }
  function renderTasks(box, list, recent = []) {
    const running = list.filter(t => t.state === "running").length;
    box.innerHTML = `<table class="coltable tasks"><thead><tr><th>Tâche</th><th>État</th><th>Avancement</th><th>Dernière exécution</th><th></th></tr></thead><tbody>${list.map(taskRow).join("")}</tbody></table>
      ${recent.length ? `<h3 class="setsub">Activité récente</h3><ul class="alist">${recent.map(r => `<li><span>${r.ok ? "" : ICON.warn + " "}${esc(r.label)}</span><span class="muted">${fmtDate(r.at)}</span></li>`).join("")}</ul>` : ""}
      <p>${running > 1 ? `<button class="btn" type="button" data-tasks-stopall>Tout arrêter</button>` : ""}${running === 0 ? `<span class="muted">Rien ne tourne en ce moment.</span>` : ""}</p>`;
  }
  async function pollTasks() {
    clearTimeout(tasksTimer);
    const box = document.getElementById("tasks-box");
    if (!box) return;
    try {
      const j = await api("/api/tasks");
      const again = document.getElementById("tasks-box");
      if (!again) return;
      renderTasks(again, j.tasks, j.recent);
      renderLots(j.lots);
    } catch (e) { box.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
    tasksTimer = setTimeout(pollTasks, 2000);
  }
  main.addEventListener("click", async e => {
    const lots = e.target.closest("[data-lots]");
    if (lots) {
      try { await api("/api/lots", { method: "POST", body: JSON.stringify({}), headers: { "Content-Type": "application/json" } }); toast("Préparation des lots lancée : suivez-la dans le tableau ci-dessus."); pollTasks(); }
      catch (err) { toast(`${ICON.warn} ${esc(err.message)}`); }
      return;
    }
    const one = e.target.closest("[data-task-stop]"), all = e.target.closest("[data-tasks-stopall]"), kill = e.target.closest("[data-task-kill]");
    if (kill) {
      if (!confirm("Forcer l'arrêt redémarre Bulle.\n\nToutes les tâches en cours sont coupées net et le site est inaccessible quelques secondes. Un scan reprendra au démarrage. Vos fichiers BD ne sont jamais modifiés.\n\nÀ utiliser seulement si « Arrêter » n'aboutit pas. Redémarrer Bulle ?")) return;
      try {
        await api("/api/tasks/kill", { method: "POST", body: JSON.stringify({ confirm: true }), headers: { "Content-Type": "application/json" } });
      } catch (_) { /* le serveur coupe la connexion en redémarrant */ }
      clearTimeout(tasksTimer);
      toast(`<div class="spinner"></div> Bulle redémarre…`, { sticky: true });
      const back = async () => { try { await api("/api/auth/status"); location.reload(); } catch (_) { setTimeout(back, 2000); } };
      setTimeout(back, 3000);
      return;
    }
    if (!one && !all) return;
    try {
      const j = await api(one ? `/api/tasks/${one.dataset.taskStop}/stop` : "/api/tasks/stop", { method: "POST" });
      const box = document.getElementById("tasks-box");
      if (box) renderTasks(box, j.tasks, j.recent);
      toast("Arrêt demandé : la tâche termine l'élément en cours.");
    } catch (err) { toast(`${ICON.warn} ${esc(err.message)}`); }
  });

  /* Image de profil : réduite dans le navigateur (96 × 96, recadrée au centre) avant d'être envoyée, pour rester légère. */
  async function uploadAvatar(file, pid) {
    if (!file || !file.type.startsWith("image/")) return;
    const url = URL.createObjectURL(file);
    try {
      const im = await new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = url; });
      const S = 96, c = document.createElement("canvas"); c.width = S; c.height = S;
      const side = Math.min(im.naturalWidth, im.naturalHeight), sx = (im.naturalWidth - side) / 2, sy = (im.naturalHeight - side) / 2;
      c.getContext("2d").drawImage(im, sx, sy, side, side, 0, 0, S, S);
      let data = c.toDataURL("image/jpeg", 0.82);
      if (data.length > 60000) data = c.toDataURL("image/jpeg", 0.6);
      await putJson(`/api/profiles/${pid}`, { avatar: data });
      await loadSettings(); updateProfileButton(); route(); toast("Vignette enregistrée");
    } catch (err) { toast(`${ICON.warn} Image non prise en compte : ${esc(err.message || err)}`); }
    finally { URL.revokeObjectURL(url); }
  }
  main.addEventListener("change", e => {
    const fi = e.target.closest("[data-avatar-file]");
    if (fi) { uploadAvatar(fi.files && fi.files[0], +fi.dataset.avatarFile); return; }
    const rs = e.target.closest("select[data-role]");
    if (rs) {
      putJson(`/api/profiles/${rs.dataset.role}`, { role: rs.value }).then(async () => { toast("Rôle enregistré"); await loadSettings(); updateProfileButton(); route(); })
        .catch(err => { toast(`${ICON.warn} ${esc(err.message)}`); route(); });
      return;
    }
    const el = e.target.closest("[data-key]");
    if (!el) return;
    let val = el.type === "checkbox" ? el.checked : el.value;
    if (el.type === "number" || el.type === "range" || (el.tagName === "SELECT" && /^-?\d+(\.\d+)?$/.test(val))) val = Number(val);
    if (el.dataset.scope === "g") saveSettings(null, { [el.dataset.key]: val });
    else saveSettings({ [el.dataset.key]: val }, null);
    if (el.dataset.key === "settings_layout" || el.dataset.key === "skin") route();
    if (el.dataset.key === "hd_min_px" || el.dataset.key === "quality_auto") { renderQualitySwitch(); setTimeout(pollQuality, 1200); }
  });

  function qualityBoxHtml(q) {
    if (!q) return `<span class="muted">Indisponible</span>`;
    const st = q.stats, j = q.job, total = st.hd + st.sd + st.todo + st.na;
    let html = `<div class="qstats"><span class="qtag hd static">HD</span> ${st.hd} · <b>SD</b> ${st.sd} · à mesurer ${st.todo}${st.na ? ` · illisibles ou PDF ${st.na}` : ""} <span class="muted">(sur ${total})</span></div>`;
    if (j.running) {
      const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
      html += `<div class="qrun"><div class="spinner" style="margin:0;width:16px;height:16px"></div> Mesure en cours${j.reason === "auto" ? " (automatique)" : ""} : ${j.done} / ${j.total} — ${j.hd} HD, ${j.sd} SD${j.errors ? `, ${j.errors} illisibles` : ""}
        <div class="pbar"><i style="width:${pct}%"></i></div></div>
        <p><button class="btn" type="button" data-action="quality-stop">Arrêter</button></p>`;
    } else {
      if (j.finished_at && j.total) html += `<small class="muted">Dernière mesure : ${j.done} albums, ${fmtDate(j.finished_at)}.</small>`;
      html += `<p><button class="btn" type="button" data-action="quality-measure" ${st.todo ? "" : "disabled"}>Mesurer maintenant${st.todo ? ` (${st.todo})` : ""}</button>
        <button class="btn" type="button" data-action="quality-remeasure">Tout remesurer</button></p>`;
    }
    return html;
  }
  let qualityTimer = null;
  async function pollQuality() {
    clearTimeout(qualityTimer);
    const box = $("#quality-box");
    if (!box) return;
    let q;
    try { q = await api("/api/quality"); } catch (_) { return; }
    box.innerHTML = qualityBoxHtml(q);
    if (q.job.running) qualityTimer = setTimeout(pollQuality, 1500);
  }

  async function settingsAction(action, btn) {
    btn.disabled = true;
    try {
      if (action === "back") { escapeBack(); return; }
      if (action === "scan") { await fetch("/api/scan", { method: "POST" }); pollScan(true); }
      else if (action === "quality-measure" || action === "quality-remeasure") {
        if (action === "quality-remeasure" && !confirm("Remesurer tous les albums ? Ça relit deux pages de chaque album (quelques minutes, en arrière-plan).")) return;
        const r = await fetch("/api/quality/measure", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(action === "quality-remeasure" ? { remeasure: true } : {}) });
        if (r.status === 409) toast("Une mesure est déjà en cours.");
        pollQuality(); setTimeout(pollQualityToast, 600);
      } else if (action === "quality-stop") { await fetch("/api/quality/stop", { method: "POST" }); setTimeout(pollQuality, 800); }
      else if (action === "clear-cache") {
        const r = await api("/api/cache/clear", { method: "POST" });
        toast(`Cache des pages vidé (${fmtSize(r.cache.total)} restants : couvertures)`);
        const el = $("#cache-size"); if (el) el.textContent = `pages ${fmtSize(r.cache.pages)} · couvertures ${fmtSize(r.cache.covers)} · archives décompressées ${fmtSize(r.cache.extract)}`;
      } else if (action === "rebuild-covers") {
        if (!confirm("Régénérer toutes les couvertures ? Cela peut prendre un moment sur une grande bibliothèque (elles réapparaissent au fur et à mesure).")) return;
        const r = await fetch("/api/covers/rebuild", { method: "POST" });
        if (r.status === 409) toast("Un scan est déjà en cours, réessayez après.");
        else pollScan(true);
      } else if (action === "logout") {
        try { await api("/api/profiles/logout", { method: "POST" }); } catch (_) { /* ignore */ }
        try { localStorage.removeItem("bulle:profile"); } catch (_) { /* ignore */ }
        location.href = "/";
      } else if (action === "account-name") {
        const name = prompt("Votre nom :", btn.dataset.name); if (!name) return;
        await putJson(`/api/profiles/${btn.dataset.id}`, { name }); await loadSettings(); updateProfileButton(); route();
      } else if (action === "account-pin") {
        const hasPin = (settings.meta.profiles || []).some(pr => pr.id === +btn.dataset.id && pr.has_pin);
        let old_pin = "";
        if (hasPin) { old_pin = prompt("Ancien mot de passe :"); if (old_pin === null) return; }
        const pin = prompt(`Nouveau mot de passe (${settings.global.account_login ? 8 : 4} caractères au moins) :`); if (!pin) return;
        await putJson(`/api/profiles/${btn.dataset.id}`, hasPin ? { pin, old_pin } : { pin }); toast("Mot de passe enregistré"); await loadSettings(); route();
      } else if (action === "account-pin-clear") {
        if (!confirm("Supprimer le mot de passe de ce profil ?")) return;
        const old_pin = prompt("Mot de passe actuel :"); if (old_pin === null) return;
        await putJson(`/api/profiles/${btn.dataset.id}`, { pin: "", old_pin }); await loadSettings(); route();
      } else if (action === "avatar-text") {
        const a = prompt("Un emoji ou quelques lettres (8 maxi) :"); if (a === null) return;
        await putJson(`/api/profiles/${btn.dataset.id}`, { avatar: a.trim().slice(0, 8) }); await loadSettings(); updateProfileButton(); route();
      } else if (action === "avatar-clear") {
        await putJson(`/api/profiles/${btn.dataset.id}`, { avatar: "" }); await loadSettings(); updateProfileButton(); route();
      } else if (action === "profile-add") {
        const name = prompt("Prénom du nouveau profil :"); if (!name) return;
        const acc = settings.global.account_login;
        const pin = prompt(acc ? "Mot de passe (8 caractères au moins) — c'est avec lui que cette personne se connectera :" : "Mot de passe (laisser vide pour aucun, 4 caractères au moins) :") || "";
        await api("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, pin }) });
        await loadSettings(); updateProfileButton(); route();
      } else if (action === "profile-edit") {
        const name = prompt("Nom du profil :", btn.dataset.name); if (name === null) return;
        const acc = settings.global.account_login;
        const pin = prompt(acc ? "Nouveau mot de passe (8 caractères au moins ; vide = ne pas changer) :" : "Nouveau mot de passe (vide = ne pas changer, 4 caractères au moins) :"); if (pin === null) return;
        const body = pin ? { name, pin } : { name };
        if (pin && +btn.dataset.id === settings.meta.profile_id && (settings.meta.profiles || []).some(pr => pr.id === +btn.dataset.id && pr.has_pin)) {
          body.old_pin = prompt("Votre mot de passe actuel :"); if (body.old_pin === null) return;
        }
        await putJson(`/api/profiles/${btn.dataset.id}`, body);
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
      } else if (action === "adult-toggle") {
        const on = btn.dataset.adult !== "1";
        if (on && !settings.global.adult_pin_set && !confirm("Aucun code n'est défini pour la rubrique Adulte : la série y sera rangée mais restera visible. Continuer ? (Le code se définit dans Réglages › Adulte.)")) return;
        const r = await putJson("/api/adult/folder", { folder_id: +btn.dataset.id, adult: on });
        settings.global.adult_count = r.count; updateAdultTab();
        toast(on ? "Série rangée dans la rubrique Adulte" : "Série retirée de la rubrique Adulte");
        if (on) pow(powFor("adult"), lastPointer.x, lastPointer.y);
        route();
      } else if (action === "rebuild-folder") {
        if (!confirm(`Relire « ${btn.dataset.name} » sur le disque (fichiers ajoutés ou jetés) et refaire ses couvertures ?`)) return;
        const r = await fetch(`/api/covers/rebuild/folder/${btn.dataset.id}`, { method: "POST" });
        if (r.status === 409) { toast("Un scan est déjà en cours, réessayez après."); return; }
        if (!r.ok) throw new Error((await r.json()).error || r.statusText);
        const j = await r.json();
        toast(`Rescan de « ${esc(btn.dataset.name)} » en cours…`);
        pollScan(true);
      } else if (action === "unignore") {
        await api("/api/ignored", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: btn.dataset.path }) });
        toast(`« ${esc(btn.dataset.path.split("/").pop())} » remis : il réapparaît dans un instant…`); pollScan(true); route();
      } else if (action === "retry-errors") {
        const r = await fetch("/api/covers/retry-errors", { method: "POST" });
        if (r.status === 409) { toast("Un scan est déjà en cours, réessayez après."); return; }
        const j = await r.json(); toast(`${plural(j.count, "album réessayé", "albums réessayés")} en tâche de fond…`); pollScan(true);
      } else if (action === "adult-unlock") {
        if (await adultPrompt()) route();
      } else if (action === "adult-lock") {
        await api("/api/adult/lock", { method: "POST" }); settings.global.adult_unlocked = false; updateAdultTab(); toast("Rubrique Adulte verrouillée"); route();
      } else if (action === "adult-pin-set") {
        const pin = prompt(settings.global.adult_pin_set ? "Nouveau code de la rubrique Adulte :" : "Code de la rubrique Adulte (chiffres ou mot de passe) :"); if (!pin) return;
        await putJson("/api/settings", { global: { adult_pin: pin } }); toast("Code de la rubrique Adulte enregistré"); route();
      } else if (action === "adult-pin-clear") {
        if (!confirm("Supprimer le code ? Les séries 18+ redeviendront visibles par tout le monde.")) return;
        await putJson("/api/settings", { global: { adult_pin: "" } }); toast("Code supprimé"); route();
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
      <div class="sheet-left">${coverHtml(it, "", 220)}<div class="sheet-listsel" id="sheet-listsel" data-id="${it.id}"></div></div>
      <div>
        <h3>${esc(it.name)}</h3>
        <div class="path">${esc(folder || "Racine")}</div>
        ${it.error ? `<p class="error">${ICON.warn} ${esc(it.error)}</p>` : ""}
        <dl>
          <dt>Format</dt><dd>${esc(formatLabel(it))}</dd>
          <dt>Taille</dt><dd>${fmtSize(it.size)}</dd>
          <dt>Pages</dt><dd>${it.pages ?? "?"}</dd>
          ${it.res ? `<dt>Qualité</dt><dd>${it.q === "hd" ? "HD" : "SD"} — ${resLabel(it)}</dd>` : ""}
          <dt>Progression</dt><dd>${p ? (p.completed ? "Lu ✓" : `Page ${p.page + 1} sur ${it.pages ?? "?"} — ${pct} %`) : "Non lu"}
            ${p && !p.completed && it.pages ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}</dd>
          <dt>Fichier</dt><dd class="path">${esc(it.path.split("/").pop())}</dd>
          ${it.meta && it.meta.oneshot ? `<dt>${siteOf(it.meta.url || it.meta.series_url)}</dt><dd>${it.meta.url ? "" : `<span class="muted">album non repéré dans la série</span> `}<b>${esc(it.meta.series_title || it.meta.title || "")}</b>${it.meta.genre ? ` · ${esc(it.meta.genre)}` : ""}${it.meta.year ? ` (${it.meta.year})` : ""} <a class="ext" href="${esc(it.meta.url || it.meta.series_url)}" target="_blank" rel="noopener">↗</a></dd>` : it.meta ? `<dt>${siteOf(it.meta.url)}</dt><dd>${it.meta.number != null ? `<b>Tome ${it.meta.number}</b> · ` : ""}${esc(it.meta.title || "")}${it.meta.year ? ` (${it.meta.year})` : ""} <a class="ext" href="${esc(it.meta.url)}" target="_blank" rel="noopener">↗</a></dd>` : (it.series ? `<dt>Bédéthèque</dt><dd class="muted">tome non reconnu dans « ${esc(it.series.title)} »</dd>` : "")}
          ${it.meta && it.meta.writers.length ? `<dt>Scénario</dt><dd>${esc(it.meta.writers.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.pencillers.length ? `<dt>Dessin</dt><dd>${esc(it.meta.pencillers.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.colorists.length ? `<dt>Couleurs</dt><dd>${esc(it.meta.colorists.join(", "))}</dd>` : ""}
          ${it.meta && it.meta.publisher ? `<dt>Éditeur</dt><dd>${esc(it.meta.publisher)}${it.meta.collection ? ` · ${esc(it.meta.collection)}` : ""}${it.meta.date ? ` · ${esc(it.meta.date)}` : ""}</dd>` : ""}
          ${it.meta && it.meta.isbn ? `<dt>ISBN</dt><dd>${esc(it.meta.isbn)}${it.meta.pages ? ` · ${it.meta.pages} planches` : ""}</dd>` : ""}
        </dl>
        <div class="summary-slot" id="sheet-summary" data-id="${it.id}"></div>
        <div class="sheet-actions">
          <div class="sa-main">
            ${it.error ? "" : `<a class="btn primary big" href="/read/${it.id}${p && !p.completed ? "" : "?page=0"}">${ICON.play} ${p && !p.completed ? `Reprendre p. ${p.page + 1}` : (p ? "Relire" : "Lire")}</a>`}
            ${p && !p.completed && !it.error ? `<a class="btn" href="/read/${it.id}?page=0">Recommencer</a>` : ""}
            ${it.error ? "" : `<span class="offline-slot" id="sheet-offline" data-id="${it.id}" data-pages="${it.pages || 0}"></span>`}
          </div>
          <div class="sa-row">
            ${it.error ? "" : (p && p.completed
              ? `<button class="btn" type="button" data-unread="${it.id}">Marquer non lu</button>`
              : `<button class="btn" type="button" data-read="${it.id}">${ICON.check} Marquer comme lu</button>`)}
            ${p && !p.completed ? `<button class="btn" type="button" data-unread="${it.id}">Effacer la progression</button>` : ""}
            <span class="lists-row" id="sheet-lists" data-id="${it.id}"></span>
          </div>
          <div class="sa-row sa-minor">
            ${parent && parent.id ? `<a class="btn mini" href="#/f/${parent.id}" data-close>📁 Ouvrir le dossier</a>` : ""}
            <a class="btn mini" href="/api/download/${it.id}">${ICON.down} Télécharger</a>
            ${isAdmin() ? `<button class="btn mini" type="button" data-recover="${it.id}" title="Relire ce fichier sur le disque : format, taille, pages, couverture (rattrape un raté du scan)">↻ Rescanner</button>` : ""}
          </div>
        </div>
      </div></div></div>`;
    renderSheetLists($("#sheet-lists"), it.id, it.lists || []);
    renderSummary($("#sheet-summary"), it);
    renderOffline($("#sheet-offline"));
  }

  // ---------------------------------------------------------------- téléphone : barre du bas et feuille « Plus »
  const moreEl = $("#more");
  const SVG = {
    lists: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1.2" fill="currentColor"/><circle cx="3.5" cy="12" r="1.2" fill="currentColor"/><circle cx="3.5" cy="18" r="1.2" fill="currentColor"/></svg>`,
    history: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
    activity: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20h18"/><path d="M6 17V11M11 17V6M16 17v-4M21 17V9"/></svg>`,
    collection: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h4v16H4zM10 4h4v16h-4zM16.5 5.2l3.9-1 3.6 14.6-3.9 1z"/></svg>`,
    random: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.3" fill="currentColor"/><circle cx="16" cy="8" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="8" cy="16" r="1.3" fill="currentColor"/><circle cx="16" cy="16" r="1.3" fill="currentColor"/></svg>`,
    adult: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>`,
    settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>`,
    scan: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>`,
    lab: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/></svg>`,
    offline: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>`,
  };
  async function openMore() {
    if (!moreEl) return;
    const p = settings.profile, g = settings.global;
    const list = settings.meta.profiles || [];
    const me = list.find(x => x.id === settings.meta.profile_id) || { name: "Moi" };
    let lists = [];
    try { lists = await getLists(); } catch (_) { /* ignore */ }
    const custom = lists.filter(l => l.kind === "custom");
    const showAdult = !g.adult_hide_tab && (g.adult_pin_set || g.adult_count > 0);   // même règle que l'entrée du menu
    const q = p.quality || "all";
    const skinSeasons = document.documentElement.dataset.skin === "seasons";
    const tile = (href, icon, label, extra = "") => `<a href="${href}" ${extra}>${icon}<span>${label}</span></a>`;
    moreEl.innerHTML = `<div class="panel" role="dialog" aria-label="Plus">
      <div class="grip"></div>
      <div class="mhead">${avatarHtml(me, "small")}<div><b>${esc(me.name)}</b><small>${me.role === "admin" ? "Administrateur" : "Lecteur"} · Bulle ${esc(settings.meta.version || "")}</small></div>
        ${!g.account_login && (list.length > 1 || g.require_profile) ? `<button class="btn" type="button" data-more="profiles">Changer</button>` : `<a class="btn" href="#/settings/account">Mon compte</a>`}</div>
      <div class="mgrid">
        ${tile("#/lists", SVG.lists, "Listes", custom.length ? `data-cnt="${custom.length}"` : "")}
        ${tile("#/history", SVG.history, "Historique")}
        ${tile("#/activity", SVG.activity, "Activité")}
        ${tile("#/collection", SVG.collection, "Collection")}
        ${tile("#/random", SVG.random, "Au hasard")}
        ${offlineApp() ? tile("/__hors_connexion", SVG.offline, "Hors connexion") : ""}
        ${showAdult ? tile("#/adult", SVG.adult, "Adulte") : ""}
        ${tile("#/settings", SVG.settings, "Réglages")}
      </div>
      ${custom.length ? `<div class="mrow" style="padding-top:4px;border-top:0"><span class="muted" style="font-weight:500;font-size:13px">Mes listes</span></div>
        <div class="mgrid">${custom.slice(0, 8).map(l => tile(`#/list/${l.id}`, SVG.lists, esc(l.name), `title="${esc(l.name)}"`)).join("")}</div>` : ""}
      <div class="mrow"><span>Qualité des albums</span><span class="right">${["all", "hd", "sd"].map(k => `<button type="button" data-more-quality="${k}" class="${q === k ? "on" : ""}">${k === "all" ? "Tout" : k.toUpperCase()}</button>`).join("")}</span></div>
      ${skinSeasons ? `<div class="mrow"><span>${feteMode() ? "Fête" : "Saison"}</span><span class="right"><button type="button" data-more="season">${feteMode() ? (FETES[document.documentElement.dataset.season] || FETES.christmas).emoji : SEASON_EMOJI[["spring", "summer", "autumn", "winter"].includes(p.season) ? p.season : currentSeason()]} Changer</button></span></div>` : ""}
      ${isAdmin() ? `<button class="mrow" type="button" data-more="scan">${SVG.scan}<span>Rechercher les nouveaux albums</span></button>` : ""}
      ${shroom && !shroom.hidden ? `<button class="mrow" type="button" data-more="lab">${SVG.lab}<span>Le laboratoire (BDConverter)</span></button>` : ""}
    </div>`;
    moreEl.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeMore() { if (moreEl && !moreEl.hidden) { moreEl.hidden = true; moreEl.innerHTML = ""; document.body.style.overflow = ""; } }
  document.addEventListener("click", e => {
    const tb = e.target.closest("#tabbar [data-tb]");
    if (tb) {
      closeModal();
      if (tb.dataset.tb === "more") { e.preventDefault(); if (moreEl && !moreEl.hidden) closeMore(); else openMore(); return; }
      if (tb.dataset.tb === "search") { e.preventDefault(); closeMore(); window.scrollTo({ top: 0 }); searchInput.focus(); searchInput.select(); return; }
      if (tb.dataset.tb === "offline" && offlineApp()) { e.preventDefault(); closeMore(); window.BulleApp.openOffline(); return; }
      closeMore();
      if (tb.getAttribute("href") === location.hash) window.scrollTo({ top: 0, behavior: "smooth" });   // onglet déjà ouvert : retour en haut
      return;
    }
    if (!moreEl || moreEl.hidden) return;
    if (e.target === moreEl) { closeMore(); return; }
    const a = e.target.closest("#more a[href]");
    if (a) {
      if (a.getAttribute("href") === "/__hors_connexion" && offlineApp()) { e.preventDefault(); window.BulleApp.openOffline(); }
      closeMore(); return;
    }
    const qb = e.target.closest("[data-more-quality]");
    if (qb) { const b = document.querySelector(`#side-quality [data-quality="${qb.dataset.moreQuality}"]`); if (b) b.click(); closeMore(); return; }
    const m = e.target.closest("[data-more]");
    if (!m) return;
    closeMore();
    if (m.dataset.more === "profiles") openProfiles();
    else if (m.dataset.more === "scan") scanBtn.click();
    else if (m.dataset.more === "season") { const b = $("#season-btn"); if (b) b.click(); }
    else if (m.dataset.more === "lab") shroom.click();
  });
  window.addEventListener("hashchange", closeMore);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && moreEl && !moreEl.hidden) closeMore(); });
  function updateTabbarOffline() { const t = $("#tb-offline"), f = $("#tb-fav"); if (!t) return; const app = !!offlineApp(); t.hidden = !app; if (f) f.hidden = app; }

  // ---------------------------------------------------------------- appli Android : lecture hors connexion
  // L'appli « Bulle pour Android » expose window.BulleApp : on peut y garder un album sur le téléphone
  // (pages à la taille de l'écran) pour le lire sans réseau. Dans un navigateur, rien de tout cela n'apparaît.
  const offlineApp = () => (window.BulleApp && typeof window.BulleApp.offlineState === "function") ? window.BulleApp : null;
  function offlineCount() {
    const app = offlineApp(), tab = $("#tab-offline");
    if (!app || !tab) return;
    tab.hidden = false;
    try { const n = JSON.parse(app.offlineList()).filter(a => a.done).length; $("#offline-count").textContent = n ? String(n) : ""; } catch (_) { /* ignore */ }
  }
  function renderOffline(slot) {
    const app = offlineApp();
    if (!slot || !app) return;
    const id = +slot.dataset.id;
    let st = {};
    try { st = JSON.parse(app.offlineState(id)) || {}; } catch (_) { /* ignore */ }
    if (st.busy) {
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      slot.innerHTML = `<button class="btn" type="button" data-offline-cancel="${id}" title="Arrêter le téléchargement">📥 ${pct} % — arrêter</button>`;
    } else if (st.ready) {
      slot.innerHTML = `<span class="btn ok" title="Lisible sans connexion sur ce téléphone">✓ Hors connexion</span><button class="btn mini" type="button" data-offline-remove="${id}" title="Libérer la place sur le téléphone">Retirer</button>`;
    } else {
      slot.innerHTML = `<button class="btn" type="button" data-offline-get="${id}" title="Garder cet album sur le téléphone pour le lire sans réseau">📥 Garder hors connexion${st.done ? ` (reprendre, ${st.done}/${st.total})` : ""}</button>`;
    }
  }
  window.onOfflineProgress = (id, done, total, state) => {
    const slot = $("#sheet-offline");
    if (slot && +slot.dataset.id === +id) renderOffline(slot);
    if (state === "done") { toast(`📥 Album gardé hors connexion (${plural(total, "page", "pages")})`); offlineCount(); }
    else if (state === "error") toast(`${ICON.warn} Téléchargement interrompu (${done}/${total}) : il reprendra où il s'est arrêté`);
  };
  modal.addEventListener("click", e => {
    const app = offlineApp();
    if (!app) return;
    const g = e.target.closest("[data-offline-get]"), r = e.target.closest("[data-offline-remove]"), c = e.target.closest("[data-offline-cancel]");
    if (!g && !r && !c) return;
    e.preventDefault();
    if (g) app.offlineDownload(+g.dataset.offlineGet);
    if (c) app.offlineCancel(+c.dataset.offlineCancel);
    if (r) { app.offlineRemove(+r.dataset.offlineRemove); toast("Album retiré du téléphone"); offlineCount(); }
    renderOffline($("#sheet-offline"));
  });
  offlineCount(); updateTabbarOffline();
  /* Nom du site d'où vient une fiche : Bédéthèque, ou BDfugue (source de secours du laboratoire). */
  const siteOf = url => /bdfugue\.com/.test(url || "") ? "BDfugue" : "Bédéthèque";
  function summaryHtml(text, url) {
    if (!text) return `<p class="summary muted">Pas de résumé sur ${siteOf(url)} pour cet album.</p>`;
    const cut = /[.…!?»]$/.test(text) ? text : text + "…";
    return `<p class="summary">${esc(cut)} ${url ? `<a class="ext" href="${esc(url)}" target="_blank" rel="noopener">${siteOf(url) === "BDfugue" ? "voir la fiche sur BDfugue" : "lire la suite sur Bédéthèque"} ↗</a>` : ""}</p>`;
  }
  async function renderSummary(slot, it) {
    if (!slot || !it.meta || !it.meta.url) return;
    if (it.meta.summary_at) { slot.innerHTML = summaryHtml(it.meta.summary, it.meta.url); return; }
    if (!isAdmin()) {   // un lecteur ne déclenche jamais de requête vers Bédéthèque
      slot.innerHTML = `<p class="summary muted">Résumé pas encore récupéré. <a class="ext" href="${esc(it.meta.url)}" target="_blank" rel="noopener">Voir la fiche sur ${siteOf(it.meta.url)} ↗</a></p>`;
      return;
    }
    if (!settings.global.bdt_enabled || settings.global.bdt_auto_summary === false) {
      slot.innerHTML = `<p class="summary muted"><button class="btn mini" type="button" data-summary="${it.id}">Lire le résumé sur ${siteOf(it.meta.url)}</button></p>`;
      return;
    }
    fetchSummary(slot, it);
  }
  async function fetchSummary(slot, it) {
    slot.innerHTML = `<p class="summary muted"><span class="spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;margin:0 6px -2px 0"></span>Résumé en cours de lecture sur ${siteOf(it.meta.url)}…</p>`;
    try {
      const r = await api(`/api/bdt/album/${it.id}/summary`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (+slot.dataset.id === +it.id) slot.innerHTML = summaryHtml(r.summary, it.meta.url);
    } catch (e) {
      if (+slot.dataset.id === +it.id) slot.innerHTML = `<p class="summary muted">Résumé indisponible : ${esc(e.message)}</p>`;
    }
  }
  modal.addEventListener("click", async e => {
    const rc = e.target.closest("[data-recover]");
    if (rc) {
      rc.disabled = true; rc.textContent = "↻ Lecture du fichier…";
      try {
        const it = await api(`/api/covers/retry/${rc.dataset.recover}`, { method: "POST" });
        it.bust = Date.now();
        const i = view.children.findIndex(c => c.id === it.id);
        if (i >= 0) view.children[i] = Object.assign(view.children[i], it);
        const cardEl = main.querySelector(`.card[data-id="${it.id}"]`); if (cardEl) cardEl.outerHTML = card(it, it.folder ? { sub: it.folder } : {});
        const cov = modal.querySelector(".sheet .cover img"); if (cov) cov.src = coverUrl(it, 300);
        toast(it.error ? `${ICON.warn} ${esc(it.error)}` : `Fichier relu : ${plural(it.pages || 0, "page", "pages")}, couverture refaite`);
        if (!it.error) { closeModal(); openInfo(it.id); return; }
      } catch (err) { toast(`${ICON.warn} ${esc(err.message)}`); }
      rc.disabled = false; rc.textContent = "↻ Rescanner ce fichier";
      return;
    }
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
    const fav = `<button class="btn ${isFav ? "fav-on" : ""}" type="button" data-fav="${nodeId}">${isFav ? "★ Favori" : "☆ Favori"}</button>`;
    const select = `<select data-listsel="${nodeId}" aria-label="Ajouter à une liste"><option value="">Ajouter à une liste…</option>
        ${others.map(l => `<option value="${l.id}">${membership.includes(l.id) ? "✓ " : ""}${esc(l.name)}${membership.includes(l.id) ? " (retirer)" : ""}</option>`).join("")}
        <option value="new">+ Nouvelle liste…</option></select>`;
    // fiche d'un album : la liste se choisit sous la pochette, le favori reste avec les boutons
    const under = $("#sheet-listsel");
    if (under && +under.dataset.id === +nodeId && container.id === "sheet-lists") { container.innerHTML = fav; under.innerHTML = select; }
    else container.innerHTML = fav + select;
  }
  async function toggleFav(nodeId, btn) {
    try {
      const r = await api("/api/favorites/toggle", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId }) });
      if (btn) { btn.classList.toggle("fav-on", r.fav); btn.textContent = r.fav ? "★ Favori" : "☆ Favori"; }
      toast(r.fav ? "Ajouté aux favoris ★" : "Retiré des favoris");
      if (r.fav) pow(powFor("fav"), lastPointer.x, lastPointer.y);
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
      else { r = await api(`/api/lists/${listId}/items`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId }) }); toast(`Ajouté à « ${esc((lists.find(l => l.id === +listId) || {}).name || "la liste")} »`); pow(powFor("list"), lastPointer.x, lastPointer.y); }
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
    for (const el of document.querySelectorAll("#maintabs [data-count], #tabbar [data-count]")) {
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
    const tab = (m = /^#\/list\/(\d+)/.exec(h)) ? "list-" + m[1] : h.startsWith("#/list/favorites") ? "favorites" : h.startsWith("#/list/readlater") ? "readlater" : h.startsWith("#/list") ? "lists" : h.startsWith("#/history") ? "history" : h.startsWith("#/activity") ? "activity" : h.startsWith("#/collection") ? "collection" : h.startsWith("#/adult") ? "adult" : h.startsWith("#/settings") ? "settings" : h.startsWith("#/s/") ? "" : "home";
    for (const a of document.querySelectorAll("#maintabs a")) a.classList.toggle("on", a.dataset.tab === tab);
    const tb = tab === "home" || tab === "readlater" || tab === "favorites" ? tab : "";
    for (const a of document.querySelectorAll("#tabbar [data-tb]")) a.classList.toggle("on", a.dataset.tb === tb);
    const more = $("#tb-more"); if (more) more.classList.toggle("on", !tb && !!tab);
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
      pow(powFor(list.kind === "favorites" ? "fav" : "list"), lastPointer.x, lastPointer.y);
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
    data.items = qf(data.items);
    const icon = l.kind === "favorites" ? "★" : l.kind === "readlater" ? "🔖" : "📚";
    const empty = l.kind === "favorites" ? "Aucun favori pour l'instant : le bouton ☆ se trouve dans la fiche d'un album (« i ») ou en haut d'une série."
      : l.kind === "readlater" ? "Rien à lire pour l'instant : « Ajouter à une liste » dans la fiche d'un album ou en haut d'une série."
        : "Liste vide : « Ajouter à une liste » dans la fiche d'un album ou en haut d'une série.";
    main.innerHTML = `<div class="listhead"><h1>${icon} ${esc(l.name)} <small class="muted h1sub">${plural(data.items.length, "élément", "éléments")}</small></h1>
      ${l.kind === "custom" ? `<button class="btn mini" type="button" data-action="list-rename" data-id="${l.id}" data-name="${esc(l.name)}">Renommer</button><button class="btn mini" type="button" data-action="list-delete" data-id="${l.id}" data-name="${esc(l.name)}">Supprimer</button>` : ""}</div>
      ${data.items.length ? `<div class="grid" id="grid">${data.items.map(it => card(it, { sub: it.folder }).replace("</a>", `<button class="remove" type="button" data-unlist="${l.id}" data-node="${it.id}" title="Retirer de la liste">×</button></a>`)).join("")}</div>` : `<div class="empty">${empty}</div>`}`;
  }
  async function viewAdult() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Adulte");
    document.title = "Rubrique Adulte — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const a = await api("/api/adult");
    settings.global.adult_unlocked = a.unlocked; settings.global.adult_pin_set = a.pin_set; settings.global.adult_count = a.count; updateAdultTab();
    if (!a.unlocked) {
      main.innerHTML = `<div class="listhead"><h1>🔞 Rubrique Adulte</h1></div>
        <form class="adult-gate" id="adult-gate"><p>${plural(a.count, "série cachée", "séries cachées")}. Entrez le code pour les voir pendant 12 heures sur cet appareil.</p>
        <div class="pin-inline"><input type="password" inputmode="numeric" autocomplete="off" name="pin" placeholder="Code" autofocus><button class="btn primary" type="submit">Déverrouiller</button><p class="error" hidden></p></div></form>`;
      $("#adult-gate").addEventListener("submit", async e => {
        e.preventDefault();
        const f = e.target, err = f.querySelector(".error");
        try {
          await api("/api/adult/unlock", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin: f.elements.pin.value }), noAdultPrompt: true });
          pow(powFor("adult")); route();
        } catch (e2) { err.textContent = e2.message; err.hidden = false; f.elements.pin.select(); }
      });
      return;
    }
    const folders = a.folders || [];
    main.innerHTML = `<div class="listhead"><h1>🔞 Rubrique Adulte <small class="muted h1sub">${plural(folders.length, "série", "séries")}</small></h1>
      ${a.pin_set ? `<button class="btn" type="button" data-action="adult-lock">Verrouiller</button>` : `<a class="btn" href="#/settings/adult">Définir un code</a>`}</div>
      ${!a.pin_set ? `<p class="muted">Aucun code n'est défini : ces séries sont visibles par tout le monde. <a href="#/settings/adult">Définir un code</a> pour les cacher.</p>` : ""}
      ${folders.length ? `<div class="grid" id="grid">${folders.map(f => card(f)).join("")}</div>` : `<div class="empty"><strong>Rien ici pour l'instant.</strong><p>Ouvrez une série et cliquez le bouton « 18+ » en haut de sa page pour la mettre dans cette rubrique.</p></div>`}`;
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
  const fmtDay = ts => ts ? new Date(ts * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "";
  const fmtDur = sec => { const m = Math.round((sec || 0) / 60); return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`; };
  async function viewHistory() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Historique");
    document.title = "Historique — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const [done, reading] = await Promise.all([api("/api/history"), api("/api/history/reading")]);
    const items = qf(done), cur = qf(reading);
    const subOf = it => `${it.folder}${it.progress && it.progress.updated_at ? " · " + fmtDay(it.progress.updated_at) : ""}${it.progress && !it.progress.completed && it.pages ? ` · p. ${it.progress.page + 1}/${it.pages}` : ""}`;
    main.innerHTML = `<h1>Historique <small class="muted h1sub">${plural(cur.length, "album en cours", "albums en cours")} · ${plural(items.length, "terminé", "terminés")}</small> <span class="h1tools"><a class="btn" href="#/activity">Activité</a></span></h1>
      ${cur.length ? `<h2>En cours</h2><div class="grid">${cur.map(it => card(it, { sub: subOf(it) })).join("")}</div>` : ""}
      <h2>Terminés <small class="muted">les plus récents d'abord</small></h2>
      ${items.length ? `<div class="grid" id="grid">${items.map(it => card(it, { sub: subOf(it) })).join("")}</div>` : `<div class="empty">Aucun album terminé pour l'instant.</div>`}`;
  }
  async function viewActivity() {
    setCrumbs([{ id: 0, name: "Accueil" }], "Activité");
    document.title = "Activité — Bulle";
    main.innerHTML = `<div class="empty"><div class="spinner"></div></div>`;
    const a = await api("/api/activity");
    const tile = (n, label, sub = "") => `<div class="stile"><b>${n}</b><span>${label}</span>${sub ? `<small class="muted">${sub}</small>` : ""}</div>`;
    const maxM = Math.max(1, ...a.months.map(m => m.pages)), maxD = Math.max(1, ...a.days.map(d => d.pages));
    const monthLabel = m => { const [y, mo] = m.split("-"); return new Date(+y, +mo - 1, 1).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" }); };
    const bars = (rows, key, max, label, title) => `<div class="bars">${rows.map(r => `<div class="bar" title="${title(r)}"><i style="height:${Math.max(2, Math.round(r[key] / max * 100))}%"></i><span>${label(r)}</span></div>`).join("")}</div>`;
    main.innerHTML = `<h1>Activité <small class="muted h1sub">vos lectures, d'après les pages tournées dans Bulle</small> <span class="h1tools"><a class="btn" href="#/history">Historique</a></span></h1>
      <h2>30 derniers jours</h2>
      <div class="stiles">${tile(a.last30.finished, "albums terminés")}${tile(a.last30.pages, "pages lues")}${tile(fmtDur(a.last30.seconds), "de lecture")}${tile(a.last30.days, "jours avec lecture")}</div>
      <h2>Par jour <small class="muted">14 derniers jours, pages lues</small></h2>
      ${bars(a.days, "pages", maxD, d => d.day.slice(8), d => `${d.day} : ${plural(d.pages, "page", "pages")}, ${fmtDur(d.seconds)}${d.finished ? `, ${plural(d.finished, "album terminé", "albums terminés")}` : ""}`)}
      ${a.months.length ? `<h2>Par mois <small class="muted">pages lues · albums terminés</small></h2>
      ${bars(a.months, "pages", maxM, m => `${monthLabel(m.month)}${m.finished ? `<em>${m.finished}</em>` : ""}`, m => `${monthLabel(m.month)} : ${plural(m.pages, "page", "pages")}, ${fmtDur(m.seconds)}, ${plural(m.finished, "album terminé", "albums terminés")}, ${plural(m.days, "jour", "jours")} de lecture`)}` : ""}
      <div class="acols">
        <section><h2>Séries en cours</h2>${a.series.length ? `<ul class="alist">${a.series.map(sr => `<li><a href="#/f/${sr.id}">${esc(sr.name)}</a><span class="muted">${sr.done || 0}/${sr.album_count} lus · ${plural(sr.reading, "en cours", "en cours")} · ${fmtDay(sr.last_at)}</span></li>`).join("")}</ul>` : `<p class="muted">Aucune série commencée.</p>`}</section>
        <section><h2>Les plus lus <small class="muted">30 jours, en temps</small></h2>${a.top.length ? `<ul class="alist">${a.top.map(t => `<li><a href="/read/${t.id}">${esc(t.name)}</a><span class="muted">${fmtDur(t.seconds)} · ${plural(t.pages, "page", "pages")}</span></li>`).join("")}</ul>` : `<p class="muted">Rien encore : tournez des pages !</p>`}</section>
      </div>
      <h2>Depuis le début</h2>
      <div class="stiles">${tile(a.total.finished, "albums terminés")}${tile(a.total.pages, "pages lues")}${tile(fmtDur(a.total.seconds), "de lecture")}${tile(a.total.days, "jours avec lecture")}</div>
      ${a.profiles ? `<h2>Tous les comptes <small class="muted">30 derniers jours</small></h2>
      <table class="coltable atable"><thead><tr><th>Compte</th><th>Pages</th><th>Temps</th><th>Terminés</th><th>Dernière lecture</th></tr></thead>
      <tbody>${a.profiles.map(pr => `<tr><td>${avatarHtml(pr, "small")} ${esc(pr.name)}</td><td>${pr.pages}</td><td>${fmtDur(pr.seconds)}</td><td>${pr.finished}</td><td>${pr.last_at ? fmtDay(pr.last_at) : "—"}</td></tr>`).join("")}</tbody></table>` : ""}
      <p class="muted">Bulle note les pages tournées dans son lecteur (pas celles lues dans une autre appli) ; le temps compte les écarts entre deux pages, plafonnés à 5 minutes.</p>`;
  }
  async function viewRandom() {
    try {
      const a = await api("/api/random");
      toast(`Au hasard : ${esc(a.name)}`); pow(powFor("random"));
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
      pow(powFor("read"), lastPointer.x, lastPointer.y);
      closeModal(); route(); return;
    }
    if (t.dataset.unread) {
      await api(`/api/progress/${t.dataset.unread}`, { method: "DELETE" });
      closeModal(); route(); return;
    }
    closeModal();
  });
  /* Échap : ferme ce qui est ouvert, sinon revient en arrière (réglages, listes, recherche → page précédente ; dossier → dossier parent). */
  function escapeBack() {
    const h = location.hash || "#/";
    if (h === "#/" || h === "" || /^#\/p\d+$/.test(h)) return;
    if (h.startsWith("#/settings")) {   // Échap / Fermer : on quitte les réglages d'un coup, quel que soit le nombre de rubriques vues
      location.hash = outsideSettings || "#/";
      return;
    }
    let m;
    if ((m = /^#\/f\/(\d+)/.exec(h))) {
      const crumbs = [...crumbsEl.querySelectorAll("a")];
      const parent = crumbs[crumbs.length - 1];
      location.hash = parent ? (parent.getAttribute("href") || "#/") : "#/";
      return;
    }
    if (navCount > 0) { navCount -= 2; history.back(); } else location.hash = "#/";   // -2 : le retour déclenche lui-même un hashchange
  }
  let navCount = 0, outsideSettings = location.hash.startsWith("#/settings") ? "" : (location.hash || "#/");
  window.addEventListener("hashchange", () => {
    navCount += 1;
    if (!location.hash.startsWith("#/settings")) outsideSettings = location.hash || "#/";
  });
  // passer d'une rubrique des réglages à l'autre ne s'empile pas dans l'historique du navigateur
  main.addEventListener("click", e => {
    const t = e.target.closest(".stabs a.tab");
    if (!t) return;
    e.preventDefault();
    location.replace(t.getAttribute("href"));
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      if (!modal.hidden) { closeModal(); return; }
      if (!lab.hidden) { closeLab(); return; }
      if (popEl) return;   // la bulle de résumé se ferme dans son propre gestionnaire
      if (e.target.matches("input, select, textarea")) { e.target.blur(); if (e.target === searchInput && !searchInput.value) escapeBack(); return; }
      escapeBack(); return;
    }
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
      const stop = scanStopping ? `<span class="muted">arrêt…</span>` : `<button class="btn mini" type="button" data-stop-scan title="Arrêter (rien n'est perdu)">■ Arrêter</button>`;
      toast(`<div class="spinner"></div>${txt} ${stop}`, { sticky: true });
      scanTimer = setTimeout(() => pollScan(true), 1500);
    } else if (refreshWhenDone) {
      scanStopping = false;
      if (s.stopped) toast(s.stopped === "covers" ? `Couvertures arrêtées (${s.covers_done}/${s.covers_total}) : les autres se feront à l'ouverture des albums` : "Scan arrêté : la bibliothèque est restée comme avant");
      else if (s.aborted) toast(`${ICON.warn} Scan annulé par sécurité, rien n'a été effacé : ${esc(s.error)}.${isAdmin() ? ` <button class="btn mini" type="button" data-force-scan title="À faire seulement si vous avez vraiment supprimé ou déplacé ces albums">Scanner quand même</button>` : ""}`, { sticky: true });
      else if (s.error) toast(`${ICON.warn} Scan impossible : ${esc(s.error)}`);
      else toast(`Terminé : ${s.albums} albums${s.added ? `, ${s.added} nouveaux` : ""}${s.new_folders ? ` (${plural(s.new_folders, "nouvelle série", "nouvelles séries")})` : ""}${s.renamed ? `, ${s.renamed} renommés ou déplacés` : ""}${s.removed ? `, ${s.removed} disparus` : ""}`);
      if (!location.hash.startsWith("#/settings")) route();
      loadStats();
      setTimeout(() => pollQualityToast(), 1500);   // le scan enchaîne souvent sur la mesure HD / SD
    }
  }
  /* Bulle de notification pendant la mesure HD / SD (automatique après un scan, ou lancée à la main) */
  let qToastTimer = null, qToastShown = false;
  async function pollQualityToast() {
    clearTimeout(qToastTimer);
    if (scanBtn.classList.contains("spin")) return;   // le scan a sa propre bulle
    let q;
    try { q = await api("/api/quality"); } catch (_) { return; }
    const j = q.job;
    if (j.running) {
      qToastShown = true;
      const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
      const stop = isAdmin() ? ` <button class="btn mini" type="button" data-stop-quality title="Arrêter (rien n'est perdu)">■ Arrêter</button>` : "";
      toast(`<div class="spinner"></div>Mesure HD / SD : ${j.done} / ${j.total} (${pct} %) · ${j.hd} HD, ${j.sd} SD${j.errors ? `, ${j.errors} illisibles` : ""}${stop}`, { sticky: true });
      qToastTimer = setTimeout(pollQualityToast, 2000);
    } else if (qToastShown) {
      qToastShown = false;
      toast(`Mesure HD / SD terminée : ${j.done} albums — ${j.hd} HD, ${j.sd} SD${j.errors ? `, ${j.errors} illisibles` : ""}`);
      if (!location.hash.startsWith("#/settings")) route();
    }
  }
  toastEl.addEventListener("click", async e => {
    if (!e.target.closest("[data-stop-quality]")) return;
    try { await fetch("/api/quality/stop", { method: "POST" }); } catch (_) { /* ignore */ }
    setTimeout(pollQualityToast, 800);
  });
  let scanStopping = false;
  scanBtn.addEventListener("click", async () => {
    if (scanBtn.classList.contains("spin")) {   // scan déjà en cours : le bouton propose de l'arrêter
      if (confirm("Un scan est en cours. L'arrêter ? (rien n'est perdu)")) stopScan();
      return;
    }
    try { await fetch("/api/scan", { method: "POST" }); } catch (_) { /* ignore */ }
    pollScan(true);
  });
  async function stopScan() {
    scanStopping = true;
    try { await fetch("/api/scan/stop", { method: "POST" }); } catch (_) { /* ignore */ }
    pollScan(true);
  }
  toastEl.addEventListener("click", async e => {
    if (e.target.closest("[data-stop-scan]")) { stopScan(); return; }
    if (e.target.closest("[data-force-scan]")) {
      if (!confirm("Scanner quand même ? Les albums introuvables seront retirés de Bulle (couvertures, mesures et progression comprises). À faire seulement si vous les avez vraiment supprimés ou déplacés.")) return;
      try { await fetch("/api/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ force: true }) }); } catch (_) { /* ignore */ }
      pollScan(true);
    }
  });

  /* Bulle mis à jour pendant que la page était ouverte : la page garde l'ancien code tant qu'on ne la recharge pas. */
  const PAGE_VERSION = ($('meta[name="bulle-version"]') || {}).content || "";
  let updateShown = false;
  function checkUpdated(serverVersion) {
    if (!PAGE_VERSION || !serverVersion || serverVersion === PAGE_VERSION || updateShown) return;
    updateShown = true;
    toast(`Bulle a été mis à jour (v${esc(serverVersion)}) <button class="btn mini primary" type="button" onclick="location.reload()">Recharger la page</button>`, { sticky: true });
  }
  setInterval(() => { if (!document.hidden) loadStats(); }, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadStats(); });

  async function loadStats() {
    try {
      const s = await api("/api/stats");
      statsEl.textContent = `${s.albums} albums · ${fmtSize(s.size)}`;
      const ver = $("#ver"); if (ver && s.version) ver.textContent = "v" + s.version;
      checkUpdated(s.version);
      statsEl.title = `${s.folders} dossiers · ${s.read} lus · dernier scan : ${fmtDate(s.last_scan)}`;
      if (s.scan && s.scan.running) pollScan(true);
      else if (!qToastShown) pollQualityToast();
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
  // bulle de résumé sur une vignette (bouton « … » à côté du « i »)
  let popEl = null;
  function closePop() { if (popEl) { popEl.remove(); popEl = null; } }
  async function openSummaryPop(btn, id) {
    closePop();
    const card = btn.closest(".card");
    const item = (view.children || []).find(c => c.id === +id) || null;
    popEl = document.createElement("div");
    popEl.className = "sumpop";
    popEl.innerHTML = `<div class="sumbody"><b>${esc(item && item.meta && item.meta.title ? item.meta.title : (card ? card.querySelector(".title").textContent : ""))}</b><p class="muted">Résumé en cours de lecture…</p></div>`;
    document.body.appendChild(popEl);
    placePop(card || btn);
    const fill = (text, url) => {
      if (!popEl) return;
      popEl.querySelector("p").outerHTML = text
        ? `<p>${esc(/[.…]$/.test(text) ? text : text + "…")} ${url ? `<a class="ext" href="${esc(url)}" target="_blank" rel="noopener">lire la suite ↗</a>` : ""}</p>`
        : `<p class="muted">Pas de résumé sur Bédéthèque pour cet album.</p>`;
      placePop(card || btn);
    };
    try {
      let r = await api(`/api/bdt/album/${id}/summary`);
      if (!r.linked) { fill(null); return; }
      if (!r.summary_at && !isAdmin()) {
        if (popEl) { popEl.querySelector("p").outerHTML = `<p class="muted">Résumé pas encore récupéré.</p>`; placePop(card || btn); }
        return;
      }
      if (!r.summary_at) r = await api(`/api/bdt/album/${id}/summary`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      fill(r.summary, item && item.meta ? item.meta.url : "");
    } catch (e) { if (popEl) popEl.querySelector("p").textContent = `Résumé indisponible : ${e.message}`; }
  }
  function placePop(anchor) {
    if (!popEl) return;
    const r = anchor.getBoundingClientRect(), w = Math.min(340, window.innerWidth - 24);
    popEl.style.width = w + "px";
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(12, Math.min(window.innerWidth - w - 12, left));
    const h = popEl.offsetHeight;
    let top = r.top - h - 14, tail = "down";
    if (top < 70) { top = r.bottom + 14; tail = "up"; }
    popEl.style.left = left + "px"; popEl.style.top = top + "px";
    popEl.dataset.tail = tail;
    popEl.style.setProperty("--tail-x", (r.left + r.width / 2 - left) + "px");
  }
  document.addEventListener("click", e => {
    if (popEl && !e.target.closest(".sumpop") && !e.target.closest("[data-sum]")) closePop();
  }, true);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closePop(); });
  window.addEventListener("scroll", closePop, { passive: true });
  window.addEventListener("hashchange", closePop);

  async function retryCover(btn) {
    const cardEl = btn.closest(".card");
    btn.disabled = true; btn.classList.add("spin");
    try {
      const it = await api(`/api/covers/retry/${btn.dataset.retry}`, { method: "POST" });
      it.bust = Date.now();
      const i = view.children.findIndex(c => c.id === it.id);
      if (i >= 0) view.children[i] = Object.assign(view.children[i], it);
      if (cardEl) cardEl.outerHTML = card(it, it.folder ? { sub: it.folder } : {});
      toast(it.error ? `${ICON.warn} Toujours en échec : ${esc(it.error)}` : "Album relu, couverture refaite");
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); btn.disabled = false; btn.classList.remove("spin"); }
  }
  async function ignoreNode(btn) {
    const folder = btn.dataset.folder === "1", name = btn.dataset.name;
    if (!confirm(`Retirer ${folder ? "le dossier" : "l'album"} « ${name} » de Bulle ?\n\nRien n'est supprimé sur le disque : ${folder ? "le dossier n'apparaîtra plus" : "il n'apparaîtra plus"}, même après un scan. Progression et listes associées sont oubliées.\nAnnulable dans Réglages › Bibliothèque › Retirés de Bulle.`)) return;
    btn.disabled = true;
    try {
      const r = await api(`/api/ignore/${btn.dataset.ignore}`, { method: "POST" });
      closeModal();
      toast(`« ${esc(name)} » retiré de Bulle${r.albums > 1 ? ` (${r.albums} albums)` : ""}`);
      listsCache = null; renderSidebar(); loadStats();
      if (folder) location.hash = r.parent_id && r.parent_id !== 1 ? `#/f/${r.parent_id}` : "#/";
      else route();
    } catch (e) { toast(`${ICON.warn} ${esc(e.message)}`); btn.disabled = false; }
  }
  document.addEventListener("click", e => {
    const ig = e.target.closest("[data-ignore]");
    if (ig) { e.preventDefault(); ignoreNode(ig); }
  });
  document.addEventListener("click", e => {
    const qb = e.target.closest("#side-quality button[data-quality]");
    if (!qb) return;
    e.preventDefault();
    if (qb.dataset.quality === (settings.profile.quality || "all")) return;
    saveSettings({ quality: qb.dataset.quality });
    renderQualitySwitch();
    view.page = 1;
    const h = location.hash || "#/";
    const nh = h.replace(/\/p\d+$/, "");
    if (nh !== h) location.hash = nh === "#" ? "#/" : nh; else route();
  });
  main.addEventListener("click", e => {
    const retry = e.target.closest("[data-retry]");
    if (retry) { e.preventDefault(); retryCover(retry); return; }
    const info = e.target.closest("[data-info]");
    if (info) { e.preventDefault(); openInfo(info.dataset.info); return; }
    const sum = e.target.closest("[data-sum]");
    if (sum) { e.preventDefault(); if (popEl && popEl.dataset.id === sum.dataset.sum) { closePop(); return; } openSummaryPop(sum, sum.dataset.sum); popEl.dataset.id = sum.dataset.sum; return; }
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
  // ================================================================ taille des pochettes (− / + au-dessus de la grille)
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-thumb]");
    if (!b) return;
    const sizes = ["s", "m", "l", "xl"];
    const i = Math.max(0, Math.min(sizes.length - 1, sizes.indexOf(settings.profile.thumb_size || "m") + (b.dataset.thumb === "+" ? 1 : -1)));
    if (sizes[i] === settings.profile.thumb_size) return;
    const y = window.scrollY;
    saveSettings({ thumb_size: sizes[i] }, null);
    route().then(() => window.scrollTo(0, y));
  });

  // ================================================================ téléchargements : clic droit, panier, .zip
  /* Clic droit sur une série ou un album : « Ajouter aux téléchargements » (+1 au compteur du panier) ou télécharger tout
     de suite. Le panier est gardé dans ce navigateur ; « Tout télécharger » donne un seul .zip (une série = un dossier). */
  const BASKET_KEY = "bulle:basket";
  const basketGet = () => { try { return JSON.parse(localStorage.getItem(BASKET_KEY) || "[]"); } catch (_) { return []; } };
  const basketSet = list => { try { localStorage.setItem(BASKET_KEY, JSON.stringify(list)); } catch (_) { /* ignore */ } updateBasketBtn(); };
  const inBasket = (kind, id) => basketGet().some(x => x.kind === kind && x.id === id);
  function updateBasketBtn(bump) {
    const btn = $("#basket-btn"); if (!btn) return;
    const n = basketGet().length;
    btn.hidden = !n;
    btn.querySelector(".cnt").textContent = n;
    btn.title = `Téléchargements : ${plural(n, "élément", "éléments")} dans le panier`;
    if (bump) { btn.classList.remove("bump"); void btn.offsetWidth; btn.classList.add("bump"); }
  }
  function plusOne(x, y, text) {
    const el = document.createElement("div");
    el.className = "plusone"; el.textContent = text;
    el.style.left = x + "px"; el.style.top = y + "px";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1000);
  }
  function basketAdd(item, x, y) {
    const list = basketGet();
    if (list.some(i => i.kind === item.kind && i.id === item.id)) { toast("Déjà dans les téléchargements"); return; }
    list.push(item); basketSet(list);
    updateBasketBtn(true);
    if (x != null) plusOne(x, y, "+1");
  }
  const bundleUrl = list => `/api/download/bundle?f=${list.filter(i => i.kind === "folder").map(i => i.id).join(",")}&a=${list.filter(i => i.kind === "album").map(i => i.id).join(",")}`;
  function startDownload(url) {
    const a = document.createElement("a"); a.href = url; a.download = ""; document.body.appendChild(a); a.click(); a.remove();
  }
  let ctxEl = null;
  function closeCtx() { if (ctxEl) { ctxEl.remove(); ctxEl = null; } }
  main.addEventListener("contextmenu", e => {
    const c = e.target.closest(".card.folder[data-id], .card.album[data-id]");
    if (!c) return;
    e.preventDefault();
    closeCtx();
    const kind = c.classList.contains("folder") ? "folder" : "album", id = +c.dataset.id;
    const name = (c.querySelector(".title") || {}).textContent || "";
    const has = inBasket(kind, id);
    ctxEl = document.createElement("div");
    ctxEl.className = "ctxmenu";
    ctxEl.innerHTML = `<div class="ctxhead">${esc(name)}</div>
      <button type="button" data-ctx="${has ? "remove" : "add"}">${has ? "Retirer des téléchargements" : "Ajouter aux téléchargements"}</button>
      <button type="button" data-ctx="now">${kind === "folder" ? "Télécharger la série (.zip)" : "Télécharger l'album"}</button>
      ${kind === "folder" ? `<button type="button" data-ctx="open">Ouvrir</button>` : `<button type="button" data-ctx="read">Lire</button>`}`;
    document.body.appendChild(ctxEl);
    const w = ctxEl.offsetWidth, h = ctxEl.offsetHeight;
    ctxEl.style.left = Math.min(e.clientX, window.innerWidth - w - 8) + "px";
    ctxEl.style.top = Math.min(e.clientY, window.innerHeight - h - 8) + "px";
    ctxEl.addEventListener("click", ev => {
      const b = ev.target.closest("[data-ctx]"); if (!b) return;
      const act = b.dataset.ctx; closeCtx();
      if (act === "add") basketAdd({ kind, id, name }, e.clientX, e.clientY);
      else if (act === "remove") { basketSet(basketGet().filter(i => !(i.kind === kind && i.id === id))); toast("Retiré des téléchargements"); }
      else if (act === "now") { startDownload(kind === "folder" ? `/api/download/folder/${id}` : `/api/download/${id}`); toast(kind === "folder" ? "Préparation du .zip de la série : le téléchargement démarre…" : "Téléchargement de l'album…"); }
      else if (act === "open") location.hash = `#/f/${id}`;
      else if (act === "read") location.href = `/read/${id}`;
    });
  });
  document.addEventListener("click", e => { if (ctxEl && !e.target.closest(".ctxmenu")) closeCtx(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeCtx(); });
  window.addEventListener("scroll", closeCtx, { passive: true });
  async function openBasket() {
    const list = basketGet();
    modal.hidden = false;
    modal.innerHTML = `<div class="backdrop"><div class="sheet basket" role="dialog" aria-modal="true">
      <button class="iconbtn close" type="button" data-basket="close" title="Fermer">${ICON.close}</button>
      <h3>Téléchargements</h3>
      ${list.length ? `<ul class="blist">${list.map((i, k) => `<li><span>${i.kind === "folder" ? ICON.folder : ""} ${esc(i.name)}</span><button class="linkbtn" type="button" data-basket="del" data-k="${k}">retirer</button></li>`).join("")}</ul>
        <p class="muted" id="basket-size">Calcul de la taille…</p>
        <div class="actions"><button class="btn primary" type="button" data-basket="go">Tout télécharger (.zip)</button><button class="btn" type="button" data-basket="clear">Vider</button></div>
        <p class="muted small">Un seul fichier .zip : chaque série dans son dossier, les fichiers tels quels (rien n'est recompressé ni modifié).</p>`
        : `<p class="muted">Le panier est vide. Clic droit sur une série ou un album › « Ajouter aux téléchargements ».</p>`}
    </div></div>`;
    if (list.length) {
      try {
        const r = await api(bundleUrl(list).replace("/bundle", "/size"));
        const el = $("#basket-size"); if (el) el.textContent = r.albums ? `${plural(r.albums, "album", "albums")} · ${fmtSize(r.bytes)}` : "Ces éléments ne sont plus dans la bibliothèque (renommés ou supprimés ?) : retirez-les.";
        const go = modal.querySelector("[data-basket=go]"); if (go && !r.albums) go.disabled = true;
      } catch (err) { const el = $("#basket-size"); if (el) el.textContent = err.message; }
    }
  }
  document.addEventListener("click", e => {
    if (e.target.closest("#basket-btn")) { openBasket(); return; }
    const b = e.target.closest("[data-basket]");
    if (!b) return;
    const act = b.dataset.basket;
    if (act === "close") closeModal();
    else if (act === "del") { const l = basketGet(); l.splice(+b.dataset.k, 1); basketSet(l); openBasket(); }
    else if (act === "clear") { basketSet([]); closeModal(); }
    else if (act === "go") {
      startDownload(bundleUrl(basketGet()));
      modal.querySelector(".actions").innerHTML = `<span class="muted">Le téléchargement démarre (il peut mettre quelques secondes à apparaître).</span><button class="btn" type="button" data-basket="clear">Vider le panier</button>`;
    }
  });
  modal.addEventListener("click", e => { if (e.target.classList.contains("backdrop") && modal.querySelector(".sheet.basket")) closeModal(); });
  updateBasketBtn();

  // ================================================================ pochette au survol des propositions Bédéthèque
  let bdtPop = null, bdtPopTimer = null;
  function hideBdtPop() { clearTimeout(bdtPopTimer); if (bdtPop) { bdtPop.remove(); bdtPop = null; } }
  main.addEventListener("mouseover", e => {
    const c = e.target.closest("[data-url][data-bdt$='pick']");
    if (!c || !isAdmin() || (bdtPop && bdtPop.dataset.url === c.dataset.url)) return;
    hideBdtPop();
    bdtPopTimer = setTimeout(async () => {
      bdtPop = document.createElement("div");
      bdtPop.className = "bdtpop"; bdtPop.dataset.url = c.dataset.url;
      bdtPop.innerHTML = `<div class="spinner"></div>`;
      document.body.appendChild(bdtPop);
      const place = () => {
        if (!bdtPop) return;
        const r = c.getBoundingClientRect(), w = bdtPop.offsetWidth, h = bdtPop.offsetHeight;
        let x = r.left + r.width / 2 - w / 2, y = r.top - h - 8;
        if (y < 8) y = r.bottom + 8;
        bdtPop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x)) + "px";
        bdtPop.style.top = Math.max(8, y) + "px";
      };
      place();
      const url = c.dataset.url, still = () => bdtPop && bdtPop.dataset.url === url;
      const show = (r, retry) => {   // miniature, sinon l'image en grand, sinon (nom deviné) la page de l'album est lue
        if (!still()) return;
        if (!r.thumb) { bdtPop.innerHTML = `<span class="muted">Pas de pochette</span>`; place(); return; }
        bdtPop.innerHTML = `<img src="${esc(r.thumb)}" referrerpolicy="no-referrer" alt="">`;
        const img = bdtPop.querySelector("img");
        img.onload = place;
        img.onerror = () => {
          if (!still()) return;
          if (r.image && img.getAttribute("src") !== r.image) { img.src = r.image; return; }
          if (r.guess && retry) { bdtPop.innerHTML = `<div class="spinner"></div>`; place(); load(true); return; }
          bdtPop.innerHTML = `<span class="muted">Pochette indisponible</span>`; place();
        };
        place();
      };
      const load = async page => {
        try { show(await api(`/api/bdt/cover?url=${encodeURIComponent(url)}${page ? "&page=1" : ""}`), !page); }
        catch (err) { if (still()) { bdtPop.innerHTML = `<span class="muted">${esc(err.message)}</span>`; place(); } }
      };
      load(false);
    }, 400);
  });
  main.addEventListener("mouseout", e => {
    const c = e.target.closest("[data-url][data-bdt$='pick']");
    if (c && !(e.relatedTarget && c.contains(e.relatedTarget))) hideBdtPop();
  });
  window.addEventListener("hashchange", hideBdtPop);
  // couverture d'un one shot agrandie au survol de sa vignette
  let osPop = null;
  main.addEventListener("mouseover", e => {
    const t = e.target.closest("[data-os-thumb]");
    if (!t || (osPop && osPop.dataset.src === t.dataset.osThumb)) return;
    if (osPop) osPop.remove();
    osPop = document.createElement("div");
    osPop.className = "bdtpop ospop"; osPop.dataset.src = t.dataset.osThumb;
    osPop.innerHTML = `<img src="${esc(t.dataset.osThumb)}" alt="">`;
    document.body.appendChild(osPop);
    const place = () => {
      if (!osPop) return;
      const r = t.getBoundingClientRect(), w = osPop.offsetWidth, h = osPop.offsetHeight;
      // à gauche de la vignette (sur le nom), pour ne pas cacher les propositions à droite
      let x = r.left - w - 10, y = r.top + r.height / 2 - h / 2;
      if (x < 8) x = r.right + 10;
      osPop.style.left = Math.max(8, x) + "px";
      osPop.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, y)) + "px";
    };
    osPop.querySelector("img").onload = place;
    place();
  });
  main.addEventListener("mouseout", e => {
    const t = e.target.closest("[data-os-thumb]");
    if (t && osPop && !(e.relatedTarget && t.contains(e.relatedTarget))) { osPop.remove(); osPop = null; }
  });
  window.addEventListener("hashchange", () => { if (osPop) { osPop.remove(); osPop = null; } });

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
      } else if ((m = /^#\/settings(?:\/(\w+))?/.exec(h))) {
        await viewSettings(m[1]);
      } else if (h.startsWith("#/adult")) {
        await viewAdult();
      } else if ((m = /^#\/collection(?:\/(\w+))?/.exec(h))) {
        await viewCollection(m[1]);
      } else if ((m = /^#\/list\/(\w+)/.exec(h))) {
        await viewList(m[1]);
      } else if (h.startsWith("#/lists")) {
        await viewLists();
      } else if (h.startsWith("#/history")) {
        await viewHistory();
      } else if (h.startsWith("#/activity")) {
        await viewActivity();
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
    if (!settings.global.account_login && settings.global.require_profile && settings.meta.profile_selected === false) openProfiles({ locked: true });
    try {
      if (settings.profile.remember_folder && !sessionStorage.getItem("bulle:visited") && (location.hash === "" || location.hash === "#/")) {
        const last = localStorage.getItem("bulle:lastHash");
        if (last && last.startsWith("#/f/")) location.replace(last);
      }
      sessionStorage.setItem("bulle:visited", "1");
    } catch (_) { /* ignore */ }
    renderQualitySwitch();
    route();
    loadStats();
    renderSidebar();
  })();
})();
