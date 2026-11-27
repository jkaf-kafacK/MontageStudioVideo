/* Éditeur MSV : timeline, aperçu en temps réel, images clés à la souris.
   Le projet est au format MSV (le même que l'onglet Montage) ; l'export utilise le moteur de rendu de MSV.
   Aucune bibliothèque, aucune étape de compilation : ce fichier fonctionne tel quel dans une application Tauri. */
"use strict";

const $ = (s) => document.querySelector(s);
const enc = encodeURIComponent;
const IN_DUR = 0.5, OUT_DUR = 0.3, PREVIEW_DIV = 2, SNAP = 1 / 60;   // aperçu calculé en demi-résolution
const FILE = (p) => `/api/editeur/fichier?path=${enc(p)}`;
const API_VERSION = 9;   // même nombre que core/editor.py : sinon MSV tourne encore avec une ancienne version
const OLD_SERVER = "MSV tourne avec une ancienne version : ferme sa fenêtre noire, relance-le, puis recharge cette page (Ctrl+F5).";

async function api(url, opts = {}) {
  const r = await fetch(url, opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)
    ? { ...opts, body: JSON.stringify(opts.body), headers: { "Content-Type": "application/json" } } : opts);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* réponse non JSON */ }
    if (r.status === 404 && msg === "Not Found" && url.startsWith("/api/editeur/")) msg = OLD_SERVER;   // adresse inconnue du serveur
    throw new Error(msg);
  }
  return r.json();
}

const num = (v, d = 0) => { const x = parseFloat(String(v ?? "").replace(",", ".")); return Number.isFinite(x) ? x : d; };
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const round = (x, n = 2) => Math.round(x * 10 ** n) / 10 ** n;
const fmtT = (t) => { t = Math.max(0, t); const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(2).padStart(5, "0")}`; };
const clone = (o) => JSON.parse(JSON.stringify(o));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let toastTimer = 0;
function alerte(msg) { const el = $("#alerte"); el.textContent = msg; el.hidden = !msg; }

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("visible"), 2600);
}

// ------------------------------------------------------------------------------------------------ état

const S = {
  cfg: null, P: null, medias: new Map(), sel: null, t: 0, playing: false, pxs: 70,
  undo: [], redo: [], vids: new Map(), imgs: new Map(), boxes: [], lut: null, lastTs: 0, dirty: false,
};

function newProject() {
  return {
    name: "mon_montage", format: "9:16", fit: "flou", fps: 30, quality: "haute", background: "#000000",
    clips: [], overlays: [], texts: [], effects: [], sfx: [], image_duration: 3, image_zoom: "aucun",
    transition: { type: "aucune", duration: 0.4 }, normalize_audio: true,
    subtitles: { source: "aucun", script: "", srt_path: "", max_words: 3, karaoke: true, animation: "aucune",
      language: "fr", whisper_model: "small", style: {} },
    lut: { name: "aucun", intensity: 1 },
    music: { path: "", volume: 0.18, ducking: true, auto: "aucune" },
    voiceover: { path: "", volume: 1, offset: 0 },
  };
}

function snapshot() { S.undo.push(JSON.stringify(S.P)); if (S.undo.length > 200) S.undo.shift(); S.redo = []; }
function changed() { S.dirty = true; renderAll(); try { localStorage.setItem("msv-editeur", JSON.stringify(S.P)); } catch (e) { /* stockage indisponible */ } }
function change(fn) { snapshot(); fn(); changed(); }
function undo() { if (!S.undo.length) return; S.redo.push(JSON.stringify(S.P)); S.P = JSON.parse(S.undo.pop()); S.sel = null; changed(); }
function redo() { if (!S.redo.length) return; S.undo.push(JSON.stringify(S.P)); S.P = JSON.parse(S.redo.pop()); S.sel = null; changed(); }

// ------------------------------------------------------------------------------------------------ médias

function info(path) { return S.medias.get(path) || { kind: "inconnu", duration: 0, width: 16, height: 9 }; }
const isImage = (path) => info(path).kind === "image";

async function ensureInfo(path) {
  if (!path || S.medias.has(path)) return;
  try { S.medias.set(path, await api(`/api/editeur/info?path=${enc(path)}`)); }
  catch (e) { S.medias.set(path, { path, name: path.split(/[\\/]/).pop(), kind: "absent", duration: 0, width: 16, height: 9 }); }
}

function video(path) {   // un lecteur caché par fichier ; d'abord le fichier d'origine, puis le proxy léger
  let v = S.vids.get(path);
  if (v) return v;
  const el = document.createElement("video");
  el.preload = "auto"; el.playsInline = true; el.muted = true; el.crossOrigin = "anonymous";
  el.src = FILE(path);
  v = { el, proxy: false };
  S.vids.set(path, v);
  const poll = async () => {
    try {
      const st = await api(`/api/editeur/proxy?path=${enc(path)}`);
      if (st.state === "pret" && st.url && !v.proxy) {
        const t = el.currentTime, playing = !el.paused;
        v.proxy = true; el.src = st.url; el.currentTime = t; if (playing) el.play().catch(() => {});
      } else if (st.state === "en cours") setTimeout(poll, 2000);
    } catch (e) { /* proxy impossible : on garde le fichier d'origine */ }
  };
  poll();
  return v;
}

function image(path) {
  let im = S.imgs.get(path);
  if (!im) { im = new Image(); im.crossOrigin = "anonymous"; im.src = FILE(path); S.imgs.set(path, im); }
  return im;
}

async function loadMedias() {
  const list = await api("/api/editeur/medias");
  for (const m of list) S.medias.set(m.path, m);
  const box = $("#liste-medias");
  box.innerHTML = list.length ? "" : '<p class="vide">Aucun média : importe des fichiers.</p>';
  for (const m of list) {
    const row = document.createElement("div");
    row.className = "media";
    const ico = m.kind === "audio" ? "♪" : m.kind === "video" ? "▶" : "";
    row.tabIndex = 0;
    row.title = "Double-clic : ajouter · clic droit : plus de choix";
    row.innerHTML = `<span class="icone">${ico}</span><div><div class="nom-media">${esc(m.name)}${m.sticker ? '<span class="badge">sticker</span>' : ""}</div>
      <div class="infos">${esc(m.kind)}${m.duration ? " · " + fmtT(m.duration) : ""}${m.width ? ` · ${m.width}×${m.height}` : ""}</div></div><span></span>`;
    if (m.kind === "image") { const im = document.createElement("img"); im.src = FILE(m.path); im.alt = ""; row.firstChild.replaceWith(im); }
    else if (m.kind === "video") {
      api(`/api/editeur/vignettes?path=${enc(m.path)}`).then((r) => {
        if (r.strip) { const im = document.createElement("img"); im.src = r.strip; im.alt = ""; im.style.objectPosition = "40% 50%"; row.firstChild.replaceWith(im); }
      }).catch(() => {});
    }
    row.ondblclick = () => addDefault(m);
    if (m.kind === "video" || m.kind === "image") {   // glisser sur un plan de la timeline : le remplace
      row.draggable = true;
      row.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/msv-media", m.path); e.dataTransfer.effectAllowed = "copy"; });
    }
    row.addEventListener("contextmenu", (e) => { e.preventDefault(); mediaMenu(m, e.clientX, e.clientY); });
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter") addDefault(m);
      else if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) { e.preventDefault(); const r = row.getBoundingClientRect(); mediaMenu(m, r.left + 40, r.bottom); }
    });
    box.append(row);
  }
}

function addMedia(m) {
  if (m.kind === "audio") { change(() => { S.P.music.path = m.path; }); toast("Musique du projet : " + m.name); return; }
  change(() => {
    S.P.clips.push(m.kind === "image" ? { path: m.path, duration: num(S.P.image_duration, 3) }
      : { path: m.path, start: 0, end: null, speed: 1, volume: 1, crop_x: 0.5 });
    S.sel = { kind: "clips", i: S.P.clips.length - 1 };
  });
  thumbs(m.path);
}

function addOverlay(m, at = S.t) {
  const [W, H] = S.cfg.formats[S.P.format] || [1080, 1920], wide = m.width > 2 * m.height;
  change(() => {
    const d = m.animated ? Math.max(1, round(m.duration || 3)) : m.kind === "video" && !m.sticker ? Math.min(m.duration || 4, 8) : m.sticker ? 3 : 4;
    S.P.overlays.push({ path: m.path, start: round(at), end: round(at + d), x: 50,
      y: m.sticker ? (wide ? (W < H ? 86 : 80) : 70) : 50,   // large : sous les sous-titres (vers 72 %)
      width: wide ? (W < H ? 88 : 50) : m.sticker ? 28 : 40, opacity: 1,
      animation: m.animated ? "aucune" : m.sticker ? "zoom" : "fondu", keyframes: "" });
    S.sel = { kind: "overlays", i: S.P.overlays.length - 1 };
  });
  toast(`Calque posé à ${fmtT(at)} : ${m.name}`);
}

function addDefault(m) {   // double-clic : audio -> musique ; sticker / image transparente -> calque ; sinon timeline
  if ((m.kind === "video" || m.kind === "image") && !m.sticker && !m.animated && emptySlots().length) { fillNextSlot(m); return; }
  if (m.kind === "audio" || !m.sticker) addMedia(m);
  else addOverlay(m);
}

// ---- modèles de montage : emplacements à remplir (core/montage_templates.py)
function emptySlots() { return S.P.clips.map((c, i) => i).filter((i) => S.P.clips[i].slot); }
function fillNextSlot(m) {   // l'emplacement choisi s'il y en a un, sinon le premier vide
  const sel = S.sel && S.sel.kind === "clips" && S.P.clips[S.sel.i] && S.P.clips[S.sel.i].slot ? S.sel.i : emptySlots()[0];
  fillSlot(sel, m);
}
async function fillSlot(i, m) {   // remplace le plan i par le média m, en gardant sa durée, son zoom et son cadrage
  const c = S.P.clips[i];
  if (!c || !["video", "image"].includes(m.kind)) return;
  const d = c.slot ? num(c.slot.duration, clipDur(c)) : clipDur(c), keep = {};
  for (const k of ["fit", "keyframes", "crop_x", "crop"]) if (c[k] != null && c[k] !== "") keep[k] = c[k];
  const nc = m.kind === "image" ? { path: m.path, duration: round(d), ...keep }
    : { path: m.path, start: 0, end: m.duration > d + 0.05 ? round(d, 3) : null, speed: 1, volume: 1, crop_x: 0.5, ...keep };
  await ensureInfo(m.path);
  const wasSlot = !!c.slot;
  change(() => { S.P.clips[i] = nc; S.sel = { kind: "clips", i }; });
  thumbs(m.path);
  const left = emptySlots().length;
  toast(!wasSlot ? "Média du plan remplacé." : left ? `Plan rempli : encore ${left} plan${left > 1 ? "s" : ""} à remplir.` : "Tous les plans sont remplis : tu peux exporter.");
}
async function showTemplates() {
  const box = $("#liste-modeles"); box.innerHTML = "<p class='vide'>Chargement…</p>";
  $("#dlg-modeles").showModal();
  let list = [];
  try { list = await api("/api/editeur/modeles"); } catch (e) { box.innerHTML = `<p class='vide'>${esc(e.message)}</p>`; return; }
  box.innerHTML = list.length ? "" : "<p class='vide'>Aucun modèle.</p>";
  for (const m of list) {
    const b = document.createElement("button");
    b.className = "carte-modele";
    b.innerHTML = `<span class="ico" aria-hidden="true">${esc(m.ico)}</span><b>${esc(m.title)}</b><small>${esc(m.description)}</small>
      <span class="infos">${esc(m.format)} · ${m.slots} plan${m.slots > 1 ? "s" : ""} · ${String(m.duration).replace(".", ",")} s</span>`;
    b.onclick = async () => {
      if (S.dirty && (S.P.clips.length || S.P.texts.length) && !confirm("Remplacer le montage en cours par ce modèle ? (pense à l'enregistrer d'abord)")) return;
      try {
        const p = await api("/api/editeur/modele", { method: "POST", body: { name: m.name } });
        $("#dlg-modeles").close();
        await openProject(p);
        $("#nom").value = S.P.name;
        for (const c of S.P.clips) thumbs(c.path);
        toast(`Modèle « ${m.title} » : remplace les ${m.slots} plans par tes vidéos (double-clic sur un média).`);
      } catch (e) { toast("Modèle impossible : " + e.message); }
    };
    box.append(b);
  }
}

function addTextAt(at = S.t) {
  change(() => {
    S.P.texts.push({ text: "Ton texte", start: round(at), end: round(at + 3), x: 50, y: 30, size: 80, color: "#FFFFFF",
      box: false, animation: "montée", keyframes: "" });
    S.sel = { kind: "texts", i: S.P.texts.length - 1 };
  });
}

// ------------------------------------------------------------------------------------------------ menus (clic droit)

function closeMenu() { const m = $("#menu"); m.hidden = true; m.innerHTML = ""; }

function menu(x, y, items) {
  items = items.filter((it, n, all) => it !== "-" || (n > 0 && all[n - 1] !== "-" && !all[n - 1].title && n < all.length - 1));
  while (items.length && items[items.length - 1] === "-") items.pop();
  if (!items.some((it) => it.run)) { closeMenu(); return; }   // rien de possible ici : pas de menu
  const m = $("#menu");
  m.innerHTML = "";
  for (const it of items) {
    if (it === "-") { m.append(document.createElement("hr")); continue; }
    if (it.title) { const t = document.createElement("div"); t.className = "titre-menu"; t.textContent = it.title; m.append(t); continue; }
    const b = document.createElement("button");
    b.setAttribute("role", "menuitem");
    b.innerHTML = `<span class="ico">${it.ico || ""}</span><span>${esc(it.label)}</span>${it.key ? `<span class="espace"></span><small class="note">${esc(it.key)}</small>` : ""}`;
    if (it.danger) b.className = "danger";
    b.onclick = () => { closeMenu(); it.run(); };
    m.append(b);
  }
  m.hidden = false;
  const r = m.getBoundingClientRect();
  m.style.left = `${clamp(x, 4, innerWidth - r.width - 4)}px`;
  m.style.top = `${clamp(y, 4, innerHeight - r.height - 4)}px`;
  const first = m.querySelector("button"); if (first) first.focus();
}

document.addEventListener("pointerdown", (e) => { if (!e.target.closest("#menu")) closeMenu(); });
document.addEventListener("keydown", (e) => {
  const m = $("#menu"); if (m.hidden) return;
  const btns = [...m.querySelectorAll("button")], i = btns.indexOf(document.activeElement);
  if (e.key === "Escape") { e.preventDefault(); closeMenu(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); btns[(i + 1) % btns.length].focus(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); btns[(i - 1 + btns.length) % btns.length].focus(); }
}, true);
window.addEventListener("blur", closeMenu);

function mediaMenu(m, x, y) {
  if (!["audio", "video", "image"].includes(m.kind)) { toast("Ce fichier ne peut pas être ajouté au montage."); return; }
  const items = [{ title: m.name }];
  if (m.kind === "audio") {
    items.push({ ico: "♪", label: "Musique du projet", run: () => { change(() => { S.P.music.path = m.path; }); toast("Musique : " + m.name); } },
      { ico: "🎙", label: "Voix off du projet", run: () => { change(() => { S.P.voiceover.path = m.path; }); toast("Voix off : " + m.name); } });
  } else {
    items.push({ ico: "▣", label: "Poser en calque au curseur", run: () => addOverlay(m) });
    if (!m.animated) items.push({ ico: "＋", label: "Ajouter à la fin de la timeline", run: () => addMedia(m) });
  }
  menu(x, y, items);
}

const ctaItem = (at) => ({ ico: "▶", label: "Animation Like · Abonne-toi · Partage", run: () => addCta(at) });

function clipAt(t) { return layoutClips().find((o) => t > o.t0 + 0.05 && t < o.t1 - 0.05); }

// Menus de zones vides : chaque zone ne propose que ce qu'on peut y mettre.
//   piste Vidéo : couper le clip sous le curseur · piste Calques : emoji, sticker · piste Textes : texte
//   aperçu (et bouton « Ajouter ») : texte, emoji, sticker · piste Audio et règle : rien
function zoneMenu(zone, x, y, at = S.t) {
  const title = { title: `À ${fmtT(at)}` };
  const addLayer = [{ ico: "😀", label: "Emoji ou sticker…", run: () => openStickers(at) }, ctaItem(at),
    { ico: "✎", label: "Créer un sticker…", run: () => openStickers(at, "creer") }];
  const addText = { ico: "T", label: "Texte", run: () => addTextAt(at) };
  const items = zone === "clips" ? (clipAt(at) ? [title, { ico: "✂", label: "Couper le clip ici", key: "S", run: () => { setTime(at); splitClip(); } }] : [])
    : zone === "overlays" ? [title, ...addLayer]
      : zone === "texts" ? [title, addText]
        : zone === "apercu" ? [title, addText, ...addLayer] : [];
  menu(x, y, items);
}

function itemRange(kind, i) {
  if (kind === "clips") { const o = layoutClips()[i]; return [o.t0, o.t1]; }
  const it = S.P[kind][i]; return [num(it.start), layerEnd(it)];
}
function inRange(kind, i) { const [a, b] = itemRange(kind, i); return S.t >= a - 1e-3 && S.t <= b + 1e-3; }

function rotateBy(kind, i, deg, reset) {   // angle fixe, ou image clé au curseur si le calque en a
  const it = S.P[kind][i], u = localTime(kind, i), pts = kfParse(it.keyframes, baseOf(kind, it));
  if (pts.length) {
    const cur = kfState(pts, u).rotation;
    kfUpsert(it, baseOf(kind, it), u, { rotation: reset ? 0 : normAngle(cur + deg) }, false);
  } else it.rotation = reset ? 0 : normAngle(num(it.rotation, 0) + deg);
  changed();
}

function currentAngle(kind, i) {
  const it = S.P[kind][i], pts = kfParse(it.keyframes, baseOf(kind, it));
  return pts.length ? kfState(pts, localTime(kind, i)).rotation : num(it.rotation, 0);
}

// Menu d'un élément : seulement les actions possibles là où se trouve le curseur.
function itemMenu(kind, i, x, y, extra = []) {
  select(kind, i);
  const it = S.P[kind][i], hasKf = kfParse(it.keyframes).length > 0, layer = kind !== "clips";
  const [a, b] = itemRange(kind, i), inside = inRange(kind, i), n = S.P[kind].length;
  const items = [{ title: kind === "clips" ? "Clip" : kind === "texts" ? "Texte" : "Calque" }];
  if (kind === "clips" && S.t > a + 0.05 && S.t < b - 0.05) items.push({ ico: "✂", label: "Couper au curseur", key: "S", run: splitClip });
  if (inside) items.push({ ico: "◆", label: "Image clé au curseur", key: "K", run: addKeyHere });
  if (hasKf) items.push({ ico: "◇", label: "Effacer les images clés", run: () => change(() => { it.keyframes = ""; }) });
  if (layer && (!hasKf || inside)) {     // avec des images clés, la rotation s'applique au temps du curseur
    items.push("-", { ico: "↻", label: "Tourner de 90° à droite", run: () => { snapshot(); rotateBy(kind, i, 90); } },
      { ico: "↺", label: "Tourner de 90° à gauche", run: () => { snapshot(); rotateBy(kind, i, -90); } });
    if (Math.abs(currentAngle(kind, i)) > 0.05) items.push({ ico: "⊥", label: "Remettre droit", run: () => { snapshot(); rotateBy(kind, i, 0, true); } });
  }
  items.push("-", { ico: "⧉", label: "Dupliquer", run: () => duplicate(kind, i) });
  if (layer) {
    if (i < n - 1) items.push({ ico: "⬆", label: "Premier plan", run: () => reorderLayer(kind, i, n - 1) });
    if (i > 0) items.push({ ico: "⬇", label: "Arrière-plan", run: () => reorderLayer(kind, i, 0) });
    if (Math.abs(num(it.start) - S.t) > 0.01) items.push({ ico: "⇤", label: "Commencer au curseur", run: () => change(() => { const d = layerEnd(it) - num(it.start); it.start = round(S.t); it.end = round(S.t + d); }) });
  }
  items.push(...extra, "-", { ico: "🗑", label: "Supprimer", key: "Suppr", danger: true, run: () => change(() => { S.P[kind].splice(i, 1); S.sel = null; }) });
  menu(x, y, items);
}

function audioMenu(key, x, y) {
  const name = key === "music" ? "Musique" : "Voix off";
  menu(x, y, [{ title: name }, { ico: "🗑", label: `Retirer la ${name.toLowerCase()}`, danger: true,
    run: () => change(() => { S.P[key].path = ""; }) }]);
}

function duplicate(kind, i) {
  change(() => {
    const it = clone(S.P[kind][i]);
    if (kind !== "clips") { const d = layerEnd(S.P[kind][i]) - num(it.start); it.start = round(layerEnd(S.P[kind][i])); it.end = round(it.start + d); }
    S.P[kind].splice(i + 1, 0, it);
    S.sel = { kind, i: i + 1 };
  });
}

function reorderLayer(kind, i, to) {
  if (i === to) return;
  change(() => { const [it] = S.P[kind].splice(i, 1); S.P[kind].splice(to, 0, it); S.sel = { kind, i: to }; });
}

// ---- stickers et emojis

let stickerAt = 0, stickerLib = null, libBuilt = false;
async function stickerLibrary() {
  if (!stickerLib) stickerLib = await api("/api/editeur/stickers");
  return stickerLib;
}
async function addAnimated(a, at = S.t) {   // sticker animé de la bibliothèque, préparé par le serveur si besoin
  if (!a.path) toast("Préparation de l'animation (quelques secondes)…");
  try {
    const m = await api("/api/editeur/sticker-anime", { method: "POST", body: { key: a.key } });
    a.path = m.path; S.medias.set(m.path, m);
    if ($("#dlg-stickers").open) $("#dlg-stickers").close();
    addOverlay({ ...m, name: a.name }, at);
  } catch (e) { toast("Animation indisponible : " + e.message); }
}
async function addCta(at = S.t) {   // animation « Like, abonne-toi, commente, partage » posée en calque
  try { const lib = await stickerLibrary(); await addAnimated(lib.animated[0], at); }
  catch (e) { toast("Animation indisponible : " + e.message); }
}
function showTab(name) {
  for (const o of document.querySelectorAll("#dlg-stickers [data-onglet]")) o.setAttribute("aria-selected", String(o.dataset.onglet === name));
  for (const pn of ["emoji", "stickers", "creer"]) $(`#panneau-${pn}`).hidden = pn !== name;
  if (name === "creer") { fillCreator(); previewCustom(); }
}
async function openStickers(at = S.t, tab = "emoji") {
  stickerAt = at;
  const dlg = $("#dlg-stickers");
  dlg.showModal();
  showTab(tab);
  if (libBuilt) return;
  try { await stickerLibrary(); } catch (e) { toast("Stickers indisponibles : " + e.message); return; }
  libBuilt = true;
  const ge = $("#grille-emoji"); ge.innerHTML = "";
  if (!stickerLib.emoji_ok) ge.innerHTML = '<p class="note">Aucune police d\'emoji en couleur sur cet ordinateur.</p>';
  for (const [cat, list] of Object.entries(stickerLib.emoji)) {
    const h = document.createElement("h3"); h.textContent = cat; ge.append(h);
    const row = document.createElement("div"); row.className = "emojis";
    for (const em of list) { const b = document.createElement("button"); b.textContent = em; b.title = "Poser " + em; b.onclick = () => placeEmoji(em); row.append(b); }
    ge.append(row);
  }
  const gs = $("#grille-stickers"); gs.innerHTML = "";
  for (const st of stickerLib.stickers) {
    const b = document.createElement("button");
    b.innerHTML = `<img src="${FILE(st.path)}" alt=""><span>${esc(st.name)}</span>`;
    b.onclick = async () => { $("#dlg-stickers").close(); await ensureInfo(st.path); addOverlay({ ...info(st.path), sticker: true, name: st.name }, stickerAt); };
    gs.append(b);
  }
  for (const a of stickerLib.animated) {   // stickers animés (vignette animée une fois prêts)
    const b = document.createElement("button");
    b.className = "anime";
    b.innerHTML = (a.path ? `<img src="${FILE(a.path)}" alt="">` : '<span class="vignette-anim">▶</span>') + `<span>${esc(a.name)}</span>`;
    b.onclick = () => addAnimated(a, stickerAt);
    gs.append(b);
  }
}

