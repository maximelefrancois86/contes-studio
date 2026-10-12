# SPDX-License-Identifier: GPL-3.0-or-later
"""Graphe d'une aventure, tel que l'onglet Flot l'édite.

- un nœud **départ** : une sortie (l'arc de la première étape) ;
- des nœuds **décision** : une entrée (plusieurs arcs peuvent y arriver), une sortie par option ;
- des nœuds **jonction** : une étape qui en continue d'autres sans question (`ensuite: <étape>`) ;
- des **arcs** : une étape = un fichier audio, de la sortie d'un nœud à l'entrée d'un autre, ou
  libre (fin de l'histoire). Une étape peut ramener à une décision déjà passée : les boucles sont
  permises (labyrinthe, histoire sans fin).

Correspondance avec le YAML du générateur : `debut`, `etapes[].ensuite` (absent = fin, id d'étape =
jonction, id de `decisions:` = décision partagée, dictionnaire = décision propre à l'étape) et
`decisions:`. Les positions à l'écran vivent à part, dans `histoires/<pack>/flot.json`.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .edition import EditError, plain, rt

QUESTION_DEFAUT = "Que va faire le héros ?"


def slug(s: str, defaut: str = "x") -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:28] or defaut


def _unique(base: str, pris: set[str]) -> str:
    final, n = base, 2
    while final in pris:
        final, n = f"{base}-{n}", n + 1
    return final


def _options(q) -> list[tuple[str, dict]]:
    opts = (q or {}).get("options") or {}
    if isinstance(opts, dict):
        return [(str(k), v if isinstance(v, dict) else {"nom": v}) for k, v in opts.items()]
    return [(str(o.get("id")), o) for o in opts]


class Graphe:
    """Lecture et modification du graphe sur l'arbre ruamel du pack (réécrit en entier ensuite)."""

    def __init__(self, raw: CommentedMap):
        self.raw = raw

    # -- accès -----------------------------------------------------------------
    @property
    def etapes(self) -> CommentedSeq:
        if not isinstance(self.raw.get("etapes"), list):
            self.raw["etapes"] = CommentedSeq()
        return self.raw["etapes"]

    @property
    def decisions(self) -> CommentedMap:
        if not isinstance(self.raw.get("decisions"), dict):
            self.raw["decisions"] = CommentedMap()
        return self.raw["decisions"]

    def etape(self, sid: str) -> CommentedMap:
        for e in self.etapes:
            if str(e.get("id")) == sid:
                return e
        raise EditError(f"Étape inconnue : {sid!r}")

    def ids_etapes(self) -> list[str]:
        return [str(e.get("id")) for e in self.etapes]

    def debut(self) -> str | None:
        if self.raw.get("debut") is not None:
            return str(self.raw["debut"])
        ids = self.ids_etapes()
        return ids[0] if ids else None

    def decision(self, did: str):
        """Dictionnaire de la décision : nommée (`decisions:`) ou propre à une étape (« @étape »)."""
        if did.startswith("@"):
            ens = self.etape(did[1:]).get("ensuite")
            if not isinstance(ens, dict):
                raise EditError(f"Décision inconnue : {did!r}")
            return ens
        if did in (self.raw.get("decisions") or {}):
            return self.decisions[did]
        raise EditError(f"Décision inconnue : {did!r}")

    def toutes_decisions(self) -> list[tuple[str, dict]]:
        out = [(str(k), v) for k, v in (self.raw.get("decisions") or {}).items()]
        out += [("@" + str(e.get("id")), e["ensuite"]) for e in self.etapes if isinstance(e.get("ensuite"), dict)]
        return out

    # -- lecture pour l'éditeur ------------------------------------------------
    def vue(self) -> dict:
        ids = self.ids_etapes()
        named = set(map(str, (self.raw.get("decisions") or {}).keys()))
        decisions, jonctions, origines = [], {}, {sid: [] for sid in ids}
        deb = self.debut()
        if deb in origines:
            origines[deb].append({"type": "depart"})
        for did, q in self.toutes_decisions():
            opts = []
            for oid, o in _options(q):
                vers = str(o["vers"]) if o.get("vers") is not None else None
                opts.append({"id": oid, "nom": str(o.get("nom") or o.get("label") or oid),
                             "illustration": o.get("illustration"), "arc": vers if vers in origines else None})
                if vers in origines:
                    origines[vers].append({"type": "option", "decision": did, "option": oid})
            decisions.append({"id": did, "question": str(q.get("question") or q.get("texte") or ""),
                              "partagee": not did.startswith("@"), "options": opts})
        arcs = []
        for e in self.etapes:
            sid = str(e.get("id"))
            ens = e.get("ensuite")
            if isinstance(ens, dict):
                vers = "@" + sid
            elif ens is None:
                vers = None
            elif str(ens) in named:
                vers = str(ens)
            else:
                vers = "j:" + str(ens)
                jonctions.setdefault(str(ens), {"id": "j:" + str(ens), "arc": str(ens) if str(ens) in origines else None})
                if str(ens) in origines:
                    origines[str(ens)].append({"type": "jonction", "jonction": "j:" + str(ens)})
            lignes = [l for l in (e.get("lignes") or []) if not (isinstance(l, dict) and set(l) & {"bruit", "musique", "ambiance", "pause"})]
            arcs.append({"id": sid, "titre": str(e.get("titre") or sid), "repliques": len(lignes),
                         "vers": vers, "origines": origines.get(sid, [])})
        # dédoublonnage : une étape atteinte par une jonction et autre chose garde ses deux origines
        return {"depart": {"arc": deb if deb in origines else None}, "decisions": decisions,
                "jonctions": list(jonctions.values()), "arcs": arcs, "a_completer": self.a_completer()}

    def a_completer(self) -> list[str]:
        """Ce qui empêchera la fabrication (vérification complète du générateur), en clair."""
        msgs = []
        ids = set(self.ids_etapes())
        if not ids:
            msgs.append("Clique sur la sortie du départ pour créer la première étape.")
        for did, q in self.toutes_decisions():
            nom = str(q.get("question") or did)
            opts = _options(q)
            if len(opts) < 2:
                msgs.append(f"La décision « {nom} » a besoin d'au moins deux options.")
            for oid, o in opts:
                if o.get("vers") is None or str(o["vers"]) not in ids:
                    msgs.append(f"L'option « {o.get('nom') or oid} » de « {nom} » ne mène encore nulle part.")
        for e in self.etapes:
            if not any(not (isinstance(l, dict) and set(l) & {"bruit", "musique", "ambiance", "pause"})
                       for l in (e.get("lignes") or [])):
                msgs.append(f"L'étape « {e.get('titre') or e.get('id')} » n'a pas encore de répliques.")
        vus, pile = set(), [self.debut()] if self.debut() else []
        while pile:
            sid = pile.pop()
            if sid in vus or sid not in ids:
                continue
            vus.add(sid)
            ens = self.etape(sid).get("ensuite")
            if isinstance(ens, dict) or (ens is not None and str(ens) in (self.raw.get("decisions") or {})):
                q = ens if isinstance(ens, dict) else self.decisions[str(ens)]
                pile += [str(o["vers"]) for _, o in _options(q) if o.get("vers") is not None]
            elif ens is not None:
                pile.append(str(ens))
        for sid in ids - vus:
            msgs.append(f"L'étape « {self.etape(sid).get('titre') or sid} » n'est reliée à rien.")
        return msgs

    # -- opérations ------------------------------------------------------------
    def _nouvelle_etape(self, titre: str = "Nouvelle étape") -> str:
        sid = _unique(slug(titre, "etape"), set(self.ids_etapes()) | set(map(str, self.raw.get("decisions") or {})))
        e = CommentedMap([("id", sid), ("titre", titre), ("lignes", CommentedSeq())])
        e["lignes"].fa.set_flow_style()
        self.etapes.append(e)
        return sid

    def creer_arc(self, origine: dict, titre: str = "Nouvelle étape") -> str:
        if origine.get("type") == "depart":
            if self.ids_etapes():
                raise EditError("Le départ a déjà son étape")
            sid = self._nouvelle_etape(titre)
            return sid
        if origine.get("type") == "option":
            q = self.decision(origine["decision"])
            for oid, o in _options(q):
                if oid == str(origine["option"]):
                    if o.get("vers") is not None and str(o["vers"]) in self.ids_etapes():
                        raise EditError("Cette option mène déjà à une étape")
                    sid = self._nouvelle_etape(str(o.get("nom") or titre))
                    self._option_dict(q, oid)["vers"] = sid
                    return sid
            raise EditError("Option inconnue")
        raise EditError("Origine inconnue")

    def _option_dict(self, q, oid: str) -> CommentedMap:
        opts = q["options"]
        if isinstance(opts, dict):
            v = opts[oid] if oid in opts else opts[next(k for k in opts if str(k) == oid)]
            if not isinstance(v, dict):
                k = next(k for k in opts if str(k) == oid)
                v = CommentedMap([("nom", v)])
                v.fa.set_flow_style()
                opts[k] = v
            return v
        return next(o for o in opts if str(o.get("id")) == oid)

    def nommer(self, did: str) -> str:
        """Une décision propre à une étape devient une décision partagée (pour qu'on puisse y accrocher d'autres arcs)."""
        if not did.startswith("@"):
            return did
        sid = did[1:]
        e = self.etape(sid)
        q = e["ensuite"]
        nid = _unique(slug(q.get("question") or sid, "choix"), set(map(str, self.raw.get("decisions") or {})) | set(self.ids_etapes()))
        self.decisions[nid] = q
        e["ensuite"] = nid
        return nid

    def attacher(self, arc: str, cible: str | None) -> None:
        e = self.etape(arc)
        ens = e.get("ensuite")
        if isinstance(ens, dict):  # l'arc portait sa propre décision : elle devient partagée, elle ne disparaît pas
            self.nommer("@" + arc)
        if cible is None:
            e.pop("ensuite", None)
        elif cible.startswith("j:"):
            t = cible[2:]
            self.etape(t)
            e["ensuite"] = t
        else:
            e["ensuite"] = self.nommer(cible) if cible.startswith("@") else (self.decision(cible) and cible)
        # les boucles sont permises : labyrinthe, histoire « blague » sans fin…

    def _suivants(self, sid: str) -> list[str]:
        ens = self.etape(sid).get("ensuite")
        if ens is None:
            return []
        if isinstance(ens, dict):
            q = ens
        elif str(ens) in (self.raw.get("decisions") or {}):
            q = self.decisions[str(ens)]
        else:
            return [str(ens)]
        return [str(o["vers"]) for _, o in _options(q) if o.get("vers") is not None]

    def _boucle(self) -> bool:
        ids = set(self.ids_etapes())
        etat: dict[str, int] = {}

        def visite(s: str) -> bool:
            if s not in ids:
                return False
            if etat.get(s) == 1:
                return True
            if etat.get(s) == 2:
                return False
            etat[s] = 1
            if any(visite(n) for n in self._suivants(s)):
                return True
            etat[s] = 2
            return False

        return any(visite(s) for s in ids)

    def creer_decision(self, question: str = QUESTION_DEFAUT) -> str:
        did = _unique(slug(question, "choix"), set(map(str, self.raw.get("decisions") or {})) | set(self.ids_etapes()))
        q = CommentedMap([("question", question), ("options", CommentedMap())])
        for k, nom in (("a", "Première idée"), ("b", "Deuxième idée")):
            o = CommentedMap([("nom", nom)])
            o.fa.set_flow_style()
            q["options"][k] = o
        self.decisions[did] = q
        return did

    def modifier_decision(self, did: str, question: str | None, options: list[dict] | None) -> None:
        q = self.decision(did)
        if question is not None:
            q["question"] = question
        if options is None:
            return
        anciennes = dict(_options(q))
        nouv = CommentedMap()
        for o in options:
            oid = str(o.get("id") or "") or _unique(slug(o.get("nom", ""), "option"), set(anciennes) | set(nouv))
            base = anciennes.get(oid) or {}
            d = CommentedMap([("nom", o.get("nom") or base.get("nom") or oid)])
            for k in ("illustration", "image", "vers"):
                v = o.get(k, base.get(k))
                if v not in (None, ""):
                    d[k] = v
            d.fa.set_flow_style()
            nouv[oid] = d
        q["options"] = nouv

    def supprimer_decision(self, did: str) -> None:
        q = self.decision(did)
        if any(o.get("vers") is not None and str(o["vers"]) in self.ids_etapes() for _, o in _options(q)):
            raise EditError("Supprime d'abord les étapes qui partent de cette décision")
        for e in self.etapes:
            ens = e.get("ensuite")
            if (did.startswith("@") and str(e.get("id")) == did[1:]) or (ens is not None and not isinstance(ens, dict) and str(ens) == did):
                e.pop("ensuite", None)
        if not did.startswith("@"):
            del self.decisions[did]

    def supprimer_arc(self, arc: str) -> None:
        e = self.etape(arc)
        if isinstance(e.get("ensuite"), dict):
            self.nommer("@" + arc)
        for _, q in self.toutes_decisions():
            for oid, o in _options(q):
                if o.get("vers") is not None and str(o["vers"]) == arc:
                    self._option_dict(q, oid).pop("vers", None)
        for x in self.etapes:
            if x is not e and not isinstance(x.get("ensuite"), dict) and x.get("ensuite") is not None and str(x["ensuite"]) == arc:
                x.pop("ensuite", None)
        if self.raw.get("debut") is not None and str(self.raw["debut"]) == arc:
            del self.raw["debut"]
        self.etapes.remove(e)
        restants = self.ids_etapes()
        if restants and self.raw.get("debut") is None and arc == (restants and None):
            pass

    def renommer_arc(self, arc: str, titre: str) -> None:
        self.etape(arc)["titre"] = titre

    # -- écriture --------------------------------------------------------------
    def texte(self) -> str:
        if self.raw.get("decisions") is not None and not self.raw["decisions"]:
            del self.raw["decisions"]
        buf = io.StringIO()
        rt().dump(self.raw, buf)
        return buf.getvalue()


def lire_positions(f: Path) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"noeuds": {}, "bulles": {}}


def ecrire_positions(f: Path, pos: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    clean = {"noeuds": {str(k): [round(float(v[0])), round(float(v[1]))] for k, v in (pos.get("noeuds") or {}).items()},
             "bulles": {str(k): [round(float(v[0])), round(float(v[1]))] for k, v in (pos.get("bulles") or {}).items()}}
    f.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def plain_graphe(g: Graphe) -> dict:  # pragma: no cover - aide au débogage
    return plain(g.raw)
