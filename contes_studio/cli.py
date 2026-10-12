# SPDX-License-Identifier: GPL-3.0-or-later
"""Ligne de commande : `python -m contes_studio serve [--port 8090] [--espace DOSSIER]`."""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> None:
    a = argparse.ArgumentParser(prog="contes-studio", description="Atelier d'histoires audio à choix")
    sub = a.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="lance l'atelier dans le navigateur (http://127.0.0.1:8090)")
    s.add_argument("--port", type=int, default=8090)
    s.add_argument("--espace", type=Path, help="espace de travail (contient histoires/) ; par défaut détecté")
    args = a.parse_args(argv)
    if args.cmd == "serve":
        import uvicorn

        from lunii_gen.paths import WORKSPACE

        from .server import create_app

        root = (args.espace or WORKSPACE).resolve()
        print(f"Atelier : http://127.0.0.1:{args.port}  (espace de travail : {root})")
        uvicorn.run(create_app(root), host="127.0.0.1", port=args.port, log_level="warning")
