// SPDX-License-Identifier: GPL-3.0-or-later
// Onglet Voix : on travaille les répliques d'un personnage, puis du suivant.
//   Pour chaque réplique : écouter, faire la voix, la refaire (nouvelle prise, on peut revenir aux
//   précédentes), l'enregistrer au micro ou déposer un fichier audio. Sans carte graphique adaptée,
//   seules l'écoute, le micro et le dépôt de fichiers sont proposés.
"use strict";

const V = { qui: null, moteur: null, tache: null, lecture: false };

async function vueVoix() {
  $("#main").innerHTML = `<p class="vide">Chargement…</p>`;
  const [pack, moteur] = await Promise.all([api(`/api/packs/${S.pid}`), api("/api/moteur-voix/etat")]);
  S.pack = pack; V.moteur = moteur;
  const persos = personnages(pack);
  if (!V.qui || !persos.find((p) => p.nom === V.qui)) V.qui = persos[0]?.nom;
  const pret = moteur.pret;
  const bandeau = pret ? "" : moteur.verdict === "deconseille"
    ? `<div class="bandeau">Cet ordinateur ne peut pas fabriquer les voix de synthèse (${esc(moteur.raisons.join(", "))}). Enregistre-les au micro 🎙 ou dépose des fichiers audio.</div>`
    : `<div class="bandeau">Les voix de synthèse ne sont pas encore installées. <a href="#/reglages">Les installer dans les Réglages</a>, ou enregistre au micro 🎙.</div>`;
  const total = persos.reduce((s, p) => s + p.manquantes, 0);
  $("#main").innerHTML = `${bandeau}
    <div class="voix-ed">
      <aside class="panneau voix-persos">
        <h2>Personnages</h2>
        <ul class="liste">${persos.map((p) => `<li class="perso${p.nom === V.qui ? " on" : ""}" data-qui="${esc(p.nom)}" title="${esc(p.description)}">
          <div class="info"><b>${esc(p.nom)}</b><small>${p.lignes.length} répliques · ${p.pretes} prêtes${p.enregistrees ? ` · ${p.enregistrees} 🎙` : ""}</small></div>
          ${p.manquantes ? `<span class="pastille warn" title="Voix à faire">${p.manquantes}</span>` : `<span class="pastille ok" title="Toutes ses voix sont prêtes">✓</span>`}</li>`).join("")}</ul>
        ${pret ? `<button class="bouton" id="v-tout" title="Fabriquer toutes les voix manquantes du pack, titre, questions et choix compris" ${total ? "" : "disabled"}>Faire toutes les voix (${total})</button>` : ""}
        <p class="aide">Moteur : ${moteur.en_marche ? "en marche (carte graphique occupée)" : pret ? "prêt, démarre à la demande" : "non disponible"}</p>
      </aside>
      <section id="v-perso"></section>
    </div>`;
  $$(".perso").forEach((li) => (li.onclick = () => { V.qui = li.dataset.qui; vueVoix(); }));
  $("#v-tout")?.addEventListener("click", () => tacheVoix({ tout: true }, "Toutes les voix"));
  rendrePerso(persos.find((p) => p.nom === V.qui), persos);
}

function personnages(pack) {
  const parQui = Object.fromEntries(pack.voix.map((v) => [v.nom, { ...v, lignes: [], pretes: 0, manquantes: 0, enregistrees: 0 }]));
  for (const sec of pack.sections) for (const l of sec.lignes) {
    if (l.kind !== "replique" || !parQui[l.qui]) continue;
    const p = parQui[l.qui];
    p.lignes.push({ ...l, sec });
    if (l.enregistrement) p.enregistrees++; else if (l.audio) p.pretes++; else p.manquantes++;
  }
  return Object.values(parQui).filter((p) => p.lignes.length);
}

