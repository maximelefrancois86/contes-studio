// SPDX-License-Identifier: GPL-3.0-or-later
// Onglet Flot : éditeur du graphe d'une aventure.
//   Couverture (une sortie) ── étape (un fichier audio) ──▶ Décision (une entrée, une sortie par choix) ──▶ …
//   Cliquer une sortie libre crée une étape ; la bulle au bout de l'étape s'accroche à l'entrée d'une décision
//   (ou reste libre : fin de l'histoire). Grille, zoom (Ctrl + molette), déplacement (glisser le fond), ascenseurs.
//   Images et voix sont visibles et écoutables directement dans les nœuds ; chaque élément a une infobulle.
"use strict";

const F = { zoom: 1, sel: null, g: null, pos: null, monde: { l: 2400, h: 1400 }, lecture: null };
const DW = 250, HDR = 58, ROW = 46, PIED = 30, JR = 14, CW = 176, CH = 168, GAP = 270, AW = 196, AH = 48;

function geomDecision(d) { return { l: DW, h: HDR + d.options.length * ROW + PIED }; }
const tip = (t) => `<title>${esc(t)}</title>`;
const coupe = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
function deuxLignes(s, n) {
  // coupe aux espaces : [ligne 1, ligne 2 (tronquée si besoin)]
  const mots = s.split(/\s+/); let a = "";
  while (mots.length && (a + " " + mots[0]).trim().length <= n) a = (a + " " + mots.shift()).trim();
  if (!a) a = mots.shift() || "";
  return [coupe(a, n), coupe(mots.join(" "), n)];
}

async function vueFlot() {
  $("#main").innerHTML = `<p class="vide">Chargement…</p>`;
  const g = await api(`/api/packs/${S.pid}/graphe`);
  if (g.type === "questions") return vueFlotQuestions();
  if (F.pid !== S.pid) { F.pid = S.pid; F.zoom = 1; F.sel = null; }  // autre atelier : vue remise à zéro
  F.g = g; F.sel = F.sel && trouver(F.sel) ? F.sel : null;
  F.pos = { noeuds: { ...(g.positions?.noeuds || {}) }, bulles: { ...(g.positions?.bulles || {}) } };
  disposer();
  $("#main").innerHTML = `
    <div class="flot-ed">
      <div class="flot-corps">
        <aside class="flot-palette">
          <h3>Glisser pour ajouter</h3>
          <div class="pal pal-dec" draggable="true" title="Glisse sur la grille pour créer une décision : l'histoire s'arrête et l'enfant choisit entre plusieurs choix.">◆ Décision</div>
          <h3>Légende</h3>
          <div class="pal pal-couv" title="La couverture : image et titre du pack. Sa sortie mène à la première étape.">▣ Couverture</div>
          <div class="pal pal-etape" title="Une étape : des répliques lues d'affilée, un seul fichier audio. Elle va d'une sortie à l'entrée d'une décision, ou se termine (fin de l'histoire).">▭ Étape</div>
          <div class="pal pal-jon" title="Suite automatique : l'histoire continue sans question vers l'étape suivante.">↦ Suite</div>
          <h3>Vue</h3>
          <div class="seg"><button id="f-zm" title="Zoom arrière (ou Ctrl + molette)">−</button><button id="f-zv" title="Revenir à la taille réelle">100 %</button><button id="f-zp" title="Zoom avant (ou Ctrl + molette)">＋</button></div>
          <button class="bouton" id="f-ajust" title="Ajuster le zoom pour voir tout le graphe">Tout voir</button>
          <button class="bouton" id="f-reorg" title="Replacer tous les nœuds automatiquement, de gauche à droite">Réorganiser</button>
          <p class="aide">Glisser le fond pour se déplacer · Suppr pour effacer la sélection · double-clic pour ouvrir</p>
        </aside>
        <div class="flot-vue" id="f-vue"><div id="f-toile"></div></div>
        <aside class="panneau flot-panneau" id="f-panneau"></aside>
      </div>
    </div>`;
  dessiner(); marquerSel(); panneau();
  const vue = $("#f-vue");
  vue.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoomer(F.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX, e.clientY);
  }, { passive: false });
  $("#f-zm").onclick = () => zoomer(F.zoom / 1.2);
  $("#f-zp").onclick = () => zoomer(F.zoom * 1.2);
  $("#f-zv").onclick = () => zoomer(1);
  $("#f-ajust").onclick = toutVoir;
  $("#f-reorg").onclick = async () => { F.pos = { noeuds: {}, bulles: {} }; disposer(); dessiner(); await sauverPositions(); };
  $(".pal-dec").ondragstart = (e) => e.dataTransfer.setData("text/plain", "decision");
  vue.ondragover = (e) => e.preventDefault();
  vue.ondrop = async (e) => {
    e.preventDefault();
    if (e.dataTransfer.getData("text/plain") !== "decision") return;
    const [x, y] = pointMonde(e);
    const r = await op({ op: "creer_decision" });
    if (r) { F.pos.noeuds[r.resultat] = [Math.round((x - 20) / 10) * 10, Math.round((y - 20) / 10) * 10]; await sauverPositions(); F.sel = { type: "decision", id: r.resultat }; dessiner(); panneau(); }
  };
  document.onkeydown = (e) => {
    if (S.onglet !== "flot" || ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
    if ((e.key === "Delete" || e.key === "Backspace") && F.sel) { e.preventDefault(); supprimerSel(); }
  };
}

