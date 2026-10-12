# SPDX-License-Identifier: GPL-3.0-or-later
"""Réglages de l'atelier, propres à l'utilisateur : ~/.config/contes-studio/reglages.json (droits 600).

Les secrets (clés d'API) ne quittent jamais le serveur : l'interface ne reçoit qu'un indicateur
« renseignée » et les quatre derniers caractères.
"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path

SECRETS = {("sons", "freesound", "cle")}

STYLE_DEFAUT = (
    "Simple children's book illustration, one big centered subject, flat shapes, thick bold "
    "black outlines, very high contrast, minimal detail, plain light background, no texture, "
    "no small elements, no text, no letters."
)
NEGATIF_DEFAUT = ("text, letters, watermark, blurry, scary, realistic photo, busy background, fine details, "
                  "small objects, gradients")


def _comfy_existant() -> tuple[str, str]:
    """Installation ComfyUI déjà présente (celle du générateur), sinon emplacement par défaut de l'atelier."""
    candidats = [
        (os.environ.get("IMGEN_COMFY_DIR"), os.environ.get("IMGEN_COMFY_PY")),
        ("~/dev/github.com/comfyanonymous/ComfyUI", "~/.venvs/comfyui/bin/python"),
    ]
    for d, py in candidats:
        if d and (Path(d).expanduser() / "main.py").exists():
            d = Path(d).expanduser()
            for p in (py, venv_python(d / ".venv"), venv_python(d / "venv"), d.parent / "python_embeded" / "python.exe"):
                if p and Path(p).expanduser().exists():
                    return str(d), str(Path(p).expanduser())
    from platformdirs import user_data_dir

    d = Path(user_data_dir("contes-studio", appauthor=False)) / "ComfyUI"
    return str(d), str(venv_python(d / ".venv"))


def venv_python(venv: Path) -> Path:
    """Python d'un environnement virtuel, selon le système."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _voix_existante() -> tuple[str, str]:
    """Environnement Qwen3-TTS déjà présent (celui du générateur), sinon emplacement de l'atelier."""
    from platformdirs import user_data_dir

    for py in (os.environ.get("CONTES_VOIX_PYTHON"), "~/.venvs/qwen3tts/bin/python", "~/.venvs/qwen3tts/Scripts/python.exe"):
        if py and Path(py).expanduser().exists():
            p = Path(py).expanduser()
            return str(p.parents[1]), str(p)
    d = Path(user_data_dir("contes-studio", appauthor=False)) / "voix"
    return str(d), str(venv_python(d / ".venv"))


def defauts() -> dict:
    d, py = _comfy_existant()
    vd, vpy = _voix_existante()
    return {
        "voix": {"dossier": vd, "python": vpy},
        "sons": {"freesound": {"cle": os.environ.get("FREESOUND_TOKEN") or os.environ.get("FREESOUND_API_KEY") or ""}},
        "illustrations": {
            "comfyui": {"url": "http://127.0.0.1:8188", "dossier": d, "python": py,
                        "modele": "flux1-schnell-fp8.safetensors", "etapes": 4},
            "style": STYLE_DEFAUT,       # « commande système » placée avant chaque description
            "negatif": NEGATIF_DEFAUT,
            "propositions": 4,
        },
    }


def _fusion(base: dict, sur: dict) -> dict:
    out = deepcopy(base)
    for k, v in sur.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusion(out[k], v)
        else:
            out[k] = v
    return out


class Reglages:
    def __init__(self, fichier: Path | None = None):
        # ~/.config/contes-studio (Linux), %APPDATA%\contes-studio (Windows), ~/Library/Application Support (macOS)
        from platformdirs import user_config_dir

        self.fichier = fichier or Path(user_config_dir("contes-studio", appauthor=False, roaming=True)) / "reglages.json"
        self._lock = threading.Lock()

    def tout(self) -> dict:
        """Réglages complets, secrets compris (usage interne au serveur)."""
        sur = {}
        if self.fichier.exists():
            try:
                sur = json.loads(self.fichier.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                sur = {}
        return _fusion(defauts(), sur)

    def get(self, *chemin, defaut=None):
        v = self.tout()
        for k in chemin:
            if not isinstance(v, dict) or k not in v:
                return defaut
            v = v[k]
        return v

    def public(self) -> dict:
        """Réglages pour l'interface : secrets masqués."""
        r = self.tout()
        for chemin in SECRETS:
            parent = r
            for k in chemin[:-1]:
                parent = parent[k]
            val = parent.get(chemin[-1]) or ""
            parent[chemin[-1]] = {"renseignee": bool(val), "fin": val[-4:] if len(val) >= 8 else ""}
        return r

    def maj(self, changes: dict) -> dict:
        """Enregistre des changements partiels. Pour un secret : chaîne vide = inchangé, None = effacé."""
        with self._lock:
            cur = {}
            if self.fichier.exists():
                try:
                    cur = json.loads(self.fichier.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    cur = {}
            for chemin in SECRETS:
                parent = changes
                for k in chemin[:-1]:
                    parent = parent.get(k) if isinstance(parent, dict) else None
                    if parent is None:
                        break
                if isinstance(parent, dict) and chemin[-1] in parent:
                    v = parent[chemin[-1]]
                    if isinstance(v, dict) or v == "":
                        del parent[chemin[-1]]  # masque renvoyé tel quel, ou champ laissé vide
                    elif v is None:
                        parent[chemin[-1]] = ""
            new = _fusion(cur, changes)
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.fichier.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(new, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.fichier)
        return self.public()
