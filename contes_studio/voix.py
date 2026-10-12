# SPDX-License-Identifier: GPL-3.0-or-later
"""Voix déjà synthétisées par le générateur (cache .cache/tts/qwen3/) : on retrouve le fichier d'une
réplique sans charger le modèle, avec la même clé que le build (texte prononcé, voix, ton, réglages)."""
from __future__ import annotations

from pathlib import Path

from lunii_gen.texte import prononcer
from lunii_gen.tones import get_tone
from lunii_gen.tts.qwen3 import Qwen3Backend


class CacheVoix:
    def __init__(self, cache_dir: Path, mode: str = "reference", size: str = "1.7B", candidats: int = 8):
        b = Qwen3Backend.__new__(Qwen3Backend)  # sans __init__ : pas de torch, pas de GPU
        b.cache_dir, b.language = cache_dir, "fr"
        b.mode, b.size, b.candidats = mode, size, candidats
        self._b = b
        self.dir = cache_dir / b.name

    def path(self, texte: str, voice, ton: str | None, prise: int = 0) -> Path | None:
        return self._b._cache_path(prononcer(texte), voice, get_tone(ton or voice.tone), prise)

    def prises(self, texte: str, voice, ton: str | None, courante: int = 0) -> list[int]:
        """Prises déjà synthétisées pour cette réplique (0, 1, 2…)."""
        return [k for k in range(0, max(courante, 0) + 4) if (p := self.path(texte, voice, ton, k)) and p.exists()]
