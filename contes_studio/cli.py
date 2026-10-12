# SPDX-License-Identifier: GPL-3.0-or-later
"""Ligne de commande.

    python -m contes_studio app      fenêtre de bureau (pywebview : WebView2 sous Windows) — usage normal
    python -m contes_studio serve    serveur seul, à ouvrir dans un navigateur (http://127.0.0.1:8090)
"""
from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serveur(root: Path, port: int):
    import uvicorn

    from .server import create_app

    return uvicorn.Server(uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="warning"))


def app(root: Path, port: int = 0) -> None:
    """Ouvre l'atelier dans sa propre fenêtre. Sans pywebview, retombe sur le navigateur."""
    port = port or _port_libre()
    serveur = _serveur(root, port)
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    for _ in range(200):
        if serveur.started:
            break
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/"
    try:
        import webview  # pywebview
    except ImportError:
        print(f"pywebview n'est pas installé : l'atelier s'ouvre dans le navigateur ({url}).")
        webbrowser.open(url)
        fil.join()
        return
    webview.create_window("Atelier d'histoires", url, width=1440, height=900, min_size=(1000, 680))
    webview.start()
    serveur.should_exit = True


def main(argv=None) -> None:
    a = argparse.ArgumentParser(prog="contes-studio", description="Atelier d'histoires audio à choix")
    sub = a.add_subparsers(dest="cmd")
    for nom, aide in (("app", "ouvre l'atelier dans une fenêtre (par défaut)"),
                      ("serve", "serveur seul, pour un navigateur (http://127.0.0.1:8090)")):
        s = sub.add_parser(nom, help=aide)
        s.add_argument("--port", type=int, default=0 if nom == "app" else 8090)
        s.add_argument("--espace", type=Path, help="espace de travail (contient histoires/) ; par défaut détecté")
    args = a.parse_args(argv)
    from lunii_gen.paths import WORKSPACE

    root = (getattr(args, "espace", None) or WORKSPACE).resolve()
    if args.cmd == "serve":
        print(f"Atelier : http://127.0.0.1:{args.port}  (espace de travail : {root})")
        _serveur(root, args.port).run()
    else:
        app(root, getattr(args, "port", 0))


def app_par_defaut() -> None:
    """Point d'entrée de l'icône de bureau (sans console sous Windows)."""
    main(["app"])