function trouver(sel) {
  if (sel.type === "decision") return F.g.decisions.find((d) => d.id === sel.id);
  if (sel.type === "arc") return F.g.arcs.find((a) => a.id === sel.id);
  if (sel.type === "couverture") return true;
  return null;
}

/* ------------------------------------------------------------- disposition */
function noeudsGraphe() {
  const n = [{ id: "couverture", type: "couverture" }];
  F.g.decisions.forEach((d) => n.push({ id: d.id, type: "decision", d }));
  F.g.jonctions.forEach((j) => n.push({ id: j.id, type: "jonction", j }));
  return n;
}
function origineNoeud(o) { return o.type === "depart" ? "couverture" : o.type === "option" ? o.decision : o.jonction; }

function disposer() {
  const noeuds = noeudsGraphe();
  // arcs qui reviennent en arrière (boucles : labyrinthe, histoire sans fin) : ignorés pour placer les colonnes
  const succ = {};
  for (const a of F.g.arcs) if (a.vers) for (const o of a.origines) (succ[origineNoeud(o)] ||= []).push(a.vers);
  const etat = {}, retour = new Set();
  const dfs = (n) => { etat[n] = 1; for (const m of succ[n] || []) { if (etat[m] === 1) retour.add(n + ">" + m); else if (!etat[m]) dfs(m); } etat[n] = 2; };
  dfs("couverture");
  const niveau = { couverture: 0 };
  for (let tour = 0; tour < noeuds.length + 2; tour++) {
    for (const a of F.g.arcs) {
      if (!a.vers) continue;
      for (const o of a.origines) {
        const src = origineNoeud(o);
        if (retour.has(src + ">" + a.vers)) continue;
        if (niveau[src] !== undefined && (niveau[a.vers] === undefined || niveau[a.vers] < niveau[src] + 1)) niveau[a.vers] = niveau[src] + 1;
      }
    }
  }
  const colonnes = {};
  noeuds.forEach((n) => {
    if (F.pos.noeuds[n.id]) return;
    const k = niveau[n.id] ?? (Math.max(0, ...Object.values(niveau)) + 1);
    (colonnes[k] ||= []).push(n);
  });
  const largeur = (n) => (n.type === "decision" ? DW : n.type === "couverture" ? CW : 2 * JR);
  const hauteur = (n) => (n.type === "decision" ? geomDecision(n.d).h : n.type === "couverture" ? CH : 2 * JR);
  let x = 40;
  Object.keys(colonnes).map(Number).sort((a, b) => a - b).forEach((k) => {
    const liste = colonnes[k];
    const total = liste.reduce((s, n) => s + hauteur(n) + 70, -70);
    let y = Math.max(40, 240 - total / 2);
    const lmax = Math.max(...liste.map(largeur));
    liste.forEach((n) => { F.pos.noeuds[n.id] = [x + (lmax - largeur(n)) / 2, y]; y += hauteur(n) + 70; });
    x += lmax + GAP;
  });
  majMonde();
}

function majMonde() {
  let l = 1600, h = 900;
  for (const [id, [x, y]] of Object.entries(F.pos.noeuds)) {
    const d = F.g.decisions.find((z) => z.id === id);
    l = Math.max(l, x + (d ? DW : CW) + 600); h = Math.max(h, y + (d ? geomDecision(d).h : CH) + 400);
  }
  for (const [x, y] of Object.values(F.pos.bulles)) { l = Math.max(l, x + 600); h = Math.max(h, y + 400); }
  const v = $("#f-vue");  // la grille remplit toujours la vue, même dézoomée
  if (v) { l = Math.max(l, (v.clientWidth - 2) / F.zoom); h = Math.max(h, (v.clientHeight - 2) / F.zoom); }
  F.monde = { l, h };
}

/* ------------------------------------------------------------- ports */
function portEntree(id) {
  const p = F.pos.noeuds[id]; if (!p) return null;
  if (id.startsWith("j:")) return [p[0], p[1] + JR];
  return [p[0], p[1] + HDR / 2];
}
function portSortie(o) {
  if (o.type === "depart") { const p = F.pos.noeuds.couverture; return [p[0] + CW, p[1] + CH / 2]; }
  if (o.type === "jonction") { const p = F.pos.noeuds[o.jonction]; return p && [p[0] + 2 * JR, p[1] + JR]; }
  const d = F.g.decisions.find((z) => z.id === o.decision); const p = F.pos.noeuds[o.decision];
  if (!d || !p) return null;
  const k = d.options.findIndex((x) => x.id === o.option);
  return [p[0] + DW, p[1] + HDR + k * ROW + ROW / 2];
}
function finArc(a) {
  if (a.vers) return portEntree(a.vers);
  if (F.pos.bulles[a.id]) return F.pos.bulles[a.id];
  const o = a.origines[0]; const s = o && portSortie(o); if (!s) return [40, 40];
  return [s[0] + AW + 90, s[1]];
}

