# SPDX-License-Identifier: GPL-3.0-or-later
"""Voix : prises, enregistrements (sans le modèle : le moteur est testé à la main, il demande une carte graphique)."""
import shutil

import pytest

from contes_studio.voix import CacheVoix
from contes_studio.voix_moteur import verdict_voix
from contes_studio.workspace import EditError, Workspace, load_pack
from lunii_gen.paths import WORKSPACE


@pytest.fixture
def ws(tmp_path) -> Workspace:
    shutil.copytree(WORKSPACE / "histoires", tmp_path / "histoires", ignore=shutil.ignore_patterns(".git"))
    return Workspace(tmp_path)


def test_prise_et_enregistrement_aller_retour(ws):
    f = ws.stories_dir / "dragon-timide.yaml"
    avant = f.read_text(encoding="utf-8")
    ws.champs_ligne("dragon-timide", "histoires", 0, 4, prise=3)
    ws.champs_ligne("dragon-timide", "histoires", 0, 4, audio="dragon-timide/voix/essai.wav")
    ln = [l for l in load_pack(f).stories[0].lines if l.speaker][4]
    assert (ln.prise, ln.audio) == (3, "dragon-timide/voix/essai.wav")
    ws.champs_ligne("dragon-timide", "histoires", 0, 4, prise=0, audio=None)
    assert f.read_text(encoding="utf-8") == avant


def test_pas_sur_un_son(ws):
    ws.ajouter_son("dragon-timide", "hibou", {"freesound": 1234})
    ws.inserer_son("dragon-timide", "histoires", 0, 0, "bruit", "hibou")
    with pytest.raises(EditError):
        ws.champs_ligne("dragon-timide", "histoires", 0, 1, prise=1)


def test_prise_change_la_cle_de_cache():
    cv = CacheVoix(WORKSPACE / ".cache" / "tts")
    pk = load_pack(WORKSPACE / "histoires" / "dragon-timide.yaml")
    v = pk.voices["braise"]
    p0, p1 = cv.path("Bonjour", v, None), cv.path("Bonjour", v, None, 1)
    assert p0 != p1 and p0 == cv.path("Bonjour", v, None, 0)


def test_verdict_voix():
    assert verdict_voix({"gpus": [{"vram_go": 16}]})[0] == "recommande"
    assert verdict_voix({"gpus": [{"vram_go": 4}]})[0] == "deconseille"
    assert verdict_voix({"gpus": []})[0] == "deconseille"