// ---- créer son sticker : base (emoji ou photo), forme, emoji accessoire, texte, contour (façon WhatsApp)
function customSpec() {
  const v = (id) => $(id).value;
  return { base: v("#cs-base"), emoji: v("#cs-emoji").trim() || "🙂", path: v("#cs-photo"), shape: v("#cs-forme"),
    accessory: v("#cs-acc").trim(), corner: v("#cs-coin"), accessory_size: num(v("#cs-taille"), 0.35),
    text: v("#cs-texte"), text_pos: v("#cs-pos"), text_color: v("#cs-couleur"), outline: $("#cs-contour").checked };
}
function fillCreator() {
  const photos = [...S.medias.values()].filter((m) => m.kind === "image" && !m.sticker);
  const sel = $("#cs-photo"), cur = sel.value;
  sel.innerHTML = photos.length ? "" : '<option value="">(aucune photo : importe-en une)</option>';
  for (const m of photos) { const o = document.createElement("option"); o.value = m.path; o.textContent = m.name; sel.append(o); }
  if (cur) sel.value = cur;
  if (!$("#cs-forme").options.length) {   // formes et coins : connus dès le démarrage (config)
    for (const s of S.cfg.sticker_shapes || []) $("#cs-forme").append(new Option(s, s));
    for (const c of S.cfg.sticker_corners || []) $("#cs-coin").append(new Option(c, c));
    $("#cs-forme").value = "originale";
  }
  const photo = $("#cs-base").value === "photo";
  $("#cs-ligne-emoji").hidden = photo; $("#cs-ligne-photo").hidden = !photo;
}
let previewTimer = 0, previewSeq = 0;
function previewCustom() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const seq = ++previewSeq, spec = customSpec();
    if (spec.base === "photo" && !spec.path) { $("#cs-apercu").removeAttribute("src"); return; }
    try {
      const r = await api("/api/editeur/sticker-perso", { method: "POST", body: { spec } });
      if (seq === previewSeq) { $("#cs-apercu").src = r.data; $("#cs-erreur").textContent = ""; }
    } catch (e) { if (seq === previewSeq) $("#cs-erreur").textContent = e.message; }
  }, 250);
}
async function createCustom() {
  try {
    const m = await api("/api/editeur/sticker-perso", { method: "POST", body: { spec: customSpec(), save: true } });
    S.medias.set(m.path, m);
    $("#dlg-stickers").close();
    addOverlay({ ...m, sticker: true, name: "sticker perso" }, stickerAt);
    loadMedias().catch(() => {});
  } catch (e) { $("#cs-erreur").textContent = e.message; }
}

async function placeEmoji(em) {
  try {
    const m = await api("/api/editeur/emoji", { method: "POST", body: { emoji: em } });
    S.medias.set(m.path, m);
    $("#dlg-stickers").close();
    addOverlay({ ...m, sticker: true, name: em }, stickerAt);
  } catch (e) { toast(e.message); }
}

const thumbCache = new Map();
function thumbs(path) {
  if (thumbCache.has(path) || !path) return thumbCache.get(path);
  thumbCache.set(path, "");
  api(`/api/editeur/vignettes?path=${enc(path)}`).then((r) => { thumbCache.set(path, r.strip || ""); renderTimeline(); }).catch(() => {});
  return "";
}

// ------------------------------------------------------------------------------------------------ modèle

// ---- courbes de vitesse : même découpage en morceaux de vitesse constante que core/speedcurve.py (rendu)
const CURVE = { piece: 0.12, min: 8, max: 40, lo: 0.1, hi: 8 };
const r4 = (x) => Math.round(x * 1e4) / 1e4;
function curvePoints(curve) {
  const txt = String(curve || "").trim();
  if (!txt || txt === "aucune") return [];
  const pre = (S.cfg.speed_curves || {})[txt];
  if (pre) return pre;
  const pts = [];
  for (const part of txt.split(/[;\n]+/)) {
    const m = part.trim().match(/^(\d+(?:[.,]\d+)?)\s*[:=]\s*(\d+(?:[.,]\d+)?)$/);
    if (m) pts.push([clamp(num(m[1]), 0, 1), clamp(num(m[2]), CURVE.lo, CURVE.hi)]);
  }
  pts.sort((a, b) => a[0] - b[0]);
  return pts.length === 1 ? [[0, pts[0][1]], [1, pts[0][1]]] : pts;
}
function curveValue(pts, u) {
  if (!pts.length) return 1;
  if (u <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    const [u0, v0] = pts[i - 1], [u1, v1] = pts[i];
    if (u <= u1) { let k = u1 <= u0 ? 0 : (u - u0) / (u1 - u0); k = k * k * (3 - 2 * k); return v0 + (v1 - v0) * k; }
  }
  return pts[pts.length - 1][1];
}
function clipEnd(c) { return c.end == null || c.end === "" ? info(c.path).duration : num(c.end); }
function speedPieces(c) {   // [[début, fin dans la source, vitesse], …]
  const s = num(c.start), e = clipEnd(c), base = Math.max(0.1, num(c.speed, 1)), pts = curvePoints(c.speed_curve);
  if (!pts.length || !(e > s)) return [[s, e, base]];
  const n = Math.round(Math.min(CURVE.max, Math.max(CURVE.min, Math.round((e - s) / CURVE.piece))));
  const step = (e - s) / n, out = [];
  for (let i = 0; i < n; i++) out.push([r4(s + i * step), r4(s + (i + 1) * step), r4(clamp(base * curveValue(pts, (i + 0.5) / n), CURVE.lo, CURVE.hi))]);
  return out;
}
function clipSrcAt(c, u) {   // moment de la source et vitesse, u secondes après le début du clip dans la timeline
  let acc = 0;
  const pcs = speedPieces(c);
  for (const [a, b, sp] of pcs) {
    const d = (b - a) / sp;
    if (u < acc + d) return { src: a + (u - acc) * sp, rate: sp };
    acc += d;
  }
  const last = pcs[pcs.length - 1];
  return { src: last[1], rate: last[2] };
}

