# SPDX-License-Identifier: GPL-3.0-or-later
"""Pilote du moteur de voix (voix_travail.py), installation de Qwen3-TTS et capacités de l'ordinateur.

Le moteur tourne dans son propre environnement Python (PyTorch, Qwen3-TTS) : l'atelier lui envoie des
demandes et suit leur progression. Tant qu'il est en marche, il garde le verrou de la carte graphique
partagé avec le générateur ; il s'arrête seul après quelques minutes sans travail.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .reglages import venv_python
from .taches import VERROU_GPU

SCRIPT = Path(__file__).with_name("voix_travail.py")
MODELES = ("Qwen/Qwen3-TTS-Tokenizer-12Hz", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
TORCH_CUDA = "https://download.pytorch.org/whl/cu128"


def dossier_hf() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def modeles_presents() -> dict[str, bool]:
    d = dossier_hf()
    return {m: any((d / f"models--{m.replace('/', '--')}" / "snapshots").glob("*/*")) for m in MODELES}


def verdict_voix(cap: dict) -> tuple[str, list[str]]:
    """Synthèse des voix : Qwen3-TTS 1.7B demande une carte NVIDIA d'au moins 8 Go."""
    vram = max((g.get("vram_go") or 0 for g in cap.get("gpus", [])), default=0)
    if cap.get("gpus") and vram >= 8:
        return "recommande", []
    if cap.get("gpus") and not vram:
        return "possible", ["mémoire de la carte graphique inconnue"]
    if cap.get("gpus"):
        return "deconseille", [f"carte graphique de {vram} Go : 8 Go au moins pour les voix"]
    return "deconseille", ["pas de carte graphique NVIDIA : les voix seraient beaucoup trop lentes ; enregistre-les au micro"]


