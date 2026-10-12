# SPDX-License-Identifier: GPL-3.0-or-later
import shutil

import pytest

from contes_studio.workspace import EditError, Workspace, load_pack
from lunii_gen.paths import WORKSPACE

AV = "painpain-joyau-sept-couronnes"


@pytest.fixture
def ws(tmp_path) -> Workspace:
    shutil.copytree(WORKSPACE / "histoires", tmp_path / "histoires", ignore=shutil.ignore_patterns(".git"))
    return Workspace(tmp_path)


def test_lecture_aventure_existante(ws):
    v = ws.graphe(AV)
    assert v["type"] == "aventure" and v["a_completer"] == []
    assert len(v["arcs"]) == 26 and len(v["decisions"]) == 6
    assert v["depart"]["arc"] == v["arcs"][0]["id"]
    assert all(len(d["options"]) == 2 and all(o["arc"] for o in d["options"]) for d in v["decisions"])
    assert v["jonctions"], "les étapes « merci » rejointes par deux branches sont des jonctions"
    assert ws.graphe("dragon-timide") == {"type": "questions"}


def test_creer_une_aventure_de_zero(ws):
    pid = ws.creer_pack("La forêt qui chante", "conteur")
    assert ws.graphe(pid)["a_completer"] == ["Clique sur la sortie du départ pour créer la première étape."]
    a1 = ws.graphe_op(pid, {"op": "creer_arc", "origine": {"type": "depart"}, "titre": "Le départ"})["resultat"]
    did = ws.graphe_op(pid, {"op": "creer_decision", "question": "Où va Lila ?"})["resultat"]
    ws.graphe_op(pid, {"op": "attacher", "arc": a1, "cible": did})
    ws.graphe_op(pid, {"op": "modifier_decision", "decision": did, "question": "Où va Lila ?",
                       "options": [{"nom": "Dans la grotte", "illustration": "une grotte"}, {"nom": "Au lac"}]})
    v = ws.graphe(pid)
    opts = v["decisions"][0]["options"]
    for o in opts:
        ws.graphe_op(pid, {"op": "creer_arc", "origine": {"type": "option", "decision": did, "option": o["id"]}})
    v = ws.graphe(pid)
    assert len(v["arcs"]) == 3 and all(o["arc"] for o in v["decisions"][0]["options"])
    assert any("pas encore de répliques" in m for m in v["a_completer"])
    for k in range(3):
        ws.ajouter_replique(pid, "etapes", k, -1, texte=f"Il était une fois, étape {k}.")
    assert ws.graphe(pid)["a_completer"] == []
    pk = load_pack(ws.stories_dir / f"{pid}.yaml", strict=True)  # vérification complète du générateur
    assert pk.adventure and len(pk.stories) == 2


def test_rejoindre_une_decision_et_boucle_permise(ws):
    v = ws.graphe(AV)
    premiere, derniere = v["decisions"][0], v["decisions"][-1]
    branche = premiere["options"][0]["arc"]  # arc d'une branche du début : on le fait sauter à la dernière décision
    ws.graphe_op(AV, {"op": "attacher", "arc": branche, "cible": derniere["id"]})
    v2 = ws.graphe(AV)
    assert not any(d["id"] == derniere["id"] for d in v2["decisions"]), "la décision propre devient partagée"
    partagee = next(d for d in v2["decisions"] if d["partagee"])
    assert next(x for x in v2["arcs"] if x["id"] == branche)["vers"] == partagee["id"]
    apres = partagee["options"][0]["arc"]  # un arc qui part de cette décision y revient : boucle (labyrinthe)
    ws.graphe_op(AV, {"op": "attacher", "arc": apres, "cible": partagee["id"]})
    pk = load_pack(ws.stories_dir / f"{AV}.yaml", strict=True)  # le générateur l'accepte
    assert any("↺" in st.title for st in pk.stories)
    from lunii_gen.pack import build_story_json  # l'archive se construit (pas de calcul infini)
    assert build_story_json


def test_suppressions(ws):
    v = ws.graphe(AV)
    d0 = v["decisions"][0]
    with pytest.raises(EditError):
        ws.graphe_op(AV, {"op": "supprimer_decision", "decision": d0["id"]})
    arc = d0["options"][0]["arc"]
    ws.graphe_op(AV, {"op": "supprimer_arc", "arc": arc})
    v2 = ws.graphe(AV)
    assert len(v2["arcs"]) == 25 and any("ne mène encore nulle part" in m for m in v2["a_completer"])
    d = ws.graphe_op(AV, {"op": "creer_decision"})["resultat"]
    ws.graphe_op(AV, {"op": "supprimer_decision", "decision": d})


def test_repliques_ajout_suppression_deplacement(ws):
    pid = "dragon-timide"
    f = ws.stories_dir / f"{pid}.yaml"
    n0 = len(ws.pack(pid)["sections"][0]["lignes"])
    k = ws.ajouter_replique(pid, "histoires", 0, 1, qui="braise", texte="Coucou !")
    lignes = ws.pack(pid)["sections"][0]["lignes"]
    assert len(lignes) == n0 + 1 and lignes[k]["texte"] == "Coucou !" and lignes[k]["qui"] == "braise"
    assert ws.deplacer_ligne(pid, "histoires", 0, k, -1) == k - 1
    assert ws.pack(pid)["sections"][0]["lignes"][k - 1]["texte"] == "Coucou !"
    ws.supprimer_ligne(pid, "histoires", 0, k - 1)
    assert len(ws.pack(pid)["sections"][0]["lignes"]) == n0
    load_pack(f, strict=True)


def test_histoire_sans_fin(ws):
    pid = ws.creer_pack("La blague sans fin", "conteur")
    a = ws.graphe_op(pid, {"op": "creer_arc", "origine": {"type": "depart"}, "titre": "Le début"})["resultat"]
    d = ws.graphe_op(pid, {"op": "creer_decision", "question": "On recommence ?"})["resultat"]
    ws.graphe_op(pid, {"op": "attacher", "arc": a, "cible": d})
    opts = ws.graphe(pid)["decisions"][0]["options"]
    b = ws.graphe_op(pid, {"op": "creer_arc", "origine": {"type": "option", "decision": d, "option": opts[0]["id"]}})["resultat"]
    c = ws.graphe_op(pid, {"op": "creer_arc", "origine": {"type": "option", "decision": d, "option": opts[1]["id"]}})["resultat"]
    ws.graphe_op(pid, {"op": "attacher", "arc": b, "cible": d})
    ws.graphe_op(pid, {"op": "attacher", "arc": c, "cible": d})  # aucune fin : on tourne en rond
    for k in range(3):
        ws.ajouter_replique(pid, "etapes", k, -1, texte="Ha ha ha.")
    assert ws.graphe(pid)["a_completer"] == []
    pk = load_pack(ws.stories_dir / f"{pid}.yaml", strict=True)
    assert pk.stories and all("↺" in st.title for st in pk.stories)
