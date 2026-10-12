# SPDX-License-Identifier: GPL-3.0-or-later
"""Tâches de fond (installation, génération d'images…) suivies par l'interface : état, journal, résultat.

Les tâches qui utilisent la carte graphique prennent le verrou partagé avec le générateur
(~/.cache/lunii-gpu.lock), pour ne jamais tourner en même temps qu'une synthèse de voix.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

VERROU_GPU = Path("~/.cache/lunii-gpu.lock").expanduser()


@dataclass
class Tache:
    id: str
    titre: str
    etat: str = "en attente"          # en attente | en cours | terminée | erreur | annulée
    journal: list[str] = field(default_factory=list)
    progression: float | None = None  # 0..1 si connue
    resultat: object = None
    erreur: str | None = None
    debut: float = field(default_factory=time.time)
    annuler: threading.Event = field(default_factory=threading.Event)

    def log(self, msg: str) -> None:
        self.journal.append(msg.rstrip())
        del self.journal[:-400]

    def public(self) -> dict:
        return {"id": self.id, "titre": self.titre, "etat": self.etat, "journal": self.journal[-60:],
                "progression": self.progression, "resultat": self.resultat, "erreur": self.erreur}


class Taches:
    def __init__(self):
        self._t: dict[str, Tache] = {}

    def lancer(self, titre: str, fn: Callable[[Tache], object]) -> Tache:
        t = Tache(uuid.uuid4().hex[:12], titre)
        self._t[t.id] = t

        def run():
            t.etat = "en cours"
            try:
                t.resultat = fn(t)
                t.etat = "annulée" if t.annuler.is_set() else "terminée"
            except Exception as e:  # noqa: BLE001
                t.etat, t.erreur = "erreur", str(e) or e.__class__.__name__
                t.log(traceback.format_exc(limit=3))

        threading.Thread(target=run, daemon=True, name=f"tache-{t.id}").start()
        return t

    def get(self, tid: str) -> Tache | None:
        return self._t.get(tid)


@contextmanager
def verrou_gpu(t: Tache | None = None, chemin: Path = VERROU_GPU):
    """Verrou de fichier portable (Windows, Linux, macOS). Sous Linux et macOS, c'est le même verrou
    flock que la commande `flock` des scripts du générateur."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(chemin), thread_local=False)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        if t:
            t.log("La carte graphique est occupée (synthèse de voix en cours ?) : en attente…")
        lock.acquire()
    try:
        yield
    finally:
        lock.release()
