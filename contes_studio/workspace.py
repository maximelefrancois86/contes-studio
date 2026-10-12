# SPDX-License-Identifier: GPL-3.0-or-later
"""Accès aux packs (fichiers YAML de histoires/) : lecture pour l'éditeur et modification d'une réplique.

Une modification ne réécrit que la ligne concernée du fichier : les commentaires (univers, plans
d'histoires), l'ordre des clés et la mise en forme restent intacts. Le pack modifié est vérifié
avec le chargeur du générateur avant d'être enregistré ; en cas d'erreur, rien n'est écrit.
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from lunii_gen.story import _parse_line, load_pack as _load_pack
from lunii_gen.tones import get_tone

SECTIONS = ("histoires", "etapes")


def load_pack(path, strict: bool = False):
    """L'atelier travaille sur des brouillons : un pack en construction reste ouvrable et modifiable.
    La vérification complète (celle du build) se fait avec strict=True."""
    return _load_pack(path, brouillon=not strict)
_PLAIN = re.compile(r"^[A-Za-zÀ-ÿ0-9_\-]+$")


from .edition import EditError, ajouter_cle, definir_champ, inserer_element, plain, rt


def _rt() -> YAML:
    return rt()


def _scalar(v) -> str:
    """Valeur YAML sur une ligne : identifiant nu si possible, sinon chaîne entre guillemets doubles."""
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return repr(v)
    v = str(v)
    if _PLAIN.match(v) and v.lower() not in ("yes", "no", "true", "false", "null", "on", "off", "y", "n"):
        return v
    return json.dumps(v, ensure_ascii=False)


@dataclass
class Workspace:
    root: Path

    @property
    def stories_dir(self) -> Path:
        return self.root / "histoires"

    def pack_path(self, pid: str) -> Path:
        p = self.stories_dir / f"{pid}.yaml"
        if "/" in pid or "\\" in pid or pid.startswith(".") or not p.is_file():
            raise EditError(f"Pack inconnu : {pid!r}")
        return p

    def packs(self) -> list[dict]:
        out = []
        for f in sorted(self.stories_dir.glob("*.yaml")):
            try:
                pk = load_pack(f)
                out.append({"id": f.stem, "titre": pk.title, "aventure": pk.adventure or _est_aventure(f),
                            "histoires": len(pk.stories), "erreur": None})
            except Exception as e:  # noqa: BLE001  (brouillon en cours)
                out.append({"id": f.stem, "titre": f.stem, "aventure": False, "histoires": 0, "erreur": str(e)})
        return out

    # -- lecture ---------------------------------------------------------------
    def pack(self, pid: str, audio_path=None) -> dict:
        """Structure du pack pour l'éditeur. `audio_path(texte, voix, ton)` -> chemin du son en cache ou None."""
        path = self.pack_path(pid)
        pk = load_pack(path)
        raw = _rt().load(path.read_text(encoding="utf-8"))
        sections = []
        for sec in SECTIONS:
            for i, item in enumerate(raw.get(sec) or []):
                lines = []
                for j, rl in enumerate(item.get("lignes") or []):
                    try:
                        ln = _parse_line(rl)
                    except ValueError as e:
                        lines.append({"j": j, "kind": "erreur", "texte": str(e)})
                        continue
                    if ln.kind:
                        lines.append({"j": j, "kind": ln.kind, "son": ln.sound})
                    elif ln.speaker is None and not ln.text:
                        lines.append({"j": j, "kind": "pause", "pause": ln.pause})
                    else:
                        qui = ln.speaker or pk.narrator
                        voice = pk.voices.get(qui)
                        ton = ln.tone or (voice.tone if voice else None)
                        d = {"j": j, "kind": "replique", "qui": qui, "ton": ln.tone, "ton_effectif": ton,
                             "texte": ln.text, "pause": ln.pause or None, "prise": ln.prise,
                             "didascalie": _didascalie(ton),
                             "enregistrement": ln.audio if ln.audio and (path.parent / ln.audio).exists() else None}
                        if audio_path and voice:
                            ap = audio_path(ln.text, voice, ton, ln.prise)
                            d["audio"] = ap.name if ap and ap.exists() else None
                            prises = getattr(audio_path, "__self__", None)
                            if prises is not None and hasattr(prises, "prises"):
                                d["prises"] = prises.prises(ln.text, voice, ton, ln.prise)
                        lines.append(d)
                sections.append({"section": sec, "i": i, "id": str(item.get("id", i)),
                                 "titre": item.get("titre") or str(item.get("id", i)),
                                 "choix": [str(c) for c in item.get("choix") or []],
                                 "ambiance": (str(item["ambiance"]) if item.get("ambiance") not in (None, "aucune", "aucun", "rien") else None),
                                 "lignes": lines})
        return {
            "id": pid, "titre": pk.title, "description": pk.description, "aventure": pk.adventure or "etapes" in raw,
            "narrateur": pk.narrator,
            "voix": [{"nom": v.name, "description": v.description, "ton": v.tone} for v in pk.voices.values()],
            "tons": sorted({t for t in _all_tones()}),
            "questions": [{"texte": q.text, "options": [{"id": o.id, "nom": o.label} for o in q.options]}
                          for q in pk.questions],
            "sections": sections,
        }

    # -- flot ------------------------------------------------------------------
    def flot(self, pid: str) -> dict:
        """Graphe des choix : arbre questions → options → histoires, ou graphe des étapes d'une aventure."""
        pk = load_pack(self.pack_path(pid))
        noeuds = [{"id": "c", "type": "couverture", "titre": pk.title, "slot": "couverture"}]
        aretes = []
        if not pk.adventure:
            vus = set()
            for i, st in enumerate(pk.stories):
                parent = "c"
                for k, choix in enumerate(st.choices):
                    nid = "o:" + "/".join(st.choices[: k + 1])
                    if nid not in vus:
                        vus.add(nid)
                        q = pk.questions[k]
                        o = q.option(choix)
                        noeuds.append({"id": nid, "type": "option", "titre": o.label, "question": q.text,
                                       "slot": f"q{k}-{choix}", "niveau": k + 1})
                        aretes.append({"de": parent, "vers": nid})
                    parent = nid
                hid = f"h:{i}"
                noeuds.append({"id": hid, "type": "histoire", "titre": st.title, "section": "histoires", "i": i,
                               "slot": f"h{i}", "niveau": len(st.choices) + 1})
                aretes.append({"de": parent, "vers": hid})
            return {"type": "questions", "questions": [q.text for q in pk.questions], "noeuds": noeuds, "aretes": aretes}
        etapes = list(pk.steps.values())
        index = {st.id: si for si, st in enumerate(etapes)}
        aretes.append({"de": "c", "vers": f"e:{pk.start}"})
        for si, st in enumerate(etapes):
            noeuds.append({"id": f"e:{st.id}", "type": "etape", "titre": st.title, "section": "etapes", "i": si,
                           "slot": f"e{si}", "fin": not st.next and not st.choice})
            if st.next:
                aretes.append({"de": f"e:{st.id}", "vers": f"e:{st.next}"})
            if st.choice:
                qid = f"q:{st.id}"
                noeuds.append({"id": qid, "type": "question", "titre": st.choice.text})
                aretes.append({"de": f"e:{st.id}", "vers": qid})
                for o in st.choice.options:
                    if o.target in index:
                        aretes.append({"de": qid, "vers": f"e:{o.target}", "libelle": o.label,
                                       "slot": f"e{si}-{o.id}"})
        return {"type": "aventure", "noeuds": noeuds, "aretes": aretes}

    # -- graphe (aventures) ----------------------------------------------------
    def graphe(self, pid: str, audio_path=None) -> dict:
        from .graphe import Graphe, lire_positions

        path = self.pack_path(pid)
        raw = _rt().load(path.read_text(encoding="utf-8"))
        if "etapes" not in raw and raw.get("histoires"):
            return {"type": "questions"}
        pk = load_pack(path)
        g = Graphe(raw)
        v = g.vue()
        ems = {tuple(map(str, e["chemin"])): e["slot"] for e in self.emplacements(pid)}
        idx = {sid: k for k, sid in enumerate(g.ids_etapes())}
        narr = pk.voices.get(pk.narrator)

        def audio(texte):
            if not (audio_path and narr and texte):
                return None
            ap = audio_path(texte, narr, "enjoué")
            return ap.name if ap and ap.exists() else None

        for d in v["decisions"]:
            d["audio"] = audio(d["question"])
            for o in d["options"]:
                o["audio"] = audio(o["nom"])
                chemin = (("etapes", str(idx[d["id"][1:]]), "ensuite", "options", o["id"]) if d["id"].startswith("@")
                          else ("decisions", d["id"], "options", o["id"]))
                o["slot"] = ems.get(chemin)
        etapes = {str(e.get("id")): e for e in raw.get("etapes") or []}
        for a in v["arcs"]:
            a["section"] = idx[a["id"]]
            a["slot"] = f"e{idx[a['id']]}"
            # voix déjà synthétisées de l'étape, dans l'ordre (écoute enchaînée depuis le graphe)
            a["audios"], a["manquantes"] = [], 0
            for rl in etapes[a["id"]].get("lignes") or []:
                try:
                    ln = _parse_line(rl)
                except ValueError:
                    continue
                if ln.kind or not ln.text:
                    continue
                vx = pk.voices.get(ln.speaker or pk.narrator)
                ap = audio_path(ln.text, vx, ln.tone or vx.tone) if (audio_path and vx) else None
                if ap and ap.exists():
                    a["audios"].append(ap.name)
                else:
                    a["manquantes"] += 1
        v.update({"type": "aventure", "titre": pk.title, "couverture": {"slot": "couverture", "audio": audio(pk.title)},
                  "positions": lire_positions(self.stories_dir / pid / "flot.json")})
        return v

    def graphe_op(self, pid: str, op: dict) -> dict:
        from .graphe import Graphe

        path = self.pack_path(pid)
        raw = _rt().load(path.read_text(encoding="utf-8"))
        g = Graphe(raw)
        nom = op.get("op")
        res = None
        if nom == "creer_arc":
            res = g.creer_arc(op["origine"], op.get("titre") or "Nouvelle étape")
        elif nom == "attacher":
            g.attacher(op["arc"], op.get("cible"))
        elif nom == "creer_decision":
            res = g.creer_decision(op.get("question") or "Que va faire le héros ?")
        elif nom == "modifier_decision":
            g.modifier_decision(op["decision"], op.get("question"), op.get("options"))
        elif nom == "supprimer_decision":
            g.supprimer_decision(op["decision"])
        elif nom == "supprimer_arc":
            g.supprimer_arc(op["arc"])
        elif nom == "renommer_arc":
            g.renommer_arc(op["arc"], op["titre"])
        else:
            raise EditError(f"Opération inconnue : {nom!r}")
        self._check_and_write(path, g.texte())
        return {"resultat": res}

    def ecrire_positions(self, pid: str, pos: dict) -> None:
        from .graphe import ecrire_positions

        self.pack_path(pid)
        ecrire_positions(self.stories_dir / pid / "flot.json", pos)

    def creer_pack(self, titre: str, narrateur: str = "conteur") -> str:
        """Nouvel atelier : une aventure vide, prête à être construite dans l'onglet Flot."""
        from lunii_gen import voices

        from .graphe import slug

        titre = titre.strip()
        if not titre:
            raise EditError("Il faut un titre")
        if narrateur not in voices.names() and narrateur not in voices.ALIASES:
            raise EditError(f"Voix inconnue : {narrateur!r}")
        base = slug(titre, "atelier")
        pid, n = base, 2
        while (self.stories_dir / f"{pid}.yaml").exists():
            pid, n = f"{base}-{n}", n + 1
        texte = (f"# Atelier créé avec l'atelier d'histoires.\n"
                 f"titre: {json.dumps(titre, ensure_ascii=False)}\n"
                 f"narrateur: narrateur\n"
                 f"voix:\n  narrateur: {narrateur}\n"
                 f"etapes: []\n")
        path = self.stories_dir / f"{pid}.yaml"
        self.stories_dir.mkdir(parents=True, exist_ok=True)
        self._check_and_write(path, texte, nouveau=True)
        return pid

    # -- sons ------------------------------------------------------------------
    def sons(self, pid: str) -> list[dict]:
        """Catalogue `sons:` du pack : définition, usages, présence en cache et crédit."""
        from lunii_gen.sons import Sonotheque

        path = self.pack_path(pid)
        pk = load_pack(path)
        raw = _rt().load(path.read_text(encoding="utf-8"))
        usages: dict[str, int] = {}
        for sec in SECTIONS:
            for item in raw.get(sec) or []:
                for k in ("ambiance", "intro"):
                    if item.get(k):
                        usages[str(item[k])] = usages.get(str(item[k]), 0) + 1
                for rl in item.get("lignes") or []:
                    if isinstance(rl, dict):
                        for k in ("bruit", "musique", "ambiance"):
                            if rl.get(k):
                                usages[str(rl[k])] = usages.get(str(rl[k]), 0) + 1
        sono = Sonotheque(self.root / ".cache" / "sons")
        out = []
        for sid, spec in pk.sounds.items():
            wav = sono.cache_dir / f"{sono._key(sid, spec)}.wav"
            meta = wav.with_suffix(".json")
            out.append({"id": sid, "spec": spec, "usages": usages.get(sid, 0),
                        "fichier": wav.name if wav.exists() else None,
                        "credit": json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None})
        return out

    def chemin_son(self, pid: str, sid: str) -> Path | None:
        from lunii_gen.sons import Sonotheque

        pk = load_pack(self.pack_path(pid))
        if sid not in pk.sounds:
            return None
        sono = Sonotheque(self.root / ".cache" / "sons")
        p = sono.cache_dir / f"{sono._key(sid, pk.sounds[sid])}.wav"
        return p if p.exists() else None

    def ajouter_son(self, pid: str, sid: str, spec: dict) -> str:
        """Ajoute un son au catalogue du pack ; renvoie l'identifiant retenu (suffixe si déjà pris)."""
        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        base = re.sub(r"[^a-z0-9]+", "-", _sans_accents(sid).lower()).strip("-")[:30] or "son"
        existants = set(map(str, (raw.get("sons") or {}).keys()))
        final, n = base, 2
        while final in existants:
            final, n = f"{base}-{n}", n + 1
        self._check_and_write(path, ajouter_cle(src, raw, "sons", final, spec))
        return final

    def inserer_son(self, pid: str, section: str, i: int, apres: int, genre: str, sid: str) -> None:
        """Insère `{bruit: sid}` ou `{musique: sid}` après la ligne `apres` de section[i]."""
        if genre not in ("bruit", "musique"):
            raise EditError(f"Genre de son inconnu : {genre!r}")
        path = self.pack_path(pid)
        if sid not in load_pack(path).sounds:
            raise EditError(f"Son absent du catalogue : {sid!r}")
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        self._check_and_write(path, inserer_element(src, raw, [section, i, "lignes"], apres, {genre: sid}))

    def definir_ambiance(self, pid: str, section: str, i: int, sid: str | None) -> None:
        path = self.pack_path(pid)
        if sid and sid not in load_pack(path).sounds:
            raise EditError(f"Son absent du catalogue : {sid!r}")
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        if section == "etapes" and not sid:
            sid = "aucune"  # une étape déclare toujours son ambiance (fichier audio à part)
        self._check_and_write(path, definir_champ(src, raw, [section, i], "ambiance", sid))

    # -- illustrations ---------------------------------------------------------
    def emplacements(self, pid: str) -> list[dict]:
        """Toutes les images du pack (couverture, options, histoires, étapes), avec la graine du build."""
        path = self.pack_path(pid)
        pk = load_pack(path)
        raw = _rt().load(path.read_text(encoding="utf-8"))
        out = []

        def ajout(slot, libelle, chemin, node, graine, groupe):
            d = node if isinstance(node, dict) else {}
            out.append({"slot": slot, "libelle": str(libelle), "chemin": chemin, "groupe": groupe,
                        "description": d.get("illustration"), "image": d.get("image"), "graine": graine,
                        "titre_carte": str(libelle)})

        ajout("couverture", pk.title, [], raw, 1, "Couverture")
        for qi, q in enumerate(raw.get("questions") or []):
            opts = q.get("options") or {}
            items = list(opts.items()) if isinstance(opts, dict) else [(o.get("id"), o) for o in opts]
            for oi, (oid, o) in enumerate(items):
                chemin = ["questions", qi, "options", oid if isinstance(opts, dict) else oi]
                nom = o if isinstance(o, str) else (o.get("nom") or o.get("label") or oid)
                ajout(f"q{qi}-{oid}", nom, chemin, o, 100 * (qi + 1) + oi, q.get("question") or f"Question {qi + 1}")
        for i, h in enumerate(raw.get("histoires") or []):
            ajout(f"h{i}", h.get("titre", f"Histoire {i + 1}"), ["histoires", i], h, 1000 + i, "Histoires")
        for si, e in enumerate(raw.get("etapes") or []):
            ajout(f"e{si}", e.get("titre", e.get("id")), ["etapes", si], e, 1000 + si, "Étapes")
            ens = e.get("ensuite")
            if isinstance(ens, dict):
                opts = ens.get("options") or {}
                items = list(opts.items()) if isinstance(opts, dict) else [(o.get("id"), o) for o in opts]
                for oi, (oid, o) in enumerate(items):
                    chemin = ["etapes", si, "ensuite", "options", oid if isinstance(opts, dict) else oi]
                    nom = o if isinstance(o, str) else (o.get("nom") or oid)
                    ajout(f"e{si}-{oid}", nom, chemin, o, 100 * (si + 1) + oi, ens.get("question") or e.get("titre"))
        premiere = {}
        for si, e in enumerate(raw.get("etapes") or []):
            ens = e.get("ensuite")
            if ens is not None and not isinstance(ens, dict):
                premiere.setdefault(str(ens), si)
        for did, q in (raw.get("decisions") or {}).items():
            did = str(did)
            si = premiere.get(did, len(raw.get("etapes") or []))
            opts = q.get("options") or {}
            items = list(opts.items()) if isinstance(opts, dict) else [(o.get("id"), o) for o in opts]
            for oi, (oid, o) in enumerate(items):
                chemin = ["decisions", did, "options", oid if isinstance(opts, dict) else oi]
                nom = o if isinstance(o, str) else (o.get("nom") or oid)
                ajout(f"d{did}-{oid}", nom, chemin, o, 100 * (si + 1) + oi, q.get("question") or did)
        # les images de la couverture et des histoires sans description retombent sur une carte-titre
        for d in out:
            d["sans_image"] = not d["image"] and not d["description"]
        return out

    def emplacement(self, pid: str, slot: str) -> dict:
        for d in self.emplacements(pid):
            if d["slot"] == slot:
                return d
        raise EditError(f"Image inconnue : {slot!r}")

    def definir_description(self, pid: str, slot: str, texte: str | None) -> None:
        e = self.emplacement(pid, slot)
        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        self._check_and_write(path, definir_champ(src, raw, e["chemin"], "illustration", (texte or "").strip() or None))

    def definir_image(self, pid: str, slot: str, relatif: str | None) -> None:
        """`relatif` : chemin de l'image relatif au dossier histoires/ (None : revenir à la description)."""
        e = self.emplacement(pid, slot)
        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        self._check_and_write(path, definir_champ(src, raw, e["chemin"], "image", relatif))

    def dossier_images(self, pid: str) -> Path:
        self.pack_path(pid)
        return self.stories_dir / pid / "images"

    # -- écriture --------------------------------------------------------------
    def edit_line(self, pid: str, section: str, i: int, j: int, *, texte: str | None = None,
                  qui: str | None = None, ton: str | None = None) -> None:
        """Modifie le texte, le personnage ou le ton de la réplique `section[i].lignes[j]`.
        `ton=""` revient au ton par défaut de la voix."""
        if section not in SECTIONS:
            raise EditError(f"Section inconnue : {section!r}")
        path = self.pack_path(pid)
        pk = load_pack(path)
        if qui is not None and qui not in pk.voices:
            raise EditError(f"Personnage inconnu : {qui!r} (voix du pack : {', '.join(pk.voices)})")
        if ton:
            from lunii_gen.tones import ALIASES, TONES

            if ton not in TONES and ton not in ALIASES:
                raise EditError(f"Ton inconnu : {ton!r}")
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        try:
            seq = raw[section][i]["lignes"]
            item = seq[j]
        except (KeyError, IndexError, TypeError) as e:
            raise EditError(f"Réplique introuvable : {section}[{i}].lignes[{j}]") from e
        line_no, col = seq.lc.item(j)
        next_line = seq.lc.item(j + 1)[0] if j + 1 < len(seq) else None
        lines = src.splitlines(keepends=True)
        phys = lines[line_no]
        eol = "\n" if phys.endswith("\n") else ""
        rest = phys[col:].rstrip("\n")
        comment = ""
        if " #" in rest:  # commentaire en fin de ligne : on le garde
            k = rest.rfind(" #")
            try:
                if _plain(_rt().load(rest[:k])) == _plain(item):
                    rest, comment = rest[:k], rest[k:]
            except Exception:  # noqa: BLE001  (« # » dans le texte)
                pass
        # on ne remplace qu'une réplique écrite sur une seule ligne (forme courante des packs)
        try:
            same = _plain(_rt().load(rest)) == _plain(item)
        except Exception:  # noqa: BLE001
            same = False
        if next_line not in (None, line_no + 1) or not same:
            raise EditError("Cette réplique s'étend sur plusieurs lignes du fichier : modifie-la dans le YAML")
        new_item = _edited(item, texte=texte, qui=qui, ton=ton)
        lines[line_no] = f"{phys[:col]}{_flow(new_item)}{comment}{eol}"
        new_src = "".join(lines)
        self._check_and_write(path, new_src)

    # -- répliques : ajout, suppression, déplacement ----------------------------
    def ajouter_replique(self, pid: str, section: str, i: int, apres: int, qui: str | None = None,
                         texte: str = "", ton: str | None = None) -> int:
        """Nouvelle réplique après la ligne `apres` (-1 : en tête). Renvoie son index."""
        from .edition import inserer_element

        path = self.pack_path(pid)
        pk = load_pack(path)
        qui = qui or pk.narrator
        if qui not in pk.voices:
            raise EditError(f"Personnage inconnu : {qui!r}")
        item = [qui, ton, texte or "…"] if ton else [qui, texte or "…"]
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        try:
            seq = raw[section][i].get("lignes")
        except (KeyError, IndexError, TypeError) as e:
            raise EditError("Section introuvable") from e
        if not seq:  # liste vide ou absente : on réécrit l'élément (fichiers d'aventure, sans perte)
            from ruamel.yaml.comments import CommentedSeq

            ligne = CommentedSeq(item)
            ligne.fa.set_flow_style()  # une réplique = une ligne du fichier : [qui, "texte"]
            nouv = CommentedSeq([ligne])
            raw[section][i]["lignes"] = nouv
            import io as _io

            buf = _io.StringIO()
            _rt().dump(raw, buf)
            self._check_and_write(path, buf.getvalue())
            return 0
        self._check_and_write(path, inserer_element(src, raw, [section, i, "lignes"], apres, item))
        return apres + 1

    def supprimer_ligne(self, pid: str, section: str, i: int, j: int) -> None:
        from .edition import supprimer_element

        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        seq = raw[section][i]["lignes"]
        if len(seq) == 1:  # dernière ligne : la liste devient vide
            from ruamel.yaml.comments import CommentedSeq
            import io as _io

            vide = CommentedSeq()
            vide.fa.set_flow_style()
            raw[section][i]["lignes"] = vide
            buf = _io.StringIO()
            _rt().dump(raw, buf)
            self._check_and_write(path, buf.getvalue())
            return
        self._check_and_write(path, supprimer_element(src, raw, [section, i, "lignes"], j))

    def deplacer_ligne(self, pid: str, section: str, i: int, j: int, sens: int) -> int:
        from .edition import echanger_elements

        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        seq = raw[section][i]["lignes"]
        k = j + (1 if sens > 0 else -1)
        if not 0 <= k < len(seq):
            return j
        self._check_and_write(path, echanger_elements(src, raw, [section, i, "lignes"], j, k))
        return k

    def champs_ligne(self, pid: str, section: str, i: int, j: int, **champs) -> None:
        """Champs d'une réplique : `prise` (0 = première prise, retirée du fichier) et `audio` (voix
        enregistrée, None = revenir à la synthèse). La réplique passe en forme dictionnaire au besoin."""
        path = self.pack_path(pid)
        src = path.read_text(encoding="utf-8")
        raw = _rt().load(src)
        try:
            seq = raw[section][i]["lignes"]
            item = seq[j]
        except (KeyError, IndexError, TypeError) as e:
            raise EditError(f"Réplique introuvable : {section}[{i}].lignes[{j}]") from e
        if isinstance(item, dict) and set(item) & {"bruit", "musique", "ambiance"}:
            raise EditError("Cette ligne n'est pas une réplique")
        d = _en_dict(_plain(item))
        for k, v in champs.items():
            if v in (None, 0, ""):
                d.pop(k, None)
            else:
                d[k] = v
        ordre = ["qui", "voix", "ton", "texte", "text", "prise", "audio"]
        d = {k: d[k] for k in ordre if k in d} | {k: v for k, v in d.items() if k not in ordre}
        if set(d) <= {"qui", "ton", "texte"} and "qui" in d:  # plus de champ particulier : forme courte
            nouveau = [d["qui"], d["ton"], d["texte"]] if d.get("ton") else [d["qui"], d["texte"]]
        else:
            nouveau = d
        from .edition import _position, _remplacer, _span

        ligne, col = _position(raw, [section, i, "lignes", j])
        fin, _ = _span(src.splitlines(keepends=True), ligne, col, item)
        self._check_and_write(path, _remplacer(src, ligne, col, fin, _flow(nouveau)))

    def _check_and_write(self, path: Path, text: str, nouveau: bool = False) -> None:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:  # fins de ligne Unix, même sous Windows
                f.write(text)
            try:
                load_pack(Path(tmp))
            except Exception as e:  # noqa: BLE001
                raise EditError(f"Le pack ne serait plus valide : {e}") from e
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _didascalie(ton: str | None) -> str | None:
    try:
        return get_tone(ton).instruct if ton else None
    except KeyError:
        return None


