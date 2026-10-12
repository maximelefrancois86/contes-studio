#!/usr/bin/env bash
# Lance l'atelier dans sa fenêtre. Crée son environnement Python au premier lancement.
#   ./atelier.sh            fenêtre de bureau
#   ./atelier.sh serve      dans le navigateur (http://127.0.0.1:8090)
set -e
ici="$(cd "$(dirname "$0")" && pwd)"
venv="${CONTES_STUDIO_VENV:-$HOME/.venvs/studio}"
if [ ! -x "$venv/bin/python" ]; then
  echo "Premier lancement : création de l'environnement de l'atelier dans $venv…"
  # --system-site-packages : la fenêtre de bureau utilise GTK et WebKit installés sur le système
  if command -v uv > /dev/null; then uv venv -q --python /usr/bin/python3 --system-site-packages "$venv"
  else /usr/bin/python3 -m venv --system-site-packages "$venv"; fi
  pip=("$venv/bin/python" -m pip install -q); command -v uv > /dev/null && pip=(uv pip install -q --python "$venv/bin/python")
  "${pip[@]}" -e "$ici[bureau]" imageio-ffmpeg pyyaml numpy soundfile
  [ -d "$ici/../gen/lunii_gen" ] && "${pip[@]}" --no-deps -e "$ici/../gen"
fi
exec "$venv/bin/python" -m contes_studio "${@:-app}"
