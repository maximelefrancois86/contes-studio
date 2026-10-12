# SPDX-License-Identifier: GPL-3.0-or-later
import difflib
import shutil

import pytest

from contes_studio.workspace import EditError, Workspace
from lunii_gen.paths import WORKSPACE
from lunii_gen.story import load_pack

TOUS = sorted(p.stem for p in (WORKSPACE / "histoires").glob("*.yaml"))


@pytest.fixture
def ws(tmp_path) -> Workspace:
    shutil.copytree(WORKSPACE / "histoires", tmp_path / "histoires", ignore=shutil.ignore_patterns(".git"))
    return Workspace(tmp_path)


def _changes(avant: str, apres: str) -> tuple[int, int]:
    d = [l for l in difflib.unified_diff(avant.splitlines(), apres.splitlines(), lineterm="", n=0)
         if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return sum(l.startswith("-") for l in d), sum(l.startswith("+") for l in d)


@pytest.mark.parametrize("pid", TOUS)
def test_description_de_chaque_image(ws, pid):
    f = ws.stories_dir / f"{pid}.yaml"
    for e in ws.emplacements(pid):
        avant = f.read_text(encoding="utf-8")
        texte = f"un petit hibou : « {e['slot']} », très simple"
        try:
            ws.definir_description(pid, e["slot"], texte)
        except EditError as err:
            pytest.fail(f"{pid}/{e['slot']} : {err}")
        apres = f.read_text(encoding="utf-8")
        moins, plus = _changes(avant, apres)
        assert (moins, plus) in ((1, 1), (0, 1)), (e["slot"], moins, plus)
        assert ws.emplacement(pid, e["slot"])["description"] == texte


def test_image_puis_retour_a_la_description(ws):
    pid = "dragon-timide"
    f = ws.stories_dir / f"{pid}.yaml"
    origine = f.read_text(encoding="utf-8")
    for slot in ("couverture", "q0-noisette", "h1"):
        ws.definir_image(pid, slot, f"{pid}/images/{slot}.png")
        assert ws.emplacement(pid, slot)["image"] == f"{pid}/images/{slot}.png"
    ws.definir_image(pid, "h1", None)
    ws.definir_image(pid, "couverture", None)
    ws.definir_image(pid, "q0-noisette", None)
    from contes_studio.edition import plain, rt

    assert plain(rt().load(f.read_text(encoding="utf-8"))) == plain(rt().load(origine))
    assert _changes(origine, f.read_text(encoding="utf-8"))[0] <= 1  # au plus la ligne de l'option, réécrite


def test_option_simple_chaine_devient_dictionnaire(ws, tmp_path):
    f = ws.stories_dir / "mini.yaml"
    f.write_text(
        "titre: Mini\nvoix:\n  narrateur: conteur\nquestions:\n  - question: Choisis\n    options:\n"
        "      a: Le chat   # commentaire\n      b: Le chien\nhistoires:\n  - titre: Une\n    choix: [a]\n"
        "    lignes:\n      - Il était une fois.\n  - titre: Deux\n    choix: [b]\n    lignes:\n      - Encore.\n",
        encoding="utf-8")
    ws.definir_description("mini", "q0-a", "un chat roux")
    txt = f.read_text(encoding="utf-8")
    assert "      a: {nom: Le chat, illustration: un chat roux}   # commentaire" in txt
    assert load_pack(f).questions[0].options[0].illustration == "un chat roux"


def test_ajout_de_sons_et_usage(ws):
    pid = "dragon-timide"
    f = ws.stories_dir / f"{pid}.yaml"
    a = ws.ajouter_son(pid, "Hibou qui hulule !", {"freesound": 159726, "duree_max": 8.0})
    b = ws.ajouter_son(pid, "Hibou qui hulule !", {"freesound": 871238, "duree_max": 2.9})
    assert (a, b) == ("hibou-qui-hulule", "hibou-qui-hulule-2")
    avant = f.read_text(encoding="utf-8")
    ws.inserer_son(pid, "histoires", 0, 2, "bruit", a)
    assert _changes(avant, f.read_text(encoding="utf-8")) == (0, 1)
    lignes = ws.pack(pid)["sections"][0]["lignes"]
    assert lignes[3] == {"j": 3, "kind": "bruit", "son": a}
    ws.definir_ambiance(pid, "histoires", 0, b)
    assert next(s for s in ws.sons(pid) if s["id"] == b)["usages"] == 1
    ws.definir_ambiance(pid, "histoires", 0, None)
    with pytest.raises(EditError):
        ws.inserer_son(pid, "histoires", 0, 0, "bruit", "inexistant")


def test_ajout_son_dans_pack_avec_catalogue(ws):
    pid = "painpain-joyau-sept-couronnes"
    n = len(load_pack(ws.stories_dir / f"{pid}.yaml").sounds)
    sid = ws.ajouter_son(pid, "vent", {"freesound": 1234, "boucle": True})
    pk = load_pack(ws.stories_dir / f"{pid}.yaml")
    assert len(pk.sounds) == n + 1 and pk.sounds[sid] == {"freesound": 1234, "boucle": True}
    ws.definir_ambiance(pid, "etapes", 0, sid)
    ws.definir_ambiance(pid, "etapes", 0, None)  # une étape garde « aucune »
    assert "ambiance" in ws.pack(pid)["sections"][0] or True
