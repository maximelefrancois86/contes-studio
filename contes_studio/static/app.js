// SPDX-License-Identifier: GPL-3.0-or-later
// Atelier : galerie des ateliers (packs) ; un atelier ouvert a quatre onglets (Flot, Répliques, Sons,
// Illustrations) ; page Réglages. Tout est en formulaires : l'utilisateur ne voit jamais le YAML.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const audio = $("#audio");
const S = { pid: null, onglet: "flot", pack: null, sec: 0, cur: null, chain: false, v: Date.now(),
  sons: { type: "bruitage", fournisseur: "freesound", q: "", page: 1 } };
const ONGLETS = ["flot", "repliques", "sons", "illustrations"];

function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.className = ""), err ? 7000 : 2200);
}
async function api(url, opts = {}) {
  if (opts.json !== undefined) { opts.body = JSON.stringify(opts.json); opts.headers = { "Content-Type": "application/json" }; delete opts.json; }
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
const fmtDuree = (s) => s >= 60 ? `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")}` : `${s} s`;
const imgSlot = (slot, gris = false) => `/api/packs/${S.pid}/illustrations/${slot}/image?v=${S.v}${gris ? "&gris=true" : ""}`;

/* ---------------------------------------------------------------- tâches */
async function suivreTache(t, surJournal) {
  for (;;) {
    const s = await api(`/api/taches/${t.id}`);
    surJournal?.(s);
    if (["terminée", "erreur", "annulée"].includes(s.etat)) return s;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

/* -------------------------------------------------------------- modale */
function modale(html) {
  const m = $("#modale"); $(".boite", m).innerHTML = html; m.hidden = false;
  m.onclick = (e) => { if (e.target === m) fermer(); };
  return $(".boite", m);
}
function fermer() { $("#modale").hidden = true; $("#modale .boite").innerHTML = ""; }
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modale").hidden) fermer(); });

/* --------------------------------------------------------------- routes */
async function route() {
  const p = location.hash.replace(/^#\/?/, "").split("/");
  audio.pause(); S.chain = false; if (typeof F !== "undefined") F.lecture = null;
  $("#onglets").hidden = true; $("#b-galerie").hidden = true;
  if (p[0] === "atelier" && p[1]) {
    S.pid = p[1]; S.onglet = ONGLETS.includes(p[2]) ? p[2] : "flot";
    if (p[3] !== undefined) S.sec = +p[3] || 0;
    $("#onglets").hidden = false; $("#b-galerie").hidden = false;
    $$("#onglets a").forEach((a) => { a.classList.toggle("on", a.dataset.o === S.onglet); a.href = `#/atelier/${S.pid}/${a.dataset.o}`; });
    const titre = (await api("/api/packs")).find((x) => x.id === S.pid)?.titre || S.pid;
    $("#titre").textContent = titre; document.title = `${titre} · Atelier`;
    return ({ flot: vueFlot, repliques: vueRepliques, sons: vueSons, illustrations: vueIllustrations })[S.onglet]();
  }
  if (p[0] === "reglages") { $("#b-galerie").hidden = false; $("#titre").textContent = "Réglages"; return vueReglages(); }
  $("#titre").textContent = "Mes ateliers"; document.title = "Atelier d'histoires";
  return vueGalerie();
}
window.addEventListener("hashchange", route);

/* -------------------------------------------------------------- galerie */
async function vueGalerie() {
  const packs = await api("/api/packs");
  $("#main").innerHTML = `<div class="galerie">
    <a class="carte nouveau" href="#" id="nouveau"><div class="plus-grand">＋</div><b>Nouvel atelier</b><span>Une nouvelle aventure à choix</span></a>
    ${packs.map((p) => `
    <a class="carte" href="#/atelier/${p.id}/flot">
      <img src="/api/packs/${p.id}/illustrations/couverture/image?v=${S.v}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <b>${esc(p.titre)}</b>
      <span>${p.erreur ? `<span class="pastille err">à corriger</span>` : p.aventure ? `Aventure · ${p.histoires} chemins` : `${p.histoires} histoires`}</span>
    </a>`).join("")}</div>`;
  $("#nouveau").onclick = async (e) => {
    e.preventDefault();
    const voix = await api("/api/catalogue-voix");
    const b = modale(`<h2>Nouvel atelier</h2>
      <div class="champ"><label>Titre de l'histoire</label><input type="text" id="n-t" placeholder="Le voyage de Lila"></div>
      <div class="champ"><label>Voix du narrateur</label><div><select id="n-v">${voix.map((v) => `<option value="${esc(v.nom)}" ${v.nom === "conteur" ? "selected" : ""}>${esc(v.nom.replace(/_/g, " "))}</option>`).join("")}</select>
        <p class="aide" id="n-d"></p></div></div>
      <div class="rangee"><span style="flex:1"></span><button class="bouton" id="n-a">Annuler</button><button class="bouton principal" id="n-ok">Créer</button></div>`);
    const desc = () => ($("#n-d", b).textContent = voix.find((v) => v.nom === $("#n-v", b).value)?.description || "");
    $("#n-v", b).onchange = desc; desc(); $("#n-t", b).focus();
    $("#n-a", b).onclick = fermer;
    $("#n-ok", b).onclick = async () => {
      try { const r = await api("/api/packs", { method: "POST", json: { titre: $("#n-t", b).value, narrateur: $("#n-v", b).value } }); fermer(); location.hash = `#/atelier/${r.id}/flot`; }
      catch (err) { toast(err.message, true); }
    };
  };
}

/* ----------------------------------------------------------------- flot */
async function vueFlotQuestions() {
  const f = await api(`/api/packs/${S.pid}/flot`);
  const NW = 190, NH = 58, GX = 70, GY = 18;
  const N = Object.fromEntries(f.noeuds.map((n) => [n.id, { ...n, out: [], inn: [] }]));
  f.aretes.forEach((a) => { N[a.de]?.out.push(a); N[a.vers]?.inn.push(a); });
  // niveaux : plus long chemin depuis la couverture (graphe sans boucle)
  const niv = { c: 0 }; const ordre = ["c"];
  for (let k = 0; k < ordre.length; k++) {
    for (const a of N[ordre[k]].out) {
      const d = niv[ordre[k]] + 1;
      if (niv[a.vers] === undefined || niv[a.vers] < d) { niv[a.vers] = d; ordre.push(a.vers); }
    }
  }
  const couches = [];
  Object.entries(niv).forEach(([id, d]) => (couches[d] ||= []).push(id));
  // ordre vertical : feuilles dans l'ordre de découverte, puis moyenne des voisins (une passe aller, une retour)
  const y = {};
  couches.forEach((c, d) => {
    if (d) c.sort((a, b) => moy(a, "inn") - moy(b, "inn"));
    c.forEach((id, k) => (y[id] = k));
  });
  function moy(id, sens) {
    const v = N[id][sens].map((a) => y[sens === "inn" ? a.de : a.vers]).filter((x) => x !== undefined);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0;
  }
  const H = Math.max(...couches.map((c) => c.length));
  const pos = {};
  couches.forEach((c, d) => c.forEach((id, k) => {
    pos[id] = { x: 20 + d * (NW + GX), y: 20 + (k + (H - c.length) / 2) * (NH + GY) };
  }));
  const W = 40 + couches.length * (NW + GX), HT = 40 + H * (NH + GY);
  const lien = (a) => {
    const p = pos[a.de], q = pos[a.vers]; if (!p || !q) return "";
    const x1 = p.x + NW, y1 = p.y + NH / 2, x2 = q.x, y2 = q.y + NH / 2, mx = (x1 + x2) / 2;
    const lab = a.libelle ? `<text class="lib" x="${mx}" y="${(y1 + y2) / 2 - 4}" text-anchor="middle">${esc(a.libelle.slice(0, 26))}</text>` : "";
    return `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" />${lab}`;
  };
  const boite = (id) => {
    const n = N[id], p = pos[id]; if (!p) return "";
    const img = n.slot ? `<image href="${imgSlot(n.slot)}" x="${p.x + 4}" y="${p.y + 4}" width="66" height="50" preserveAspectRatio="xMidYMid slice"/>` : "";
    const tx = n.slot ? p.x + 76 : p.x + 10;
    const mots = esc(n.titre).split(" "); const l1 = [], l2 = [];
    for (const m of mots) ((l1.join(" ").length + m.length < (n.slot ? 15 : 24)) && !l2.length ? l1 : l2).push(m);
    const cliquable = n.section ? `data-section="${n.i}"` : "";
    return `<g class="n ${n.type}${n.fin ? " fin" : ""}" ${cliquable}><rect x="${p.x}" y="${p.y}" width="${NW}" height="${NH}" rx="10"/>${img}
      <text x="${tx}" y="${p.y + 24}">${l1.join(" ")}</text><text x="${tx}" y="${p.y + 42}">${l2.join(" ").slice(0, n.slot ? 16 : 26)}${l2.join(" ").length > (n.slot ? 16 : 26) ? "…" : ""}</text>
      <title>${esc(n.titre)}${n.question ? " — " + esc(n.question) : ""}</title></g>`;
  };
  const entetes = f.type === "questions"
    ? f.questions.map((q, k) => `<text class="ent" x="${20 + (k + 1) * (NW + GX)}" y="14">${esc(q.slice(0, 30))}</text>`).join("") : "";
  $("#main").innerHTML = `
    <p class="aide">Pack à questions : chaque colonne est une question, chaque chemin mène à une histoire (graphe en lecture seule).
      Clique sur une ${f.type === "questions" ? "histoire" : "étape"} pour modifier ses répliques.</p>
    <div class="flot"><svg width="${W}" height="${HT + 10}" viewBox="0 0 ${W} ${HT + 10}">
      <style>
        .flot path{fill:none;stroke:var(--line);stroke-width:2}
        .flot .n rect{fill:var(--panel);stroke:var(--line);stroke-width:1.5}
        .flot .n text{fill:var(--ink);font-size:13px}
        .flot .n.histoire rect,.flot .n.etape rect{stroke:var(--accent)}
        .flot .n.question rect{fill:var(--accent-2);rx:28px}
        .flot .n.fin rect{stroke-width:3}
        .flot .n[data-section]{cursor:pointer}.flot .n[data-section]:hover rect{fill:var(--accent-2)}
        .flot .lib{fill:var(--ink-2);font-size:11px}.flot .ent{fill:var(--ink-2);font-size:12px;font-weight:600}
      </style>${entetes}${f.aretes.map(lien).join("")}${Object.keys(pos).map(boite).join("")}</svg></div>`;
  $$(".flot .n[data-section]").forEach((g) => (g.onclick = () => { location.hash = `#/atelier/${S.pid}/repliques/${g.dataset.section}`; }));
}

/* ------------------------------------------------------------ répliques */
async function vueRepliques() {
  const tok = (S.tok = (S.tok || 0) + 1);
  $("#main").innerHTML = `<p class="vide">Chargement…</p>`;
  const [pack, sons] = await Promise.all([api(`/api/packs/${S.pid}`), api(`/api/packs/${S.pid}/sons`)]);
  if (tok !== S.tok) return;
  S.pack = pack; S.catalogue = sons; S.sec = Math.min(S.sec, pack.sections.length - 1);
  renderRepliques();
}

function renderRepliques() {
  const p = S.pack; const sec = p.sections[S.sec];
  const reps = sec.lignes.filter((l) => l.kind === "replique");
  const manque = reps.filter((l) => !l.audio).length;
  const opts = (list, val, vide) => (vide ? `<option value="">${esc(vide)}</option>` : "") +
    list.map((x) => `<option ${x === val ? "selected" : ""}>${esc(x)}</option>`).join("");
  const ambs = S.catalogue;
  $("#main").innerHTML = `
    <div class="voix">${p.voix.map((v) => `<span title="${esc(v.description)}"><b>${esc(v.nom)}</b> · ${esc(v.ton || "neutre")}</span>`).join("")}</div>
    <div class="secs">${p.sections.map((s, k) => `<button data-k="${k}" class="${k === S.sec ? "on" : ""}">${esc(s.titre)}
      ${s.choix.length ? `<small>${esc(s.choix.join(" · "))}</small>` : ""}</button>`).join("")}</div>
    <div class="barre">
      <button class="bouton" id="chain">▶ Écouter à partir de la réplique choisie</button>
      <button class="bouton" id="stop">■ Arrêter</button>
      <label class="rangee">Ambiance <select id="amb">${opts(ambs.map((s) => s.id), sec.ambiance, "aucune")}</select></label>
      <span class="stat">${reps.length} répliques${manque ? ` · <b>${manque} voix à refaire</b>` : " · toutes les voix sont prêtes"}</span>
    </div>
    <table><tbody>${sec.lignes.map((l) => l.kind === "replique" ? `
      <tr data-j="${l.j}">
        <td class="n">${l.j + 1}</td>
        <td class="q"><select data-f="qui">${opts(p.voix.map((v) => v.nom), l.qui)}</select></td>
        <td class="t"><select data-f="ton">${opts(p.tons, l.ton, "ton de la voix (" + (l.ton_effectif || "neutre") + ")")}</select></td>
        <td><textarea data-f="texte" rows="1">${esc(l.texte)}</textarea></td>
        <td class="a">${l.audio ? `<button class="play" data-a="${esc(l.audio)}" title="Écouter">▶</button>`
          : `<span class="manque" title="Voix à refaire : texte, ton ou personnage modifié. Elle sera synthétisée à la prochaine fabrication.">!</span>`}
          <button class="plus" data-plus="${l.j}" title="Ajouter un son après cette réplique">♪</button>
          <span class="outils-ligne"><button data-op="ajouter" data-j="${l.j}" title="Nouvelle réplique en dessous">＋</button><button data-op="monter" data-j="${l.j}" title="Monter">↑</button><button data-op="descendre" data-j="${l.j}" title="Descendre">↓</button><button data-op="supprimer" data-j="${l.j}" title="Supprimer">🗑</button></span></td>
      </tr>` : `<tr class="son"><td class="n">${l.j + 1}</td><td colspan="3">${l.kind === "pause" ? `⏸ pause ${l.pause ?? ""} s`
        : `${l.kind === "bruit" ? "🔔 bruitage" : l.kind === "musique" ? "🎵 musique" : l.kind === "ambiance" ? "🌲 ambiance" : esc(l.kind)} : ${esc(l.son ?? "aucun")}`}</td>
        <td class="a">${l.son && S.catalogue.find((s) => s.id === l.son)?.fichier ? `<button class="play" data-son="${esc(l.son)}" title="Écouter">▶</button>` : ""}
          <button class="plus" data-plus="${l.j}" title="Ajouter un son après cette ligne">♪</button>
          <span class="outils-ligne"><button data-op="monter" data-j="${l.j}" title="Monter">↑</button><button data-op="descendre" data-j="${l.j}" title="Descendre">↓</button><button data-op="supprimer" data-j="${l.j}" title="Supprimer">🗑</button></span></td></tr>`).join("")}
    </tbody></table>
    <div class="rangee" style="margin-top:10px"><button class="bouton principal" data-op="ajouter" data-j="${sec.lignes.length - 1}">＋ Ajouter une réplique</button>
      ${sec.lignes.length ? "" : `<span class="aide">Cette étape est vide : écris sa première réplique.</span>`}</div>`;
  bindRepliques();
}

function bindRepliques() {
  const sec = S.pack.sections[S.sec];
  $$(".secs button").forEach((b) => (b.onclick = () => { S.sec = +b.dataset.k; stopChain(); history.replaceState(null, "", `#/atelier/${S.pid}/repliques/${S.sec}`); renderRepliques(); }));
  $$("tr[data-j]").forEach((tr) => {
    const j = +tr.dataset.j;
    tr.onclick = (e) => { if (!["TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName)) select(j); };
    tr.querySelectorAll("select").forEach((s) => (s.onchange = () => sauver(tr, { [s.dataset.f]: s.value })));
    const ta = tr.querySelector("textarea");
    const fit = () => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + 2 + "px"; };
    fit(); ta.addEventListener("input", fit);
    ta.dataset.orig = ta.value;
    ta.onfocus = () => select(j, false);
    ta.onblur = () => { if (ta.value !== ta.dataset.orig) sauver(tr, { texte: ta.value }); };
    ta.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ta.blur(); } };
  });
  $$(".play[data-a]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); stopChain(); jouer(`/api/voix/${b.dataset.a}`); }));
  $$(".play[data-son]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); stopChain(); jouer(`/api/packs/${S.pid}/sons/${b.dataset.son}/audio`); }));
  $$(".plus").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); ajouterSonApres(+b.dataset.plus); }));
  $$("[data-op]").forEach((b) => (b.onclick = async (e) => {
    e.stopPropagation();
    const j = +b.dataset.j, o = b.dataset.op;
    if (o === "supprimer" && !confirm("Supprimer cette ligne ?")) return;
    const action = o === "monter" || o === "descendre" ? "deplacer" : o;
    try {
      const r = await api(`/api/packs/${S.pid}/lignes/${action}`, { method: "POST", json: { section: sec.section, i: sec.i, j, sens: o === "monter" ? -1 : 1 } });
      await vueRepliques(); select(r.j);
      if (o === "ajouter") { const ta = $(`tr[data-j="${r.j}"] textarea`); if (ta) { ta.focus(); ta.select(); } }
    } catch (err) { toast(err.message, true); }
  }));
  $("#chain").onclick = () => { S.chain = true; jouerDepuis(S.cur ?? premiere()); };
  $("#stop").onclick = stopChain;
  $("#amb").onchange = async (e) => {
    try { await api(`/api/packs/${S.pid}/ambiance`, { method: "POST", json: { section: sec.section, i: sec.i, son: e.target.value || null } }); toast("Ambiance enregistrée"); await vueRepliques(); }
    catch (err) { toast(err.message, true); }
  };
}

function ajouterSonApres(j) {
  const sec = S.pack.sections[S.sec];
  if (!S.catalogue.length) { toast("Ce pack n'a encore aucun son : ajoute-en dans l'onglet Sons.", true); return; }
  const b = modale(`<h2>Ajouter un son après la ligne ${j + 1}</h2>
    <div class="champ"><label>Son</label><select id="m-son">${S.catalogue.map((s) => `<option value="${esc(s.id)}">${esc(s.id)}${s.credit ? " — " + esc(s.credit.nom || "") : ""}</option>`).join("")}</select></div>
    <div class="champ"><label>Comme</label><select id="m-genre"><option value="bruit">bruitage (court, entre deux répliques)</option><option value="musique">musique (jouée seule)</option></select></div>
    <div class="rangee"><button class="bouton" id="m-ecoute">▶ Écouter</button><span style="flex:1"></span>
      <button class="bouton" id="m-annul">Annuler</button><button class="bouton principal" id="m-ok">Ajouter</button></div>`);
  $("#m-ecoute", b).onclick = () => jouer(`/api/packs/${S.pid}/sons/${$("#m-son", b).value}/audio`);
  $("#m-annul", b).onclick = fermer;
  $("#m-ok", b).onclick = async () => {
    try {
      await api(`/api/packs/${S.pid}/sons/inserer`, { method: "POST", json: { section: sec.section, i: sec.i, apres: j, genre: $("#m-genre", b).value, son: $("#m-son", b).value } });
      fermer(); toast("Son ajouté"); await vueRepliques(); select(j + 1);
    } catch (e) { toast(e.message, true); }
  };
}

function select(j, scroll = true) {
  S.cur = j;
  $$("tr[data-j]").forEach((tr) => tr.classList.toggle("cur", +tr.dataset.j === j));
  if (scroll) $(`tr[data-j="${j}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function sauver(tr, change) {
  const j = +tr.dataset.j; const sec = S.pack.sections[S.sec];
  tr.classList.add("saving");
  try {
    const l = await api(`/api/packs/${S.pid}/ligne`, { method: "POST", json: { section: sec.section, i: sec.i, j, ...change } });
    sec.lignes[sec.lignes.findIndex((x) => x.j === j)] = l;
    const y = window.scrollY; renderRepliques(); window.scrollTo(0, y); select(j, false);
    toast(l.audio ? "Enregistré" : "Enregistré · la voix sera refaite à la prochaine fabrication");
  } catch (e) {
    tr.classList.remove("saving"); toast(e.message, true);
    const ta = tr.querySelector("textarea"); if (ta) ta.value = ta.dataset.orig;
  }
}

function jouer(url) { audio.src = url; audio.play().catch(() => {}); }
const reps = () => S.pack.sections[S.sec].lignes.filter((l) => l.kind === "replique");
const premiere = () => reps()[0]?.j ?? 0;
function jouerDepuis(j) {
  const l = reps().find((x) => x.j >= j && x.audio);
  if (!l) { stopChain(); return; }
  select(l.j); jouer(`/api/voix/${l.audio}`); S.playing = l.j;
}
function stopChain() { S.chain = false; audio.pause(); }
audio.onended = () => { if (S.chain && S.onglet === "repliques") jouerDepuis(S.playing + 1); };

/* ----------------------------------------------------------------- sons */
async function vueSons() {
  const [cat, four] = await Promise.all([api(`/api/packs/${S.pid}/sons`), api("/api/sons/fournisseurs")]);
  S.catalogue = cat;
  const f = four.fournisseurs.find((x) => x.id === S.sons.fournisseur) || four.fournisseurs[0];
  $("#main").innerHTML = `<div class="deux">
    <section class="panneau"><h2>Sons de ce pack</h2>
      ${cat.length ? `<ul class="liste">${cat.map((s) => `<li>
        ${s.fichier ? `<button class="play" data-son="${esc(s.id)}" title="Écouter">▶</button>` : `<span class="manque" title="Pas encore téléchargé : il le sera à la prochaine fabrication">!</span>`}
        <div class="info"><b>${esc(s.id)}</b>
          <small>${s.spec.boucle ? "ambiance en boucle" : s.spec.musique ? "musique générée" : s.spec.genere ? "son généré" : "bruitage"}
          · utilisé ${s.usages} fois${s.credit?.auteur ? ` · ${esc(s.credit.nom)} par ${esc(s.credit.auteur)}` : ""}</small></div></li>`).join("")}</ul>`
        : `<p class="vide">Aucun son pour l'instant. Cherche un bruitage ou une bande son à droite.</p>`}
    </section>
    <section class="panneau"><h2>Chercher</h2>
      <div class="rangee" style="margin-bottom:10px">
        <span class="seg"><button data-t="bruitage" class="${S.sons.type === "bruitage" ? "on" : ""}">Bruitages</button><button data-t="bande-son" class="${S.sons.type === "bande-son" ? "on" : ""}">Bandes son</button></span>
        <select id="four">${four.fournisseurs.map((x) => `<option value="${x.id}" ${x.id === f.id ? "selected" : ""}>${esc(x.nom)}</option>`).join("")}</select>
        <span class="aide">${esc(f.licences)}</span>
      </div>
      ${f.pret ? `<form id="fq" class="rangee"><input type="search" id="q" placeholder="en anglais : owl, rain, door creak…" value="${esc(S.sons.q)}" style="flex:1">
        <button class="bouton principal">Chercher</button></form><div id="res" style="margin-top:10px"></div>`
        : `<p class="avert">${esc(f.message)}</p><a class="bouton" href="#/reglages">Ouvrir les Réglages</a>`}
    </section></div>`;
  $$(".play[data-son]").forEach((b) => (b.onclick = () => jouer(`/api/packs/${S.pid}/sons/${b.dataset.son}/audio`)));
  $$(".seg button").forEach((b) => (b.onclick = () => { S.sons.type = b.dataset.t; S.sons.page = 1; vueSons(); }));
  $("#four").onchange = (e) => { S.sons.fournisseur = e.target.value; vueSons(); };
  if ($("#fq")) {
    $("#fq").onsubmit = (e) => { e.preventDefault(); S.sons.q = $("#q").value; S.sons.page = 1; chercherSons(); };
    if (S.sons.q) chercherSons();
  }
}

async function chercherSons() {
  const r = $("#res"); r.innerHTML = `<p class="vide">Recherche…</p>`;
  try {
    const d = await api(`/api/sons/recherche?` + new URLSearchParams({ fournisseur: S.sons.fournisseur, q: S.sons.q, type: S.sons.type, page: S.sons.page }));
    if (!d.resultats.length) { r.innerHTML = `<p class="vide">Rien trouvé. Essaie d'autres mots, en anglais.</p>`; return; }
    const usages = S.sons.type === "bruitage" ? [["bruit", "bruitage"]] : [["ambiance", "ambiance en boucle"], ["musique", "musique"]];
    r.innerHTML = `<p class="aide">${d.total} résultats · page ${d.page} / ${d.pages}</p><ul class="liste">${d.resultats.map((x) => `<li>
      <button class="play" data-apercu="${esc(x.apercu)}" title="Écouter">▶</button>
      <div class="info"><b title="${esc(x.titre)}">${esc(x.titre)}</b><small>${fmtDuree(x.duree)} · ${esc(x.auteur)} · <a href="${esc(x.page)}" target="_blank" rel="noopener">fiche</a></small></div>
      <select data-u>${usages.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
      <button class="bouton" data-ajout="${esc(x.id)}" data-titre="${esc(x.titre)}">Ajouter</button></li>`).join("")}</ul>
      <div class="rangee" style="margin-top:8px">${d.page > 1 ? `<button class="bouton" id="prec">← Précédents</button>` : ""}${d.page < d.pages ? `<button class="bouton" id="suiv">Suivants →</button>` : ""}</div>`;
    $$(".play[data-apercu]", r).forEach((b) => (b.onclick = () => jouer(b.dataset.apercu)));
    $$("[data-ajout]", r).forEach((b) => (b.onclick = async () => {
      const nom = prompt("Nom de ce son dans le pack (sans accents ni espaces de préférence) :", b.dataset.titre.replace(/\.(wav|mp3|ogg|flac|aiff?)$/i, "").slice(0, 30));
      if (!nom) return;
      b.disabled = true; b.textContent = "…";
      try {
        const a = await api(`/api/packs/${S.pid}/sons`, { method: "POST", json: { fournisseur: S.sons.fournisseur, son: b.dataset.ajout, usage: $("[data-u]", b.parentElement).value, nom } });
        toast(a.telecharge ? `« ${a.id} » ajouté au pack` : a.message, !a.telecharge);
        const q = S.sons.q; await vueSons(); S.sons.q = q;
      } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Ajouter"; }
    }));
    if ($("#prec")) $("#prec").onclick = () => { S.sons.page--; chercherSons(); };
    if ($("#suiv")) $("#suiv").onclick = () => { S.sons.page++; chercherSons(); };
  } catch (e) { r.innerHTML = `<p class="avert">${esc(e.message)}</p>`; }
}

/* -------------------------------------------------------- illustrations */
async function vueIllustrations() {
  const [ems, etat] = await Promise.all([api(`/api/packs/${S.pid}/illustrations`), api("/api/illustrations/etat")]);
  S.comfy = etat;
  const peutGenerer = etat.comfyui.connecte || (etat.comfyui.installe && etat.comfyui.modele_present);
  const groupes = [...new Set(ems.map((e) => e.groupe))];
  const ORIG = { fichier: ["image choisie", "ok"], generee: ["générée", "ok"], carte: ["carte-titre", "warn"] };
  $("#main").innerHTML = `
    <p class="aide">${peutGenerer ? "Décris chaque image en quelques mots, puis demande des propositions, ou dépose ton propre fichier."
      : `La génération d'images n'est pas disponible ${etat.capacites.verdict === "deconseille" ? "sur cet ordinateur" : "pour l'instant"} : dépose tes propres images (glisser-déposer sur une vignette). <a href="#/reglages">Réglages</a>`}
      L'encart montre l'image telle que la conteuse l'affichera (16 niveaux de gris).</p>
    ${groupes.map((g) => `<div class="groupe"><h2>${esc(g)}</h2><div class="vignettes">${ems.filter((e) => e.groupe === g).map((e) => `
      <div class="vign" data-slot="${e.slot}">
        <div class="imgs"><img src="${imgSlot(e.slot)}" alt=""><img class="gris" src="${imgSlot(e.slot, true)}" alt="aperçu en gris"></div>
        <div class="corps">
          <div class="rangee"><b style="flex:1">${esc(e.libelle)}</b><span class="pastille ${ORIG[e.origine][1]}">${ORIG[e.origine][0]}</span></div>
          <textarea data-desc placeholder="Description de l'image (ex. : un petit dragon vert qui sourit)">${esc(e.description || "")}</textarea>
          <div class="rangee">
            ${peutGenerer ? `<button class="bouton principal" data-prop>✨ Proposer</button>` : ""}
            <label class="bouton">📁 Déposer<input type="file" accept="image/*" hidden data-fichier></label>
            ${e.image ? `<button class="bouton" data-retirer title="Revenir à l'image décrite">↺</button>` : ""}
          </div>
        </div>
      </div>`).join("")}</div></div>`).join("")}`;
  $$(".vign").forEach((v) => {
    const slot = v.dataset.slot;
    const ta = $("[data-desc]", v); ta.dataset.orig = ta.value;
    ta.onblur = async () => {
      if (ta.value === ta.dataset.orig) return;
      try { await api(`/api/packs/${S.pid}/illustrations/${slot}/description`, { method: "POST", json: { texte: ta.value } }); ta.dataset.orig = ta.value; toast("Description enregistrée"); }
      catch (e) { toast(e.message, true); ta.value = ta.dataset.orig; }
    };
    $("[data-prop]", v)?.addEventListener("click", () => proposer(slot, ta.value));
    $("[data-fichier]", v).onchange = (e) => e.target.files[0] && deposer(slot, e.target.files[0]);
    $("[data-retirer]", v)?.addEventListener("click", async () => {
      try { await api(`/api/packs/${S.pid}/illustrations/${slot}/image`, { method: "DELETE" }); S.v = Date.now(); vueIllustrations(); }
      catch (e) { toast(e.message, true); }
    });
    v.ondragover = (e) => { e.preventDefault(); v.classList.add("survol"); };
    v.ondragleave = () => v.classList.remove("survol");
    v.ondrop = (e) => { e.preventDefault(); v.classList.remove("survol"); const f = e.dataTransfer.files[0]; if (f) deposer(slot, f); };
  });
}

async function deposer(slot, fichier) {
  const fd = new FormData(); fd.append("fichier", fichier);
  try { recadrer(slot, await api("/api/images/deposer", { method: "POST", body: fd })); }
  catch (e) { toast(e.message, true); }
}

async function proposer(slot, description) {
  const b = modale(`<h2>Propositions</h2><p class="aide">${esc(description || "")}</p><progress id="m-prog"></progress>
    <div class="journal" id="m-journal"></div><div class="rangee" style="margin-top:10px"><span style="flex:1"></span><button class="bouton" id="m-annul">Annuler</button></div>`);
  let t;
  $("#m-annul", b).onclick = async () => { if (t) await api(`/api/taches/${t.id}/annuler`, { method: "POST" }); fermer(); };
  try {
    t = await api(`/api/packs/${S.pid}/illustrations/${slot}/proposer`, { method: "POST", json: { description } });
    const s = await suivreTache(t, (s) => {
      const j = $("#m-journal"); if (j) j.textContent = s.journal.join("\n");
      const p = $("#m-prog"); if (p && s.progression != null) p.value = s.progression;
    });
    if ($("#modale").hidden) return;
    if (s.etat !== "terminée") { $("#m-journal").textContent += `\n${s.erreur || s.etat}`; return; }
    const b2 = modale(`<h2>Choisis une proposition</h2><div class="props">${s.resultat.map((p, k) => `<img src="/api/images/brouillons/${p.jeton}" data-k="${k}" alt="proposition ${k + 1}">`).join("")}</div>
      <div class="rangee" style="margin-top:10px"><button class="bouton" id="m-encore">✨ D'autres propositions</button><span style="flex:1"></span><button class="bouton" id="m-annul">Fermer</button></div>`);
    $$(".props img", b2).forEach((im) => (im.onclick = () => recadrer(slot, s.resultat[+im.dataset.k])));
    $("#m-encore", b2).onclick = () => proposer(slot, description);
    $("#m-annul", b2).onclick = fermer;
  } catch (e) { toast(e.message, true); fermer(); }
}

function recadrer(slot, d) {
  const b = modale(`<h2>Cadrer l'image</h2>
    <div class="recadrage">
      <div><div class="zone"><img id="m-img" src="/api/images/brouillons/${d.jeton}" alt=""><div class="cadre"><div class="poignee"></div></div></div>
        <p class="aide">Déplace le cadre et tire sur le rond pour l'agrandir. Le cadre garde la forme de l'écran (4:3).</p>
        ${d.avertissements.map((a) => `<p class="avert">⚠ ${esc(a)}</p>`).join("")}</div>
      <div class="apercus"><b>Sur l'écran (couleur puis gris)</b><img id="m-coul" alt=""><img id="m-gris" alt=""><div id="m-av"></div></div>
    </div>
    <div class="rangee" style="margin-top:12px"><span style="flex:1"></span><button class="bouton" id="m-annul">Annuler</button><button class="bouton principal" id="m-ok">Utiliser cette image</button></div>`);
  const img = $("#m-img", b), cadre = $(".cadre", b);
  let c = { ...d.cadre };
  const ech = () => img.clientWidth / d.largeur;
  const place = () => { const s = ech(); Object.assign(cadre.style, { left: c.x * s + "px", top: c.y * s + "px", width: c.l * s + "px", height: c.h * s + "px" }); };
  let tempo;
  const apercu = () => {
    clearTimeout(tempo);
    tempo = setTimeout(async () => {
      const corps = { jeton: d.jeton, cadre: c };
      for (const [id, g] of [["m-coul", false], ["m-gris", true]]) {
        const r = await fetch(`/api/images/apercu${g ? "?gris=true" : ""}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
        if (r.ok && $("#" + id)) $("#" + id).src = URL.createObjectURL(await r.blob());
      }
      const av = await api("/api/images/controle", { method: "POST", json: corps }).catch(() => ({ avertissements: [] }));
      if ($("#m-av")) $("#m-av").innerHTML = av.avertissements.length ? av.avertissements.map((a) => `<p class="avert">⚠ ${esc(a)}</p>`).join("") : `<p class="pastille ok">Lisible sur l'écran</p>`;
    }, 200);
  };
  const borne = () => {
    c.l = Math.max(40, Math.min(c.l, d.largeur)); c.h = Math.round(c.l * 3 / 4);
    if (c.h > d.hauteur) { c.h = d.hauteur; c.l = Math.round(c.h * 4 / 3); }
    c.x = Math.max(0, Math.min(c.x, d.largeur - c.l)); c.y = Math.max(0, Math.min(c.y, d.hauteur - c.h));
  };
  let drag = null;
  cadre.onpointerdown = (e) => {
    e.preventDefault(); cadre.setPointerCapture(e.pointerId);
    drag = { mode: e.target.classList.contains("poignee") ? "taille" : "deplace", x: e.clientX, y: e.clientY, c: { ...c } };
  };
  cadre.onpointermove = (e) => {
    if (!drag) return;
    const s = ech(), dx = (e.clientX - drag.x) / s, dy = (e.clientY - drag.y) / s;
    if (drag.mode === "deplace") { c.x = drag.c.x + dx; c.y = drag.c.y + dy; }
    else { c.l = drag.c.l + Math.max(dx, dy * 4 / 3); }
    c = { ...c, x: Math.round(c.x), y: Math.round(c.y), l: Math.round(c.l) }; borne(); place();
  };
  cadre.onpointerup = () => { if (drag) { drag = null; apercu(); } };
  if (img.complete) { place(); apercu(); } else img.onload = () => { place(); apercu(); };
  $("#m-annul", b).onclick = fermer;
  $("#m-ok", b).onclick = async () => {
    try { await api(`/api/packs/${S.pid}/illustrations/${slot}/image`, { method: "POST", json: { jeton: d.jeton, cadre: c } }); fermer(); S.v = Date.now(); toast("Image enregistrée"); vueIllustrations(); }
    catch (e) { toast(e.message, true); }
  };
}

/* ------------------------------------------------------------ réglages */
async function vueReglages() {
  const [r, four, etat] = await Promise.all([api("/api/reglages"), api("/api/sons/fournisseurs"), api("/api/illustrations/etat")]);
  const cf = r.illustrations.comfyui; const cap = etat.capacites; const ec = etat.comfyui;
  const VERDICT = { recommande: ["recommandée", "ok"], possible: ["possible, mais lente", "warn"], deconseille: ["déconseillée", "err"] };
  $("#main").innerHTML = `<div class="reglages">
    <section class="panneau"><h2>Sons</h2>
      ${four.fournisseurs.map((f) => `<div data-four="${f.id}"><p><b>${esc(f.nom)}</b> · <span class="aide">${esc(f.licences)}</span>
        <span class="pastille ${f.pret ? "ok" : "warn"}">${f.pret ? "prêt" : "à configurer"}</span></p>
        ${f.reglages.map((x) => { const v = r.sons[f.id]?.[x.cle]; return `<div class="champ"><label>${esc(x.libelle)}</label><div>
          <input type="${x.secret ? "password" : "text"}" data-cle="${x.cle}" autocomplete="off" placeholder="${x.secret && v?.renseignee ? `renseignée (…${esc(v.fin)}) : laisser vide pour la garder` : ""}">
          <p class="aide">${esc(x.aide)}</p></div></div>`; }).join("")}
        <div class="rangee"><button class="bouton principal" data-enr>Enregistrer</button><button class="bouton" data-test>Tester la connexion</button>
          ${f.reglages.some((x) => x.secret) ? `<button class="bouton" data-eff>Effacer la clé</button>` : ""}</div></div>`).join("")}
    </section>
    <section class="panneau"><h2>Illustrations</h2>
      <table class="tableau-cap"><tbody>
        <tr><td>Ordinateur</td><td>${esc(cap.systeme)}</td></tr>
        <tr><td>Carte graphique</td><td>${cap.gpus.length ? cap.gpus.map((g) => `${esc(g.nom)}${g.vram_go ? ` (${g.vram_go} Go)` : ""}`).join(", ") : "aucune carte NVIDIA détectée"}</td></tr>
        <tr><td>Mémoire vive</td><td>${cap.ram_go} Go</td></tr>
        <tr><td>Disque libre</td><td>${cap.disque_libre_go} Go</td></tr>
        <tr><td>Génération d'images</td><td><span class="pastille ${VERDICT[cap.verdict][1]}">${VERDICT[cap.verdict][0]}</span> ${cap.raisons.map(esc).join(" · ")}</td></tr>
        <tr><td>ComfyUI</td><td>${ec.connecte ? `<span class="pastille ok">en marche</span>` : ec.installe ? `<span class="pastille warn">installé, arrêté</span>` : `<span class="pastille">non installé</span>`}
          ${ec.installe && !ec.modele_present ? `<span class="pastille err">modèle ${esc(ec.modele)} absent</span>` : ""}</td></tr>
      </tbody></table>
      <div class="rangee" style="margin:10px 0">
        ${ec.installe && !ec.connecte ? `<button class="bouton principal" id="c-dem">Démarrer ComfyUI</button>` : ""}
        ${!ec.installe && cap.verdict !== "deconseille" ? `<button class="bouton principal" id="c-inst">Installer ComfyUI et le modèle (environ 20 Go)</button>` : ""}
        ${!ec.installe && cap.verdict === "deconseille" ? `<span class="aide">Sur cet ordinateur, dépose tes propres images dans l'onglet Illustrations.</span>` : ""}
      </div>
      ${etat.plan.length && cap.verdict !== "deconseille" ? `<details><summary>Ce que fera l'installation</summary><ol>${etat.plan.map((p) => `<li>${esc(p.titre)}${p.erreur ? ` <span class="avert">${esc(p.erreur)}</span>` : ""}</li>`).join("")}</ol></details>` : ""}
      <div id="c-tache" hidden><progress id="c-prog"></progress><div class="journal" id="c-journal"></div><button class="bouton" id="c-annul">Annuler</button></div>
      <h3>Génération</h3>
      <div class="champ"><label>Commande système (style)</label><div><textarea id="g-style" rows="4">${esc(r.illustrations.style)}</textarea>
        <p class="aide">Placée avant chaque description pour cadrer toutes les images : style, sujet unique, fond simple, fort contraste (l'écran est petit et en gris). En anglais, c'est plus efficace.</p></div></div>
      <div class="champ"><label>À éviter</label><textarea id="g-neg" rows="2">${esc(r.illustrations.negatif)}</textarea></div>
      <div class="champ"><label>Propositions par demande</label><input type="number" id="g-n" min="1" max="8" value="${r.illustrations.propositions}"></div>
      <details><summary>Réglages avancés de ComfyUI</summary>
        <div class="champ"><label>Adresse</label><input type="text" id="c-url" value="${esc(cf.url)}"></div>
        <div class="champ"><label>Dossier d'installation</label><input type="text" id="c-dossier" value="${esc(cf.dossier)}"></div>
        <div class="champ"><label>Python de ComfyUI</label><input type="text" id="c-python" value="${esc(cf.python)}"></div>
        <div class="champ"><label>Modèle</label><select id="c-modele">${[...new Set([cf.modele, ...ec.modeles])].map((m) => `<option ${m === cf.modele ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div>
        <div class="champ"><label>Étapes de calcul</label><input type="number" id="c-etapes" min="1" max="50" value="${cf.etapes}"></div>
      </details>
      <div class="rangee" style="margin-top:10px"><button class="bouton principal" id="g-enr">Enregistrer</button></div>
    </section></div>`;
  $$("[data-four]").forEach((sec) => {
    const fid = sec.dataset.four;
    const valeurs = () => Object.fromEntries($$("[data-cle]", sec).map((i) => [i.dataset.cle, i.value]));
    $("[data-enr]", sec).onclick = async () => { await api("/api/reglages", { method: "PUT", json: { sons: { [fid]: valeurs() } } }); toast("Enregistré"); vueReglages(); };
    $("[data-test]", sec).onclick = async () => {
      const v = valeurs(); if (Object.values(v).some(Boolean)) await api("/api/reglages", { method: "PUT", json: { sons: { [fid]: v } } });
      const t = await api(`/api/sons/fournisseurs/${fid}/tester`, { method: "POST" }); toast(t.message, !t.ok); if (t.ok) vueReglages();
    };
    $("[data-eff]", sec)?.addEventListener("click", async () => {
      const cles = Object.fromEntries($$("[data-cle]", sec).map((i) => [i.dataset.cle, null]));
      await api("/api/reglages", { method: "PUT", json: { sons: { [fid]: cles } } }); toast("Clé effacée"); vueReglages();
    });
  });
  $("#g-enr").onclick = async () => {
    await api("/api/reglages", { method: "PUT", json: { illustrations: {
      style: $("#g-style").value, negatif: $("#g-neg").value, propositions: +$("#g-n").value,
      comfyui: { url: $("#c-url").value, dossier: $("#c-dossier").value, python: $("#c-python").value, modele: $("#c-modele").value, etapes: +$("#c-etapes").value } } } });
    toast("Enregistré"); vueReglages();
  };
  const lancer = async (route, quoi) => {
    $("#c-tache").hidden = false;
    const t = await api(route, { method: "POST" }).catch((e) => { toast(e.message, true); return null; });
    if (!t) return;
    $("#c-annul").onclick = () => api(`/api/taches/${t.id}/annuler`, { method: "POST" });
    const s = await suivreTache(t, (s) => {
      $("#c-journal") && ($("#c-journal").textContent = s.journal.join("\n"));
      if ($("#c-prog")) s.progression != null ? ($("#c-prog").value = s.progression) : $("#c-prog").removeAttribute("value");
    });
    toast(s.etat === "terminée" ? `${quoi} : terminé` : `${quoi} : ${s.erreur || s.etat}`, s.etat !== "terminée");
    if (s.etat === "terminée") vueReglages();
  };
  $("#c-dem")?.addEventListener("click", () => lancer("/api/illustrations/comfyui/demarrer", "Démarrage"));
  $("#c-inst")?.addEventListener("click", () => {
    if (confirm("Télécharger et installer ComfyUI et le modèle d'images (environ 20 Go) ? L'installation peut prendre une heure.")) lancer("/api/illustrations/comfyui/installer", "Installation");
  });
}

route();