function clipDur(c) {
  if (isImage(c.path)) return Math.max(0.1, num(c.duration, num(S.P.image_duration, 3)));
  return Math.max(0.05, speedPieces(c).reduce((d, [a, b, sp]) => d + (b - a) / sp, 0));
}

function layoutClips() {
  let t = 0;
  return S.P.clips.map((c, i) => { const d = clipDur(c); const o = { i, c, t0: t, t1: t + d }; t += d; return o; });
}

function totalDur() {
  const L = layoutClips();
  let T = L.length ? L[L.length - 1].t1 : 0;
  for (const k of ["overlays", "texts"]) for (const it of S.P[k]) T = Math.max(T, num(it.end, num(it.start) + 3));
  return T;
}

const layerEnd = (it) => (it.end == null || it.end === "" ? totalDur() : num(it.end));

// ------------------------------------------------------------------------------------------------ images clés

function kfParse(text, base) {   // même écriture que core/keyframes.py
  const out = [];
  let prev = { x: 50, y: 50, scale: 1, opacity: 1, rotation: 0, ...base };
  for (const part of String(text || "").split(";").map((s) => s.trim()).filter(Boolean)) {
    const p = { ...prev };
    const tm = part.match(/(-?\d+(?:[.,]\d+)?)\s*s\b/); if (!tm) continue;
    p.t = num(tm[1]);
    const at = part.match(/@\s*(-?\d+(?:[.,]\d+)?)\s*[,;/ ]\s*(-?\d+(?:[.,]\d+)?)/); if (at) { p.x = num(at[1]); p.y = num(at[2]); }
    const sc = part.match(/[×xX*]\s*(\d+(?:[.,]\d+)?)/); if (sc) p.scale = num(sc[1]);
    const op = part.match(/(\d+(?:[.,]\d+)?)\s*%/); if (op) p.opacity = num(op[1]) / 100;
    const ro = part.match(/(-?\d+(?:[.,]\d+)?)\s*°/); if (ro) p.rotation = num(ro[1]);
    out.push(p); prev = p;
  }
  return out.sort((a, b) => a.t - b.t);
}

function kfFormat(pts, isClip) {
  return pts.map((p) => isClip ? `${round(p.t)}s @${round(p.x, 1)},${round(p.y, 1)} ×${round(p.scale)}`
    : `${round(p.t)}s @${round(p.x, 1)},${round(p.y, 1)} ×${round(p.scale)} ${Math.round(p.opacity * 100)}% ${round(p.rotation, 1)}°`).join(" ; ");
}

function kfValue(pts, key, t) {
  if (t <= pts[0].t) return pts[0][key];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if (t < b.t) { if (b.t - a.t < 1e-6) return b[key]; const p = clamp((t - a.t) / (b.t - a.t), 0, 1); return a[key] + (b[key] - a[key]) * p * p * (3 - 2 * p); }
  }
  return pts[pts.length - 1][key];
}

function kfState(pts, t) { const o = {}; for (const k of ["x", "y", "scale", "opacity", "rotation"]) o[k] = kfValue(pts, k, t); return o; }

function kfUpsert(item, base, tLocal, values, isClip) {
  const pts = kfParse(item.keyframes, base);
  const hit = pts.find((p) => Math.abs(p.t - tLocal) < SNAP * 2);
  if (hit) Object.assign(hit, values);
  else pts.push({ ...(pts.length ? kfState(pts, tLocal) : { x: 50, y: 50, scale: 1, opacity: 1, rotation: 0, ...base }), ...values, t: round(tLocal) });
  item.keyframes = kfFormat(pts.sort((a, b) => a.t - b.t), isClip);
}

// ------------------------------------------------------------------------------------------------ sélection

function selItem() { return S.sel ? S.P[S.sel.kind][S.sel.i] : null; }
function select(kind, i) { S.sel = kind ? { kind, i } : null; renderInspector(); renderTimeline(); }
function localTime(kind, i) {   // temps du curseur depuis le début de l'élément (images clés)
  if (kind === "clips") { const o = layoutClips()[i]; return o ? S.t - o.t0 : 0; }
  return S.t - num(S.P[kind][i].start);
}
const baseOf = (kind, it) => (kind === "clips" ? { x: 50, y: 50, scale: 1 }
  : { x: num(it.x, 50), y: num(it.y, 50), scale: 1, opacity: 1, rotation: num(it.rotation, 0) });
const normAngle = (a) => { a = ((a % 360) + 360) % 360; return round(a > 180 ? a - 360 : a, 1); };

// ------------------------------------------------------------------------------------------------ aperçu

const c2d = $("#ecran2d"), ctxBase = c2d.getContext("2d");
const cgl = $("#ecrangl"), cly = $("#ecrancalques"), ctxLayers = cly.getContext("2d");
let ctx = ctxBase;   // image (filtre couleur appliqué) puis calques (non filtrés, comme au rendu)

function fitCanvas() {   // l'aperçu occupe toute la place disponible, au bon format
  if (!S.cfg || !S.P) return;                // pas encore démarré
  const sc = $("#scene"), [cw, ch] = canvasSize();
  const w = sc.clientWidth - 8, h = sc.clientHeight - 8;
  if (w <= 0 || h <= 0) return;
  const k = Math.min(w / cw, h / ch);
  for (const c of [c2d, cgl, cly]) { c.style.width = `${Math.floor(cw * k)}px`; c.style.height = `${Math.floor(ch * k)}px`; }
}
window.addEventListener("resize", () => { fitCanvas(); placeStep(); });
if (window.ResizeObserver) new ResizeObserver(() => fitCanvas()).observe($("#scene"));   // panneaux masqués / affichés

// barre entre l'aperçu et la timeline : glisser pour agrandir l'un ou l'autre (double-clic : taille d'origine)
function setTimelineHeight(px) {
  const h = px == null ? null : Math.round(clamp(px, 110, innerHeight * 0.6));
  if (h == null) document.body.style.removeProperty("--h-timeline"); else document.body.style.setProperty("--h-timeline", `${h}px`);
  try { if (h == null) localStorage.removeItem("msv-editeur-timeline"); else localStorage.setItem("msv-editeur-timeline", String(h)); } catch (e) { /* stockage indisponible */ }
}
function bindSplitter() {
  const bar = $("#separateur");
  bar.addEventListener("pointerdown", (e) => {
    e.preventDefault(); bar.setPointerCapture(e.pointerId); bar.classList.add("actif");
    const move = (ev) => setTimelineHeight(innerHeight - ev.clientY);
    const up = () => { bar.classList.remove("actif"); bar.removeEventListener("pointermove", move); bar.removeEventListener("pointerup", up); };
    bar.addEventListener("pointermove", move); bar.addEventListener("pointerup", up);
  });
  bar.addEventListener("dblclick", () => setTimelineHeight(null));
  bar.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault(); e.stopPropagation();
    setTimelineHeight($(".timeline").offsetHeight + (e.key === "ArrowUp" ? 20 : -20));
  });
  try { const h = localStorage.getItem("msv-editeur-timeline"); if (h) setTimelineHeight(num(h)); } catch (e) { /* stockage indisponible */ }
}

const PANELS = { medias: 210, reglages: 260 };   // largeur d'origine des panneaux de côté (px)

function setPanelWidth(name, px) {   // null : largeur d'origine
  const w = px == null ? null : Math.round(clamp(px, 150, Math.max(200, Math.min(640, innerWidth * 0.42))));
  const v = `--l-${name}`;
  if (w == null) document.body.style.removeProperty(v); else document.body.style.setProperty(v, `${w}px`);
  try { if (w == null) localStorage.removeItem("msv-editeur-" + v.slice(2)); else localStorage.setItem("msv-editeur-" + v.slice(2), String(w)); } catch (e) { /* stockage indisponible */ }
}

function bindPanelEdges() {   // bords des panneaux Médias et Réglages : glisser, double-clic, flèches gauche / droite
  for (const edge of document.querySelectorAll(".bord-panneau")) {
    const name = edge.dataset.panneau, panel = edge.parentElement;
    edge.addEventListener("pointerdown", (e) => {
      e.preventDefault(); edge.setPointerCapture(e.pointerId); edge.classList.add("actif"); document.body.classList.add("redim");
      const r = panel.getBoundingClientRect();
      const move = (ev) => setPanelWidth(name, name === "medias" ? ev.clientX - r.left : r.right - ev.clientX);
      const up = () => {
        edge.classList.remove("actif"); document.body.classList.remove("redim");
        edge.removeEventListener("pointermove", move); edge.removeEventListener("pointerup", up);
      };
      edge.addEventListener("pointermove", move); edge.addEventListener("pointerup", up);
    });
    edge.addEventListener("dblclick", () => setPanelWidth(name, null));
    edge.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault(); e.stopPropagation();
      const grow = (e.key === "ArrowRight") === (name === "medias");
      setPanelWidth(name, panel.offsetWidth + (grow ? 20 : -20));
    });
    try { const w = localStorage.getItem("msv-editeur-l-" + name); if (w) setPanelWidth(name, num(w)); } catch (e) { /* stockage indisponible */ }
  }
}

function setBig(on) {   // grand aperçu : médias et réglages masqués, l'aperçu prend leur place
  document.body.classList.toggle("grand", on);
  $("#grand").setAttribute("aria-pressed", String(on));
  $("#grand").title = on ? "Afficher les panneaux (F)" : "Grand aperçu : masque les panneaux, timeline réduite (F)";
  try { localStorage.setItem("msv-editeur-grand", on ? "oui" : "non"); } catch (e) { /* stockage indisponible */ }
}

function canvasSize() { const [W, H] = S.cfg.formats[S.P.format] || [1080, 1920]; return [Math.round(W / PREVIEW_DIV), Math.round(H / PREVIEW_DIV)]; }

function drawMedia(src, sw, sh, fit, cx, crop, cw, ch) {
  let sx = 0, sy = 0, w = sw, h = sh;
  if (crop) { sx = sw * num(crop.left) / 100; sy = sh * num(crop.top) / 100; w = sw * (1 - (num(crop.left) + num(crop.right)) / 100); h = sh * (1 - (num(crop.top) + num(crop.bottom)) / 100); }
  if (w < 2 || h < 2) return;
  const cover = Math.max(cw / w, ch / h), contain = Math.min(cw / w, ch / h);
  if (fit === "rogner" || fit === S.cfg.face) {
    const dw = w * cover, dh = h * cover;
    ctx.drawImage(src, sx, sy, w, h, (cw - dw) * cx, (ch - dh) * 0.5, dw, dh);
    return;
  }
  if (fit === "bandes" || fit === "cadre") { ctx.fillStyle = S.P.background || "#000"; ctx.fillRect(0, 0, cw, ch); }
  else {
    const dw = w * cover, dh = h * cover;
    ctx.save(); ctx.filter = "blur(10px) brightness(0.85)"; ctx.drawImage(src, sx, sy, w, h, (cw - dw) / 2, (ch - dh) / 2, dw, dh); ctx.restore();
  }
  const dw = w * contain, dh = h * contain;
  ctx.drawImage(src, sx, sy, w, h, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
}

function syncVideo(el, s, rate, play) {
  if (!Number.isFinite(s)) return;
  if (play) {
    el.playbackRate = rate;
    if (el.paused) { el.currentTime = s; el.play().catch(() => {}); }
    else if (Math.abs(el.currentTime - s) > 0.3) el.currentTime = s;
  } else {
    if (!el.paused) el.pause();
    if (Math.abs(el.currentTime - s) > 0.04 && !el.seeking) el.currentTime = s;
  }
}

function drawClip(o, t, cw, ch, activeVids) {
  const c = o.c, m = info(c.path), u = t - o.t0;
  const fit = c.fit || S.P.fit;
  ctx.save();
  const pts = kfParse(c.keyframes);
  if (pts.length) {   // zoom et point visé (comme zoompan au rendu)
    const st = kfState(pts, u), z = Math.max(1, st.scale);
    const x0 = clamp(st.x / 100 * cw - cw / z / 2, 0, cw - cw / z), y0 = clamp(st.y / 100 * ch - ch / z / 2, 0, ch - ch / z);
    ctx.setTransform(z, 0, 0, z, -x0 * z, -y0 * z);
  }
  if (m.kind === "image") {
    const im = image(c.path);
    if (im.complete && im.naturalWidth) drawMedia(im, im.naturalWidth, im.naturalHeight, fit, num(c.crop_x, 0.5), c.crop, cw, ch);
  } else if (m.kind === "video") {
    const v = video(c.path), at = clipSrcAt(c, u);   // courbe de vitesse : la vitesse change au cours du clip
    activeVids.add(v.el);
    syncVideo(v.el, at.src, at.rate, S.playing);
    v.el.muted = !S.playing || !!c.mute;
    v.el.volume = clamp(num(c.volume, 1), 0, 1);
    if (v.el.readyState >= 2) drawMedia(v.el, v.el.videoWidth, v.el.videoHeight, fit, num(c.crop_x, 0.5), c.crop, cw, ch);
  } else {
    ctx.fillStyle = "#300"; ctx.fillRect(0, 0, cw, ch);
    ctx.fillStyle = "#faa"; ctx.font = "14px sans-serif"; ctx.fillText("Fichier illisible : " + (m.name || c.path), 10, 24);
  }
  ctx.restore();
}

function presetState(anim, u, d, H) {   // animations d'entrée des calques (approximation de core/layers.py)
  const st = { dy: 0, scale: 1, alpha: 1, rot: 0 };
  if (anim === "aucune") return st;
  const din = Math.min(IN_DUR, d / 3), dout = Math.min(OUT_DUR, d / 4);
  st.alpha = clamp(u / din, 0, 1) * clamp((d - u) / dout, 0, 1);
  const p = clamp(u / din, 0, 1), back = (x) => 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2;
  if (anim === "montée") st.dy = H * 0.06 * (1 - p) ** 3;
  if (anim === "zoom" || anim === "pulsation") st.scale = 0.5 + 0.5 * back(p);
  if (anim === "pulsation") st.scale *= 1 + 0.07 * Math.sin(2 * Math.PI * 1.6 * u);
  if (anim === "rebond") st.dy = -H * 0.04 * Math.abs(Math.sin(Math.PI * 1.6 * u));
  if (anim === "balancement") st.rot = 0.14 * Math.sin(2 * Math.PI * 1.1 * u);
  return st;
}

function fontFamily(file) { return (file || "Montserrat.ttf").replace(/\.[^.]+$/, ""); }

function textLines(words, maxW, font) {
  ctx.font = font;
  const lines = []; let cur = [];
  for (const w of words) {
    const test = [...cur, w].join(" ");
    if (cur.length && ctx.measureText(test).width > maxW) { lines.push(cur); cur = [w]; } else cur.push(w);
  }
  if (cur.length) lines.push(cur);
  return lines;
}

function layerState(kind, it, u, d, H) {
  const pts = kfParse(it.keyframes, baseOf(kind, it));
  if (pts.length) { const s = kfState(pts, u); return { x: s.x, y: s.y, scale: s.scale, alpha: s.opacity, rot: s.rotation * Math.PI / 180, dy: 0 }; }
  const p = presetState(it.animation || (kind === "texts" ? "montée" : "fondu"), u, d, H);
  return { x: num(it.x, 50), y: num(it.y, 50), scale: p.scale, alpha: p.alpha, rot: p.rot + num(it.rotation, 0) * Math.PI / 180, dy: p.dy };
}

const sheets = new Map();   // stickers animés : planche d'images préparée par le serveur (une requête par fichier)
function sheet(path) {
  let s = sheets.get(path);
  if (!s) {
    s = { ready: false };
    sheets.set(path, s);
    api(`/api/editeur/planche?path=${enc(path)}`).then((m) => {
      Object.assign(s, m);
      s.img = new Image(); s.img.onload = () => { s.ready = true; }; s.img.src = FILE(m.image);
    }).catch(() => { s.failed = true; });
  }
  return s;
}
function sheetIndex(s, u) {   // dernière image commencée au temps u (s) ; l'animation boucle, comme au rendu
  const ms = ((u * 1000) % s.total + s.total) % s.total;
  let lo = 0, hi = s.starts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (s.starts[mid] <= ms) lo = mid; else hi = mid - 1; }
  return lo;
}