def _est_aventure(f: Path) -> bool:
    import yaml

    try:
        return "etapes" in (yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    except Exception:  # noqa: BLE001
        return False


def _sans_accents(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _all_tones() -> list[str]:
    from lunii_gen.tones import TONES

    return list(TONES)


def _plain(v):
    """Valeur Python simple (sans les types ruamel) pour comparer."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v if isinstance(v, (int, float, bool)) or v is None else str(v)


def _en_dict(it) -> dict:
    """Réplique sous forme de dictionnaire, quelle que soit sa forme dans le fichier."""
    if isinstance(it, str):
        return {"texte": it}
    if isinstance(it, list):
        return {"qui": it[0], "texte": it[1]} if len(it) == 2 else {"qui": it[0], "ton": it[1], "texte": it[2]}
    return dict(it)


def _edited(item, *, texte, qui, ton):
    """Nouvelle valeur de la réplique, dans la même forme que l'originale quand c'est possible."""
    it = _plain(item)
    if isinstance(it, str):
        if qui is None and not ton:
            return texte if texte is not None else it
        it = {"texte": it}
    if isinstance(it, list):
        cur_qui, cur_ton, cur_txt = (it[0], None, it[1]) if len(it) == 2 else (it[0], it[1], it[2])
        q = qui if qui is not None else cur_qui
        t = cur_ton if ton is None else (ton or None)
        x = texte if texte is not None else cur_txt
        return [q, t, x] if t else [q, x]
    if isinstance(it, dict):
        key_txt = "text" if "text" in it and "texte" not in it else "texte"
        key_qui = "voix" if "voix" in it and "qui" not in it else "qui"
        if texte is not None:
            it[key_txt] = texte
        if qui is not None:
            it[key_qui] = qui
        if ton is not None:
            if ton:
                it["ton"] = ton
            else:
                it.pop("ton", None)
        order = [key_qui, "ton", key_txt]
        return {k: it[k] for k in order if k in it} | {k: v for k, v in it.items() if k not in order}
    raise EditError("Cette ligne n'est pas une réplique")


def _flow(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_scalar(x) for x in v[:-1]) + (", " if len(v) > 1 else "") + json.dumps(str(v[-1]), ensure_ascii=False) + "]"
    if isinstance(v, dict):
        parts = []
        for k, x in v.items():
            parts.append(f"{k}: {json.dumps(str(x), ensure_ascii=False) if k in ('texte', 'text') else _scalar(x)}")
        return "{" + ", ".join(parts) + "}"
    return json.dumps(str(v), ensure_ascii=False)


def dump_for_tests(v) -> str:  # pragma: no cover - aide au débogage
    buf = io.StringIO()
    _rt().dump(v, buf)
    return buf.getvalue()