function rendrePerso(p, persos) {
  const el = $("#v-perso"); if (!p) { el.innerHTML = `<p class="vide">Aucune réplique dans ce pack.</p>`; return; }
  const pret = V.moteur.pret;
  const k = persos.findIndex((x) => x.nom === p.nom);
  const suivant = persos[(k + 1) % persos.length];
  const opts = (list, val, vide) => (vide ? `<option value="">${esc(vide)}</option>` : "") + list.map((x) => `<option ${x === val ? "selected" : ""}>${esc(x)}</option>`).join("");
  let section = null;
  el.innerHTML = `
    <div class="panneau">
      <div class="rangee"><h2 style="flex:1;margin:0">${esc(p.nom)}</h2>
        ${persos.length > 1 ? `<button class="bouton" id="v-suiv" title="Passer au personnage suivant">${esc(suivant.nom)} →</button>` : ""}</div>
      <p class="aide">${esc(p.description || "")} · ton habituel : ${esc(p.ton || "neutre")}</p>
      <div class="rangee">
        ${pret ? `<button class="bouton principal" id="v-faire" title="Fabriquer les voix de synthèse qui manquent pour ce personnage" ${p.manquantes ? "" : "disabled"}>Faire ses voix (${p.manquantes})</button>` : ""}
        <button class="bouton" id="v-ecoute" title="Écouter ses répliques à la suite">${V.lecture ? "■ Arrêter" : "▶ Écouter ses répliques"}</button>
        <span class="aide">${p.lignes.length} répliques · ${p.pretes} voix de synthèse · ${p.enregistrees} enregistrées · ${p.manquantes} à faire</span>
      </div>
      <div id="v-tache" hidden><progress id="v-prog"></progress><span class="aide" id="v-msg"></span> <button class="bouton" id="v-annul" title="Arrêter la fabrication">Annuler</button></div>
    </div>
    <table class="voix-lignes"><tbody>${p.lignes.map((l, n) => {
      const entete = l.sec !== section ? ((section = l.sec), `<tr class="sep"><td colspan="4">${esc(l.sec.titre)}</td></tr>`) : "";
      return entete + `<tr data-n="${n}">
        <td class="t"><select data-f="ton" title="Ton de cette réplique">${opts(S.pack.tons, l.ton, "ton habituel (" + (l.ton_effectif || "neutre") + ")")}</select></td>
        <td><textarea data-f="texte" rows="1" title="Texte de la réplique : modifier le texte oblige à refaire la voix">${esc(l.texte)}</textarea></td>
        <td class="etat">${etatLigne(l, pret)}</td>
        <td class="a"><button class="bouton" data-micro="${n}" title="Enregistrer cette réplique au micro, ou déposer un fichier audio">🎙</button></td></tr>`;
    }).join("")}</tbody></table>`;
  const lignes = p.lignes;
  $("#v-suiv")?.addEventListener("click", () => { V.qui = suivant.nom; vueVoix(); });
  $("#v-faire")?.addEventListener("click", () => tacheVoix({ qui: p.nom }, `Voix de ${p.nom}`));
  $("#v-ecoute").onclick = () => (V.lecture ? arreterEcoute() : ecouterPerso(lignes));
  $$(".voix-lignes tr[data-n]").forEach((tr) => {
    const l = lignes[+tr.dataset.n];
    const cible = { section: l.sec.section, i: l.sec.i, j: l.j };
    const ta = $("textarea", tr);
    const fit = () => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + 2 + "px"; };
    fit(); ta.oninput = fit; ta.dataset.orig = ta.value;
    ta.onblur = () => { if (ta.value !== ta.dataset.orig) modifierLigne(cible, { texte: ta.value }); };
    $("select", tr).onchange = (e) => modifierLigne(cible, { ton: e.target.value });
    $("[data-micro]", tr).onclick = () => enregistrer(l, cible);
    $$("[data-act]", tr).forEach((b) => (b.onclick = () => actionLigne(b.dataset.act, l, cible, b)));
  });
}

function etatLigne(l, pret) {
  if (l.enregistrement) {
    return `<span class="pastille ok" title="Voix enregistrée : elle remplace la voix de synthèse">🎙 enregistrée</span>
      <button class="play" data-act="ecouter" title="Écouter l'enregistrement">▶</button>
      <button class="bouton petit" data-act="retirer" title="Supprimer l'enregistrement et revenir à la voix de synthèse">✕</button>`;
  }
  const prises = l.prises || [];
  const k = prises.indexOf(l.prise);
  const nav = prises.length > 1 ? `<span class="prises" title="Choisis la prise gardée pour l'histoire">
      <button class="bouton petit" data-act="prec" ${k <= 0 ? "disabled" : ""} title="Prise précédente">◀</button>
      prise ${k + 1}/${prises.length}
      <button class="bouton petit" data-act="suiv" ${k >= prises.length - 1 ? "disabled" : ""} title="Prise suivante">▶</button></span>` : "";
  if (l.audio) {
    return `<button class="play" data-act="ecouter" title="Écouter cette voix">▶</button>${nav}
      ${pret ? `<button class="bouton petit" data-act="refaire" title="Refaire la voix (nouvelle prise ; les précédentes restent disponibles)">↻ Refaire</button>` : ""}`;
  }
  return `<span class="manque" title="Voix pas encore faite">!</span>${nav}
    ${pret ? `<button class="bouton petit" data-act="faire" title="Fabriquer cette voix maintenant">Faire</button>` : `<span class="aide">à enregistrer</span>`}`;
}