function drawLayer(kind, i, it, t, cw, ch, activeVids) {
  const s0 = num(it.start), e0 = layerEnd(it);
  if (t < s0 || t >= e0) return;
  const u = t - s0, st = layerState(kind, it, u, e0 - s0, ch);
  const k = Math.min(cw, ch) / 1080;
  let w, h, draw;
  if (kind === "overlays" && info(it.path).animated) {
    const s = sheet(it.path);
    if (!s.ready) return;
    const f = sheetIndex(s, u), sx = (f % s.cols) * s.fw, sy = Math.floor(f / s.cols) * s.fh;
    w = cw * clamp(num(it.width, 30), 2, 100) / 100; h = w * s.fh / s.fw;
    draw = () => ctx.drawImage(s.img, sx, sy, s.fw, s.fh, -w / 2, -h / 2, w, h);
  } else if (kind === "overlays") {
    const m = info(it.path);
    let src = null, sw = 0, sh = 0;
    if (m.kind === "video") {
      const v = video(it.path); activeVids.add(v.el);
      const dur = m.duration || 1;
      syncVideo(v.el, u % dur, 1, S.playing); v.el.muted = true;
      if (v.el.readyState >= 2) { src = v.el; sw = v.el.videoWidth; sh = v.el.videoHeight; }
    } else { const im = image(it.path); if (im.complete && im.naturalWidth) { src = im; sw = im.naturalWidth; sh = im.naturalHeight; } }
    if (!src) return;
    w = cw * clamp(num(it.width, 30), 2, 100) / 100; h = w * sh / sw;
    draw = () => ctx.drawImage(src, -w / 2, -h / 2, w, h);
  } else {
    const size = clamp(num(it.size, 80), 16, 300) * k, font = `800 ${size}px "${fontFamily()}"`;
    const lines = textLines(String(it.text || "").split(/\s+/).filter(Boolean), cw * 0.9, font);
    const lh = size * 1.12;
    w = Math.max(...lines.map((l) => ctx.measureText(l.join(" ")).width), 1); h = lh * lines.length;
    draw = () => {
      ctx.font = font; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      if (it.box === true || it.box === "true" || it.box === 1) {
        ctx.fillStyle = "rgba(0,0,0,0.6)"; const pad = 22 * k;
        ctx.beginPath(); ctx.roundRect(-w / 2 - pad, -h / 2 - pad * 0.6, w + 2 * pad, h + pad, 18 * k); ctx.fill();
      }
      lines.forEach((l, j) => {
        const y = -h / 2 + lh * (j + 0.5);
        ctx.lineWidth = 12 * k; ctx.lineJoin = "round"; ctx.strokeStyle = "#000"; ctx.strokeText(l.join(" "), 0, y);
        ctx.fillStyle = it.color || "#FFFFFF"; ctx.fillText(l.join(" "), 0, y);
      });
    };
  }
  const cx = st.x / 100 * cw, cy = st.y / 100 * ch + st.dy;
  ctx.save();
  ctx.globalAlpha = clamp(st.alpha * (kind === "overlays" ? num(it.opacity, 1) : 1), 0, 1);
  ctx.translate(cx, cy); ctx.rotate(st.rot); ctx.scale(st.scale, st.scale);
  draw();
  ctx.restore();
  const c = Math.abs(Math.cos(st.rot)), sn = Math.abs(Math.sin(st.rot));   // cadre englobant du calque tourné
  const bw = (w * c + h * sn) * st.scale, bh = (w * sn + h * c) * st.scale;
  S.boxes.push({ kind, i, x: cx - bw / 2, y: cy - bh / 2, w: bw, h: bh });
}

// ---- sous-titres d'un script (aperçu ; les autres sources sont calculées à l'export)

function scriptCues(T) {
  const st = S.P.subtitles;
  const words = String(st.script || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length || T <= 0) return [];
  const weight = (w) => w.length + 1.5 + (/[.!?…]$/.test(w) ? 6 : /[,;:]$/.test(w) ? 3 : 0);
  const total = words.reduce((a, w) => a + weight(w), 0);
  let t = 0.05; const span = T - 0.1;
  const timed = words.map((w) => { const d = span * weight(w) / total; const o = [w, t, t + d]; t += d; return o; });
  const cues = []; let cur = [];
  const mw = Math.max(1, num(st.max_words, 3));
  for (const w of timed) {
    cur.push(w);
    const len = cur.reduce((a, x) => a + x[0].length + 1, 0);
    if (cur.length >= mw || len >= 22 || /[.!?…,]$/.test(w[0])) { cues.push(cur); cur = []; }
  }
  if (cur.length) cues.push(cur);
  return cues.map((c) => ({ start: c[0][1], end: c[c.length - 1][2], words: c }));
}

const backEase = (x, s = 2) => { x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2; };
const ANIM_DUR = { pop: 0.18, rebond: 0.36, fondu: 0.16, glissement: 0.22, "machine à écrire": 0.14, "mot par mot": 0.16 };

function captionState(kind, t, H) {   // même calcul que core/subanim.py
  const d = ANIM_DUR[kind]; if (!d || t >= d) return {};
  const x = Math.max(0, t / d);
  if (kind === "pop" || kind === "mot par mot") return { scale: 0.65 + 0.35 * backEase(x) };
  if (kind === "rebond") return { dy: -0.04 * H * Math.exp(-4 * x) * Math.cos(2.5 * Math.PI * x), alpha: Math.min(1, 3 * x) };
  if (kind === "fondu") return { alpha: x };
  if (kind === "glissement") return { dy: 0.05 * H * (1 - (1 - (1 - x) ** 3)), alpha: Math.min(1, 2 * x) };
  return {};
}

function drawSubtitles(t, T, cw, ch) {
  const st = S.P.subtitles;
  if (st.source !== "script") return;
  const cue = scriptCues(T).find((c) => t >= c.start && t < c.end);
  if (!cue) return;
  const style = { size: 72, color: "#FFFFFF", highlight_color: "#FFD60A", position: 0.72, uppercase: true, stroke_width: 6, highlight_mode: "couleur", ...(st.style || {}) };
  const kind = st.animation || "aucune", karaoke = !!st.karaoke;
  const k = Math.min(cw, ch) / 1080;
  let words = cue.words.map((w) => (style.uppercase ? w[0].toUpperCase() : w[0]));
  let j = cue.words.findIndex((w, n) => t >= w[1] && (n + 1 >= cue.words.length || t < cue.words[n + 1][1]));
  if (j < 0) j = 0;
  let size = num(style.size, 72) * k, anim = {}, visible = words.length, active = karaoke ? j : -1, wscale = 1;
  const tw = t - cue.words[j][1];
  if (kind === "mot par mot") { words = [words[j]]; size *= 1.6; anim = captionState(kind, tw, ch); active = karaoke ? 0 : -1; }
  else {
    if (j === 0 || !karaoke && kind !== "machine à écrire") anim = captionState(kind, karaoke || kind === "machine à écrire" ? tw : t - cue.start, ch);
    if (kind === "pop" && karaoke) wscale = 1 + 0.14 * backEase(clamp(tw / 0.18, 0, 1));
    if (kind === "machine à écrire") visible = j + 1;
  }
  const font = (s) => `800 ${s}px "${fontFamily(style.font)}"`;
  const lines = textLines(words, cw * 0.86, font(size));
  const lh = size * 1.12, blockH = lh * lines.length, cy = ch * num(style.position, 0.72);
  ctx.save();
  ctx.globalAlpha = anim.alpha ?? 1;
  ctx.translate(cw / 2, cy + (anim.dy || 0)); ctx.scale(anim.scale || 1, anim.scale || 1);
  ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  let idx = 0;
  lines.forEach((ln, li) => {
    const widths = ln.map((w, n) => { ctx.font = font(size * (idx + n === active ? wscale : 1)); return ctx.measureText(w).width; });
    ctx.font = font(size);
    const space = ctx.measureText(" ").width, lw = widths.reduce((a, b) => a + b, 0) + space * (ln.length - 1);
    let x = -lw / 2; const y = -blockH / 2 + lh * (li + 0.5);
    ln.forEach((w, n) => {
      const gi = idx + n;
      if (gi < visible) {
        ctx.font = font(size * (gi === active ? wscale : 1));
        ctx.textAlign = "left"; ctx.lineWidth = num(style.stroke_width, 6) * 2 * k; ctx.strokeStyle = style.stroke_color || "#000";
        ctx.strokeText(w, x, y);
        ctx.fillStyle = gi === active ? style.highlight_color : style.color; ctx.fillText(w, x, y);
      }
      x += widths[n] + space;
    });
    idx += ln.length;
  });
  ctx.restore();
}

function draw() {
  const [cw, ch] = canvasSize();
  if (c2d.width !== cw || c2d.height !== ch) { for (const c of [c2d, cgl, cly]) { c.width = cw; c.height = ch; } fitCanvas(); }
  ctx = ctxBase;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, cw, ch);
  S.boxes = [];
  const t = S.t, L = layoutClips(), active = new Set();
  const o = L.find((x) => t >= x.t0 && t < x.t1) || (L.length && t >= L[L.length - 1].t1 - 1e-3 ? L[L.length - 1] : null);
  if (o) drawClip(o, Math.min(t, o.t1 - 1e-3), cw, ch, active);
  ctx = ctxLayers;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cw, ch);
  S.P.overlays.forEach((it, i) => drawLayer("overlays", i, it, t, cw, ch, active));
  S.P.texts.forEach((it, i) => drawLayer("texts", i, it, t, cw, ch, active));
  drawSubtitles(t, totalDur(), cw, ch);
  for (const v of S.vids.values()) if (!active.has(v.el) && !v.el.paused) v.el.pause();
  drawLut();
  placeHandle();
}

// ---- filtre LUT : WebGL2 (texture 3D), même table que le rendu

const GL = { gl: null, prog: null, tex: null, lut: null, name: null };
function initGL() {
  const gl = cgl.getContext("webgl2", { premultipliedAlpha: false });
  if (!gl) return false;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const p = gl.createProgram();
  gl.attachShader(p, sh(gl.VERTEX_SHADER, `#version 300 es
    in vec2 a; out vec2 uv; void main(){ uv = vec2((a.x+1.)/2., (1.-a.y)/2.); gl_Position = vec4(a,0.,1.); }`));
  gl.attachShader(p, sh(gl.FRAGMENT_SHADER, `#version 300 es
    precision mediump float; precision mediump sampler3D;
    in vec2 uv; out vec4 o; uniform sampler2D img; uniform sampler3D lut; uniform float k, n;
    void main(){ vec4 c = texture(img, uv); vec3 g = texture(lut, c.rgb * ((n-1.)/n) + 0.5/n).rgb; o = vec4(mix(c.rgb, g, k), 1.); }`));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return false;
  gl.useProgram(p);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(p, "a"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  GL.tex = gl.createTexture(); GL.lut = gl.createTexture();
  gl.uniform1i(gl.getUniformLocation(p, "img"), 0); gl.uniform1i(gl.getUniformLocation(p, "lut"), 1);
  GL.gl = gl; GL.prog = p;
  return true;
}

async function loadLut(name) {
  if (name === GL.name) return;
  GL.name = name; S.lut = null;
  if (!name || name === "aucun") return;
  if (!GL.gl && !initGL()) { toast("Aperçu du filtre couleur impossible (WebGL2 absent) : il sera appliqué à l'export."); return; }
  const { size, data } = await api(`/api/editeur/lut?name=${enc(name)}`);
  const gl = GL.gl;
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, GL.lut);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);   // lignes de 33 × 3 octets : pas un multiple de 4
  gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGB8, size, size, size, 0, gl.RGB, gl.UNSIGNED_BYTE, new Uint8Array(data));
  for (const [p, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
    [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_3D, p, v);
  gl.uniform1f(gl.getUniformLocation(GL.prog, "n"), size);
  S.lut = name;
}

function drawLut() {
  const on = !!S.lut && S.P.lut.name === S.lut && num(S.P.lut.intensity, 1) > 0.001;
  $("#scene").classList.toggle("lut", on);
  if (!on) return;
  const gl = GL.gl;
  gl.viewport(0, 0, cgl.width, cgl.height);
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, GL.tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c2d);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.uniform1f(gl.getUniformLocation(GL.prog, "k"), clamp(num(S.P.lut.intensity, 1), 0, 1));
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
}

// ---- son du projet (musique, voix off)

const audios = { music: new Audio(), voiceover: new Audio() };
function syncAudio() {
  for (const key of ["music", "voiceover"]) {
    const a = audios[key], path = S.P[key].path, off = key === "voiceover" ? num(S.P.voiceover.offset) : 0;
    if (!path) { if (!a.paused) a.pause(); continue; }
    if (a.dataset.path !== path) { a.dataset.path = path; a.src = FILE(path); }
    a.volume = clamp(num(S.P[key].volume, key === "music" ? 0.18 : 1), 0, 1);
    const s = S.t - off;
    if (S.playing && s >= 0) { if (a.paused) { a.currentTime = s; a.play().catch(() => {}); } else if (Math.abs(a.currentTime - s) > 0.3) a.currentTime = s; }
    else if (!a.paused) a.pause();
  }
}