/* ------------------------------------------------------------- dessin */
function courbe([x1, y1], [x2, y2]) {
  if (x2 < x1 + 60) {  // retour en arrière (boucle) : l'arc fait le tour par en dessous des nœuds
    const xa = x1 + AW + 40, yb = Math.max(y1, y2) + 170;
    return `M${x1},${y1} H${xa - 60} C${xa + 40},${y1} ${xa + 40},${yb} ${xa - 60},${yb} H${x2 - 60} C${x2 - 150},${yb} ${x2 - 150},${y2} ${x2},${y2}`;
  }
  const h = Math.min(AW + 20, Math.max(0, x2 - x1 - 40)); const m = Math.max(50, Math.abs(x2 - x1 - h) / 2);
  return `M${x1},${y1} H${x1 + h} C${x1 + h + m},${y1} ${x2 - m},${y2} ${x2},${y2}`;
}
const bouton = (x, y, attrs, symbole, aide, r = 11) =>
  `<g class="btn" ${attrs} transform="translate(${x},${y})"><circle r="${r}"/><text y="4" text-anchor="middle">${symbole}</text>${tip(aide)}</g>`;

function dessiner() {
  majMonde();
  const { l, h } = F.monde;
  const g = F.g;
  const arcs = g.arcs.map((a) => {
    if (!a.origines.length) return dessinOrphelin(a);
    const fin = finArc(a);
    return a.origines.map((o, k) => {
      const debut = portSortie(o); if (!debut) return "";
      const cx = o.type === "option" || o.type === "depart" ? debut[0] + 14 + AW / 2 : (debut[0] + fin[0]) / 2;
      const cy = o.type === "option" || o.type === "depart" ? debut[1] : (debut[1] + fin[1]) / 2;
      const etat = a.repliques ? `${a.repliques} répliques${a.manquantes ? ` · ${a.manquantes} voix à faire` : ""}` : "aucune réplique";
      if (a.lien) {  // lien direct : pas d'audio, on passe tout droit à la suite
        return `<g class="arc lien" data-arc="${esc(a.id)}">
          <path class="trait" d="${courbe(debut, fin)}"/><path class="prise" d="${courbe(debut, fin)}">${tip("Lien direct : l'histoire passe tout droit à la suite, sans audio. Double-clic pour y ajouter des répliques.")}</path>
          ${k === 0 ? `<g class="carte-etape lien" transform="translate(${debut[0] + 16},${debut[1] - 12})"><rect width="92" height="24" rx="12"/>
            <text x="46" y="16" text-anchor="middle" class="petit">lien direct</text>${tip("Lien direct (sans audio). Double-clic : ajouter des répliques pour en faire une étape.")}</g>
            <circle class="bulle accrochee" data-bulle="${esc(a.id)}" cx="${fin[0]}" cy="${fin[1]}" r="7">${tip("Bout du lien : glisse-le sur une autre décision, ou dans le vide pour finir ici")}</circle>` : ""}
        </g>`;
      }
      return `<g class="arc${a.repliques ? "" : " vide"}" data-arc="${esc(a.id)}">
        <path class="trait" d="${courbe(debut, fin)}"/><path class="prise" d="${courbe(debut, fin)}">${tip("Étape « " + a.titre + " » : clique pour la sélectionner, double-clique pour écrire ses répliques")}</path>
        ${k === 0 ? `<g class="carte-etape" transform="translate(${cx - AW / 2},${cy - AH / 2})">
          <rect width="${AW}" height="${AH}" rx="9"/>${tip("Étape « " + a.titre + " » : " + etat + ". Double-clic : écrire les répliques et les sons.")}
          <text x="10" y="19" class="t">${esc(coupe(a.titre, a.audios.length ? 17 : 20))}</text><text x="10" y="36" class="petit">${esc(etat)}</text>
          ${a.audios.length ? bouton(AW - 44, AH / 2, `data-ecoute="${esc(a.id)}"`, F.lecture === a.id ? "■" : "▶", "Écouter l'étape (voix déjà prêtes, enchaînées)") : ""}
          ${bouton(AW - 17, AH / 2, `data-ouvrir="${esc(a.id)}"`, "✎", "Écrire les répliques et les sons de cette étape")}
        </g>` : ""}
        ${k === 0 ? `<circle class="bulle${a.vers ? " accrochee" : ""}" data-bulle="${esc(a.id)}" cx="${fin[0]}" cy="${fin[1]}" r="9">${tip(a.vers ? "Bout de l'étape, accroché. Glisse-le ailleurs pour changer la suite, ou dans le vide pour finir l'histoire ici." : "Bout de l'étape : l'histoire se termine ici. Glisse-le sur l'entrée ○ d'une décision pour continuer.")}</circle>` : ""}
      </g>`;
    }).join("");
  }).join("");
  const p0 = F.pos.noeuds.couverture;
  const couv = `<g class="noeud couv" data-noeud="couverture" transform="translate(${p0[0]},${p0[1]})">
    <rect class="corps" width="${CW}" height="${CH}" rx="12"/>${tip("Couverture du pack : son image et son titre. Double-clic pour les voir en grand.")}
    <rect class="tete" width="${CW}" height="26" rx="12"/><text x="12" y="18" class="t">Couverture</text>
    <image href="${imgSlot("couverture")}" x="10" y="32" width="${CW - 20}" height="${(CW - 20) * 3 / 4}" preserveAspectRatio="xMidYMid slice"/>
    ${g.couverture.audio ? bouton(CW - 22, CH - 18, `data-voix="${esc(g.couverture.audio)}"`, "▶", "Écouter le titre lu par le narrateur") : ""}
    <circle class="port sortie${g.depart.arc ? " pris" : ""}" data-sortie='{"type":"depart"}' cx="${CW}" cy="${CH / 2}" r="9">${tip(g.depart.arc ? "Sortie : mène à la première étape" : "Sortie : clique pour créer la première étape")}</circle></g>`;
  const decs = g.decisions.map((d) => {
    const p = F.pos.noeuds[d.id]; const gd = geomDecision(d);
    const q = d.question || "(question à écrire)";
    return `<g class="noeud dec" data-noeud="${esc(d.id)}" transform="translate(${p[0]},${p[1]})">
      <rect class="corps" width="${DW}" height="${gd.h}" rx="12"/>${tip("Décision : l'histoire s'arrête et l'enfant choisit avec la molette. Clique pour modifier, double-clic pour voir images et voix.")}
      <rect class="tete" width="${DW}" height="${HDR}" rx="12"/>
      ${(([l1, l2]) => `<text x="14" y="24" class="q">${esc(l1)}</text><text x="14" y="43" class="q">${esc(l2)}</text>`)(deuxLignes(q, d.audio ? 25 : 29))}
      ${d.audio ? bouton(DW - 22, HDR / 2, `data-voix="${esc(d.audio)}"`, "▶", "Écouter la question") : ""}
      <circle class="port entree" data-entree="${esc(d.id)}" cx="0" cy="${HDR / 2}" r="10">${tip("Entrée : dépose ici la bulle ● d'une étape pour qu'elle mène à cette décision")}</circle>
      ${d.options.map((o, k) => `<g class="option" transform="translate(0,${HDR + k * ROW})">
        <line x1="8" x2="${DW - 8}" y1="0" y2="0"/>
        ${o.slot ? `<image href="${imgSlot(o.slot)}" x="10" y="5" width="48" height="36" preserveAspectRatio="xMidYMid slice">${tip("Image du choix (onglet Illustrations)")}</image>` : ""}
        <text x="66" y="${ROW / 2 + 5}">${esc(coupe(o.nom, 18))}</text>
        ${o.audio ? bouton(DW - 50, ROW / 2, `data-voix="${esc(o.audio)}"`, "▶", "Écouter ce choix", 10) : ""}
        ${o.arc ? "" : bouton(DW - 74, ROW / 2, `data-retirer="${esc(o.id)}" data-dec="${esc(d.id)}"`, "−", "Retirer ce choix", 9)}
        <circle class="port sortie${o.arc ? " pris" : ""}" data-sortie='${esc(JSON.stringify({ type: "option", decision: d.id, option: o.id }))}' cx="${DW}" cy="${ROW / 2}" r="9">${tip(o.arc ? "Sortie de « " + o.nom + " » : mène à son étape" : "Sortie de « " + o.nom + " » : clique pour créer l'étape qui suit ce choix")}</circle>
        ${o.arc ? "" : `<text class="plus" x="${DW}" y="${ROW / 2 + 4}" text-anchor="middle">+</text>`}</g>`).join("")}
      <g transform="translate(0,${HDR + d.options.length * ROW})"><line x1="8" x2="${DW - 8}" y1="0" y2="0"/>
        ${bouton(22, PIED / 2, `data-ajouter="${esc(d.id)}"`, "＋", "Ajouter un choix", 9)}<text x="38" y="${PIED / 2 + 4}" class="petit">ajouter un choix</text></g>
    </g>`;
  }).join("");
  const jons = g.jonctions.map((j) => {
    const p = F.pos.noeuds[j.id];
    return `<g class="noeud jon" data-noeud="${esc(j.id)}" transform="translate(${p[0]},${p[1]})">
      <circle class="corps" cx="${JR}" cy="${JR}" r="${JR}"/><text x="${JR}" y="${JR + 4}" text-anchor="middle">↦</text>
      <circle class="port entree" data-entree="${esc(j.id)}" cx="0" cy="${JR}" r="7">${tip("Entrée d'une suite automatique : dépose ici la bulle d'une étape pour qu'elle continue sans question")}</circle>
      ${tip("Suite automatique : l'histoire continue sans question")}</g>`;
  }).join("");
  let svg = $("#f-svg");
  if (!svg) {
    $("#f-toile").innerHTML = `<svg id="f-svg">
      <defs><pattern id="f-grille" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="var(--grille)" stroke-width="1"/></pattern>
        <pattern id="f-grille2" width="100" height="100" patternUnits="userSpaceOnUse"><rect width="100" height="100" fill="url(#f-grille)"/><path d="M100 0H0V100" fill="none" stroke="var(--grille2)" stroke-width="1.2"/></pattern></defs>
      <rect id="f-fond" fill="url(#f-grille2)"/><g id="f-contenu"></g></svg>`;
    svg = $("#f-svg");
    interactions();
  }
  svg.setAttribute("width", l * F.zoom); svg.setAttribute("height", h * F.zoom); svg.setAttribute("viewBox", `0 0 ${l} ${h}`);
  $("#f-fond").setAttribute("width", l); $("#f-fond").setAttribute("height", h);
  $("#f-contenu").innerHTML = arcs + couv + decs + jons;
  $("#f-zv").textContent = Math.round(F.zoom * 100) + " %";
  marquerSel();
}

