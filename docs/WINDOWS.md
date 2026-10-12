# Windows

L'atelier doit tourner sur un ordinateur Windows 10 ou 11, comme une application.

## Choix de la fenêtre : pywebview

L'interface est une application web servie par le Python de l'atelier. pywebview l'affiche dans
une vraie fenêtre, avec le moteur WebView2 d'Edge, déjà présent sur Windows 10 et 11 : pas de
navigateur à ouvrir, pas de deuxième programme à installer.

| Option | Pour | Contre |
|---|---|---|
| **pywebview** (retenu) | aucune réécriture ; un seul processus Python ; léger | fenêtre simple (pas de menus natifs riches) |
| NiceGUI | interface écrite en Python, sur FastAPI ; son mode bureau est pywebview | réécrire l'interface ; migration possible plus tard, écran par écran |
| Electron, Tauri 2 | outils de bureau complets (mises à jour, installeur) | Python en processus séparé (« sidecar ») ; Node ou Rust en plus |
| Flet, PySide6 | interfaces natives | tout réécrire ; plus de partage avec le lecteur web du site |

## Lancer (développement)

```powershell
py -3.12 -m venv %LOCALAPPDATA%\contes-studio\venv
%LOCALAPPDATA%\contes-studio\venv\Scripts\pip install -e ..\gen -e .[bureau]
%LOCALAPPDATA%\contes-studio\venv\Scripts\python -m contes_studio app
```

## Ce qui est déjà portable

- Chemins avec `pathlib` ; réglages dans `%APPDATA%\contes-studio\reglages.json` (platformdirs).
- Verrou de la carte graphique avec `filelock` (pas de `fcntl`).
- Fichiers YAML écrits avec des fins de ligne Unix, même sous Windows.
- ComfyUI : installation sans git (archive), Python de l'environnement en `Scripts\python.exe`,
  processus lancé sans fenêtre de console.
- Détection de la carte graphique avec `nvidia-smi` (installé avec le pilote NVIDIA).

## À faire pour Pépé

1. **Paquet** : PyInstaller (`--windowed`, icône), dossier autonome dans `%LOCALAPPDATA%`, raccourci
   sur le bureau. Construit sur un runner Windows de GitHub Actions (le générateur, privé, devra
   être accessible au build).
2. **ffmpeg** : l'embarquer (paquet `imageio-ffmpeg`) au lieu de compter sur le PATH.
3. **Voix** : Qwen3-TTS demande une carte NVIDIA d'au moins 8 Go. Vérifier l'ordinateur de Pépé
   avant tout ; sinon prévoir micro ou voix faites ailleurs (FEUILLE-DE-ROUTE, 0.4).
4. **Premier lancement guidé** : choisir le dossier des ateliers, renseigner la clé Freesound,
   tester la carte graphique.
5. **Micro** : WebView2 demande l'autorisation la première fois (cliquer « Autoriser »). Sous Linux,
   l'atelier accepte lui-même les demandes de micro de sa page (WebKitGTK refuse sinon).
   À faire : accepter aussi automatiquement sous Windows (événement `PermissionRequested` de WebView2).
6. Tester réellement sur une machine Windows : rien n'a encore été exécuté sous Windows.