// ------------------------------------------------------------------------------------------------ lecture

function setTime(t) { S.t = clamp(t, 0, Math.max(0, totalDur())); }
function play(on) {
  S.playing = on ?? !S.playing;
  if (S.playing && S.t >= totalDur() - 0.05) S.t = 0;
  $("#lecture").textContent = S.playing ? "❚❚" : "▶";
  S.lastTs = performance.now();
}

function loop(ts) {
  if (S.playing) {
    S.t += (ts - S.lastTs) / 1000;
    if (S.t >= totalDur()) { S.t = totalDur(); play(false); }
  }
  S.lastTs = ts;
  syncAudio();
  draw();
  $("#temps").textContent = `${fmtT(S.t)} / ${fmtT(totalDur())}`;
  $("#tete").style.left = `${80 + S.t * S.pxs}px`;
  if (S.playing) followHead();
  requestAnimationFrame(loop);
}

function followHead() {
  const box = $("#pistes"), x = 80 + S.t * S.pxs;
  if (x > box.scrollLeft + box.clientWidth - 40 || x < box.scrollLeft + 80) box.scrollLeft = x - 120;
}

// ------------------------------------------------------------------------------------------------ timeline

function lanes(items) {   // calques qui se chevauchent : un couloir chacun
  const ends = [], out = [];
  items.forEach((it, i) => {
    const s = num(it.start), e = layerEnd(it);
    let lane = ends.findIndex((x) => x <= s + 1e-3);
    if (lane < 0) { lane = ends.length; ends.push(0); }
    ends[lane] = e; out[i] = lane;
  });
  return { out, n: Math.max(1, ends.length) };
}

function renderTimeline() {
  const T = totalDur(), pxs = S.pxs;
  $("#contenu").style.width = `${80 + (T + 10) * pxs}px`;
  const regle = $("#regle"); regle.innerHTML = "";
  const step = pxs > 120 ? 1 : pxs > 40 ? 2 : pxs > 20 ? 5 : 10;
  for (let s = 0; s <= T + 10; s += step) {
    const g = document.createElement("div"); g.className = "graduation"; g.style.left = `${s * pxs}px`; g.textContent = fmtT(s).replace(/\.\d+$/, "");
    regle.append(g);
  }
  const L = layoutClips(), pc = $("#p-clips"); pc.innerHTML = "";
  for (const o of L) {
    const b = bloc("clip", o.c.slot ? `＋ Plan ${o.c.slot.n || o.i + 1} · ${o.c.slot.label}` : o.c.path.split(/[\\/]/).pop(), o.t0, o.t1, "clips", o.i);
    if (o.c.slot) b.classList.add("emplacement");
    b.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/msv-media")) { e.preventDefault(); b.classList.add("cible-depot"); } });
    b.addEventListener("dragleave", () => b.classList.remove("cible-depot"));
    b.addEventListener("drop", (e) => {
      const m = S.medias.get(e.dataTransfer.getData("text/msv-media"));
      b.classList.remove("cible-depot");
      if (m) { e.preventDefault(); fillSlot(o.i, m); }
    });
    const strip = thumbs(o.c.path);
    if (strip) b.style.backgroundImage = `url(${strip})`;
    keyDiamonds(b, o.c.keyframes, "clips", o.i, o.t1 - o.t0);
    pc.append(b);
  }
  for (const kind of ["overlays", "texts"]) {
    const items = S.P[kind], { out, n } = lanes(items), box = $(`#p-${kind}`);
    box.innerHTML = ""; box.parentElement.style.height = `${n * 32 + 8}px`;   // 32 px par ligne (aperçu plus grand)
    items.forEach((it, i) => {
      const label = kind === "texts" ? `T  ${it.text}` : `▣  ${String(it.path).split(/[\\/]/).pop()}`;
      const b = bloc(kind, label, num(it.start), layerEnd(it), kind, i);
      b.style.top = `${4 + out[i] * 32}px`; b.style.bottom = "auto"; b.style.height = "28px";
      keyDiamonds(b, it.keyframes, kind, i, layerEnd(it) - num(it.start));
      box.append(b);
    });
  }
  const pa = $("#p-audio"); pa.innerHTML = "";
  for (const key of ["music", "voiceover"]) {
    const path = S.P[key].path; if (!path) continue;
    const off = key === "voiceover" ? num(S.P.voiceover.offset) : 0, d = Math.min(info(path).duration || T, Math.max(T, 1));
    const b = bloc("audio", `${key === "music" ? "♪ Musique" : "🎙 Voix off"} · ${path.split(/[\\/]/).pop()}`, off, off + d, null, -1);
    b.dataset.audio = key;
    if (key === "voiceover") { b.style.top = "21px"; b.style.height = "16px"; } else { b.style.height = "16px"; b.style.bottom = "auto"; }
    pa.append(b);
  }
}

function bloc(cls, label, t0, t1, kind, i) {
  const b = document.createElement("div");
  b.className = `bloc ${cls}${S.sel && S.sel.kind === kind && S.sel.i === i ? " choisi" : ""}`;
  b.style.left = `${t0 * S.pxs}px`; b.style.width = `${Math.max(6, (t1 - t0) * S.pxs)}px`;
  b.textContent = label; b.title = label;
  if (kind) {
    b.dataset.kind = kind; b.dataset.i = i;
    b.innerHTML += '<span class="bord g"></span><span class="bord d"></span>';
    b.addEventListener("pointerdown", (e) => startDrag(e, kind, i));
  }
  return b;
}

function keyDiamonds(b, text, kind, i, dur) {
  const it = S.P[kind][i];
  for (const p of kfParse(text, baseOf(kind, it))) {
    if (p.t < 0 || p.t > dur + 1e-3) continue;
    const d = document.createElement("span"); d.className = "losange"; d.style.left = `${p.t * S.pxs}px`;
    d.title = `Image clé à ${fmtT(p.t)}`;
    d.addEventListener("pointerdown", (e) => {
      e.stopPropagation(); select(kind, i);
      setTime((kind === "clips" ? layoutClips()[i].t0 : num(it.start)) + p.t);
    });
    b.append(d);
  }
}

let drag = null;
function startDrag(e, kind, i) {
  if (e.button !== 0 || e.target.closest(".losange")) return;
  e.preventDefault();
  select(kind, i);
  const mode = e.target.classList.contains("g") ? "g" : e.target.classList.contains("d") ? "d" : "move";
  drag = { kind, i, mode, x0: e.clientX, before: JSON.stringify(S.P), orig: clone(S.P[kind][i]), moved: false };
  e.target.closest(".bloc").setPointerCapture(e.pointerId);
}

window.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dt = (e.clientX - drag.x0) / S.pxs;
  if (Math.abs(e.clientX - drag.x0) > 2) drag.moved = true;
  if (!drag.moved) return;
  const it = S.P[drag.kind][drag.i], o = drag.orig;
  if (drag.kind === "clips") {
    const img = isImage(it.path), sp = Math.max(0.1, num(it.speed, 1));
    if (drag.mode === "move") { showInsertion(e.clientX); return; }
    if (img) {
      const d0 = num(o.duration, num(S.P.image_duration, 3));
      it.duration = round(Math.max(0.2, drag.mode === "d" ? d0 + dt : d0 - dt));
    } else if (drag.mode === "g") {
      const endS = o.end == null || o.end === "" ? info(it.path).duration : num(o.end);
      it.start = round(clamp(num(o.start) + dt * sp, 0, endS - 0.1), 3);
    } else {
      const endS = o.end == null || o.end === "" ? info(it.path).duration : num(o.end);
      it.end = round(clamp(endS + dt * sp, num(o.start) + 0.1, info(it.path).duration || 1e9), 3);
    }
  } else {
    const s = num(o.start), en = o.end == null || o.end === "" ? totalDur() : num(o.end);
    if (drag.mode === "move") { const d = Math.max(-s, dt); it.start = round(s + d); it.end = round(en + d); }
    else if (drag.mode === "g") it.start = round(clamp(s + dt, 0, en - 0.1));
    else it.end = round(Math.max(s + 0.1, en + dt));
  }
  renderTimeline();
});

window.addEventListener("pointerup", (e) => {
  if (!drag) return;
  const d = drag; drag = null;
  $("#insertion").hidden = true;
  if (!d.moved) return;
  if (d.kind === "clips" && d.mode === "move") {
    const to = dropIndex(e.clientX);
    if (to !== d.i && to !== d.i + 1) {
      S.undo.push(d.before); S.redo = [];
      const [c] = S.P.clips.splice(d.i, 1);
      const at = to > d.i ? to - 1 : to;
      S.P.clips.splice(at, 0, c);
      S.sel = { kind: "clips", i: at };
      changed();
    }
    return;
  }
  S.undo.push(d.before); S.redo = []; changed();
});

function timeAt(clientX) { const r = $("#contenu").getBoundingClientRect(); return (clientX - r.left - 80) / S.pxs; }
function dropIndex(clientX) {
  const t = timeAt(clientX), L = layoutClips();
  for (const o of L) if (t < (o.t0 + o.t1) / 2) return o.i;
  return L.length;
}
function showInsertion(clientX) {
  const L = layoutClips(), to = dropIndex(clientX);
  const t = to < L.length ? L[to].t0 : (L.length ? L[L.length - 1].t1 : 0);
  const ins = $("#insertion"), pc = $("#p-clips").parentElement;
  ins.hidden = false; ins.style.left = `${80 + t * S.pxs - 1}px`; ins.style.top = `${pc.offsetTop}px`; ins.style.height = `${pc.offsetHeight}px`;
}

function scrubAt(e) { setTime(timeAt(e.clientX)); }
$("#regle").addEventListener("pointerdown", (e) => {
  scrubAt(e); const mv = (ev) => scrubAt(ev);
  window.addEventListener("pointermove", mv);
  window.addEventListener("pointerup", () => window.removeEventListener("pointermove", mv), { once: true });
});
for (const id of ["#p-clips", "#p-overlays", "#p-texts", "#p-audio"]) {
  $(id).addEventListener("pointerdown", (e) => { if (e.target === e.currentTarget) { scrubAt(e); select(null); } });
}

// ------------------------------------------------------------------------------------------------ gestes dans l'aperçu

function canvasPoint(e) { const r = c2d.getBoundingClientRect(); return [(e.clientX - r.left) * c2d.width / r.width, (e.clientY - r.top) * c2d.height / r.height]; }

function placeHandle() {
  const h = $("#poignee"), it = selItem();
  const box = it && S.sel.kind !== "clips" ? S.boxes.find((b) => b.kind === S.sel.kind && b.i === S.sel.i) : null;
  if (!box) { h.hidden = true; return; }
  const cv = $("#scene").classList.contains("lut") ? cgl : c2d;
  const r = cv.getBoundingClientRect(), sr = $("#scene").getBoundingClientRect(), k = r.width / c2d.width;
  h.hidden = false;
  Object.assign(h.style, { left: `${r.left - sr.left + box.x * k}px`, top: `${r.top - sr.top + box.y * k}px`, width: `${box.w * k}px`, height: `${box.h * k}px` });
}

// ---- suivi d'objet : cadre tracé sur l'aperçu, suivi par MSV (core/tracking.py), images clés du calque
function videoMapping(c, cw, ch) {   // aperçu <-> image source (fractions), mêmes calculs que drawMedia
  const m = info(c.path), sw = m.width || 1, sh = m.height || 1, crop = c.crop;
  let sx = 0, sy = 0, w = sw, h = sh;
  if (crop) { sx = sw * num(crop.left) / 100; sy = sh * num(crop.top) / 100; w = sw * (1 - (num(crop.left) + num(crop.right)) / 100); h = sh * (1 - (num(crop.top) + num(crop.bottom)) / 100); }
  const fit = c.fit || S.P.fit, cover = fit === "rogner" || fit === S.cfg.face;
  const k = cover ? Math.max(cw / w, ch / h) : Math.min(cw / w, ch / h);
  const dx0 = cover ? (cw - w * k) * num(c.crop_x, 0.5) : (cw - w * k) / 2, dy0 = (ch - h * k) / 2;
  return { toSrc: (x, y) => [(sx + (x - dx0) / k) / sw, (sy + (y - dy0) / k) / sh],
           toCanvas: (u, v) => [dx0 + (u * sw - sx) * k, dy0 + (v * sh - sy) * k], k, sw, sh };
}
function clipTimeAt(c, src) {   // inverse de clipSrcAt : temps depuis le début du clip pour un moment de la source
  let acc = 0;
  for (const [a, b, sp] of speedPieces(c)) {
    if (src <= b) return acc + Math.max(0, src - a) / sp;
    acc += (b - a) / sp;
  }
  return acc;
}
function startTrack(kind, i) {
  const it = S.P[kind][i], o = clipAt(S.t) || layoutClips().find((x) => S.t >= x.t0 && S.t < x.t1);
  if (!inRange(kind, i)) { toast("Place d'abord le curseur sur le calque, là où l'objet est visible."); return; }
  if (!o || info(o.c.path).kind !== "video") { toast("Il faut une vidéo sous le curseur pour suivre un objet."); return; }
  const fit = o.c.fit || S.P.fit;
  if (fit === S.cfg.face || fit === "cadre") { toast(`Suivi d'objet impossible avec le cadrage « ${fit} » : choisis « rogner », « flou » ou « bandes » pour ce clip.`); return; }
  if (kfParse(o.c.keyframes).length) { toast("Ce clip a des images clés de zoom : retire-les pour suivre un objet."); return; }
  S.track = { kind, i, o };
  $("#scene").classList.add("suivi");
  toast("Trace un rectangle autour de l'objet à suivre (Échap pour annuler).");
}
function stopTrack() { S.track = null; $("#scene").classList.remove("suivi"); $("#cadre-suivi").hidden = true; }
document.addEventListener("keydown", (e) => { if (S.track && e.key === "Escape") { e.preventDefault(); stopTrack(); toast("Suivi annulé."); } }, true);
function trackPointer(e) {
  const box = $("#cadre-suivi"), sc = $("#scene"), [x0, y0] = canvasPoint(e);
  const cv = sc.classList.contains("lut") ? cgl : c2d, r = cv.getBoundingClientRect(), sr = sc.getBoundingClientRect(), k = r.width / c2d.width;
  let x1 = x0, y1 = y0;
  const draw = () => Object.assign(box.style, { left: `${r.left - sr.left + Math.min(x0, x1) * k}px`, top: `${r.top - sr.top + Math.min(y0, y1) * k}px`,
    width: `${Math.abs(x1 - x0) * k}px`, height: `${Math.abs(y1 - y0) * k}px` });
  box.hidden = false; draw();
  sc.setPointerCapture(e.pointerId);
  const move = (ev) => { [x1, y1] = canvasPoint(ev); draw(); };
  const up = () => {
    sc.removeEventListener("pointermove", move); sc.removeEventListener("pointerup", up);
    if (Math.abs(x1 - x0) < 6 || Math.abs(y1 - y0) < 6) { box.hidden = true; toast("Rectangle trop petit : trace-le autour de l'objet."); return; }
    runTrack([Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)]);
  };
  sc.addEventListener("pointermove", move); sc.addEventListener("pointerup", up);
}
async function runTrack(rect) {
  const { kind, i, o } = S.track, it = S.P[kind][i], c = o.c, cw = c2d.width, ch = c2d.height;
  stopTrack();
  const map = videoMapping(c, cw, ch);
  const [u0, v0] = map.toSrc(rect[0], rect[1]), [u1, v1] = map.toSrc(rect[0] + rect[2], rect[1] + rect[3]);
  const box = [clamp(u0, 0, 1), clamp(v0, 0, 1), clamp(u1, 0, 1) - clamp(u0, 0, 1), clamp(v1, 0, 1) - clamp(v0, 0, 1)];
  const tEnd = Math.min(layerEnd(it), o.t1) - 0.02;
  const t0 = clipSrcAt(c, S.t - o.t0).src, t1 = clipSrcAt(c, tEnd - o.t0).src;
  toast("Suivi de l'objet en cours…");
  let res;
  try { res = await api("/api/editeur/suivi", { method: "POST", body: { path: c.path, t0, t1, box } }); }
  catch (err) { toast("Suivi impossible : " + err.message); return; }
  const base = baseOf(kind, it), local = S.t - num(it.start);
  const kpts = kfParse(it.keyframes, base), now = kpts.length ? kfState(kpts, local) : { x: base.x, y: base.y, scale: 1, opacity: 1, rotation: base.rotation };
  const first = res.points[0], [fx, fy] = map.toCanvas(first.x, first.y);
  const dx = now.x - fx / cw * 100, dy = now.y - fy / ch * 100;   // le calque garde son écart avec l'objet
  const pts = [];
  let lastT = -1;
  res.points.forEach((p, n) => {
    const T = o.t0 + clipTimeAt(c, p.t), tl = round(T - num(it.start), 2);
    if (tl - lastT < 0.2 && n !== res.points.length - 1) return;   // 5 images clés par seconde suffisent
    const [px, py] = map.toCanvas(p.x, p.y);
    pts.push({ t: tl, x: clamp(px / cw * 100 + dx, -50, 150), y: clamp(py / ch * 100 + dy, -50, 150), scale: now.scale, opacity: now.opacity, rotation: now.rotation });
    lastT = tl;
  });
  const before = kpts.filter((p) => p.t < pts[0].t - 1e-3);   // images clés d'avant le suivi gardées
  change(() => { it.keyframes = kfFormat([...before, ...pts], false); });
  toast(`Objet suivi : ${pts.length} images clés` + (res.lost ? ` (perdu ${res.lost} images, position gardée)` : "") + ".");
}

