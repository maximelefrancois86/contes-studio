# SPDX-License-Identifier: GPL-3.0-or-later
"""Modifications chirurgicales d'un fichier YAML de pack : on ne touche qu'aux lignes concernées.

Toutes les fonctions prennent le texte source et l'arbre ruamel correspondant (avec positions), et
renvoient le nouveau texte. Une valeur doit tenir sur une seule ligne du fichier pour être
modifiée ; sinon, EditError invite à passer par l'éditeur de texte.
"""
from __future__ import annotations

import json
import re

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


class EditError(ValueError):
    """Modification refusée (adresse inconnue, valeur sur plusieurs lignes, pack invalide)."""


_PLAIN = re.compile(r"^[A-Za-zÀ-ÿ0-9_\-./]+$")
_PLAIN_LARGE = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 '’.!?…()\-]*$")
_RESERVES = {"yes", "no", "true", "false", "null", "on", "off", "y", "n", "~"}


def rt() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 100000
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def plain(v):
    """Valeur Python simple (sans les types ruamel) pour comparer."""
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v if isinstance(v, (int, float, bool)) or v is None else str(v)


def scalar(v) -> str:
    """Valeur YAML sur une ligne : mot nu si possible, sinon chaîne entre guillemets doubles."""
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return repr(v)
    v = str(v)
    if v and v == v.strip() and v.lower() not in _RESERVES and _nu_possible(v):
        return v
    return json.dumps(v, ensure_ascii=False)


def _nu_possible(v: str) -> bool:
    """Le texte peut-il s'écrire sans guillemets, seul ou dans une liste/un dictionnaire en ligne ?"""
    if not _PLAIN_LARGE.match(v) or ": " in v or " #" in v or v.endswith(":"):
        return False
    try:
        return rt().load(v) == v and plain(rt().load("[" + v + "]")) == [v] and \
            plain(rt().load("{k: " + v + "}")) == {"k": v}
    except Exception:  # noqa: BLE001
        return False