async function modifierLigne(cible, change) {
  try { await api(`/api/packs/${S.pid}/ligne`, { method: "POST", json: { ...cible, ...change } }); toast("Enregistré · la voix est à refaire"); vueVoix(); }
  catch (e) { toast(e.message, true); vueVoix(); }
}

async function actionLigne(act, l, cible, bouton) {
  if (act === "ecouter") { jouer(l.enregistrement ? `/api/packs/${S.pid}/voix/fichier/${l.enregistrement.split("/").pop()}` : `/api/voix/${l.audio}`); return; }
  if (act === "prec" || act === "suiv") {
    const prises = l.prises; const k = prises.indexOf(l.prise) + (act === "prec" ? -1 : 1);
    const r = await api(`/api/packs/${S.pid}/voix/prise`, { method: "POST", json: { ...cible, prise: prises[k] } }).catch((e) => toast(e.message, true));
    if (r?.audio) jouer(`/api/voix/${r.audio}`);
    vueVoix(); return;
  }
  if (act === "retirer") {
    if (!confirm("Supprimer cet enregistrement ? La voix de synthèse sera utilisée à la place.")) return;
    await api(`/api/packs/${S.pid}/voix/enregistrement/retirer`, { method: "POST", json: cible }).catch((e) => toast(e.message, true));
    vueVoix(); return;
  }
  bouton.disabled = true; bouton.textContent = "…";
  const t = act === "refaire"
    ? await api(`/api/packs/${S.pid}/voix/refaire`, { method: "POST", json: cible }).catch((e) => (toast(e.message, true), null))
    : await api(`/api/packs/${S.pid}/voix/faire`, { method: "POST", json: { cibles: [[cible.section, cible.i, cible.j]] } }).catch((e) => (toast(e.message, true), null));
  if (!t) { vueVoix(); return; }
  const s = await suivreVoix(t);
  await vueVoix();
  if (s.etat === "terminée") {
    const l2 = personnages(S.pack).flatMap((p) => p.lignes).find((x) => x.sec.section === cible.section && x.sec.i === cible.i && x.j === cible.j);
    if (l2?.audio) jouer(`/api/voix/${l2.audio}`);  // on écoute tout de suite la nouvelle prise
  }
}

async function tacheVoix(demande, titre) {
  const t = await api(`/api/packs/${S.pid}/voix/faire`, { method: "POST", json: demande }).catch((e) => (toast(e.message, true), null));
  if (!t) return;
  await suivreVoix(t, titre);
  vueVoix();
}

async function suivreVoix(t, titre) {
  const box = $("#v-tache");
  if (box) { box.hidden = false; $("#v-msg").textContent = titre || "Fabrication de la voix…"; $("#v-annul").onclick = () => api(`/api/taches/${t.id}/annuler`, { method: "POST" }); }
  const s = await suivreTache(t, (s) => {
    const p = $("#v-prog"); if (p) { if (s.progression != null) p.value = s.progression; else p.removeAttribute("value"); }
    const m = $("#v-msg"); if (m) m.textContent = s.journal.slice(-1)[0] || titre || "";
  });
  if (s.etat === "erreur") toast(s.erreur, true);
  else if (s.etat === "terminée") toast("Voix prêtes");
  return s;
}

function ecouterPerso(lignes) {
  const files = lignes.map((l) => l.enregistrement ? `/api/packs/${S.pid}/voix/fichier/${l.enregistrement.split("/").pop()}` : l.audio ? `/api/voix/${l.audio}` : null).filter(Boolean);
  if (!files.length) { toast("Aucune voix prête pour ce personnage", true); return; }
  V.lecture = true; let k = 0;
  const suivante = () => { if (!V.lecture || k >= files.length) { V.lecture = false; const b = $("#v-ecoute"); if (b) b.textContent = "▶ Écouter ses répliques"; return; }
    audio.addEventListener("ended", suivante, { once: true }); jouer(files[k++]); };
  const b = $("#v-ecoute"); if (b) b.textContent = "■ Arrêter";
  suivante();
}
function arreterEcoute() { V.lecture = false; audio.pause(); const b = $("#v-ecoute"); if (b) b.textContent = "▶ Écouter ses répliques"; }

