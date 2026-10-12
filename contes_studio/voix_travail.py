# SPDX-License-Identifier: GPL-3.0-or-later
"""Moteur de voix : tourne dans l'environnement Python du modèle (Qwen3-TTS), lancé par l'atelier.

N'importe que le générateur (lunii_gen) et la bibliothèque standard : ce fichier est exécuté par un
autre Python que celui de l'atelier. Il garde le modèle chargé tant qu'on lui envoie du travail, et
s'arrête après quelques minutes sans demande (la carte graphique est alors libérée).

Protocole : une demande JSON par ligne sur l'entrée standard, des messages JSON sur la sortie.
  → {"id": "t1", "espace": "...", "pack": "x", "cibles": [["etapes", 0, 3], ...]}   répliques précises
  → {"id": "t2", "espace": "...", "pack": "x", "qui": "braise"}                       un personnage
  → {"id": "t3", "espace": "...", "pack": "x", "tout": true}                          tout le pack
  ← {"id": ..., "etat": "progres", "fait": 3, "total": 12} … {"id": ..., "etat": "fini", "faites": 12}
  ← {"id": ..., "etat": "erreur", "message": "..."}
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

INACTIVITE = float(os.environ.get("CONTES_VOIX_INACTIVITE", "180"))  # s avant de libérer la carte

# toute sortie parasite (chargement des modèles) part sur stderr : stdout ne porte que nos messages
_sortie = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr


def envoyer(**m) -> None:
    _sortie.write(json.dumps(m, ensure_ascii=False) + "\n")
    _sortie.flush()


_moteurs: dict[str, object] = {}


def moteur(espace: Path):
    from lunii_gen.tts import load_backend

    cle = str(espace)
    if cle not in _moteurs:
        _moteurs[cle] = load_backend("qwen3", cache_dir=espace / ".cache" / "tts", language="fr",
                                     mode="reference", batch_size=16)
    return _moteurs[cle]


def elements(espace: Path, d: dict) -> list[tuple]:
    import yaml

    from lunii_gen.story import _parse_line, load_pack
    from lunii_gen.texte import prononcer
    from lunii_gen.tones import get_tone

    f = espace / "histoires" / f"{d['pack']}.yaml"
    pk = load_pack(f, brouillon=True)
    raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    narr = pk.voices[pk.narrator]
    out = []

    def ajout(rl):
        try:
            ln = _parse_line(rl)
        except ValueError:
            return
        if ln.kind or not ln.text or ln.audio:
            return
        qui = ln.speaker or pk.narrator
        if d.get("qui") and qui != d["qui"]:
            return
        v = pk.voices.get(qui)
        if v is None:
            return
        out.append((prononcer(ln.text), v, get_tone(ln.tone or v.tone), ln.prise))

    if d.get("cibles"):
        for sec, i, j in d["cibles"]:
            ajout(raw[sec][int(i)]["lignes"][int(j)])
    else:
        for sec in ("histoires", "etapes"):
            for item in raw.get(sec) or []:
                for rl in item.get("lignes") or []:
                    ajout(rl)
        if d.get("tout") or d.get("qui") == pk.narrator:  # titre, questions et choix lus par le narrateur
            textes = [pk.title] + [q.text for q in pk.questions] + [o.label for q in pk.questions for o in q.options]
            for st in pk.steps.values():
                if st.choice:
                    textes += [st.choice.text] + [o.label for o in st.choice.options]
            out += [(prononcer(t), narr, get_tone("enjoué"), 0) for t in textes if t]
    return out


def traiter(d: dict) -> None:
    espace = Path(d["espace"])
    b = moteur(espace)
    items = [x for x in elements(espace, d) if not b._cache_path(*x).exists()]
    vus, uniques = set(), []
    for x in items:
        p = b._cache_path(*x)
        if p not in vus:
            vus.add(p)
            uniques.append(x)
    total = len(uniques)
    envoyer(id=d["id"], etat="progres", fait=0, total=total)
    for k in range(0, total, 16):
        b.synthesize_many(uniques[k:k + 16])
        envoyer(id=d["id"], etat="progres", fait=min(total, k + 16), total=total)
    envoyer(id=d["id"], etat="fini", faites=total)


def main() -> None:
    demandes: queue.Queue = queue.Queue()

    def lire():  # fil de lecture : fonctionne aussi sous Windows (pas de select sur un tube)
        for ligne in sys.stdin:
            demandes.put(ligne)
        demandes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    envoyer(etat="pret", pid=os.getpid())
    while True:
        try:
            ligne = demandes.get(timeout=INACTIVITE)
        except queue.Empty:
            envoyer(etat="arret", raison="inactivite")
            return
        if ligne is None or not ligne.strip():
            if ligne is None:
                return
            continue
        try:
            d = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if d.get("quitter"):
            return
        t0 = time.time()
        try:
            traiter(d)
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            envoyer(id=d.get("id"), etat="erreur", message=f"{e.__class__.__name__}: {e}")
        print(f"[voix] demande {d.get('id')} traitée en {time.time() - t0:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
