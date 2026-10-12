# SPDX-License-Identifier: GPL-3.0-or-later
"""Serveur de l'atelier : API JSON + interface web (fichiers de static/), en local uniquement."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .voix import CacheVoix
from .workspace import EditError, Workspace

STATIC = Path(__file__).with_name("static")


class LineEdit(BaseModel):
    section: str
    i: int
    j: int
    texte: str | None = None
    qui: str | None = None
    ton: str | None = None


def create_app(root: Path) -> FastAPI:
    ws = Workspace(root)
    voix = CacheVoix(root / ".cache" / "tts")
    app = FastAPI(title="Atelier d'histoires", version=__version__)

    @app.get("/api/infos")
    def infos():
        return {"version": __version__, "espace": str(root)}

    @app.get("/api/packs")
    def packs():
        return ws.packs()

    @app.get("/api/packs/{pid}")
    def pack(pid: str):
        try:
            return ws.pack(pid, voix.path)
        except EditError as e:
            raise HTTPException(404, str(e)) from e
        except Exception as e:  # noqa: BLE001  (YAML en cours d'écriture)
            raise HTTPException(422, f"Pack illisible : {e}") from e

    @app.post("/api/packs/{pid}/ligne")
    def edit(pid: str, e: LineEdit):
        try:
            ws.edit_line(pid, e.section, e.i, e.j, texte=e.texte, qui=e.qui, ton=e.ton)
        except EditError as err:
            raise HTTPException(400, str(err)) from err
        data = ws.pack(pid, voix.path)
        sec = next(s for s in data["sections"] if s["section"] == e.section and s["i"] == e.i)
        return next(l for l in sec["lignes"] if l["j"] == e.j)

    @app.get("/api/voix/{name}")
    def audio(name: str):
        p = voix.dir / name
        if "/" in name or not name.endswith(".wav") or not p.is_file():
            raise HTTPException(404, "Voix absente du cache")
        return FileResponse(p, media_type="audio/wav")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
