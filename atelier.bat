@echo off
rem Lance l'atelier dans sa fenetre. Cree son environnement Python au premier lancement.
setlocal
set "ICI=%~dp0"
if "%CONTES_STUDIO_VENV%"=="" set "CONTES_STUDIO_VENV=%LOCALAPPDATA%\contes-studio\venv"
if not exist "%CONTES_STUDIO_VENV%\Scripts\python.exe" (
  echo Premier lancement : creation de l'environnement de l'atelier...
  py -3.12 -m venv "%CONTES_STUDIO_VENV%" || py -3 -m venv "%CONTES_STUDIO_VENV%"
  "%CONTES_STUDIO_VENV%\Scripts\python.exe" -m pip install -q -e "%ICI%.[bureau]" imageio-ffmpeg pyyaml numpy soundfile
  if exist "%ICI%..\gen\lunii_gen" "%CONTES_STUDIO_VENV%\Scripts\python.exe" -m pip install -q --no-deps -e "%ICI%..\gen"
)
if "%~1"=="" ( "%CONTES_STUDIO_VENV%\Scripts\pythonw.exe" -m contes_studio app ) else ( "%CONTES_STUDIO_VENV%\Scripts\python.exe" -m contes_studio %* )