function marquerSel() {
  $$("#f-contenu .sel").forEach((x) => x.classList.remove("sel"));
  const s = F.sel; if (!s) return;
  const el = s.type === "couverture" ? $('[data-noeud="couverture"]') : s.type === "decision" ? $(`[data-noeud="${CSS.escape(s.id)}"]`)
    : $$(`[data-arc="${CSS.escape(s.id)}"]`)[0];
  el?.classList.add("sel");
}

function dessinOrphelin(a) {
  const p = F.pos.bulles["o:" + a.id] || [40, 40];
  return `<g class="arc orphelin" data-arc="${esc(a.id)}"><g class="carte-etape" transform="translate(${p[0]},${p[1]})"><rect width="${AW}" height="${AH}" rx="9"/>
    <text x="10" y="28" class="t">${esc(coupe(a.titre, 18))} (isolée)</text>${tip("Étape reliée à rien : supprime-la, ou relie un choix à elle dans le YAML")}</g></g>`;
}

/* ------------------------------------------------------------- écoute */
function ecouterEtape(id) {
  if (F.lecture === id) { F.lecture = null; audio.pause(); dessiner(); return; }
  const a = F.g.arcs.find((x) => x.id === id); if (!a?.audios.length) return;
  F.lecture = id; let k = 0;
  const suivante = () => {
    if (F.lecture !== id || k >= a.audios.length) { if (F.lecture === id) F.lecture = null; dessiner(); return; }
    audio.addEventListener("ended", suivante, { once: true }); jouer(`/api/voix/${a.audios[k++]}`);
  };
  dessiner(); suivante();
}