let gesture = null;
$("#scene").addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;              // clic droit : menu (voir bind)
  if (S.track) { e.preventDefault(); trackPointer(e); return; }   // suivi d'objet : tracer le cadre
  const [x, y] = canvasPoint(e);
  const hit = [...S.boxes].reverse().find((b) => x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h);
  if (hit) select(hit.kind, hit.i);
  else if (!S.sel || S.sel.kind !== "clips") {
    const o = layoutClips().find((c) => S.t >= c.t0 && S.t < c.t1);
    select(o ? "clips" : null, o ? o.i : 0);
  }
  if (!S.sel) return;
  const it = selItem(), kind = S.sel.kind, u = localTime(kind, S.sel.i);
  const pts = kfParse(it.keyframes, baseOf(kind, it));
  const cur = pts.length ? kfState(pts, u) : baseOf(kind, it);
  gesture = { x0: x, y0: y, cur, before: JSON.stringify(S.P), moved: false };
  $("#scene").setPointerCapture(e.pointerId);
});

$("#scene").addEventListener("pointermove", (e) => {
  if (!gesture || !S.sel) return;
  const [x, y] = canvasPoint(e), it = selItem(), kind = S.sel.kind;
  const dx = (x - gesture.x0) / c2d.width * 100, dy = (y - gesture.y0) / c2d.height * 100;
  if (Math.abs(dx) + Math.abs(dy) < 0.3) return;
  gesture.moved = true;
  if (kind === "clips") {   // déplace le point visé (sens inverse : on « tire » l'image)
    const z = Math.max(1, gesture.cur.scale || 1);
    kfUpsert(it, {}, localTime(kind, S.sel.i), { x: round(clamp(gesture.cur.x - dx / z, 0, 100), 1), y: round(clamp(gesture.cur.y - dy / z, 0, 100), 1), scale: z }, true);
  } else if (kfParse(it.keyframes).length) {
    kfUpsert(it, baseOf(kind, it), localTime(kind, S.sel.i), { x: round(gesture.cur.x + dx, 1), y: round(gesture.cur.y + dy, 1) }, false);
  } else { it.x = round(clamp(gesture.cur.x + dx, 0, 100), 1); it.y = round(clamp(gesture.cur.y + dy, 0, 100), 1); }
  renderInspector();
});

$("#scene").addEventListener("pointerup", () => {
  if (gesture && gesture.moved) { S.undo.push(gesture.before); S.redo = []; changed(); }
  gesture = null;
});

$("#scene").addEventListener("wheel", (e) => {
  const it = selItem(); if (!it) return;
  e.preventDefault();
  const f = Math.pow(1.0015, -e.deltaY), kind = S.sel.kind, u = localTime(kind, S.sel.i);
  if (e.shiftKey && kind !== "clips") {     // Maj + molette : rotation (pas de 5°)
    const step = (e.deltaY || e.deltaX) > 0 ? 5 : -5;
    if (kfParse(it.keyframes).length && !inRange(kind, S.sel.i)) { toast("Place le curseur sur le calque pour le tourner."); return; }
    snapshot(); rotateBy(kind, S.sel.i, step, false); return;
  }
  snapshot();
  if (kind === "clips") {
    const pts = kfParse(it.keyframes), cur = pts.length ? kfState(pts, u) : { x: 50, y: 50, scale: 1 };
    kfUpsert(it, {}, u, { x: cur.x, y: cur.y, scale: round(clamp(cur.scale * f, 1, 8)) }, true);
  } else if (kfParse(it.keyframes).length) {
    const cur = kfState(kfParse(it.keyframes, baseOf(kind, it)), u);
    kfUpsert(it, baseOf(kind, it), u, { scale: round(clamp(cur.scale * f, 0.05, 10)) }, false);
  } else if (kind === "overlays") it.width = round(clamp(num(it.width, 30) * f, 2, 100), 1);
  else it.size = round(clamp(num(it.size, 80) * f, 16, 300));
  changed();
}, { passive: false });

// ------------------------------------------------------------------------------------------------ inspecteur

function field(label, input) {
  const row = document.createElement("label"); row.className = "ligne-form";
  const s = document.createElement("span"); s.textContent = label;
  row.append(s, input); return row;
}
function inputNum(val, step, onset, min, max) {
  const el = document.createElement("input"); el.type = "number"; el.step = step; el.value = val ?? "";
  if (min != null) el.min = min; if (max != null) el.max = max;
  el.onchange = () => change(() => onset(el.value === "" ? null : num(el.value))); return el;
}
function inputText(val, onset, area) {
  const el = document.createElement(area ? "textarea" : "input"); if (!area) el.type = "text"; el.value = val ?? "";
  el.onchange = () => change(() => onset(el.value)); return el;
}
function inputSelect(val, choices, onset) {
  const el = document.createElement("select");
  for (const c of choices) { const o = document.createElement("option"); [o.value, o.textContent] = Array.isArray(c) ? c : [c, c]; el.append(o); }
  el.value = val ?? ""; el.onchange = () => change(() => onset(el.value)); return el;
}
function inputRange(val, min, max, step, onset) {
  const el = document.createElement("input"); el.type = "range"; el.min = min; el.max = max; el.step = step; el.value = val;
  el.onpointerdown = () => snapshot(); el.oninput = () => { onset(num(el.value)); S.dirty = true; renderTimeline(); };
  el.onchange = () => changed(); return el;
}
function inputCheck(val, onset) { const el = document.createElement("input"); el.type = "checkbox"; el.checked = !!val; el.onchange = () => change(() => onset(el.checked)); return el; }
function button(label, fn, cls) { const b = document.createElement("button"); b.textContent = label; b.onclick = fn; if (cls) b.className = cls; return b; }
function h3(t) { const h = document.createElement("h3"); h.textContent = t; return h; }

function keyframesBlock(kind, i, it) {
  const box = document.createElement("div"); box.className = "cles";
  const isClip = kind === "clips", pts = kfParse(it.keyframes, baseOf(kind, it)), u = localTime(kind, i);
  box.append(h3("Images clés"));
  if (!pts.length) {
    const p = document.createElement("p"); p.className = "note";
    p.textContent = isClip ? "Molette sur l'aperçu : zoom ; glisser : point visé. Chaque geste pose une image clé au curseur."
      : "Pose une image clé (◆), déplace le curseur, puis bouge le calque dans l'aperçu : il ira d'une position à l'autre.";
    box.append(p);
  }
  pts.forEach((p, n) => {
    const row = document.createElement("div"); row.className = "cle" + (Math.abs(p.t - u) < SNAP * 2 ? " ici" : "");
    row.innerHTML = `<b>◆</b><span>${fmtT(p.t)}</span><span class="note">${isClip ? `×${round(p.scale)} @${round(p.x, 0)},${round(p.y, 0)}`
      : `@${round(p.x, 0)},${round(p.y, 0)} ×${round(p.scale)} ${Math.round(p.opacity * 100)}% ${round(p.rotation, 0)}°`}</span><span class="espace"></span>`;
    row.append(button("aller", () => setTime((isClip ? layoutClips()[i].t0 : num(it.start)) + p.t), "petit"),
      button("✕", () => change(() => { pts.splice(n, 1); it.keyframes = kfFormat(pts, isClip); }), "petit"));
    box.append(row);
  });
  const here = pts.length ? kfState(pts, u) : baseOf(kind, it);
  if (!isClip && pts.length) {
    box.append(field("Opacité", inputRange(here.opacity, 0, 1, 0.05, (v) => kfUpsert(it, baseOf(kind, it), u, { opacity: v }, false))));
    box.append(field("Angle", inputRange(here.rotation, -180, 180, 1, (v) => kfUpsert(it, baseOf(kind, it), u, { rotation: v }, false))));
  }
  if (isClip) box.append(field("Zoom", inputRange(here.scale || 1, 1, 4, 0.01, (v) => kfUpsert(it, {}, u, { x: here.x, y: here.y, scale: v }, true))));
  const bs = document.createElement("div"); bs.className = "boutons";
  bs.append(button("◆ Image clé ici", () => addKeyHere()));
  if (pts.length) bs.append(button("Tout effacer", () => change(() => { it.keyframes = ""; })));
  box.append(bs);
  return box;
}

