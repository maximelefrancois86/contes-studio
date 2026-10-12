# SPDX-License-Identifier: GPL-3.0-or-later
"""ComfyUI : état, démarrage, installation guidée et génération d'illustrations (FLUX.1 schnell).

L'installation ne demande ni git ni droits d'administrateur : archive de ComfyUI depuis GitHub,
environnement Python dédié, PyTorch adapté à la carte graphique, puis le modèle (17 Go).
"""
from __future__ import annotations

import io
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

from ..reglages import venv_python

ARCHIVE = "https://github.com/comfyanonymous/ComfyUI/archive/refs/heads/master.zip"
MODELES = {
    "flux1-schnell-fp8.safetensors":
        "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors",
}
TORCH_INDEX = {"cuda": "https://download.pytorch.org/whl/cu128", "cpu": "https://download.pytorch.org/whl/cpu"}
W, H = 640, 480  # 4:3, recadré puis réduit en 320x240


class Comfy:
    def __init__(self, conf: dict):
        self.url = conf.get("url", "http://127.0.0.1:8188").rstrip("/")
        self.dossier = Path(conf.get("dossier", "")).expanduser()
        self.python = Path(conf.get("python", "")).expanduser()
        self.modele = conf.get("modele", "flux1-schnell-fp8.safetensors")
        self.etapes = int(conf.get("etapes", 4))

    # -- état ------------------------------------------------------------------
    def _req(self, route: str, data=None, timeout: float = 10) -> bytes:
        req = urllib.request.Request(self.url + route, json.dumps(data).encode() if data is not None else None,
                                     {"Content-Type": "application/json"} if data is not None else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def connecte(self) -> bool:
        try:
            self._req("/system_stats", timeout=2)
            return True
        except Exception:  # noqa: BLE001
            return False

    def installe(self) -> bool:
        return (self.dossier / "main.py").exists() and self.python.exists()

    def fichier_modele(self) -> Path:
        return self.dossier / "models" / "checkpoints" / self.modele

    def modeles(self) -> list[str]:
        try:
            info = json.loads(self._req("/object_info/CheckpointLoaderSimple"))
            return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
        except Exception:  # noqa: BLE001
            d = self.dossier / "models" / "checkpoints"
            return sorted(p.name for p in d.glob("*.safetensors")) if d.exists() else []

    def etat(self) -> dict:
        connecte = self.connecte()
        mods = self.modeles() if connecte or self.installe() else []
        return {"connecte": connecte, "installe": self.installe(), "url": self.url,
                "dossier": str(self.dossier), "modele": self.modele, "modele_present": self.modele in mods,
                "modeles": mods}

    # -- démarrage -------------------------------------------------------------
    def demarrer(self, t=None, attente: int = 240) -> bool:
        if self.connecte():
            return True
        if not self.installe():
            raise RuntimeError("ComfyUI n'est pas installé à cet endroit : " + str(self.dossier))
        port = urllib.parse.urlparse(self.url).port or 8188
        log = open(self.dossier / "contes-studio-comfyui.log", "a", encoding="utf-8")  # noqa: SIM115
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        else:
            kw["start_new_session"] = True
        subprocess.Popen([str(self.python), "main.py", "--listen", "127.0.0.1", "--port", str(port)],
                         cwd=self.dossier, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
        for s in range(attente):
            if t and t.annuler.is_set():
                return False
            if self.connecte():
                if t:
                    t.log(f"ComfyUI répond après {s} s.")
                return True
            time.sleep(1)
        raise TimeoutError("ComfyUI ne répond pas : voir contes-studio-comfyui.log dans son dossier")

    def liberer(self) -> None:
        """Décharge le modèle de la carte graphique (pour laisser la place aux voix)."""
        try:
            self._req("/free", {"unload_models": True, "free_memory": True})
        except Exception:  # noqa: BLE001
            pass

    # -- génération ------------------------------------------------------------
    def _graphe(self, texte: str, negatif: str, graine: int, n: int) -> dict:
        return {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.modele}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": texte, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negatif, "clip": ["4", 1]}},
            "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": W, "height": H, "batch_size": n}},
            "3": {"class_type": "KSampler", "inputs": {
                "seed": graine, "steps": self.etapes, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                "latent_image": ["5", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "contes-studio", "images": ["8", 0]}},
        }

    def generer(self, description: str, style: str, negatif: str, n: int = 4, t=None,
                graine: int | None = None, delai: float = 600) -> list[Image.Image]:
        """`style` est la « commande système » placée avant la description."""
        texte = f"{style.strip()} {description.strip()}".strip()
        graine = random.randrange(2 ** 31) if graine is None else graine
        pid = json.loads(self._req("/prompt", {"prompt": self._graphe(texte, negatif, graine, n)}))["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < delai:
            if t and t.annuler.is_set():
                self._req("/interrupt", {})
                return []
            hist = json.loads(self._req(f"/history/{pid}"))
            if pid in hist:
                if hist[pid].get("status", {}).get("status_str") == "error":
                    raise RuntimeError("ComfyUI : erreur pendant la génération")
                imgs = []
                for o in hist[pid]["outputs"]["9"]["images"]:
                    q = urllib.parse.urlencode({"filename": o["filename"], "subfolder": o.get("subfolder", ""),
                                                "type": o["type"]})
                    imgs.append(Image.open(io.BytesIO(self._req("/view?" + q, timeout=60))).convert("RGB"))
                return imgs
            if t:
                t.progression = min(0.95, (time.time() - t0) / (20 + 6 * n))
            time.sleep(1)
        raise TimeoutError("ComfyUI : délai dépassé")


# -- installation ---------------------------------------------------------------
def _python_systeme() -> list[str] | None:
    """Commande d'un Python ≥ 3.10 présent sur la machine (pour créer l'environnement)."""
    cands = [["py", "-3.12"], ["py", "-3.11"], ["py", "-3"]] if os.name == "nt" else \
        [["python3.12"], ["python3.11"], ["python3"]]
    for c in cands:
        if shutil.which(c[0]):
            try:
                v = subprocess.run(c + ["-c", "import sys;print(sys.version_info[:2]>=(3,10))"],
                                   capture_output=True, text=True, timeout=20).stdout.strip()
                if v == "True":
                    return c
            except Exception:  # noqa: BLE001
                continue
    if not getattr(sys, "frozen", False) and sys.version_info >= (3, 10):
        return [sys.executable]
    return None


def etapes_installation(dossier: Path, capacites: dict, modele: str) -> list[dict]:
    """Plan d'installation, affiché avant de lancer (et exécuté par `installer`)."""
    venv = dossier / ".venv"
    py = venv_python(venv)
    uv = shutil.which("uv")
    if uv:
        creer = [uv, "venv", "--python", "3.12", str(venv)]
        pip = [uv, "pip", "install", "--python", str(py)]
    else:
        base = _python_systeme()
        creer = (base + ["-m", "venv", str(venv)]) if base else None
        pip = [str(py), "-m", "pip", "install"]
    if capacites.get("cuda"):
        torch = pip + ["torch", "torchvision", "torchaudio", "--index-url", TORCH_INDEX["cuda"]]
    elif capacites.get("apple"):
        torch = pip + ["torch", "torchvision", "torchaudio"]
    else:
        torch = pip + ["torch", "torchvision", "torchaudio", "--index-url", TORCH_INDEX["cpu"]]
    return [
        {"titre": "Télécharger ComfyUI", "telechargement": ARCHIVE, "vers": str(dossier), "zip": True},
        {"titre": "Créer l'environnement Python", "commande": creer, "si_absent": str(py),
         "erreur": None if creer else "Aucun Python 3.10 ou plus récent trouvé : installe Python depuis python.org"},
        {"titre": "Installer PyTorch (environ 3 Go)", "commande": torch},
        {"titre": "Installer les dépendances de ComfyUI", "commande": pip + ["-r", str(dossier / "requirements.txt")]},
        {"titre": f"Télécharger le modèle {modele} (environ 17 Go)", "telechargement": MODELES.get(modele),
         "vers": str(dossier / "models" / "checkpoints" / modele),
         "erreur": None if modele in MODELES else f"Pas d'adresse de téléchargement connue pour {modele}"},
    ]


def _telecharger(url: str, dest: Path, t) -> None:
    """Téléchargement avec reprise (en-tête Range) et progression."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    deja = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={deja}-"} if deja else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0) + (deja if r.status == 206 else 0)
        if r.status != 206:
            deja = 0
        with open(part, "ab" if deja else "wb") as f:
            n, dernier = deja, 0.0
            while True:
                if t and t.annuler.is_set():
                    raise InterruptedError("téléchargement annulé (il reprendra où il en était)")
                bloc = r.read(1 << 20)
                if not bloc:
                    break
                f.write(bloc)
                n += len(bloc)
                if t and total:
                    t.progression = n / total
                    if time.time() - dernier > 5:
                        t.log(f"  {n / 1e9:.2f} / {total / 1e9:.2f} Go")
                        dernier = time.time()
    part.replace(dest)


def installer(dossier: Path, capacites: dict, modele: str, t) -> dict:
    dossier = Path(dossier).expanduser()
    plan = etapes_installation(dossier, capacites, modele)
    for k, e in enumerate(plan, 1):
        if t.annuler.is_set():
            break
        t.log(f"[{k}/{len(plan)}] {e['titre']}")
        t.progression = None
        if e.get("erreur"):
            raise RuntimeError(e["erreur"])
        if "telechargement" in e:
            dest = Path(e["vers"])
            if e.get("zip"):
                if (dossier / "main.py").exists():
                    t.log("  déjà présent")
                    continue
                dossier.parent.mkdir(parents=True, exist_ok=True)
                tmp = dossier.parent / "comfyui-master.zip"
                _telecharger(e["telechargement"], tmp, t)
                with zipfile.ZipFile(tmp) as z:
                    racine = z.namelist()[0].split("/")[0]
                    z.extractall(dossier.parent)
                extrait = dossier.parent / racine
                if not dossier.exists():
                    extrait.rename(dossier)
                else:
                    for q in extrait.iterdir():
                        shutil.move(str(q), dossier / q.name)
                    extrait.rmdir()
                tmp.unlink(missing_ok=True)
            else:
                if dest.exists():
                    t.log("  déjà présent")
                    continue
                _telecharger(e["telechargement"], dest, t)
            continue
        if e.get("si_absent") and Path(e["si_absent"]).exists():
            t.log("  déjà présent")
            continue
        p = subprocess.Popen(e["commande"], cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace")
        for line in p.stdout:  # type: ignore[union-attr]
            if line.strip():
                t.log("  " + line.rstrip()[:200])
            if t.annuler.is_set():
                p.terminate()
                break
        if p.wait() != 0 and not t.annuler.is_set():
            raise RuntimeError(f"Échec de l'étape « {e['titre']} » (code {p.returncode})")
    return {"dossier": str(dossier), "python": str(venv_python(dossier / ".venv"))}


def plateforme() -> str:
    return f"{platform.system()} {platform.machine()}"