/* ------------------------------------------------------------- interactions */
function pointMonde(e) {
  const r = $("#f-svg").getBoundingClientRect();
  return [(e.clientX - r.left) / F.zoom, (e.clientY - r.top) / F.zoom];
}

function zoomer(z, cx, cy) {
  const v = $("#f-vue"); z = Math.min(2.5, Math.max(0.1, z));
  const r = v.getBoundingClientRect();
  cx ??= r.left + v.clientWidth / 2; cy ??= r.top + v.clientHeight / 2;
  const wx = (v.scrollLeft + cx - r.left) / F.zoom, wy = (v.scrollTop + cy - r.top) / F.zoom;
  F.zoom = z; dessiner();
  v.scrollLeft = wx * z - (cx - r.left); v.scrollTop = wy * z - (cy - r.top);
}

function toutVoir() {
  const v = $("#f-vue");
  let mx = 0, my = 0;
  for (const [id, [x, y]] of Object.entries(F.pos.noeuds)) {
    const d = F.g.decisions.find((z) => z.id === id);
    mx = Math.max(mx, x + (d ? DW : CW)); my = Math.max(my, y + (d ? geomDecision(d).h : CH));
  }
  for (const [x, y] of Object.values(F.pos.bulles)) { mx = Math.max(mx, x + 20); my = Math.max(my, y + 20); }
  zoomer(Math.max(0.35, Math.min(1.2, (v.clientWidth - 20) / (mx + 60), (v.clientHeight - 20) / (my + 60))));
  v.scrollLeft = 0; v.scrollTop = 0;
}

let sauverTempo, enAttente = [];
function sauverPositions() {
  clearTimeout(sauverTempo);
  return new Promise((ok) => {
    enAttente.push(ok);
    sauverTempo = setTimeout(async () => {
      const attente = enAttente; enAttente = [];
      await api(`/api/packs/${S.pid}/graphe/positions`, { method: "PUT", json: F.pos }).catch((e) => toast(e.message, true));
      attente.forEach((f) => f());
    }, 300);
  });
}

async function op(corps) {
  try {
    const r = await api(`/api/packs/${S.pid}/graphe`, { method: "POST", json: corps });
    const pos = F.pos; F.g = r.graphe; F.pos = pos; disposer(); dessiner(); panneau();
    return r;
  } catch (e) { toast(e.message, true); return null; }
}

function optionsDe(d) { return d.options.map((o) => ({ id: o.id, nom: o.nom })); }

