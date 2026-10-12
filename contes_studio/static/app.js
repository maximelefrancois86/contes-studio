// SPDX-License-Identifier: GPL-3.0-or-later
// Éditeur de répliques : liste des packs, sections (histoires ou étapes), répliques éditables,
// écoute de la voix déjà synthétisée, lecture enchaînée.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const audio = $("#audio");
const S = { packs: [], pack: null, sec: 0, chain: false, cur: null };

function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.className = ""), err ? 6000 : 2000);
}
async function api(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

async function loadPacks() {
  S.packs = await api("/api/packs");
  $("#packs").innerHTML = S.packs.map((p) => `<a href="#${p.id}" data-id="${p.id}" class="${p.erreur ? "err" : ""}">
    ${esc(p.titre)}<small>${p.erreur ? "à corriger : " + esc(p.erreur.slice(0, 60)) : p.aventure ? `aventure · ${p.histoires} chemins` : `${p.histoires} histoires`}</small></a>`).join("");
}

async function openPack(id) {
  document.querySelectorAll("#packs a").forEach((a) => a.classList.toggle("on", a.dataset.id === id));
  const tok = (S.tok = (S.tok || 0) + 1);
  $("#main").innerHTML = `<p class="vide">Chargement…</p>`;
  let data;
  try { data = await api(`/api/packs/${id}`); } catch (e) { if (tok === S.tok) $("#main").innerHTML = `<p class="vide">${esc(e.message)}</p>`; return; }
  if (tok !== S.tok) return;  // un autre pack a été choisi entre-temps
  S.pack = data;
  S.sec = Math.min(S.sec, S.pack.sections.length - 1);
  render();
}

function render() {
  const p = S.pack; const sec = p.sections[S.sec];
  const reps = sec.lignes.filter((l) => l.kind === "replique");
  const manque = reps.filter((l) => !l.audio).length;
  const opts = (list, val, vide) => (vide ? `<option value="">${esc(vide)}</option>` : "") +
    list.map((x) => `<option ${x === val ? "selected" : ""}>${esc(x)}</option>`).join("");
  $("#main").innerHTML = `
    <h2>${esc(p.titre)}</h2>
    <div class="meta">${p.aventure ? "Aventure" : "Pack à questions"} · ${p.sections.length} ${p.aventure ? "étapes" : "histoires"}
      ${p.questions.length ? " · " + p.questions.map((q) => esc(q.texte)).join(" → ") : ""}</div>
    <div class="voix">${p.voix.map((v) => `<span title="${esc(v.description)}"><b>${esc(v.nom)}</b> · ${esc(v.ton || "neutre")}</span>`).join("")}</div>
    <div class="secs">${p.sections.map((s, k) => `<button data-k="${k}" class="${k === S.sec ? "on" : ""}">${esc(s.titre)}
      ${s.choix.length ? `<small>${esc(s.choix.join(" · "))}</small>` : ""}</button>`).join("")}</div>
    <div class="barre">
      <button id="chain">▶ Écouter à partir de la réplique choisie</button>
      <button id="stop">■ Arrêter</button>
      <span class="stat">${reps.length} répliques${manque ? ` · <b>${manque} à resynthétiser</b>` : " · toutes les voix sont prêtes"}</span>
    </div>
    <table><tbody>${sec.lignes.map((l) => l.kind === "replique" ? `
      <tr data-j="${l.j}">
        <td class="n">${l.j + 1}</td>
        <td class="q"><select data-f="qui">${opts(p.voix.map((v) => v.nom), l.qui)}</select></td>
        <td class="t"><select data-f="ton">${opts(p.tons, l.ton, "ton de la voix (" + (l.ton_effectif || "neutre") + ")")}</select></td>
        <td><textarea data-f="texte" rows="${Math.max(1, Math.ceil(l.texte.length / 90))}">${esc(l.texte)}</textarea></td>
        <td class="a">${l.audio ? `<button class="play" data-a="${esc(l.audio)}" title="Écouter">▶</button>`
          : `<span class="manque" title="Voix absente du cache : texte, ton ou personnage modifié. Elle sera synthétisée au prochain build.">!</span>`}</td>
      </tr>` : `<tr class="son"><td class="n">${l.j + 1}</td><td colspan="4">${l.kind === "pause" ? `pause ${l.pause ?? ""} s` : `${esc(l.kind)} : ${esc(l.son ?? "aucun")}`}</td></tr>`).join("")}
    </tbody></table>`;
  bind();
}

function bind() {
  document.querySelectorAll(".secs button").forEach((b) => (b.onclick = () => { S.sec = +b.dataset.k; stopChain(); render(); }));
  document.querySelectorAll("tr[data-j]").forEach((tr) => {
    const j = +tr.dataset.j;
    tr.onclick = (e) => { if (e.target.tagName !== "TEXTAREA" && e.target.tagName !== "SELECT") select(j); };
    const fit = (t) => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; };
    tr.querySelectorAll("textarea").forEach((t) => { fit(t); t.addEventListener("input", () => fit(t)); });
    tr.querySelectorAll("select").forEach((s) => (s.onchange = () => save(tr, { [s.dataset.f]: s.value })));
    const ta = tr.querySelector("textarea");
    ta.dataset.orig = ta.value;
    ta.onfocus = () => select(j, false);
    ta.onblur = () => { if (ta.value !== ta.dataset.orig) save(tr, { texte: ta.value }); };
    ta.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ta.blur(); } };
  });
  document.querySelectorAll(".play").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); stopChain(); play(b.dataset.a); }));
  $("#chain").onclick = () => { S.chain = true; playFrom(S.cur ?? firstJ()); };
  $("#stop").onclick = stopChain;
}

function select(j, scroll = true) {
  S.cur = j;
  document.querySelectorAll("tr[data-j]").forEach((tr) => tr.classList.toggle("cur", +tr.dataset.j === j));
  if (scroll) document.querySelector(`tr[data-j="${j}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function save(tr, change) {
  const j = +tr.dataset.j; const sec = S.pack.sections[S.sec];
  tr.classList.add("saving");
  try {
    const l = await api(`/api/packs/${S.pack.id}/ligne`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section: sec.section, i: sec.i, j, ...change }),
    });
    const k = sec.lignes.findIndex((x) => x.j === j); sec.lignes[k] = l;
    const y = window.scrollY; render(); window.scrollTo(0, y); select(j, false);
    toast(l.audio ? "Enregistré" : "Enregistré · la voix sera resynthétisée au prochain build");
  } catch (e) {
    tr.classList.remove("saving"); toast(e.message, true);
    const ta = tr.querySelector("textarea"); if (ta) ta.value = ta.dataset.orig;
  }
}

function play(name) { audio.src = `/api/voix/${name}`; audio.play().catch(() => {}); }
const reps = () => S.pack.sections[S.sec].lignes.filter((l) => l.kind === "replique");
const firstJ = () => reps()[0]?.j ?? 0;
function playFrom(j) {
  const l = reps().find((x) => x.j >= j && x.audio);
  if (!l) { stopChain(); return; }
  select(l.j); play(l.audio); S.playing = l.j;
}
function stopChain() { S.chain = false; audio.pause(); }
audio.onended = () => { if (S.chain) playFrom(S.playing + 1); };

window.addEventListener("hashchange", () => openPack(location.hash.slice(1)));
loadPacks().then(() => { if (location.hash) openPack(location.hash.slice(1)); });