function renderInspector() {
  const f = $("#formulaire"); f.innerHTML = "";
  const it = selItem(), P = S.P;
  if (!it) {
    $("#titre-inspecteur").textContent = "Projet";
    f.append(field("Cadrage", inputSelect(P.fit, S.cfg.fits, (v) => { P.fit = v; })));
    f.append(field("Durée photo (s)", inputNum(P.image_duration, 0.5, (v) => { P.image_duration = v ?? 3; }, 0.5, 60)));
    f.append(field("Transition", inputSelect(P.transition.type, S.cfg.transitions, (v) => { P.transition.type = v; })));
    f.append(h3("Filtre couleur"));
    f.append(field("LUT", inputSelect(P.lut.name, S.cfg.luts, (v) => { P.lut.name = v; loadLut(v); })));
    f.append(field("Intensité", inputRange(num(P.lut.intensity, 1), 0, 1, 0.05, (v) => { P.lut.intensity = v; })));
    f.append(h3("Sous-titres"));
    f.append(field("Source", inputSelect(P.subtitles.source, [["aucun", "aucun"], ["script", "script (texte lu)"], ["whisper", "automatiques (Whisper)"], ["vidéo", "pistes de la vidéo"]], (v) => { P.subtitles.source = v; })));
    if (P.subtitles.source === "script") f.append(field("Script", inputText(P.subtitles.script, (v) => { P.subtitles.script = v; }, true)));
    f.append(field("Animation", inputSelect(P.subtitles.animation || "aucune", S.cfg.sub_animations, (v) => { P.subtitles.animation = v; })));
    f.append(field("Karaoké", inputCheck(P.subtitles.karaoke, (v) => { P.subtitles.karaoke = v; })));
    f.append(field("Mots / ligne", inputNum(P.subtitles.max_words, 1, (v) => { P.subtitles.max_words = v ?? 3; }, 1, 10)));
    f.append(field("Position", inputRange(num((P.subtitles.style || {}).position, 0.72), 0.05, 0.95, 0.01, (v) => { P.subtitles.style = { ...(P.subtitles.style || {}), position: v }; })));
    if (P.subtitles.source !== "script" && P.subtitles.source !== "aucun") {
      const n = document.createElement("p"); n.className = "note"; n.textContent = "Ces sous-titres sont calculés à l'export (pas d'aperçu)."; f.append(n);
    }
    f.append(h3("Audio"));
    const audiosList = [["", "aucun"], ...[...S.medias.values()].filter((m) => m.kind === "audio").map((m) => [m.path, m.name])];
    f.append(field("Musique", inputSelect(P.music.path, audiosList, (v) => { P.music.path = v; })));
    f.append(field("Volume musique", inputRange(num(P.music.volume, 0.18), 0, 1, 0.01, (v) => { P.music.volume = v; })));
    f.append(field("Voix off", inputSelect(P.voiceover.path, audiosList, (v) => { P.voiceover.path = v; })));
    return;
  }
  const kind = S.sel.kind, i = S.sel.i;
  if (kind === "clips") {
    const img = isImage(it.path);
    $("#titre-inspecteur").textContent = img ? "Photo" : "Clip vidéo";
    f.append(field("Fichier", Object.assign(document.createElement("span"), { textContent: it.path.split(/[\\/]/).pop() })));
    if (img) f.append(field("Durée (s)", inputNum(it.duration ?? P.image_duration, 0.1, (v) => { it.duration = v; }, 0.2)));
    else {
      f.append(field("Début (s)", inputNum(it.start ?? 0, 0.01, (v) => { it.start = v ?? 0; }, 0)));
      f.append(field("Fin (s)", inputNum(it.end, 0.01, (v) => { it.end = v; }, 0)));
      f.append(field("Vitesse", inputNum(it.speed ?? 1, 0.05, (v) => { it.speed = clamp(v ?? 1, 0.1, 4); }, 0.1, 4)));
      const names = Object.keys(S.cfg.speed_curves || {}), cur = it.speed_curve || "aucune", custom = !names.includes(cur);
      f.append(field("Courbe de vitesse", inputSelect(custom ? "perso" : cur, [...names.map((x) => [x, x]), ["perso", "personnalisée…"]], (v) => {
        if (v === "perso") it.speed_curve = custom ? cur : "0:1 ; 0.5:0.3 ; 1:1";
        else if (v === "aucune") delete it.speed_curve; else it.speed_curve = v;
      })));
      if (custom) {
        const inp = Object.assign(document.createElement("input"), { type: "text", value: cur, spellcheck: false,
          title: "Position dans le clip (0 à 1) : vitesse. Exemple : 0:1 ; 0.5:0.3 ; 1:1" });
        inp.addEventListener("change", () => change(() => { it.speed_curve = inp.value.trim() || "aucune"; if (it.speed_curve === "aucune") delete it.speed_curve; }));
        f.append(field("Points (0 à 1 : vitesse)", inp));
      }
      f.append(field("Volume", inputRange(num(it.volume, 1), 0, 2, 0.05, (v) => { it.volume = v; })));
    }
    f.append(field("Cadrage", inputSelect(it.fit || "", [["", "celui du projet"], ...S.cfg.fits.map((x) => [x, x])], (v) => { if (v) it.fit = v; else delete it.fit; })));
    f.append(field("Position (rogner)", inputRange(num(it.crop_x, 0.5), 0, 1, 0.01, (v) => { it.crop_x = v; })));
    f.append(keyframesBlock(kind, i, it));
    const bs = document.createElement("div"); bs.className = "boutons";
    bs.append(button("✂ Couper ici", splitClip), button("Dupliquer", () => change(() => { S.P.clips.splice(i + 1, 0, clone(it)); })),
      button("Supprimer", () => change(() => { S.P.clips.splice(i, 1); S.sel = null; })));
    f.append(bs);
    return;
  }
  $("#titre-inspecteur").textContent = kind === "texts" ? "Texte" : "Calque";
  if (kind === "texts") {
    f.append(field("Texte", inputText(it.text, (v) => { it.text = v; }, true)));
    f.append(field("Taille", inputNum(it.size ?? 80, 1, (v) => { it.size = v ?? 80; }, 16, 300)));
    const col = document.createElement("input"); col.type = "color"; col.value = it.color || "#FFFFFF";
    col.onchange = () => change(() => { it.color = col.value.toUpperCase(); });
    f.append(field("Couleur", col));
    f.append(field("Bandeau", inputCheck(it.box === true || it.box === "true", (v) => { it.box = v; })));
  } else {
    f.append(field("Fichier", Object.assign(document.createElement("span"), { textContent: String(it.path).split(/[\\/]/).pop() })));
    f.append(field("Largeur (%)", inputNum(it.width ?? 30, 1, (v) => { it.width = v ?? 30; }, 2, 100)));
    f.append(field("Opacité", inputRange(num(it.opacity, 1), 0.05, 1, 0.05, (v) => { it.opacity = v; })));
  }
  f.append(field("Début (s)", inputNum(it.start ?? 0, 0.01, (v) => { it.start = v ?? 0; }, 0)));
  f.append(field("Fin (s)", inputNum(it.end, 0.01, (v) => { it.end = v; }, 0)));
  if (!kfParse(it.keyframes).length) {
    f.append(field("Angle (°)", inputRange(num(it.rotation, 0), -180, 180, 1, (v) => { it.rotation = v; })));
    f.append(field("X (%)", inputNum(it.x ?? 50, 0.5, (v) => { it.x = v ?? 50; }, 0, 100)));
    f.append(field("Y (%)", inputNum(it.y ?? 50, 0.5, (v) => { it.y = v ?? 50; }, 0, 100)));
    f.append(field("Animation", inputSelect(it.animation || (kind === "texts" ? "montée" : "fondu"), S.cfg.layer_animations, (v) => { it.animation = v; })));
  }
  const suivre = Object.assign(document.createElement("button"), { textContent: "🎯 Suivre un objet de la vidéo",
    title: "Le calque suit un objet qui bouge : place le curseur, clique, puis trace un rectangle autour de l'objet" });
  suivre.onclick = () => startTrack(kind, i);
  f.append(field("Suivi", suivre));
  f.append(keyframesBlock(kind, i, it));
  f.append(button("Supprimer", () => change(() => { S.P[kind].splice(i, 1); S.sel = null; })));
}

function addKeyHere() {
  const it = selItem();
  if (!it) { toast("Choisis d'abord un clip, un calque ou un texte."); return; }
  const kind = S.sel.kind, u = localTime(kind, S.sel.i);
  if (!inRange(kind, S.sel.i)) { toast("Place d'abord le curseur sur l'élément choisi."); return; }
  const pts = kfParse(it.keyframes, baseOf(kind, it));
  const cur = pts.length ? kfState(pts, u) : baseOf(kind, it);
  change(() => kfUpsert(it, baseOf(kind, it), u, cur, kind === "clips"));
  toast(`Image clé à ${fmtT(u)}`);
}

function splitClip() {
  const L = layoutClips();
  const o = S.sel && S.sel.kind === "clips" && S.t > L[S.sel.i].t0 && S.t < L[S.sel.i].t1 ? L[S.sel.i] : L.find((x) => S.t > x.t0 + 0.05 && S.t < x.t1 - 0.05);
  if (!o) { toast("Place le curseur au milieu d'un clip pour le couper."); return; }
  change(() => {
    const c = o.c, u = S.t - o.t0, a = clone(c), b = clone(c);
    if (isImage(c.path)) { a.duration = round(u); b.duration = round(clipDur(c) - u); }
    else {
      const s = clipSrcAt(c, u).src; a.end = round(s, 3); b.start = round(s, 3);
      if (curvePoints(c.speed_curve).length) { delete a.speed_curve; delete b.speed_curve; toast("Courbe de vitesse retirée des deux morceaux : choisis-la de nouveau si besoin."); }
    }
    const pts = kfParse(c.keyframes);
    if (pts.length) {   // les images clés suivent leur moitié
      a.keyframes = kfFormat(pts.filter((p) => p.t <= u + 1e-3), true);
      b.keyframes = kfFormat(pts.filter((p) => p.t >= u - 1e-3).map((p) => ({ ...p, t: p.t - u })), true);
    }
    S.P.clips.splice(o.i, 1, a, b);
    S.sel = { kind: "clips", i: o.i + 1 };
  });
}

// ------------------------------------------------------------------------------------------------ projet, export

function renderAll() { renderTimeline(); renderInspector(); $("#nom").value = S.P.name || ""; $("#format").value = S.P.format; }

async function openProject(p) {
  S.P = { ...newProject(), ...p };
  await Promise.all([...S.P.clips.map((c) => ensureInfo(c.path)), ...S.P.overlays.map((o) => ensureInfo(o.path)),
    ensureInfo(S.P.music.path), ensureInfo(S.P.voiceover.path)]);
  S.sel = null; S.undo = []; S.redo = []; S.t = 0;
  loadLut(S.P.lut && S.P.lut.name);
  renderAll();
}

function openThumbnail() {   // page /miniature avec l'image sous le curseur (moment exact dans la vidéo source)
  const o = clipAt(S.t) || layoutClips().find((x) => S.t >= x.t0 && S.t <= x.t1);
  const fmt = ["16:9", "9:16", "1:1"].includes(S.P.format) ? S.P.format : "16:9";
  let url = `/miniature?format=${enc(fmt)}`;
  if (o) url += `&src=${enc(o.c.path)}&t=${round(clipSrcAt(o.c, S.t - o.t0).src, 2)}`;
  if (new URLSearchParams(location.search).get("bureau")) {   // application de bureau : même fenêtre, retour au même instant
    try { localStorage.setItem("msv-editeur", JSON.stringify(S.P)); } catch (e) { /* stockage indisponible */ }   // rouvert au retour
    location.href = url + `&retour=${enc(`/editeur?bureau=1&t=${round(S.t, 2)}`)}`;
  } else window.open(url, "_blank", "noopener");
}

async function save() {
  try { const r = await api("/api/editeur/projet", { method: "POST", body: S.P }); S.dirty = false; toast(`Projet enregistré : ${r.name}.json`); }
  catch (e) { toast("Enregistrement impossible : " + e.message); }
}

async function showOpen() {
  const box = $("#liste-projets"); box.innerHTML = "<p class='vide'>Chargement…</p>";
  $("#dlg-ouvrir").showModal();
  const list = await api("/api/editeur/projets");
  box.innerHTML = list.length ? "" : "<p class='vide'>Aucun projet enregistré.</p>";
  for (const p of list) {
    box.append(button(`${p.name}  ·  ${new Date(p.modified * 1000).toLocaleString()}`, async () => {
      $("#dlg-ouvrir").close();
      try { await openProject(await api(`/api/editeur/projet?nom=${enc(p.name)}`)); toast("Projet ouvert : " + p.name); }
      catch (e) { toast("Ouverture impossible : " + e.message); }
    }));
  }
}

function showHelp() {
  let off = false;
  try { off = localStorage.getItem("msv-editeur-aide") === "non"; } catch (e) { off = false; }
  $("#aide-masquer").checked = off;
  $("#dlg-aide").showModal();
}

// ---- visite guidée : une étape à la fois ; la zone concernée est éclairée, une bulle l'explique, « OK » passe à la suivante
const TOUR = [
  { sel: ".medias .titre-panneau .bouton", title: "Importer tes fichiers",
    text: "Clique sur <b>Importer</b> pour choisir tes vidéos, photos et musiques. Tu peux aussi les glisser depuis l'Explorateur Windows directement dans la liste des médias. Tes fichiers restent sur ton ordinateur." },
  { sel: "#liste-medias", title: "Les mettre dans le montage",
    text: "<b>Double-clique</b> sur un média : une vidéo ou une photo va au bout de la piste Vidéo, un son devient la musique, un sticker se pose en calque. <b>Clic droit</b> sur un média pour choisir toi-même." },
  { sel: ".piste[data-piste='clips']", title: "Arranger les clips", side: ["dessus", "dessous"],
    text: "Glisse un clip pour changer l'ordre. Tire un de ses bords pour le raccourcir. Pour le couper : clique sur la règle pour placer le curseur orange, puis appuie sur <kbd>S</kbd>." },
  { sel: "#ajouter", title: "Ajouter textes, emojis et stickers", side: ["dessus", "gauche"],
    text: "<b>＋ Ajouter</b> pose au curseur un texte, un emoji, un sticker ou l'animation <b>Like · Abonne-toi · Commente · Partage</b>. Tu peux aussi <b>créer ton propre sticker</b> à partir d'un emoji ou d'une photo." },
  { sel: "#scene", title: "Placer un calque dans l'image", side: ["droite", "gauche", "dedans"],
    text: "Dans l'aperçu, <b>glisse</b> un calque pour le déplacer. <b>Molette</b> : plus grand ou plus petit. <kbd>Maj</kbd> + <b>molette</b> : le faire tourner. <b>Clic droit</b> dessus : tourner de 90°, dupliquer, premier plan, supprimer…" },
  { sel: ".piste[data-piste='overlays']", title: "Animer avec les images clés", side: ["dessus", "dessous"],
    text: "Choisis un calque, place le curseur sur lui et appuie sur <kbd>K</kbd> : c'est une image clé (un losange jaune). Avance le curseur puis déplace, agrandis ou tourne le calque : une deuxième image clé se crée et le calque passe en douceur de l'une à l'autre." },
  { sel: ".inspecteur", title: "Régler le projet", side: ["gauche", "dessous"],
    text: "Ce panneau montre les réglages de ce qui est choisi. Clique dans le vide de l'aperçu pour voir ceux du <b>projet</b> : filtre couleur, sous-titres animés, musique, format, recadrage sur le visage." },
  { sel: "#exporter", title: "Enregistrer et exporter", side: ["dessous", "gauche"],
    text: "<b>Enregistrer</b> garde ton projet pour plus tard. <b>Exporter</b> calcule la vidéo finale en pleine qualité ; un lien permet ensuite de l'ouvrir. La visite reste disponible avec le bouton <b>?</b>." },
];
let tourStep = -1;

function startTour() {
  if ($("#dlg-aide").open) $("#dlg-aide").close();
  closeMenu(); setBig(false); play(false);
  tourStep = 0; $("#visite").hidden = false;
  showStep();
}
function endTour() { tourStep = -1; $("#visite").hidden = true; }
function stepTour(d) {
  const n = tourStep + d;
  if (n >= TOUR.length) { endTour(); toast("Visite terminée. Bon montage !"); return; }
  tourStep = clamp(n, 0, TOUR.length - 1); showStep();
}
function showStep() {
  const st = TOUR[tourStep], n = TOUR.length;
  $("#visite-num").textContent = `Étape ${tourStep + 1} sur ${n}`;
  $("#visite-titre").textContent = `${tourStep + 1}. ${st.title}`;
  $("#visite-texte").innerHTML = st.text;   // textes écrits ci-dessus (aucune donnée de l'utilisateur)
  $("#visite-points").innerHTML = TOUR.map((_, i) => `<span class="${i === tourStep ? "ici" : i < tourStep ? "vu" : ""}"></span>`).join("");
  $("#visite-prec").hidden = tourStep === 0;
  $("#visite-ok").textContent = tourStep === n - 1 ? "Terminer ✓" : `OK · étape ${tourStep + 2} ›`;
  placeStep();
  $("#visite-ok").focus();
}
function placeStep() {   // éclaire la zone de l'étape et pose la bulle à côté, du côté où elle tient
  if (tourStep < 0) return;
  const st = TOUR[tourStep], el = document.querySelector(st.sel), spot = $("#visite .spot"), b = $("#visite .bulle");
  const r = el ? el.getBoundingClientRect() : null, vw = innerWidth, vh = innerHeight, gap = 16;
  const bw = b.offsetWidth, bh = b.offsetHeight;
  let x = (vw - bw) / 2, y = (vh - bh) / 2, side = "aucun";
  spot.hidden = !(r && r.width > 0 && r.height > 0);
  if (!spot.hidden) {
    const p = 6, L = r.left - p, T = r.top - p, W = r.width + 2 * p, H = r.height + 2 * p;
    Object.assign(spot.style, { left: `${L}px`, top: `${T}px`, width: `${W}px`, height: `${H}px` });
    const fits = { droite: vw - L - W >= bw + gap + 8, gauche: L >= bw + gap + 8, dessous: vh - T - H >= bh + gap + 8, dessus: T >= bh + gap + 8, dedans: true };
    side = (st.side || ["droite", "gauche", "dessous", "dessus"]).find((k) => fits[k]) || "dedans";
    if (side === "droite") { x = L + W + gap; y = T + H / 2 - bh / 2; }
    else if (side === "gauche") { x = L - bw - gap; y = T + H / 2 - bh / 2; }
    else if (side === "dessous") { x = L + W / 2 - bw / 2; y = T + H + gap; }
    else if (side === "dessus") { x = L + W / 2 - bw / 2; y = T - bh - gap; }
    else { x = L + W / 2 - bw / 2; y = T + H - bh - gap; }   // grande zone : bulle en bas, à l'intérieur
    x = clamp(x, 8, vw - bw - 8); y = clamp(y, 8, vh - bh - 8);
    b.style.setProperty("--fx", `${clamp(L + W / 2 - x, 22, bw - 22)}px`);   // flèche : vers le milieu de la zone
    b.style.setProperty("--fy", `${clamp(T + H / 2 - y, 22, bh - 22)}px`);
  }
  b.dataset.cote = side;
  b.style.left = `${Math.round(x)}px`; b.style.top = `${Math.round(y)}px`;
}