function interactions() {
  const svg = $("#f-svg"), vue = $("#f-vue");
  let drag = null;
  svg.onpointerdown = async (e) => {
    const t = e.target;
    const btn = t.closest(".btn");
    if (btn) {
      e.stopPropagation();
      if (btn.dataset.voix) { F.lecture = null; jouer(`/api/voix/${btn.dataset.voix}`); }
      else if (btn.dataset.ecoute) ecouterEtape(btn.dataset.ecoute);
      else if (btn.dataset.ouvrir) ouvrirArc(btn.dataset.ouvrir);
      else if (btn.dataset.ajouter) {
        const d = F.g.decisions.find((x) => x.id === btn.dataset.ajouter);
        await op({ op: "modifier_decision", decision: d.id, options: [...optionsDe(d), { nom: `Choix ${d.options.length + 1}` }] });
      } else if (btn.dataset.retirer) {
        const d = F.g.decisions.find((x) => x.id === btn.dataset.dec);
        await op({ op: "modifier_decision", decision: d.id, options: optionsDe(d).filter((o) => o.id !== btn.dataset.retirer) });
      }
      return;
    }
    const sortie = t.closest("[data-sortie]"), bulle = t.closest("[data-bulle]"), noeud = t.closest("[data-noeud]"), arc = t.closest("[data-arc]");
    if (sortie) {
      e.stopPropagation();
      const o = JSON.parse(sortie.dataset.sortie);
      if (sortie.classList.contains("pris")) {
        const a = F.g.arcs.find((x) => x.origines.some((y) => JSON.stringify(y) === JSON.stringify(o)));
        if (a) { F.sel = { type: "arc", id: a.id }; marquerSel(); panneau(); }
        return;
      }
      creerArc(o); return;
    }
    if (bulle) { drag = { type: "bulle", id: bulle.dataset.bulle }; svg.setPointerCapture(e.pointerId); return; }
    if (noeud) {
      const id = noeud.dataset.noeud; const p0 = F.pos.noeuds[id];
      drag = { type: "noeud", id, dep: pointMonde(e), p0: [...p0], bouge: false }; svg.setPointerCapture(e.pointerId);
      return;
    }
    if (arc) { F.sel = { type: "arc", id: arc.dataset.arc }; marquerSel(); panneau(); return; }
    drag = { type: "fond", x: e.clientX, y: e.clientY, sl: vue.scrollLeft, st: vue.scrollTop }; svg.setPointerCapture(e.pointerId);
    svg.classList.add("main");
  };
  svg.onpointermove = (e) => {
    if (!drag) return;
    if (drag.type === "fond") { vue.scrollLeft = drag.sl - (e.clientX - drag.x); vue.scrollTop = drag.st - (e.clientY - drag.y); return; }
    const [x, y] = pointMonde(e);
    if (drag.type === "noeud") {
      if (Math.abs(x - drag.dep[0]) + Math.abs(y - drag.dep[1]) > 3) drag.bouge = true;
      if (!drag.bouge) return;
      const nx = Math.round((drag.p0[0] + x - drag.dep[0]) / 10) * 10, ny = Math.round((drag.p0[1] + y - drag.dep[1]) / 10) * 10;
      F.pos.noeuds[drag.id] = [Math.max(0, nx), Math.max(0, ny)]; dessiner();
      return;
    }
    if (drag.type === "bulle") {
      F.pos.bulles[drag.id] = [x, y];
      const a = F.g.arcs.find((z) => z.id === drag.id); const vers = a.vers; a.vers = null; dessiner(); a.vers = vers;
      drag.cible = entreeProche(x, y);
      $$("[data-entree]").forEach((c) => c.classList.toggle("vise", c.dataset.entree === drag.cible));
    }
  };
  svg.onpointerup = async () => {
    const d = drag; drag = null; svg.classList.remove("main");
    if (!d) return;
    if (d.type === "noeud") {
      if (d.bouge) { await sauverPositions(); return; }
      F.sel = d.id === "couverture" ? { type: "couverture" } : d.id.startsWith("j:") ? null : { type: "decision", id: d.id };
      marquerSel(); panneau(); return;
    }
    if (d.type === "bulle") {
      const a = F.g.arcs.find((z) => z.id === d.id);
      if (d.cible && d.cible !== a.vers) { delete F.pos.bulles[a.id]; await sauverPositions(); await op({ op: "attacher", arc: a.id, cible: d.cible }); }
      else if (!d.cible && a.vers) { await sauverPositions(); await op({ op: "attacher", arc: a.id, cible: null }); }
      else { if (d.cible) delete F.pos.bulles[a.id]; await sauverPositions(); dessiner(); }
    }
  };
  svg.ondblclick = (e) => {
    const sous = document.elementFromPoint(e.clientX, e.clientY) || e.target;
    if (sous.closest(".btn")) return;
    const noeud = sous.closest("[data-noeud]"), arc = sous.closest("[data-arc]");
    if (arc && !noeud) { ouvrirArc(arc.dataset.arc); return; }
    if (!noeud) return;
    const id = noeud.dataset.noeud;
    if (id === "couverture") ficheCouverture();
    else if (!id.startsWith("j:")) ficheDecision(id);
  };
}

