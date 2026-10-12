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

from lunii_gen.story import _parse_line, load_pack
from lunii_gen.tones import get_tone

SECTIONS = ("histoires", "etapes")
_PLAIN = re.compile(r"^[A-Za-zÀ-ÿ0-9_\-]+$")


class EditError(ValueError):
    """Modification refusée (adresse inconnue, ligne non éditable, pack invalide)."""


def _rt() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 100000
    y.indent(mapping=2, sequence=4, offset=2)
    return y


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
        if "/" in pid or not p.is_file():
            raise EditError(f"Pack inconnu : {pid!r}")
        return p

    def packs(self) -> list[dict]:
        out = []
        for f in sorted(self.stories_dir.glob("*.yaml")):
            try:
                pk = load_pack(f)
                out.append({"id": f.stem, "titre": pk.title, "aventure": pk.adventure,
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
                             "texte": ln.text, "pause": ln.pause or None}
                        if audio_path and voice:
                            ap = audio_path(ln.text, voice, ton)
                            d["audio"] = ap.name if ap and ap.exists() else None
                        lines.append(d)
                sections.append({"section": sec, "i": i, "id": str(item.get("id", i)),
                                 "titre": item.get("titre") or str(item.get("id", i)),
                                 "choix": [str(c) for c in item.get("choix") or []], "lignes": lines})
        return {
            "id": pid, "titre": pk.title, "description": pk.description, "aventure": pk.adventure,
            "narrateur": pk.narrator,
            "voix": [{"nom": v.name, "description": v.description, "ton": v.tone} for v in pk.voices.values()],
            "tons": sorted({t for t in _all_tones()}),
            "questions": [{"texte": q.text, "options": [{"id": o.id, "nom": o.label} for o in q.options]}
                          for q in pk.questions],
            "sections": sections,
        }

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

    def _check_and_write(self, path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                load_pack(Path(tmp))
            except Exception as e:  # noqa: BLE001
                raise EditError(f"Le pack ne serait plus valide : {e}") from e
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


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