/* ------------------------------------------------------------- enregistrement */
function enregistrer(l, cible) {
  const b = modale(`<h2>Enregistrer la voix de ${esc(l.qui)}</h2>
    <div class="souffleur" title="Texte à lire">${esc(l.texte)}</div>
    ${l.didascalie ? `<p class="aide">Ton : ${esc(l.didascalie)}</p>` : ""}
    <div class="rangee micro">
      <button class="bouton principal gros" id="r-rec" title="Commencer ou arrêter l'enregistrement">● Enregistrer</button>
      <span id="r-temps" class="aide">0,0 s</span><canvas id="r-niveau" width="220" height="24" title="Niveau du micro"></canvas>
    </div>
    <audio id="r-ecoute" controls hidden></audio>
    <p class="aide">Ou dépose un fichier audio (MP3, WAV, M4A, OGG…) :</p>
    <label class="zone-depot" id="r-depot" title="Glisse un fichier ici, ou clique pour le choisir">Glisser un fichier ici, ou cliquer pour choisir<input type="file" accept="audio/*" hidden id="r-fichier"></label>
    <div class="rangee" style="margin-top:12px"><span style="flex:1"></span><button class="bouton" id="r-annul">Annuler</button>
      <button class="bouton principal" id="r-ok" disabled title="Garder cet enregistrement pour la réplique">Utiliser</button></div>`);
  let rec = null, flux = null, morceaux = [], blob = null, nom = "micro.webm", t0 = 0, minuterie = null, ctx = null;
  const fin = () => { flux?.getTracks().forEach((x) => x.stop()); clearInterval(minuterie); if (ctx && ctx.state !== "closed") ctx.close(); ctx = null; };
  const pret = (b2, n) => { blob = b2; nom = n; const a = $("#r-ecoute", b); a.src = URL.createObjectURL(b2); a.hidden = false; $("#r-ok", b).disabled = false; };
  $("#r-rec", b).onclick = async () => {
    if (rec && rec.state === "recording") { rec.stop(); return; }
    try { flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { toast("Micro inaccessible : " + e.message, true); return; }
    morceaux = []; rec = new MediaRecorder(flux);
    rec.ondataavailable = (e) => e.data.size && morceaux.push(e.data);
    rec.onstop = () => { fin(); $("#r-rec", b).textContent = "● Recommencer"; pret(new Blob(morceaux, { type: rec.mimeType || "audio/webm" }), "micro.webm"); };
    rec.start(); t0 = Date.now(); $("#r-rec", b).textContent = "■ Arrêter";
    minuterie = setInterval(() => ($("#r-temps", b).textContent = ((Date.now() - t0) / 1000).toFixed(1).replace(".", ",") + " s"), 100);
    // vu-mètre
    ctx = new AudioContext(); const an = ctx.createAnalyser(); ctx.createMediaStreamSource(flux).connect(an);
    const buf = new Uint8Array(an.fftSize), cv = $("#r-niveau", b), g = cv.getContext("2d");
    const dessine = () => { if (!rec || rec.state !== "recording") return; an.getByteTimeDomainData(buf);
      const v = Math.max(...buf.map((x) => Math.abs(x - 128))) / 128;
      g.clearRect(0, 0, cv.width, cv.height); g.fillStyle = v > 0.9 ? "#E95B67" : "#29C6D4"; g.fillRect(0, 4, cv.width * v, 16); requestAnimationFrame(dessine); };
    dessine();
  };
  const fichier = (f) => { if (f) pret(f, f.name); };
  $("#r-fichier", b).onchange = (e) => fichier(e.target.files[0]);
  const z = $("#r-depot", b);
  z.ondragover = (e) => { e.preventDefault(); z.classList.add("survol"); };
  z.ondragleave = () => z.classList.remove("survol");
  z.ondrop = (e) => { e.preventDefault(); z.classList.remove("survol"); fichier(e.dataTransfer.files[0]); };
  $("#r-annul", b).onclick = () => { fin(); fermer(); };
  $("#r-ok", b).onclick = async () => {
    const fd = new FormData(); fd.append("section", cible.section); fd.append("i", cible.i); fd.append("j", cible.j); fd.append("fichier", blob, nom);
    $("#r-ok", b).disabled = true; $("#r-ok", b).textContent = "…";
    try { await api(`/api/packs/${S.pid}/voix/enregistrement`, { method: "POST", body: fd }); fin(); fermer(); toast("Enregistrement gardé"); vueVoix(); }
    catch (e) { toast(e.message, true); $("#r-ok", b).disabled = false; $("#r-ok", b).textContent = "Utiliser"; }
  };
}