function entreeProche(x, y) {
  let best = null, dmin = 36;
  for (const n of [...F.g.decisions.map((d) => d.id), ...F.g.jonctions.map((j) => j.id)]) {
    const p = portEntree(n); if (!p) continue;
    const dd = Math.hypot(p[0] - x, p[1] - y);
    if (dd < dmin) { dmin = dd; best = n; }
  }
  return best;
}

async function creerArc(origine) {
  const r = await op({ op: "creer_arc", origine });
  if (!r) return;
  const s = portSortie(origine);
  F.pos.bulles[r.resultat] = [s[0] + AW + 90, s[1]];
  await sauverPositions(); F.sel = { type: "arc", id: r.resultat }; dessiner(); panneau();
  toast("Nouvelle étape : glisse sa bulle ● sur l'entrée d'une décision, ou laisse-la libre pour finir l'histoire.");
}

function ouvrirArc(id) {
  const a = F.g.arcs.find((x) => x.id === id);
  if (a) location.hash = `#/atelier/${S.pid}/repliques/${a.section}`;
}

async function supprimerSel() {
  const s = F.sel; if (!s) return;
  if (s.type === "arc") {
    const a = trouver(s);
    if (confirm(`Supprimer l'étape « ${a.titre} » et ses ${a.repliques} répliques ?`)) { F.sel = null; await op({ op: "supprimer_arc", arc: a.id }); }
  } else if (s.type === "decision") {
    const d = trouver(s);
    if (confirm(`Supprimer la décision « ${d.question} » ?`)) { if (await op({ op: "supprimer_decision", decision: d.id })) { delete F.pos.noeuds[d.id]; F.sel = null; sauverPositions(); dessiner(); panneau(); } }
  }
}

/* ------------------------------------------------------------- panneau latéral */
function panneau() {
  const el = $("#f-panneau"); if (!el) return;
  const todo = F.g.a_completer;
  const bas = `<h3>${todo.length ? "À compléter avant fabrication" : "Prêt à fabriquer"}</h3>
    ${todo.length ? `<ul class="todo">${todo.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : `<p class="pastille ok">Le graphe est complet</p>`}`;
  const s = F.sel; const x = s && trouver(s);
  if (s?.type === "decision" && x) {
    el.innerHTML = `<h2>Décision</h2>
      <label class="aide">Question posée à l'enfant</label><textarea id="p-q" rows="2" title="Lue par le narrateur quand l'histoire s'arrête">${esc(x.question)}</textarea>
      <label class="aide">Choix (dans l'ordre de la molette)</label>
      <div id="p-opts">${x.options.map((o) => `<div class="rangee p-opt" data-id="${esc(o.id)}"><input type="text" value="${esc(o.nom)}" style="flex:1" title="Nom du choix, lu par le narrateur">
        <button class="bouton" data-suppr title="${o.arc ? "Ce choix mène à une étape : supprime d'abord l'étape" : "Retirer ce choix"}" ${o.arc ? "disabled" : ""}>✕</button></div>`).join("")}</div>
      <div class="rangee" style="margin:8px 0"><button class="bouton" id="p-plus" title="Ajouter un choix">＋ Choix</button><span style="flex:1"></span><button class="bouton principal" id="p-ok" title="Enregistrer la question et les choix">Enregistrer</button></div>
      <div class="rangee"><button class="bouton" id="p-fiche" title="Voir les images des choix et écouter les voix">Images et voix…</button><button class="bouton" id="p-del" title="Supprimer cette décision (touche Suppr)">Supprimer</button></div>
      <p class="aide">${x.partagee ? "Plusieurs étapes peuvent mener à cette décision." : "Une seule étape mène ici ; glisse d'autres bulles sur son entrée pour la partager."}</p>${bas}`;
    $("#p-plus").onclick = () => $("#p-opts").insertAdjacentHTML("beforeend", `<div class="rangee p-opt" data-id=""><input type="text" placeholder="Nouveau choix" style="flex:1"><button class="bouton" data-suppr title="Retirer ce choix">✕</button></div>`);
    $("#p-opts").onclick = (e) => { const b = e.target.closest("[data-suppr]"); if (b && !b.disabled) b.parentElement.remove(); };
    $("#p-ok").onclick = () => op({ op: "modifier_decision", decision: x.id, question: $("#p-q").value,
      options: $$(".p-opt").map((r) => ({ id: r.dataset.id || null, nom: $("input", r).value.trim() })).filter((o) => o.nom) });
    $("#p-fiche").onclick = () => ficheDecision(x.id);
    $("#p-del").onclick = supprimerSel;
  } else if (s?.type === "arc" && x) {
    const fin = x.lien ? "lien direct : aucune réplique, l'histoire passe tout droit à la suite"
      : x.vers ? (x.vers.startsWith("j:") ? "continue sans question" : "mène à une décision") : "fin de l'histoire";
    el.innerHTML = `<h2>Étape</h2><label class="aide">Titre</label><input type="text" id="p-t" value="${esc(x.titre)}" style="width:100%" title="Titre de l'étape (pour toi ; il n'est pas lu)">
      <p class="aide">${x.repliques} répliques · ${fin}${x.manquantes ? ` · ${x.manquantes} voix à faire` : ""}</p>
      <div class="rangee"><button class="bouton principal" id="p-ouvrir" title="Ouvrir l'onglet Répliques sur cette étape">Écrire les répliques</button>
        ${x.audios.length ? `<button class="bouton" id="p-ecoute" title="Écouter les voix déjà prêtes, enchaînées">▶ Écouter</button>` : ""}
        <button class="bouton" id="p-del" title="Supprimer cette étape (touche Suppr)">Supprimer</button></div>${bas}`;
    $("#p-t").onchange = (e) => op({ op: "renommer_arc", arc: x.id, titre: e.target.value });
    $("#p-ouvrir").onclick = () => ouvrirArc(x.id);
    $("#p-ecoute")?.addEventListener("click", () => ecouterEtape(x.id));
    $("#p-del").onclick = supprimerSel;
  } else if (s?.type === "couverture") {
    el.innerHTML = `<h2>Couverture</h2><img src="${imgSlot("couverture")}" style="width:100%;border-radius:8px">
      <div class="rangee" style="margin:8px 0">${F.g.couverture.audio ? `<button class="play" id="p-a" title="Écouter le titre">▶</button> <span>« ${esc(F.g.titre)} »</span>` : `<span class="aide">Le titre sera lu à la prochaine fabrication</span>`}</div>
      <button class="bouton" id="p-ill" title="Ouvrir l'onglet Illustrations">Changer l'image…</button>${bas}`;
    $("#p-a")?.addEventListener("click", () => jouer(`/api/voix/${F.g.couverture.audio}`));
    $("#p-ill").onclick = () => (location.hash = `#/atelier/${S.pid}/illustrations`);
  } else {
    el.innerHTML = `<h2>${esc(F.g.titre)}</h2><p class="aide">${F.g.arcs.length} étapes · ${F.g.decisions.length} décisions.
      Clique un élément pour le modifier ; double-clique pour l'ouvrir.</p>${bas}`;
  }
}