async function showFile(path, action) {   // ouvert par Windows (lecteur vidéo, Explorateur) : marche aussi dans l'application de bureau
  try { await api("/api/editeur/montrer", { method: "POST", body: { path, action } }); }
  catch (e) { toast("Impossible d'ouvrir le fichier : " + e.message); }
}

// ---- export : vidéo HD ou 4K, plusieurs vidéos d'un coup, projet Premiere Pro / DaVinci Resolve (extras MSV Pro)
const exportChoice = () => document.querySelector('input[name="export-type"]:checked').value;
const seriesChecked = () => [...document.querySelectorAll("#serie-liste input:checked")].map((i) => i.value);

function updateExportChoice() {   // seuls les choix possibles ici peuvent être lancés ; sinon on dit pourquoi
  const v = exportChoice(), lock = $("#export-verrou");
  $("#export-serie").hidden = v !== "serie";
  const needs = { "4k": ["4k"], serie: ["serie"].concat($("#serie-qualite").value === "4K" ? ["4k"] : []), nle: ["nle"] }[v] || [];
  const extra = needs.find((x) => !(S.cfg.extras || {})[x]);
  const n = seriesChecked().length;
  let why = "";
  if (extra) why = S.cfg.edition === "pro"
    ? `🔑 Cet export demande une licence MSV Pro active. <a href="${S.cfg.pro_page}">Activer ma licence</a>`
    : `⭐ Cet export fait partie de MSV Pro. <a href="${S.cfg.pro_page}">Découvrir MSV Pro</a>`;
  else if (v !== "serie" && !S.P.clips.length) why = "Ajoute d'abord des clips à la timeline.";
  else if (v === "serie" && !n) why = "Coche les vidéos à traiter.";
  lock.innerHTML = why; lock.hidden = !why;
  $("#export-go").disabled = !!why;
  $("#export-go").textContent = v === "serie" && n ? `Lancer l'export (${n} vidéo${n > 1 ? "s" : ""})` : "Lancer l'export";
}

function fillSeries() {
  const box = $("#serie-liste"), keep = new Set(seriesChecked());
  const vids = [...S.medias.values()].filter((m) => m.kind === "video" && !m.sticker);
  box.innerHTML = vids.length ? "" : "<p class='note'>Aucune vidéo dans la médiathèque : importe-les d'abord.</p>";
  for (const m of vids) {
    const l = document.createElement("label");
    l.innerHTML = `<input type="checkbox"> <span>${esc(m.name)}</span> <small>${fmtT(m.duration)}</small>`;
    l.firstChild.value = m.path; l.firstChild.checked = keep.has(m.path);
    box.append(l);
  }
}

function openExport() {
  play(false);
  const empty = emptySlots().length;
  if (empty && !confirm(`${empty} plan${empty > 1 ? "s" : ""} du modèle ${empty > 1 ? "sont" : "est"} encore à remplir (il${empty > 1 ? "s" : ""} apparaîtra${empty > 1 ? "ont" : ""} comme une consigne grise). Exporter quand même ?`)) return;
  $("#export-choix").hidden = false; $("#export-suivi").hidden = true;
  fillSeries(); updateExportChoice();
  $("#dlg-export").showModal();
}

function showResult(path, notes, info) {
  const p = $("#export-lien"); p.hidden = false;
  const video = /\.mp4$/i.test(path);
  p.innerHTML = `<span class="boutons">${video ? '<button type="button" data-montrer="ouvrir">▶ Ouvrir la vidéo</button>' : ""}
    <button type="button" data-montrer="dossier">📂 Afficher dans le dossier</button></span>
    ${info ? `<p class="note">${esc(info)}</p>` : ""}
    ${notes && notes.length ? `<details><summary>À refaire dans le logiciel (${notes.length})</summary><ul>${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></details>` : ""}
    <small>${esc(path)}</small>`;
  for (const b of p.querySelectorAll("[data-montrer]")) b.onclick = () => showFile(path, b.dataset.montrer);
}

async function runExport() {
  const v = exportChoice();
  $("#export-choix").hidden = true; $("#export-suivi").hidden = false;
  $("#export-lien").hidden = true; $("#export-barre").value = 0; $("#export-msg").textContent = "Démarrage…";
  try {
    if (v === "nle") {
      $("#export-msg").textContent = "Préparation des fichiers pour Premiere Pro et DaVinci Resolve…";
      const r = await api("/api/editeur/export-nle", { method: "POST", body: S.P });
      $("#export-barre").value = 1;
      $("#export-msg").textContent = "Projet prêt pour Premiere Pro et DaVinci Resolve.";
      showResult(r.xml, r.notes, "Premiere Pro : Fichier > Importer. DaVinci Resolve : Fichier > Importer > Timeline.");
      return;
    }
    const hd = S.P.quality && S.P.quality !== "4K" ? S.P.quality : "haute";
    const { id } = v === "serie"
      ? await api("/api/editeur/serie", { method: "POST", body: { project: S.P, videos: seriesChecked(), quality: $("#serie-qualite").value } })
      : await api("/api/editeur/rendu", { method: "POST", body: { ...S.P, quality: v === "4k" ? "4K" : hd } });
    for (;;) {
      await new Promise((r) => setTimeout(r, 700));
      const st = await api(`/api/editeur/rendu/${id}`);
      $("#export-barre").value = st.progress || 0;
      $("#export-msg").textContent = st.state === "en cours" ? (st.message || "Rendu…") : st.state === "fini" ? `Terminé en ${st.seconds} s.` : "Le rendu a échoué.";
      if (st.state === "fini") {
        const n = (st.videos || []).length;
        showResult(st.video, null, n > 1 ? `${n} vidéos créées dans le même dossier.` : "");
        return;
      }
      if (st.state === "erreur") { $("#export-msg").textContent = "Le rendu a échoué : " + st.error; return; }
    }
  } catch (e) { $("#export-msg").textContent = "L'export a échoué : " + e.message; }
}

async function importFiles(files) {
  for (const f of files) {
    const fd = new FormData(); fd.append("fichier", f);
    try { await api("/api/editeur/importer", { method: "POST", body: fd }); toast("Importé : " + f.name); }
    catch (e) { toast(`${f.name} : ${e.message}`); }
  }
  await loadMedias();
}

// ------------------------------------------------------------------------------------------------ démarrage

function bind() {
  $("#lecture").onclick = () => play();
  $("#debut").onclick = () => setTime(0);
  $("#fin").onclick = () => setTime(totalDur());
  $("#annuler").onclick = undo; $("#refaire").onclick = redo;
  $("#enregistrer").onclick = save; $("#ouvrir").onclick = showOpen; $("#modeles").onclick = showTemplates; $("#exporter").onclick = openExport; $("#miniature").onclick = openThumbnail;
  $("#export-go").onclick = runExport;
  $("#export-annuler").onclick = () => $("#dlg-export").close();
  for (const el of document.querySelectorAll('input[name="export-type"], #serie-qualite')) el.addEventListener("change", updateExportChoice);
  $("#serie-liste").addEventListener("change", updateExportChoice);
  $("#ajouter").onclick = (e) => { const r = e.currentTarget.getBoundingClientRect(); zoneMenu("apercu", r.left, r.top - 150); };
  for (const b of document.querySelectorAll("#dlg-stickers [data-onglet]")) b.onclick = () => showTab(b.dataset.onglet);
  for (const id of ["#cs-base", "#cs-emoji", "#cs-photo", "#cs-forme", "#cs-acc", "#cs-coin", "#cs-taille", "#cs-texte", "#cs-pos", "#cs-couleur", "#cs-contour"]) {
    $(id).addEventListener("input", () => { if (id === "#cs-base") fillCreator(); previewCustom(); });
  }
  $("#cs-creer").onclick = (e) => { e.preventDefault(); createCustom(); };
  $("#aide").onclick = () => showHelp();
  $("#visite-go").onclick = startTour;
  $("#visite-ok").onclick = () => stepTour(1);
  $("#visite-prec").onclick = () => stepTour(-1);
  $("#visite-quitter").onclick = endTour;
  $("#grand").onclick = () => setBig(!document.body.classList.contains("grand"));
  bindSplitter(); bindPanelEdges();
  window.addEventListener("keydown", (e) => {   // pendant la visite : seules ses touches comptent
    if (tourStep < 0) return;
    if (e.key === "Escape") endTour();
    else if (e.key === "ArrowRight" || (e.key === "Enter" && e.target === document.body)) stepTour(1);
    else if (e.key === "ArrowLeft") stepTour(-1);
    else if (e.key === "Tab" || e.key === "Enter" || e.key === " ") { e.stopImmediatePropagation(); return; }   // boutons de la bulle
    e.preventDefault(); e.stopImmediatePropagation();
  }, true);
  $("#dlg-aide").addEventListener("close", () => {
    try { localStorage.setItem("msv-editeur-aide", $("#aide-masquer").checked ? "non" : "oui"); } catch (e) { /* stockage indisponible */ }
  });
  $("#emoji-ok").onclick = (e) => { e.preventDefault(); placeEmoji($("#emoji-libre").value.trim()); };
  // clic droit : timeline (éléments et zones vides) et aperçu
  for (const [id, zone] of [["#p-clips", "clips"], ["#p-overlays", "overlays"], ["#p-texts", "texts"], ["#p-audio", "audio"], ["#regle", "regle"]]) {
    $(id).addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const b = e.target.closest(".bloc");
      if (b && b.dataset.kind) itemMenu(b.dataset.kind, +b.dataset.i, e.clientX, e.clientY);
      else if (b && b.dataset.audio) audioMenu(b.dataset.audio, e.clientX, e.clientY);
      else zoneMenu(zone, e.clientX, e.clientY, Math.max(0, timeAt(e.clientX)));
    });
  }
  $("#scene").addEventListener("contextmenu", (e) => {
    e.preventDefault();
    const [x, y] = canvasPoint(e);
    const hit = [...S.boxes].reverse().find((b) => x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h);
    if (hit) itemMenu(hit.kind, hit.i, e.clientX, e.clientY);
    else {   // sous le clip affiché : ses actions, plus de quoi ajouter un calque à cet instant
      const o = layoutClips().find((c) => S.t >= c.t0 && S.t < c.t1);
      if (o) itemMenu("clips", o.i, e.clientX, e.clientY, ["-", { title: "Ajouter ici" }, { ico: "T", label: "Texte", run: () => addTextAt(S.t) },
        { ico: "😀", label: "Emoji ou sticker…", run: () => openStickers(S.t) }, ctaItem(S.t),
        { ico: "✎", label: "Créer un sticker…", run: () => openStickers(S.t, "creer") }]);
      else zoneMenu("apercu", e.clientX, e.clientY);
    }
  });
  $("#nom").onchange = () => change(() => { S.P.name = $("#nom").value.trim() || "mon_montage"; });
  $("#format").onchange = () => change(() => { S.P.format = $("#format").value; });
  $("#zoom").oninput = () => { S.pxs = num($("#zoom").value, 70); renderTimeline(); };
  $("#importer").onchange = (e) => importFiles([...e.target.files]);
  const zone = $("#liste-medias");
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("survol"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("survol"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("survol"); importFiles([...e.dataTransfer.files]); });
  window.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) return;
    const mod = e.ctrlKey || e.metaKey;
    if (e.code === "Space") { e.preventDefault(); play(); }
    else if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
    else if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
    else if (e.key === "s" || e.key === "S") splitClip();
    else if ((e.key === "Delete" || e.key === "Backspace") && S.sel) { change(() => { S.P[S.sel.kind].splice(S.sel.i, 1); S.sel = null; }); }
    else if (e.key === "ArrowLeft") setTime(S.t - (e.shiftKey ? 1 : 1 / 30));
    else if (e.key === "ArrowRight") setTime(S.t + (e.shiftKey ? 1 : 1 / 30));
    else if (e.key === "Home") setTime(0);
    else if (e.key === "End") setTime(totalDur());
    else if (e.key === "k" || e.key === "K") addKeyHere();
    else if ((e.key === "f" || e.key === "F") && !mod) setBig(!document.body.classList.contains("grand"));
  });
  window.addEventListener("beforeunload", (e) => { if (S.dirty) { e.preventDefault(); e.returnValue = ""; } });
}

async function main() {
  S.cfg = await api("/api/editeur/config");
  if (S.cfg.edition === "pro") {
    $("#edition").hidden = false;
    if (!S.cfg.licence.active) { $("#edition").textContent = "PRO · activer la licence"; $("#edition").classList.add("a-activer"); }
  }
  else $("#vers-pro").hidden = false;                   // édition libre : bouton vers la Pro
  if (S.cfg.api !== API_VERSION) alerte(OLD_SERVER);
  try { if (localStorage.getItem("msv-editeur-grand") === "oui") setBig(true); } catch (e) { /* stockage indisponible */ }
  for (const [k, [w, h]] of Object.entries(S.cfg.formats)) { const o = document.createElement("option"); o.value = k; o.textContent = `${k} (${w}×${h})`; $("#format").append(o); }
  for (const f of S.cfg.fonts) { try { const ff = new FontFace(fontFamily(f), `url(/editeur/polices/${enc(f)})`); document.fonts.add(await ff.load()); } catch (e) { /* police système à la place */ } }
  bind();
  await loadMedias().catch(() => { $("#liste-medias").innerHTML = "<p class='vide'>Médiathèque illisible.</p>"; });
  const q = new URLSearchParams(location.search);
  let saved = null;
  if (q.get("projet")) { try { saved = await api(`/api/editeur/projet?nom=${enc(q.get("projet"))}`); } catch (e) { toast("Projet introuvable : " + q.get("projet")); } }
  if (!saved) { try { saved = JSON.parse(localStorage.getItem("msv-editeur") || "null"); } catch (e) { saved = null; } }
  await openProject(saved || newProject());
  fitCanvas();
  if (q.get("t")) setTime(num(q.get("t")));
  for (const c of S.P.clips) thumbs(c.path);
  let firstTime = true;   // aide affichée au premier lancement (puis avec le bouton « ? »)
  try { firstTime = localStorage.getItem("msv-editeur-aide") !== "non"; } catch (e) { firstTime = true; }
  if (firstTime && !q.get("t")) showHelp();
  requestAnimationFrame((ts) => { S.lastTs = ts; loop(ts); });
}

main().catch((e) => { document.body.innerHTML = `<p style="padding:20px">L'éditeur n'a pas pu démarrer : ${e.message}</p>`; });
