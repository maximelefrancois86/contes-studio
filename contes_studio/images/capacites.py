# SPDX-License-Identifier: GPL-3.0-or-later
"""Peut-on générer des images sur cet ordinateur ? Carte graphique, mémoire, disque (Windows, Linux, macOS)."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

GIB = 1024 ** 3
DISQUE_INSTALL = 30  # Go : ComfyUI + PyTorch (~6) + FLUX.1 schnell fp8 (~17) + marge


def _nvidia_smi() -> list[dict]:
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if os.name == "nt" else None)
    if not exe or not Path(exe).exists():
        return []
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return []
    gpus = []
    for line in out.strip().splitlines():
        nom, _, mem = line.rpartition(",")
        if nom:
            gpus.append({"nom": nom.strip(), "vram_go": round(float(mem) / 1024, 1), "source": "nvidia-smi"})
    return gpus


def _proc_nvidia() -> list[dict]:
    gpus = []
    for info in Path("/proc/driver/nvidia/gpus").glob("*/information"):
        m = re.search(r"Model:\s*(.+)", info.read_text(errors="ignore"))
        if m:
            gpus.append({"nom": m.group(1).strip(), "vram_go": None, "source": "pilote"})
    return gpus


def _vram_comfy(url: str) -> float | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/system_stats", timeout=2) as r:
            devs = json.load(r).get("devices") or []
        return round(max(d.get("vram_total", 0) for d in devs) / GIB, 1) if devs else None
    except Exception:  # noqa: BLE001
        return None


def _vram_torch(python: str | None) -> float | None:
    if not python or not Path(python).exists():
        return None
    code = "import torch;print(torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 0)"
    try:
        out = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=60).stdout.strip()
        return round(int(out) / GIB, 1) if out and int(out) else None
    except Exception:  # noqa: BLE001
        return None


def rapport(comfy_url: str = "http://127.0.0.1:8188", comfy_python: str | None = None,
            dossier_install: str | None = None) -> dict:
    import psutil

    gpus = _nvidia_smi() or _proc_nvidia()
    for g in gpus:
        if g["vram_go"] is None:
            g["vram_go"] = _vram_comfy(comfy_url) or _vram_torch(comfy_python)
    apple = platform.system() == "Darwin" and platform.machine() == "arm64"
    ram = round(psutil.virtual_memory().total / GIB, 1)
    cible = Path(dossier_install).expanduser() if dossier_install else Path.home()
    while not cible.exists() and cible != cible.parent:
        cible = cible.parent
    disque = round(shutil.disk_usage(cible).free / GIB, 1)

    raisons, verdict = [], "deconseille"
    vram = max((g["vram_go"] or 0 for g in gpus), default=0)
    if gpus and vram >= 12:
        verdict = "recommande"
    elif gpus and (vram >= 8 or not vram):
        verdict = "possible"
        raisons.append("carte graphique un peu juste : génération plus lente" if vram else
                       "mémoire de la carte graphique inconnue")
    elif apple and ram >= 16:
        verdict = "possible"
        raisons.append("Mac Apple Silicon : génération possible mais lente")
    else:
        raisons.append("pas de carte graphique NVIDIA d'au moins 8 Go : la génération serait très lente")
    if ram < 16:
        verdict = "deconseille" if ram < 12 else verdict
        raisons.append(f"mémoire vive : {ram} Go (16 Go conseillés)")
    if disque < DISQUE_INSTALL:
        raisons.append(f"espace disque libre : {disque} Go ({DISQUE_INSTALL} Go nécessaires pour installer)")
    return {"systeme": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "gpus": gpus, "ram_go": ram, "disque_libre_go": disque, "disque_requis_go": DISQUE_INSTALL,
            "verdict": verdict, "raisons": raisons, "cuda": bool(gpus), "apple": apple}
