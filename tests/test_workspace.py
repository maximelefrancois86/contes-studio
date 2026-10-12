# SPDX-License-Identifier: GPL-3.0-or-later
import shutil
from pathlib import Path

import pytest

from contes_studio.workspace import EditError, Workspace
from lunii_gen.paths import WORKSPACE

PACKS = ["dragon-timide", "painpain-joyau-sept-couronnes", "tiny-et-la-guerre-des-doudous"]


@pytest.fixture
def ws(tmp_path) -> Workspace:
    (tmp_path / "histoires").mkdir()
    for p in PACKS:
        shutil.copy(WORKSPACE / "histoires" / f"{p}.yaml", tmp_path / "histoires")
    return Workspace(tmp_path)


def _replique(ws, pid, forme):
    """Première réplique écrite sous une forme donnée (list2, list3, dict, str)."""
    from contes_studio.workspace import _plain, _rt

    raw = _rt().load((ws.stories_dir / f"{pid}.yaml").read_text(encoding="utf-8"))
    for sec in ("histoires", "etapes"):
        for i, it in enumerate(raw.get(sec) or []):
            for j, l in enumerate(it.get("lignes") or []):
                l = _plain(l)
                f = ("list2" if isinstance(l, list) and len(l) == 2 else "list3" if isinstance(l, list) else
                     "dict" if isinstance(l, dict) and ("texte" in l or "qui" in l) else
                     "str" if isinstance(l, str) else None)
                if f == forme:
                    return sec, i, j
    pytest.skip(f"aucune réplique de forme {forme} dans {pid}")


def _diff(a: str, b: str) -> list[int]:
    la, lb = a.splitlines(), b.splitlines()
    assert len(la) == len(lb)
    return [k for k, (x, y) in enumerate(zip(la, lb)) if x != y]


@pytest.mark.parametrize("pid", PACKS)
@pytest.mark.parametrize("forme", ["list2", "list3", "dict"])
def test_texte_une_seule_ligne_change(ws, pid, forme):
    sec, i, j = _replique(ws, pid, forme)
    f = ws.stories_dir / f"{pid}.yaml"
    avant = f.read_text(encoding="utf-8")
    ws.edit_line(pid, sec, i, j, texte='Bonjour « toi », dit-il : "#1" ! Tu viens ?')
    apres = f.read_text(encoding="utf-8")
    assert len(_diff(avant, apres)) == 1
    lignes = next(s for s in ws.pack(pid)["sections"] if s["section"] == sec and s["i"] == i)["lignes"]
    assert next(l for l in lignes if l["j"] == j)["texte"] == 'Bonjour « toi », dit-il : "#1" ! Tu viens ?'


def test_ton_ajoute_puis_retire(ws):
    pid = "dragon-timide"
    sec, i, j = _replique(ws, pid, "list2")
    ws.edit_line(pid, sec, i, j, ton="chuchoté")
    l = next(s for s in ws.pack(pid)["sections"] if s["i"] == i)["lignes"][j]
    assert l["ton"] == "chuchoté"
    ws.edit_line(pid, sec, i, j, ton="")
    l = next(s for s in ws.pack(pid)["sections"] if s["i"] == i)["lignes"][j]
    assert l["ton"] is None


def test_personnage_inconnu_refuse_sans_rien_ecrire(ws):
    pid = "dragon-timide"
    sec, i, j = _replique(ws, pid, "list2")
    f = ws.stories_dir / f"{pid}.yaml"
    avant = f.read_text(encoding="utf-8")
    with pytest.raises(EditError):
        ws.edit_line(pid, sec, i, j, qui="personne-inconnue")
    assert f.read_text(encoding="utf-8") == avant
    assert not list(ws.stories_dir.glob(".*.tmp"))


def test_adresse_inconnue(ws):
    with pytest.raises(EditError):
        ws.edit_line("dragon-timide", "histoires", 99, 0, texte="x")
    with pytest.raises(EditError):
        ws.edit_line("../secret", "histoires", 0, 0, texte="x")