class MoteurVoix:
    def __init__(self, conf_python: str | None):
        self.python = Path(conf_python).expanduser() if conf_python else None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._abonnes: dict[str, callable] = {}
        self._verrou = None
        self._installe_cache: tuple[float, bool, str] | None = None

    # -- état --------------------------------------------------------------------
    def installe(self) -> tuple[bool, str]:
        if not self.python or not self.python.exists():
            return False, "environnement des voix absent"
        if self._installe_cache and time.time() - self._installe_cache[0] < 60:
            return self._installe_cache[1], self._installe_cache[2]
        try:
            r = subprocess.run([str(self.python), "-c", "import qwen_tts, lunii_gen, torch; print(torch.cuda.is_available())"],
                               capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0
            msg = "" if ok else (r.stderr.strip().splitlines() or ["erreur inconnue"])[-1]
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        self._installe_cache = (time.time(), ok, msg)
        return ok, msg

    def en_marche(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- processus ---------------------------------------------------------------
    def _demarrer(self) -> None:
        from filelock import FileLock

        if self.en_marche():
            return
        if not self.python or not self.python.exists():
            raise RuntimeError("Les voix ne sont pas installées : voir les Réglages")
        VERROU_GPU.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = FileLock(str(VERROU_GPU), thread_local=False)
        self._verrou.acquire()  # attend la fin d'une fabrication en cours
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._proc = subprocess.Popen([str(self.python), "-u", str(SCRIPT)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      encoding="utf-8", errors="replace", **kw)
        threading.Thread(target=self._lire, args=(self._proc,), daemon=True).start()
        threading.Thread(target=self._journal, args=(self._proc,), daemon=True).start()

    def _lire(self, proc: subprocess.Popen) -> None:
        for ligne in proc.stdout:  # type: ignore[union-attr]
            try:
                m = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            f = self._abonnes.get(str(m.get("id")))
            if f:
                f(m)
        proc.wait()
        self._liberer()
        for f in list(self._abonnes.values()):
            f({"etat": "erreur", "message": "le moteur de voix s'est arrêté"})
        self._abonnes.clear()

    def _journal(self, proc: subprocess.Popen) -> None:
        self.derniers = []
        for ligne in proc.stderr:  # type: ignore[union-attr]
            self.derniers.append(ligne.rstrip())
            del self.derniers[:-50]
            for f in list(self._abonnes.values()):
                f({"etat": "journal", "ligne": ligne.rstrip()})

    def _liberer(self) -> None:
        if self._verrou is not None:
            try:
                self._verrou.release()
            except Exception:  # noqa: BLE001
                pass
            self._verrou = None

    def arreter(self) -> None:
        with self._lock:
            if self.en_marche():
                try:
                    self._proc.stdin.write(json.dumps({"quitter": True}) + "\n")  # type: ignore[union-attr]
                    self._proc.stdin.flush()  # type: ignore[union-attr]
                    self._proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    self._proc.kill()
            self._liberer()

    # -- demandes ------------------------------------------------------------------
    def faire(self, demande: dict, t) -> dict:
        """Envoie une demande et suit sa progression dans la tâche `t` ; renvoie le message final."""
        fini = threading.Event()
        res: dict = {}

        def recu(m: dict) -> None:
            if m.get("etat") == "progres":
                t.progression = (m["fait"] / m["total"]) if m.get("total") else None
                if m.get("total"):
                    t.log(f"{m['fait']} / {m['total']} voix")
                else:
                    t.log("toutes ces voix sont déjà prêtes")
            elif m.get("etat") == "journal":
                if any(k in m["ligne"] for k in ("lots :", "!", "Error", "chargement")):
                    t.log("  " + m["ligne"][:160])
            elif m.get("etat") in ("fini", "erreur"):
                res.update(m)
                fini.set()

        with self._lock:
            self._demarrer()
            self._abonnes[demande["id"]] = recu
            t.log("Moteur de voix prêt" if self.en_marche() else "Démarrage du moteur de voix…")
            self._proc.stdin.write(json.dumps(demande, ensure_ascii=False) + "\n")  # type: ignore[union-attr]
            self._proc.stdin.flush()  # type: ignore[union-attr]
        while not fini.wait(0.5):
            if t.annuler.is_set():
                self.arreter()
                return {"etat": "annulée"}
        self._abonnes.pop(demande["id"], None)
        if res.get("etat") == "erreur":
            raise RuntimeError(res.get("message") or "erreur du moteur de voix")
        return res


# -- installation ------------------------------------------------------------------
def etapes_installation(dossier: Path, cap: dict, gen: Path | None) -> list[dict]:
    venv = dossier / ".venv"
    py = venv_python(venv)
    uv = shutil.which("uv")
    if uv:
        creer, pip = [uv, "venv", "--python", "3.12", str(venv)], [uv, "pip", "install", "--python", str(py)]
    else:
        from .images.comfy import _python_systeme

        base = _python_systeme()
        creer, pip = ((base + ["-m", "venv", str(venv)]) if base else None), [str(py), "-m", "pip", "install"]
    torch = pip + ["torch", "torchaudio"] + (["--index-url", TORCH_CUDA] if cap.get("cuda") else [])
    paquets = pip + ["qwen-tts", "soundfile", "pyyaml", "pillow", "numpy", "imageio-ffmpeg", "huggingface_hub"]
    gen_cmd = (pip + ["--no-deps", "-e", str(gen)]) if gen and (gen / "pyproject.toml").exists() else None
    code = ("from huggingface_hub import snapshot_download\n"
            f"for m in {list(MODELES)!r}:\n    print('modèle', m, flush=True); snapshot_download(m)\n")
    return [
        {"titre": "Créer l'environnement Python des voix", "commande": creer, "si_absent": str(py),
         "erreur": None if creer else "Aucun Python 3.10 ou plus récent trouvé : installe Python depuis python.org"},
        {"titre": "Installer PyTorch (environ 3 Go)", "commande": torch},
        {"titre": "Installer Qwen3-TTS", "commande": paquets},
        {"titre": "Installer le générateur d'histoires", "commande": gen_cmd,
         "erreur": None if gen_cmd else "Générateur introuvable (dossier gen/)"},
        {"titre": "Télécharger les modèles de voix (environ 8 Go)", "commande": [str(py), "-c", code]},
    ]


def installer(dossier: Path, cap: dict, gen: Path | None, t) -> dict:
    plan = etapes_installation(dossier, cap, gen)
    dossier.mkdir(parents=True, exist_ok=True)
    for k, e in enumerate(plan, 1):
        if t.annuler.is_set():
            break
        t.log(f"[{k}/{len(plan)}] {e['titre']}")
        if e.get("erreur"):
            raise RuntimeError(e["erreur"])
        if e.get("si_absent") and Path(e["si_absent"]).exists():
            t.log("  déjà présent")
            continue
        p = subprocess.Popen(e["commande"], cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace")
        for ligne in p.stdout:  # type: ignore[union-attr]
            if ligne.strip():
                t.log("  " + ligne.rstrip()[:200])
            if t.annuler.is_set():
                p.terminate()
                break
        if p.wait() != 0 and not t.annuler.is_set():
            raise RuntimeError(f"Échec de l'étape « {e['titre']} » (code {p.returncode})")
    return {"python": str(venv_python(dossier / ".venv"))}