/* ------------------------------------------------------------- fiches (double-clic) */
function ficheDecision(id) {
  const d = F.g.decisions.find((x) => x.id === id); if (!d) return;
  const b = modale(`<h2>${esc(d.question || "Décision")}</h2>
    <div class="rangee" style="margin-bottom:12px">${d.audio ? `<button class="play" data-voix="${esc(d.audio)}" title="Écouter la question">▶</button> question lue par le narrateur`
      : `<span class="manque" title="Pas encore synthétisée">!</span> <span class="aide">La question sera lue à la prochaine fabrication.</span>`}</div>
    <div class="vignettes">${d.options.map((o) => `<div class="vign"><div class="imgs">
      ${o.slot ? `<img src="${imgSlot(o.slot)}" alt=""><img class="gris" src="${imgSlot(o.slot, true)}" alt="" title="Telle que la conteuse l'affichera">` : ""}</div>
      <div class="corps"><b>${esc(o.nom)}</b><div class="rangee">${o.audio ? `<button class="play" data-voix="${esc(o.audio)}" title="Écouter ce choix">▶</button> choix lu`
        : `<span class="manque" title="Pas encore synthétisé">!</span> <span class="aide">pas encore lu</span>`}</div>
        <span class="aide">${o.arc ? `mène à « ${esc(F.g.arcs.find((a) => a.id === o.arc)?.titre || o.arc)} »` : "ne mène encore nulle part"}</span></div></div>`).join("")}</div>
    <div class="rangee" style="margin-top:12px"><button class="bouton" id="m-ill" title="Ouvrir l'onglet Illustrations">Modifier les images…</button><span style="flex:1"></span><button class="bouton" id="m-f">Fermer</button></div>`);
  $$("[data-voix]", b).forEach((x) => (x.onclick = () => jouer(`/api/voix/${x.dataset.voix}`)));
  $("#m-f", b).onclick = fermer;
  $("#m-ill", b).onclick = () => { fermer(); location.hash = `#/atelier/${S.pid}/illustrations`; };
}

function ficheCouverture() {
  const b = modale(`<h2>${esc(F.g.titre)}</h2><div class="rangee" style="align-items:start">
    <img src="${imgSlot("couverture")}" style="width:320px;border-radius:8px" title="En couleur"><img src="${imgSlot("couverture", true)}" style="width:320px;border-radius:8px" title="Telle que la conteuse l'affichera"></div>
    <div class="rangee" style="margin-top:10px">${F.g.couverture.audio ? `<button class="play" id="m-a" title="Écouter le titre">▶</button> titre lu par le narrateur` : ""}<span style="flex:1"></span><button class="bouton" id="m-f">Fermer</button></div>`);
  $("#m-a", b)?.addEventListener("click", () => jouer(`/api/voix/${F.g.couverture.audio}`));
  $("#m-f", b).onclick = fermer;
}