def flow(v) -> str:
    """Valeur YAML en style « flow » sur une ligne."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{scalar(str(k))}: {flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(flow(x) for x in v) + "]"
    return scalar(v)


def resoudre(raw, chemin: list):
    node = raw
    for k in chemin:
        try:
            node = node[k]
        except (KeyError, IndexError, TypeError) as e:
            raise EditError(f"Élément introuvable : {'/'.join(map(str, chemin))}") from e
    return node


def _position(raw, chemin: list) -> tuple[int, int]:
    """(ligne, colonne) où commence la valeur désignée par `chemin`."""
    if not chemin:
        raise EditError("Pas de position pour la racine")
    parent = resoudre(raw, chemin[:-1])
    k = chemin[-1]
    if isinstance(parent, CommentedSeq):
        return parent.lc.item(k)
    if isinstance(parent, CommentedMap):
        return parent.lc.value(k)
    raise EditError("Position introuvable")


def _span(lines: list[str], ligne: int, col: int, valeur) -> tuple[int, str]:
    """Fin (exclue) de la valeur écrite sur une seule ligne à partir de `col`, et le commentaire de fin."""
    phys = lines[ligne].rstrip("\n")
    rest = phys[col:]
    cands = sorted({len(rest), *[k for k in range(len(rest)) if rest.startswith(" #", k)]})
    attendu = plain(valeur)
    for k in cands:
        try:
            if plain(rt().load(rest[:k])) == attendu:
                k = len(rest[:k].rstrip())  # les espaces avant un commentaire restent en place
                return col + k, phys[col + k:]
        except Exception:  # noqa: BLE001
            continue
    raise EditError("Cette valeur s'étend sur plusieurs lignes du fichier : modifie-la dans le YAML")


def _remplacer(src: str, ligne: int, col: int, fin: int, texte: str) -> str:
    lines = src.splitlines(keepends=True)
    phys = lines[ligne]
    eol = "\n" if phys.endswith("\n") else ""
    lines[ligne] = phys[:col] + texte + phys[fin:].rstrip("\n") + eol
    return "".join(lines)


def _inserer(src: str, apres: int, texte: str) -> str:
    """Insère une ligne après la ligne `apres` (-1 : en tête)."""
    lines = src.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.insert(apres + 1, texte.rstrip("\n") + "\n")
    return "".join(lines)


def remplacer_valeur(src: str, raw, chemin: list, nouvelle) -> str:
    """Remplace la valeur (sur une ligne) désignée par `chemin` par `nouvelle` (écrite en flow)."""
    ligne, col = _position(raw, chemin)
    lines = src.splitlines(keepends=True)
    fin, _ = _span(lines, ligne, col, resoudre(raw, chemin))
    return _remplacer(src, ligne, col, fin, flow(nouvelle))


def definir_champ(src: str, raw, chemin: list, cle: str, valeur) -> str:
    """Donne la valeur `valeur` (None : supprime) à la clé `cle` du dictionnaire désigné par `chemin`.
    Un nœud qui n'est qu'une chaîne (option `id: Libellé`) devient `{nom: Libellé, cle: valeur}`."""
    node = resoudre(raw, chemin)
    lines = src.splitlines(keepends=True)
    if not isinstance(node, CommentedMap):
        if not chemin or isinstance(node, (list, CommentedSeq)):
            raise EditError("Cet élément ne peut pas recevoir de champ")
        if valeur is None:
            return src
        return remplacer_valeur(src, raw, chemin, {"nom": plain(node), cle: valeur})
    if node.fa.flow_style():  # {nom: …, illustration: …} sur une ligne
        d = plain(node)
        if valeur is None:
            d.pop(cle, None)
        else:
            d[cle] = valeur
        return remplacer_valeur(src, raw, chemin, d)
    if cle in node:
        ligne, col = node.lc.value(cle)
        fin, _ = _span(lines, ligne, col, node[cle])
        if valeur is not None:
            return _remplacer(src, ligne, col, fin, flow(valeur))
        kl, kc = node.lc.key(cle)
        if lines[kl][:kc].strip():  # première clé d'un élément de liste (« - cle: … »)
            raise EditError(f"Impossible de retirer « {cle} » ici : modifie le YAML")
        del lines[kl]
        return "".join(lines)
    if valeur is None:
        return src
    if not node:
        raise EditError("Dictionnaire vide : modifie le YAML")
    k0 = next(iter(node))
    kl, kc = node.lc.key(k0)
    _span(lines, *node.lc.value(k0), node[k0])  # la première clé doit tenir sur sa ligne
    return _inserer(src, kl, " " * kc + f"{scalar(cle)}: {flow(valeur)}")


def inserer_element(src: str, raw, chemin_liste: list, apres: int, element) -> str:
    """Insère `element` dans la liste désignée par `chemin_liste`, après l'élément `apres` (-1 : en tête),
    avec la même indentation que ses voisins."""
    seq = resoudre(raw, chemin_liste)
    if not isinstance(seq, CommentedSeq) or not len(seq):
        raise EditError("Liste vide ou introuvable : modifie le YAML")
    lines = src.splitlines(keepends=True)
    ref = max(0, apres)
    ligne, col = seq.lc.item(ref)
    _span(lines, ligne, col, seq[ref])
    prefixe = lines[ligne][:col]
    if not prefixe.rstrip().endswith("-"):
        raise EditError("Liste écrite en ligne : modifie le YAML")
    return _inserer(src, ligne if apres >= 0 else ligne - 1, prefixe + flow(element))


def ajouter_cle(src: str, raw, cle_racine: str, cle: str, valeur) -> str:
    """Ajoute `cle: valeur` à la fin du dictionnaire de premier niveau `cle_racine` (créé au besoin)."""
    lines = src.splitlines(keepends=True)
    if cle_racine not in raw:
        bloc = f"\n{cle_racine}:\n  {scalar(cle)}: {flow(valeur)}\n"
        return src.rstrip("\n") + "\n" + bloc
    node = raw[cle_racine]
    if isinstance(node, CommentedMap) and cle in node:
        raise EditError(f"« {cle} » existe déjà dans {cle_racine}")
    kl, kc = raw.lc.key(cle_racine)
    if isinstance(node, CommentedMap) and node.fa.flow_style():
        d = plain(node)
        d[cle] = valeur
        return remplacer_valeur(src, raw, [cle_racine], d)
    indent = node.lc.key(next(iter(node)))[1] if isinstance(node, CommentedMap) and node else kc + 2
    fin = kl  # dernière ligne du bloc : indentation > celle de la clé racine
    for n in range(kl + 1, len(lines)):
        s = lines[n]
        if not s.strip():
            continue
        if len(s) - len(s.lstrip(" ")) <= kc and not s.lstrip().startswith("#"):
            break
        if len(s) - len(s.lstrip(" ")) > kc:
            fin = n
    return _inserer(src, fin, " " * indent + f"{scalar(cle)}: {flow(valeur)}")


def _ligne_element(src: str, seq, k: int) -> int:
    lines = src.splitlines(keepends=True)
    ligne, col = seq.lc.item(k)
    _span(lines, ligne, col, seq[k])
    if not lines[ligne][:col].rstrip().endswith("-"):
        raise EditError("Liste écrite en ligne : modifie le YAML")
    return ligne


def supprimer_element(src: str, raw, chemin_liste: list, k: int) -> str:
    seq = resoudre(raw, chemin_liste)
    ligne = _ligne_element(src, seq, k)
    lines = src.splitlines(keepends=True)
    del lines[ligne]
    return "".join(lines)


def echanger_elements(src: str, raw, chemin_liste: list, a: int, b: int) -> str:
    seq = resoudre(raw, chemin_liste)
    la, lb = _ligne_element(src, seq, a), _ligne_element(src, seq, b)
    lines = src.splitlines(keepends=True)
    lines[la], lines[lb] = lines[lb], lines[la]
    for n in (la, lb):  # la dernière ligne du fichier peut ne pas finir par un saut de ligne
        if not lines[n].endswith("\n") and n != len(lines) - 1:
            lines[n] += "\n"
    return "".join(lines)
